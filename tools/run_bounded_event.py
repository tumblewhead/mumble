#!/usr/bin/env python3
"""Small fixed-chart C evidence experiment; no new nonlinear fitting campaign.

Frozen fits provide declared anchors only. Original observations enter each
factor once, without an additional posterior/prior. Truth is read for scoring
after every C inference/audit process has finished. Refuses to overwrite output.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import subprocess
import tempfile
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / "experiments/bounded_event_001"
CASE = "cell_a_35hz_s202610240"
PROBE_NAMES = ["zero", "inside_R0", "inside_SOC_Q", "outside_Q", "outside_SOC"]


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def save(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def source_hashes() -> dict[str, str]:
    paths = ["Makefile", "src/scm_model.c", "include/scm_model.h", "src/scm_assess.c",
             "include/scm_assess.h", "include/scm_estimator.h", "src/scm_evidence.c",
             "include/scm_evidence.h", "tests/test_evidence.c", "tools/evidence_probe.c",
             "tools/run_bounded_event.py", "experiments/bounded_event_001/plan.json"]
    return {p: sha(ROOT / p) for p in paths}


def nominal() -> dict:
    return {"theta": [math.log(math.sqrt(a*b)) for a, b in
                      ((.015, .15), (.15, 1.5), (1.5, 30.))] +
                     [math.log(150.), math.log(300.), .68, math.log(.06)],
            "alpha": [.12, .2, .2, .2, .025, 0., 0., 0., .005],
            "coordinate_scales": [1., 1., 1., 1., 1., .1, 1., .2, .2, .2, .2,
                                  .03, .03, .03, .03, .03]}


def anchor_text(fit: dict, data_hash: str, radii: list[float]) -> str:
    candidates = np.zeros((5, 16))
    candidates[1, 7] = .025
    candidates[2, 5:7] = [.005, .0025]
    candidates[3, 6] = .3
    candidates[4, 5] = .1
    rows = ["3 0.001", data_hash]
    rows += [" ".join(format(v, ".17g") for v in values) for values in
             (fit["theta"], fit["alpha"], fit["coordinate_scales"], radii)]
    rows.append(str(len(candidates)))
    rows += [" ".join(format(v, ".17g") for v in row) for row in candidates]
    return "\n".join(rows) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--binary", type=Path, default=ROOT / "build/scm_evidence_probe")
    args = parser.parse_args()
    out = args.output_dir.resolve()
    if out.exists():
        parser.error("Output directory exists; use a new path to preserve previous evidence")
    plan = json.loads((STUDY / "plan.json").read_text())
    original = json.loads((ROOT / "results/streaming_results.json").read_text())
    reference = {r["checkpoint_s"]: r for r in original["records"] if r["case_id"] == CASE}
    data = ROOT / "data" / f"{CASE}.csv"
    data_hash = sha(data)
    if data_hash != reference[900]["input_sha256"]:
        raise ValueError("Input differs from the frozen reference")
    out.mkdir(parents=True)
    before = source_hashes()
    metadata = {
        "schema": "mumble_bounded_event_receipt_v1", "started_utc": datetime.now(timezone.utc).isoformat(),
        "source_revision": git("rev-parse", "HEAD"), "branch": git("branch", "--show-current"),
        "worktree_status_before": git("status", "--porcelain"), "source_sha256": before,
        "plan_sha256": sha(STUDY / "plan.json"), "data_sha256": data_hash,
        "reference_results_sha256": sha(ROOT / "results/streaming_results.json"),
        "tail_control_sha256": sha(ROOT / "results/tail_only_result.json"),
        "binary_sha256": sha(args.binary), "platform": platform.platform(),
        "python": platform.python_version(), "numpy": np.__version__,
        "nominal_Hz": 35, "case_id": CASE, "new_nonlinear_fits": 0,
        "truth_policy": "Only post-inference scoring; no truth fields in C configuration or guard",
        "coverage_validated": False, "bounded_cold_start_demonstrated": False,
        "memory_scope": "C sizeof and host compiler stack accounting; no MCU resource qualification",
        "runs": []}
    run_anchors = [reference[400]["result"], reference[900]["result"],
                   reference[1800]["result"], nominal()]
    with tempfile.TemporaryDirectory(prefix="mumble_bounded_probe_") as temporary:
        executable = Path(temporary) / "scm_evidence_probe"
        executable.write_bytes(args.binary.read_bytes())
        executable.chmod(0o700)
        if sha(executable) != metadata["binary_sha256"]:
            raise RuntimeError("Probe changed while snapshotting")
        for spec, anchor in zip(plan["runs"], run_anchors, strict=True):
            name = spec["name"]
            config = out / f"{name}_anchor.txt"
            config.write_text(anchor_text(anchor, data_hash, plan["candidate_policy"]["scaled_radii"]))
            command = [str(executable), str(data), str(config), str(spec["end_samples"]),
                       str(spec["split_samples"]), "256"]
            begin = time.perf_counter()
            process = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=60)
            (out / f"{name}.stderr.txt").write_text(process.stderr)
            if process.returncode:
                (out / f"{name}.failed_stdout.txt").write_text(process.stdout)
                raise RuntimeError(f"{name}: C probe exited {process.returncode}: {process.stderr}")
            result = json.loads(process.stdout)
            if result["end_samples"] != spec["end_samples"] or result["source_id"] != data_hash:
                raise ValueError("C output identity/count mismatch")
            for checkpoint in result["checkpoints"]:
                for candidate in checkpoint["candidates"]:
                    index = candidate["candidate_index"]
                    candidate["probe_name"] = PROBE_NAMES[index] if index >= 0 else "minimum_norm_affine_step"
            save(out / f"{name}.json", result)
            metadata["runs"].append({**spec, "file": f"{name}.json", "config_sha256": sha(config),
                                     "command": [str(args.binary.resolve()), *command[1:]],
                                     "process_wall_s": time.perf_counter()-begin, "result": result})
            print(json.dumps({"completed": name, "samples": spec["end_samples"],
                              "wall_s": metadata["runs"][-1]["process_wall_s"]}), flush=True)
    metadata["source_unchanged"] = before == source_hashes()
    metadata["binary_unchanged"] = metadata["binary_sha256"] == sha(args.binary)
    if not metadata["source_unchanged"] or not metadata["binary_unchanged"]:
        raise RuntimeError("Source or executable changed during the experiment")

    # Inference has finished. Truth enters only this independent scoring section.
    manifest = json.loads((ROOT / "data/manifest.json").read_text())
    case = next(c for c in manifest["cases"] if c["case_id"] == CASE)
    truth = case["truth"]
    metadata["truth_manifest_sha256"] = sha(ROOT / "data/manifest.json")
    checks: list[dict] = []
    summary: list[dict] = []

    def check(name: str, passed: bool, **values: object) -> None:
        checks.append({"name": name, "passed": bool(passed), **values})

    tolerance = plan["checks"]
    for run in metadata["runs"]:
        for checkpoint in run["result"]["checkpoints"]:
            name = run["name"] + "/" + checkpoint["label"]
            moment = checkpoint["host_direct_affine_audit"]
            check(name + "/Gram", moment["gram_relative_frobenius_error"] <=
                  tolerance["factor_vs_reference_relative_Gram_tolerance"],
                  relative_error=moment["gram_relative_frobenius_error"])
            check(name + "/gradient", moment["gradient_relative_l2_error"] <= 1e-8,
                  relative_error=moment["gradient_relative_l2_error"])
            for candidate in checkpoint["candidates"]:
                error = abs(candidate["factor_minus_direct_affine"])/max(1., abs(candidate["direct_affine_cost"]))
                check(name + "/affine_cost/" + candidate["probe_name"], error <=
                      tolerance["factor_vs_direct_affine_relative_cost_tolerance"], relative_error=error)
                if candidate["probe_name"].startswith("outside_"):
                    check(name + "/reject/" + candidate["probe_name"], candidate["guard_code"] == -15)
                if candidate["exact_nonlinear_replay_available"]:
                    q, soc = candidate["Q_Ah"], candidate["current_SOC"]
                    true_soc = truth["z0"] - checkpoint["charge_Ah"] / truth["Q_Ah"]
                    candidate["truth_scoring_only"] = {
                        "Q_relative_error_percent": 100*(q/truth["Q_Ah"]-1),
                        "current_SOC_error_pp": 100*(soc-true_soc)}
            anchor_seconds = {"unexcited_400": 400, "informative_900": 900,
                              "carry_1800_to_2100": 1800}.get(run["name"])
            if anchor_seconds and checkpoint["samples"] == anchor_seconds*35:
                old = reference[anchor_seconds]
                G = np.asarray(checkpoint["gram"])
                Gref = np.asarray(old["result"]["joint_normal"])
                error = float(np.linalg.norm(G-Gref)/np.linalg.norm(Gref))
                check(name + "/frozen_reference_Gram", error <= 1e-9, relative_error=error)
                for new_target, old_target in (("Q_Ah", "Q_Ah"), ("current_SOC", "current_soc")):
                    new = checkpoint["targets"][new_target]
                    prior = old["assessment"]["parameters"][old_target]
                    check(name + "/availability/" + new_target,
                          new["local_range_available"] == (prior["local_halfwidth"] is not None))
                    if prior["local_halfwidth"] is not None:
                        error = abs(new["two_sigma_halfwidth"]/prior["local_halfwidth"]-1)
                        check(name + "/halfwidth/" + new_target, error <=
                              tolerance["local_halfwidth_relative_tolerance"], relative_error=error)
            step = next(c for c in checkpoint["candidates"] if c["candidate_index"] == -1)
            summary.append({"run": run["name"], "checkpoint": checkpoint["label"],
                            "samples": checkpoint["samples"], "rank": checkpoint["numerical_rank"],
                            "Q_local": checkpoint["targets"]["Q_Ah"],
                            "SOC_local": checkpoint["targets"]["current_SOC"],
                            "gamma_minus": checkpoint["gamma_minus_structural_status"],
                            "residual_monitor": checkpoint.get("residual_monitor"),
                            "local_step_guard": step["guard"], "local_step": step})
        save(out / f"{run['name']}.json", run["result"])

    early = metadata["runs"][0]["result"]["checkpoints"][-1]
    check("unexcited_400/gamma_minus", early["gamma_minus_structural_status"] == "unexcited")
    check("unexcited_400/Q_SOC_withheld", not early["targets"]["Q_Ah"]["local_range_available"]
          and not early["targets"]["current_SOC"]["local_range_available"])
    informative = metadata["runs"][1]["result"]["checkpoints"][-1]
    check("informative_900/Q_SOC_precision", all(informative["targets"][k]["passes_reference_precision_screen"]
                                                 for k in ("Q_Ah", "current_SOC")))
    tail = metadata["runs"][2]["result"]["checkpoints"][-1]
    step = next(c for c in tail["candidates"] if c["candidate_index"] == -1)
    final = reference[2100]
    difference_q = 100*(step["Q_Ah"]/math.exp(final["result"]["theta"][6])-1)
    difference_soc = 100*(step["current_SOC"]-final["scores"]["current_SOC_estimate"])
    excess_nll = (step["exact_nonlinear_cost"]-final["result"]["objective_full"]
                  if step["exact_nonlinear_cost"] is not None else None)
    check("tail/local_step_inside_chart", step["guard_code"] == 0)
    check("tail/Q_vs_frozen_full", abs(difference_q) <= tolerance["tail_candidate_vs_frozen_full_Q_relative_percent_tolerance"],
          difference_relative_percent=difference_q)
    check("tail/SOC_vs_frozen_full", abs(difference_soc) <= tolerance["tail_candidate_vs_frozen_full_SOC_pp_tolerance"],
          difference_pp=difference_soc)
    check("tail/nonlinear_NLL_vs_frozen_full", excess_nll is not None and excess_nll <=
          tolerance["tail_candidate_excess_nonlinear_NLL_tolerance"], excess_NLL=excess_nll)
    check("tail/precision_retained", all(tail["targets"][k]["passes_reference_precision_screen"] for k in ("Q_Ah", "current_SOC")))
    cold = metadata["runs"][3]["result"]["checkpoints"][-1]
    cold_step = next(c for c in cold["candidates"] if c["candidate_index"] == -1)
    check("nominal/unsupported_update_rejected", cold_step["guard_code"] != 0)
    control = json.loads((ROOT / "results/tail_only_result.json").read_text())
    metadata["frozen_tail_only_control"] = {"source": "results/tail_only_result.json", "summary": control["summary"],
        "interpretation": "Independent frozen tail-only nonlinear fit; different entering-state problem, not new evidence or a factor added to this experiment"}
    metadata["summary"] = summary
    metadata["checks"] = checks
    metadata["all_preregistered_checks_passed"] = all(c["passed"] for c in checks)
    metadata["tail_comparison"] = {"Q_difference_from_full_percent": difference_q,
        "SOC_difference_from_full_pp": difference_soc, "excess_exact_NLL": excess_nll,
        "truth_scoring_only": step.get("truth_scoring_only")}
    metadata["finished_utc"] = datetime.now(timezone.utc).isoformat()
    # Run files contain detailed factors; the compact receipt links them instead of duplicating them.
    for run in metadata["runs"]:
        run.pop("result")
        run["result_sha256"] = sha(out / run["file"])
    save(out / "receipt.json", metadata)
    print(json.dumps({"all_checks_passed": metadata["all_preregistered_checks_passed"],
                      "checks": len(checks), "tail": metadata["tail_comparison"]}), flush=True)
    return 0 if metadata["all_preregistered_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
