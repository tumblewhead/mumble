#!/usr/bin/env python3
"""Observable child wrapper for the unchanged qualified surrogate solver.

Only two evaluator JSON files and one entering-vector text file are inputs.
There is no observation/truth option, model entry point, retry or continuation.
Each invocation marker is closed before calling the solver; its result is
closed before the next marker can be created.  A missing completion means
unknown progress, never an assumed zero-cost failed solve.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import re
import resource
import sys
import time
import traceback
from typing import Any, Callable


QUALIFIED_MATH_SHA256 = "870583ec263f4bf4e69b80aa9fc06402336deb606aeaa88533389ddce715261b"
EVALUATOR_SCHEMA = "mumble_retained_likelihood_stream_evaluator_v1"
GRAM_LAYOUT = "lower-packed-row-major: i*(i+1)/2+j for j<=i"
EVALUATOR_COORDINATES = ["logtau1", "logtau2", "logtau3", "loggamma_plus", "loggamma_minus",
                         "logQ", "R0", "R1", "R2", "R3", "H", "z", "v1", "v2", "v3", "h"]
MAX_BLOCK_BYTES = 1024 * 1024
MAX_WARM_BYTES = 4096
MAX_OUTPUT_BYTES = 2 * 1024 * 1024
DECIMAL = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError(f"nonfinite JSON constant: {value}")


def _finite_json_float(value):
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"nonfinite JSON exponent: {value}")
    return parsed


def _strict_json(data: bytes) -> Any:
    return json.loads(data.decode("utf-8"), object_pairs_hook=_no_duplicates,
                      parse_constant=_reject_constant, parse_float=_finite_json_float)


def _number(value: Any, name: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"{name}: expected a finite JSON number")
    return float(value)


def _vector(value: Any, length: int, name: str) -> list[float]:
    if not isinstance(value, list) or len(value) != length:
        raise ValueError(f"{name}: expected exactly {length} JSON numbers")
    return [_number(item, name) for item in value]


def _read_bounded(path: Path, limit: int) -> bytes:
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"input exceeds fixed byte cap: {path}")
    return data


def _read_warm(data: bytes) -> list[float]:
    tokens = data.decode("ascii").split()
    if len(tokens) != 16 or any(DECIMAL.fullmatch(token) is None for token in tokens):
        raise ValueError("warm input must contain exactly sixteen finite decimal tokens")
    values = [float(token) for token in tokens]
    if not all(math.isfinite(value) for value in values):
        raise ValueError("nonfinite warm coordinate")
    return values


def _validate_block(payload: Any, charge_min: float, charge_max: float) -> None:
    if not isinstance(payload, dict):
        raise ValueError("evaluator JSON must be an object")
    expected = {"schema": EVALUATOR_SCHEMA, "status": "ok", "dimension": 16,
                "coordinate_names": EVALUATOR_COORDINATES, "sigma_V": .001,
                "gram_layout": GRAM_LAYOUT, "charge_extrema_include_initial_zero": True}
    for key, value in expected.items():
        if payload.get(key) != value:
            raise ValueError(f"evaluator identity mismatch: {key}")
    _vector(payload.get("x"), 16, "x")
    _vector(payload.get("gradient"), 16, "gradient")
    _vector(payload.get("gram"), 136, "gram")
    if _number(payload.get("cost"), "cost") < 0.:
        raise ValueError("negative squared-residual likelihood cost")
    if (_number(payload.get("charge_min_Ah"), "charge_min_Ah") != charge_min
            or _number(payload.get("charge_max_Ah"), "charge_max_Ah") != charge_max):
        raise ValueError("block and CLI charge extrema differ")
    prefix = payload.get("prefix_requested")
    if type(prefix) is not int or not 0 <= prefix <= 252000:
        raise ValueError("invalid evaluator prefix")
    for key in ("records_read", "records_accumulated", "model_step_calls", "model_predict_calls"):
        if type(payload.get(key)) is not int or payload[key] != prefix:
            raise ValueError(f"evaluator prefix accounting mismatch: {key}")
    for key in ("source_generations", "learner_ingests", "fit_calls", "truth_reads"):
        if type(payload.get(key)) is not int or payload[key] != 0:
            raise ValueError(f"unexpected evaluator activity: {key}")


def _load_math():
    if any(os.environ.get(name) != "1" for name in
           ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")):
        raise ValueError("set OPENBLAS_NUM_THREADS=OMP_NUM_THREADS=MKL_NUM_THREADS=1 before child import")
    path = Path(__file__).resolve().with_name("replacement_math.py")
    if _sha(path.read_bytes()) != QUALIFIED_MATH_SHA256:
        raise ValueError("math module differs from the reviewed unchanged source")
    module = importlib.import_module("replacement_math")
    if Path(module.__file__).resolve() != path:
        raise ValueError("wrong replacement_math import location")
    if module.np.__version__ != module.PINNED_NUMPY or module.scipy.__version__ != module.PINNED_SCIPY:
        raise ValueError("numerical dependency version differs from qualified source")
    return module


def _resources(wall_start: float, cpu_start: float) -> dict[str, Any]:
    return {"wall_s": time.monotonic() - wall_start, "CPU_s": time.process_time() - cpu_start,
            "own_peak_RSS_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
            "timing_semantics": "Worker entry through this receipt snapshot; its final encoding/fsync excluded"}


def _safe_failure(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return repr(value)
    if isinstance(value, dict):
        return {str(key): _safe_failure(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_safe_failure(item) for item in value]
    return value


class _ReceiptWriter:
    def __init__(self, output: Path):
        self.output = output
        self.files: dict[str, Any] = {}
        self.total_bytes = 0

    def write(self, name: str, value: Any) -> None:
        data = (json.dumps(value, indent=2, allow_nan=False) + "\n").encode("utf-8")
        if self.total_bytes + len(data) > MAX_OUTPUT_BYTES:
            raise ValueError("worker cumulative output exceeds fixed 2 MiB cap")
        path = self.output / name
        with path.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        self.files[name] = {"sha256": _sha(data), "bytes": len(data)}
        self.total_bytes += len(data)


def _validate_result(result: Any, support: Any, rm: Any) -> None:
    if not isinstance(result, dict) or result.get("status") not in ("converged", "unresolved", "infeasible_candidate"):
        raise ValueError("invalid solver result status")
    candidate = _vector(result.get("candidate_x"), 16, "candidate_x")
    actual_feasible = support.diagnostics(candidate)["strictly_feasible"]
    if result.get("feasibility", {}).get("strictly_feasible") is not actual_feasible:
        raise ValueError("solver feasibility receipt disagrees with the unchanged support")
    counts = result.get("evaluation_counts", {})
    for key, upper in (("iterations", rm.MAX_ITERATIONS),
                       ("combined_objective_gradient", rm.MAX_COMBINED_EVALUATIONS)):
        if type(counts.get(key)) is not int or not 0 <= counts[key] <= upper:
            raise ValueError(f"solver accounting outside frozen limit: {key}")
    for key in ("model_calls", "observation_reads"):
        if type(counts.get(key)) is not int or counts[key] != 0:
            raise ValueError(f"unexpected solver activity: {key}")
    expected_converged = (bool(result.get("optimizer", {}).get("success", False))
                          and actual_feasible and bool(result.get("KKT", {}).get("passed", False)))
    if (result["status"] == "converged") != expected_converged:
        raise ValueError("solver status bypasses independent KKT/support requirement")


def run_worker(old_path: Path, new_path: Path, warm_path: Path,
               charge_min: float, charge_max: float, output_dir: Path,
               *, solve_function: Callable | None = None) -> dict[str, Any]:
    """One child transaction; injected callable is only for fabricated checks.

    The CLI cannot select an alternate solver.  The caller must not retry this
    function against canonical inputs after either started marker exists.
    """
    wall_start, cpu_start = time.monotonic(), time.process_time()
    counts = {"started_markers": 0, "solver_calls_entered": 0,
              "solver_calls_returned": 0, "results_saved": 0}
    stage = "reserve_output_directory"
    try:
        output_dir.mkdir(exist_ok=False)
    except Exception as error:
        return {"schema": "mumble_surrogate_worker_status_v1", "status": "failed",
                "exit_code": 1, "stage": stage, "exception_type": type(error).__name__,
                "message": str(error), "counts": counts, "output_directory": str(output_dir)}
    writer = _ReceiptWriter(output_dir)
    inputs = {}
    results = {}
    try:
        stage = "record_worker_start"
        source = Path(__file__).resolve()
        writer.write("worker_started.json", {
            "schema": "mumble_surrogate_worker_started_v1", "pid": os.getpid(),
            "utc": datetime.now(timezone.utc).isoformat(),
            "worker_source_sha256": _sha(source.read_bytes()),
            "qualified_math_sha256": QUALIFIED_MATH_SHA256,
            "environment": {"python": sys.version,
                            "thread_environment": {name: os.environ.get(name) for name in
                                                   ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")}},
            "input_paths": {"old_block": str(old_path), "new_block": str(new_path), "warm": str(warm_path)},
            "output_directory": str(output_dir), "solves_max": 2, "retries": 0,
            "no_completion_semantics": "A started marker without result/exception preserves unknown progress; do not infer zero evaluations or retry.",
        })
        stage = "validate_inputs_and_math"
        old_bytes = _read_bounded(old_path, MAX_BLOCK_BYTES)
        new_bytes = _read_bounded(new_path, MAX_BLOCK_BYTES)
        warm_bytes = _read_bounded(warm_path, MAX_WARM_BYTES)
        input_rows = (("old_block", old_path, old_bytes), ("new_block", new_path, new_bytes),
                      ("warm", warm_path, warm_bytes))
        inputs = {name: {"path": str(path), "sha256": _sha(data), "bytes": len(data)}
                  for name, path, data in input_rows}
        charge_min = _number(charge_min, "charge_min")
        charge_max = _number(charge_max, "charge_max")
        old_payload, new_payload = _strict_json(old_bytes), _strict_json(new_bytes)
        _validate_block(old_payload, charge_min, charge_max)
        _validate_block(new_payload, charge_min, charge_max)
        if old_payload["prefix_requested"] != new_payload["prefix_requested"]:
            raise ValueError("likelihood blocks own different observation prefixes")
        rm = _load_math()
        old = rm.QuadraticBlock.from_evaluator(old_payload, "frozen")
        new = rm.QuadraticBlock.from_evaluator(new_payload, "replacement")
        warm = rm.np.array(_read_warm(warm_bytes), dtype=rm.np.float64)
        support = rm.Support(charge_min, charge_max)
        for name, x in (("warm", warm), ("old anchor", old.anchor), ("new anchor", new.anchor)):
            if not support.diagnostics(x)["strictly_feasible"]:
                raise ValueError(f"{name} outside exact common support; no clipping")
        policy = rm.build_pair_policy(old, new)
        prior = rm.public_prior()
        writer.write("inputs.json", {"files": inputs, "charge_min_Ah": charge_min,
                                     "charge_max_Ah": charge_max,
                                     "prefix_records": old_payload["prefix_requested"],
                                     "warm_start_x": warm.tolist()})
        writer.write("policy.json", policy)
        writer.write("prior.json", prior)
        warm_before = warm.tobytes()
        solver = rm._solve_one if solve_function is None else solve_function
        for ordinal, (label, block) in enumerate((("frozen", old), ("replacement", new)), 1):
            stage = f"{label}:start_marker"
            writer.write(f"{label}.started.json", {
                "schema": "mumble_surrogate_solve_started_v1", "solve": label,
                "invocation_number": ordinal, "policy_sha256": policy["policy_sha256"],
                "warm_start_x": warm.tolist(), "input_hashes": inputs,
                "semantics": "Durably recorded immediately before the call. If killed here, entry/progress is unknown and the invocation remains reserved.",
            })
            counts["started_markers"] += 1
            returned_result = None
            try:
                stage = f"{label}:solver_call"
                counts["solver_calls_entered"] += 1
                returned_result = solver(block, warm, support, policy)
                counts["solver_calls_returned"] += 1
                stage = f"{label}:validate_and_save_result"
                _validate_result(returned_result, support, rm)
                if warm.tobytes() != warm_before:
                    raise AssertionError("common warm start mutated")
                writer.write(f"{label}.result.json", returned_result)
                counts["results_saved"] += 1
                results[label] = returned_result
            except BaseException as error:
                marker = {
                    "schema": "mumble_surrogate_solve_exception_v1", "solve": label,
                    "invocation_number": ordinal, "stage": stage,
                    "exception_type": type(error).__name__, "message": str(error),
                    "traceback": traceback.format_exc(), "counts": dict(counts),
                    "resources": _resources(wall_start, cpu_start),
                    "within_call_evaluations": "Unknown if solver raised before returning; started invocation remains counted, no retry",
                }
                if isinstance(returned_result, dict):
                    marker["returned_result_summary"] = _safe_failure({
                        key: returned_result.get(key) for key in ("status", "candidate_x", "optimizer", "evaluation_counts")})
                writer.write(f"{label}.exception.json", _safe_failure(marker))
                raise
        stage = "verify_immutable_inputs"
        for name, path, original in input_rows:
            limit = MAX_WARM_BYTES if name == "warm" else MAX_BLOCK_BYTES
            if _read_bounded(path, limit) != original:
                raise ValueError(f"input changed during child work: {name}")
        if _sha(Path(rm.__file__).read_bytes()) != QUALIFIED_MATH_SHA256:
            raise ValueError("math source changed during child work")
        if _sha(source.read_bytes()) != writer_source_hash(output_dir):
            raise ValueError("worker source changed during child work")
        stage = "save_pair"
        pair = {"schema": "mumble_replacement_surrogate_pair_v1", "policy": policy,
                "prior": prior, "frozen": results["frozen"], "replacement": results["replacement"],
                "status": "converged" if all(row["status"] == "converged" for row in results.values()) else "unresolved",
                "solves": 2, "starts_per_arm": 1, "retries": 0,
                "model_calls": 0, "observation_reads": 0,
                "evidence_ownership": "Arms are alternatives: new block replaces old; never add their evidence or the recursive posterior"}
        writer.write("pair.json", pair)
        status = {"schema": "mumble_surrogate_worker_status_v1", "status": "completed",
                  "exit_code": 0, "pair_status": pair["status"], "counts": dict(counts),
                  "solve_statuses": {key: row["status"] for key, row in results.items()},
                  "all_candidates_strictly_feasible": all(row["feasibility"]["strictly_feasible"] for row in results.values()),
                  "output_directory": str(output_dir), "files_before_final_receipt": dict(writer.files),
                  "bytes_before_final_receipt": writer.total_bytes,
                  "resources": _resources(wall_start, cpu_start),
                  "model_calls": 0, "observation_reads": 0, "truth_reads": 0,
                  "interpretation": "Finite feasible unresolved candidates remain unresolved; audit/transaction policy is frozen by the parent contract, with no MAP or optimum claim"}
        writer.write("worker_result.json", status)
        return status
    except BaseException as error:
        status = {"schema": "mumble_surrogate_worker_status_v1", "status": "failed",
                  "exit_code": 1, "stage": stage, "exception_type": type(error).__name__,
                  "message": str(error), "traceback": traceback.format_exc(), "counts": dict(counts),
                  "completed_solve_labels": list(results), "inputs": inputs,
                  "output_directory": str(output_dir), "files_before_failure_receipt": dict(writer.files),
                  "resources": _resources(wall_start, cpu_start),
                  "model_calls": 0, "observation_reads": 0, "truth_reads": 0,
                  "no_retry": True}
        try:
            writer.write("worker_failure.json", _safe_failure(status))
        except Exception as receipt_error:
            status["failure_receipt_error"] = str(receipt_error)
        return status


def writer_source_hash(output_dir: Path) -> str:
    """Read only this worker's already closed started receipt."""
    return _strict_json((output_dir / "worker_started.json").read_bytes())["worker_source_sha256"]


def export_configuration(path: Path) -> dict[str, Any]:
    rm = _load_math()
    value = {"schema": "mumble_surrogate_worker_configuration_v1",
             "math_source_sha256": QUALIFIED_MATH_SHA256,
             "worker_source_sha256": _sha(Path(__file__).read_bytes()),
             "prior": rm.public_prior(), "numerical_policy": rm.numerical_policy(),
             "worker_interface": {"block_schema": EVALUATOR_SCHEMA, "block_max_bytes": MAX_BLOCK_BYTES,
                                  "warm_max_bytes": MAX_WARM_BYTES, "output_max_bytes": MAX_OUTPUT_BYTES},
             "reporting_prior_derivative_evaluations": "Parent may count two separate post-inference derivative evaluations; these change no candidate or optimizer call count"}
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")
    return {"path": str(path), "sha256": _sha(path.read_bytes()), "bytes": path.stat().st_size}


def qualify_orchestration(output: Path, configuration_path: Path) -> dict[str, Any]:
    """Two stub-only child compositions plus parser/exclusivity checks."""
    import tempfile
    from unittest.mock import patch

    rm = _load_math()
    checks = []
    summaries = {}
    wall_start, cpu_start = time.monotonic(), time.process_time()

    def check(name, passed, detail=None):
        checks.append({"name": name, "pass": bool(passed), "detail": detail})

    with tempfile.TemporaryDirectory(prefix="mumble_worker_fabricated_") as directory:
        base = Path(directory)
        warm = rm.PUBLIC_MEAN.tolist()
        gram = rm.pack_lower(rm.np.diag(rm.KERNEL_PRECISION))
        payload = {"schema": EVALUATOR_SCHEMA, "status": "ok", "dimension": 16,
                   "coordinate_names": EVALUATOR_COORDINATES, "sigma_V": .001,
                   "x": warm, "cost": 0., "gradient": [0.] * 16, "gram": gram,
                   "gram_layout": GRAM_LAYOUT, "charge_min_Ah": 0., "charge_max_Ah": 0.,
                   "charge_extrema_include_initial_zero": True, "prefix_requested": 0,
                   "records_read": 0, "records_accumulated": 0, "model_step_calls": 0,
                   "model_predict_calls": 0, "source_generations": 0, "learner_ingests": 0,
                   "fit_calls": 0, "truth_reads": 0}
        old_path, new_path, warm_path = base / "old.json", base / "new.json", base / "warm.txt"
        old_path.write_text(json.dumps(payload, allow_nan=False))
        new_path.write_text(json.dumps(payload, allow_nan=False))
        warm_path.write_text(" ".join(format(value, ".17g") for value in warm) + "\n")
        for case, fail_second in (("two_returns", False), ("second_call_exception", True)):
            out = base / case
            calls = []
            first_hash = []

            def stub(block, common_warm, support, policy):
                calls.append(block.name)
                if block.name == "frozen":
                    check(f"{case}:first_marker_precedes_call", (out / "frozen.started.json").is_file())
                else:
                    check(f"{case}:first_result_closed_before_second_call", (out / "frozen.result.json").is_file())
                    check(f"{case}:second_marker_precedes_call", (out / "replacement.started.json").is_file())
                    first_hash.append(_sha((out / "frozen.result.json").read_bytes()))
                    if fail_second:
                        raise RuntimeError("fabricated second-call failure")
                return {"name": block.name, "status": "unresolved",
                        "candidate_x": common_warm.tolist(), "warm_start_x": common_warm.tolist(),
                        "optimizer": {"success": False, "status": 0, "message": "fabricated stub"},
                        "KKT": {"passed": False}, "feasibility": support.diagnostics(common_warm),
                        "evaluation_counts": {"iterations": 0, "combined_objective_gradient": 0,
                                              "model_calls": 0, "observation_reads": 0},
                        "fabricated_orchestration_stub": True}

            with patch.object(rm, "_solve_one", side_effect=AssertionError("real optimizer forbidden in orchestration qualification")) as guard:
                status = run_worker(old_path, new_path, warm_path, 0., 0., out, solve_function=stub)
                check(f"{case}:no_real_optimizer_calls", guard.call_count == 0)
            check(f"{case}:exactly_two_stub_calls", calls == ["frozen", "replacement"], calls)
            check(f"{case}:first_result_hash_preserved", first_hash == [_sha((out / "frozen.result.json").read_bytes())])
            if fail_second:
                check("second_exception:partial_failure_counted", status["exit_code"] == 1
                      and status["counts"] == {"started_markers": 2, "solver_calls_entered": 2,
                                               "solver_calls_returned": 1, "results_saved": 1})
                check("second_exception:markers_preserved", (out / "replacement.exception.json").is_file()
                      and (out / "worker_failure.json").is_file() and not (out / "pair.json").exists())
            else:
                check("normal:complete_pair_and_counts", status["exit_code"] == 0
                      and status["counts"] == {"started_markers": 2, "solver_calls_entered": 2,
                                               "solver_calls_returned": 2, "results_saved": 2}
                      and (out / "pair.json").is_file())
                check("normal:unresolved_not_promoted", status["pair_status"] == "unresolved")
            before = {path.name: _sha(path.read_bytes()) for path in out.iterdir()}
            repeat = run_worker(old_path, new_path, warm_path, 0., 0., out, solve_function=stub)
            check(f"{case}:existing_output_rejected_without_call_or_overwrite", repeat["exit_code"] == 1
                  and calls == ["frozen", "replacement"]
                  and before == {path.name: _sha(path.read_bytes()) for path in out.iterdir()})
            summaries[case] = {"status": status, "stub_call_order": calls,
                               "first_result": _strict_json((out / "frozen.result.json").read_bytes()),
                               "output_files_sha256": before}
            if fail_second:
                summaries[case]["second_exception"] = _strict_json((out / "replacement.exception.json").read_bytes())

        for name, data in (("duplicate_key", b'{"a":1,"a":2}'),
                           ("nonfinite_constant", b'{"a":NaN}'),
                           ("overflowed_number", b'{"a":1e999}'),
                           ("trailing_JSON", b'{} {}')):
            try:
                _strict_json(data)
            except (ValueError, UnicodeError):
                rejected = True
            else:
                rejected = False
            check(f"parser:{name}_rejected", rejected)
        for name, text in (("extra_warm_token", "0 " * 17), ("nondecimal_warm", "1_0 " * 16),
                           ("nonfinite_warm", "1e999 " * 16)):
            try:
                _read_warm(text.encode())
            except ValueError:
                rejected = True
            else:
                rejected = False
            check(f"parser:{name}_rejected", rejected)
    configuration = export_configuration(configuration_path)
    check("qualified_math_source_unchanged", _sha(Path(rm.__file__).read_bytes()) == QUALIFIED_MATH_SHA256)
    report = {"schema": "mumble_surrogate_worker_qualification_v1",
              "status": "pass" if all(row["pass"] for row in checks) else "failed",
              "worker_source_sha256": _sha(Path(__file__).read_bytes()),
              "math_source_sha256": QUALIFIED_MATH_SHA256,
              "configuration_export": configuration, "checks": checks,
              "check_count": len(checks), "failed_count": sum(not row["pass"] for row in checks),
              "cases": summaries, "stub_solver_calls": 4, "real_optimizer_calls": 0,
              "model_calls": 0, "canonical_input_reads": 0,
              "resources": _resources(wall_start, cpu_start)}
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
    return {"status": report["status"], "checks": report["check_count"],
            "failed": report["failed_count"], "path": str(output),
            "sha256": _sha(output.read_bytes()), "configuration": configuration,
            "real_optimizer_calls": 0}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--old-block", required=True, type=Path)
    parser.add_argument("--new-block", required=True, type=Path)
    parser.add_argument("--warm", required=True, type=Path)
    parser.add_argument("--charge-min", required=True, type=float)
    parser.add_argument("--charge-max", required=True, type=float)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    result = run_worker(args.old_block, args.new_block, args.warm,
                        args.charge_min, args.charge_max, args.output_dir)
    compact = {key: result[key] for key in ("schema", "status", "exit_code", "counts", "output_directory")}
    for key in ("pair_status", "solve_statuses", "all_candidates_strictly_feasible", "stage", "exception_type", "message", "failure_receipt_error"):
        if key in result:
            compact[key] = result[key]
    print(json.dumps(_safe_failure(compact), allow_nan=False))
    return int(result["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
