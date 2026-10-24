#!/usr/bin/env python3
"""Preregistered bounded_event_002 host comparison; no nonlinear fit campaign.

The four B001 anchor files are reused byte-for-byte. Each C process owns its
bounded paired ingestion and separate host replay audit. Truth is loaded only
after all C processes finish, for scoring candidates selected by the declared
likelihood bound. Output directories must be new; failed evidence is preserved.
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


ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / "experiments/bounded_event_002"
PRIOR = ROOT / "experiments/bounded_event_001/receipt_scaled_givens"
SOURCES = (
    "Makefile", "src/scm_model.c", "include/scm_model.h", "src/scm_assess.c",
    "include/scm_assess.h", "include/scm_estimator.h", "src/scm_evidence.c",
    "include/scm_evidence.h", "src/scm_remainder.c", "include/scm_remainder.h",
    "tests/test_remainder.c", "tools/remainder_probe.c", "tools/run_remainder.py",
    "experiments/bounded_event_002/plan.json",
)


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def save(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def git(*arguments: str) -> str:
    return subprocess.check_output(["git", *arguments], cwd=ROOT, text=True).strip()


def source_hashes() -> dict[str, str]:
    return {name: sha(ROOT / name) for name in SOURCES}


def safe_sha(path: Path) -> str | None:
    try:
        return sha(path)
    except OSError:
        return None


def captured_text(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value or ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--binary", type=Path, default=ROOT / "build/scm_remainder_probe")
    args = parser.parse_args()
    out = args.output_dir.resolve()
    if out.exists():
        parser.error("Output directory already exists; preserve it and select a new path")
    plan = json.loads((STUDY / "plan.json").read_text())
    budget = plan["budget"]["nll_units"]
    case_id = plan["case"]
    data = ROOT / "data" / f"{case_id}.csv"
    data_hash = sha(data)
    prior_receipt = json.loads((PRIOR / "receipt.json").read_text())
    if data_hash != prior_receipt["data_sha256"]:
        raise ValueError("Observation source differs from the frozen B001 comparison")
    before = source_hashes()
    anchors_before = {s["anchor_config"]: sha(ROOT / s["anchor_config"]) for s in plan["runs"]}
    executable_hash = sha(args.binary)
    out.mkdir(parents=True)
    metadata = {
        "schema": "mumble_remainder_receipt_v1",
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "source_revision": git("rev-parse", "HEAD"),
        "branch": git("branch", "--show-current"),
        "worktree_status_before": git("status", "--porcelain"),
        "source_sha256": before, "plan_sha256": sha(STUDY / "plan.json"),
        "data_sha256": data_hash, "prior_receipt_sha256": sha(PRIOR / "receipt.json"),
        "anchor_source_sha256": anchors_before,
        "retained_reference_sha256": sha(ROOT / "results/streaming_results.json"),
        "binary_sha256": executable_hash, "platform": platform.platform(),
        "python": platform.python_version(), "case_id": case_id,
        "budget_NLL": budget, "nominal_Hz": 35, "new_nonlinear_fits": 0,
        "arithmetic_validated": False, "coverage_validated": False,
        "bounded_cold_start_demonstrated": False, "updates_applied": False,
        "truth_policy": "No truth in inference, anchor, curvature, bounds, budget or candidate generation; score selected candidates only after every C process completes",
        "host_audit_arithmetic": "C double state/Jacobian; exact affine-amplitude reordering and long-double response/cost accumulation; no outward rounding claim",
        "runs": [], "operational_failures": [],
    }
    with tempfile.TemporaryDirectory(prefix="mumble_remainder_probe_") as temporary:
        executable = Path(temporary) / "scm_remainder_probe"
        executable.write_bytes(args.binary.read_bytes())
        executable.chmod(0o700)
        if sha(executable) != executable_hash:
            raise RuntimeError("Executable changed while taking the private run snapshot")
        for specification in plan["runs"]:
            name = specification["name"]
            anchor_source = ROOT / specification["anchor_config"]
            config = out / f"{name}_anchor.txt"
            config.write_bytes(anchor_source.read_bytes())
            tokens = config.read_text().split()
            command = [str(executable), str(data), str(config),
                       str(specification["end_samples"]), str(specification["split_samples"]),
                       str(plan["acquisition"]["max_event_samples"]), str(budget)]
            begin = time.perf_counter()
            run = {**specification, "file": f"{name}.json",
                   "anchor_source_sha256": anchors_before[specification["anchor_config"]],
                   "config_sha256": sha(config),
                   "command": [str(args.binary.resolve()), *command[1:]]}
            if len(tokens) < 3 or tokens[2] != data_hash or run["config_sha256"] != run["anchor_source_sha256"]:
                metadata["operational_failures"].append({"run": name, "kind": "anchor_identity_or_hash_mismatch"})
                metadata["runs"].append(run)
                break
            try:
                process = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=60)
            except subprocess.TimeoutExpired as error:
                stdout, stderr = captured_text(error.stdout), captured_text(error.stderr)
                (out / f"{name}.failed_stdout.txt").write_text(stdout)
                (out / f"{name}.stderr.txt").write_text(stderr)
                run["process_wall_s"] = time.perf_counter() - begin
                metadata["operational_failures"].append({"run": name, "kind": "timeout", "timeout_s": 60,
                                                         "stderr": stderr})
                metadata["runs"].append(run)
                break
            except OSError as error:
                run["process_wall_s"] = time.perf_counter() - begin
                (out / f"{name}.failed_stdout.txt").write_text("")
                (out / f"{name}.stderr.txt").write_text(str(error) + "\n")
                metadata["operational_failures"].append({"run": name, "kind": "process_launch", "error": str(error)})
                metadata["runs"].append(run)
                break
            run["process_wall_s"] = time.perf_counter() - begin
            (out / f"{name}.stderr.txt").write_text(process.stderr)
            if process.returncode:
                (out / f"{name}.failed_stdout.txt").write_text(process.stdout)
                metadata["operational_failures"].append({"run": name, "returncode": process.returncode,
                                                         "stderr": process.stderr})
                metadata["runs"].append(run)
                break
            try:
                result = json.loads(process.stdout)
                if not isinstance(result, dict) or result.get("source_id") != data_hash or result.get("end_samples") != specification["end_samples"]:
                    raise ValueError("Probe count or source identity mismatch")
                expected_counts = ([specification["split_samples"]] if 0 < specification["split_samples"] < specification["end_samples"] else []) + [specification["end_samples"]]
                if [c["samples"] for c in result["checkpoints"]] != expected_counts:
                    raise ValueError("Probe checkpoint counts mismatch")
            except (ValueError, TypeError, KeyError) as error:
                (out / f"{name}.failed_stdout.txt").write_text(process.stdout)
                metadata["operational_failures"].append({"run": name, "kind": "invalid_JSON_or_identity", "error": str(error),
                                                         "stderr": process.stderr})
                metadata["runs"].append(run)
                break
            save(out / run["file"], result)
            run["result"] = result
            metadata["runs"].append(run)
            print(json.dumps({"completed": name, "samples": specification["end_samples"],
                              "wall_s": run["process_wall_s"]}), flush=True)
    metadata["source_unchanged"] = before == {name: safe_sha(ROOT / name) for name in before}
    metadata["binary_unchanged"] = executable_hash == safe_sha(args.binary)
    metadata["data_unchanged"] = data_hash == safe_sha(data)
    metadata["anchor_sources_unchanged"] = anchors_before == {name: safe_sha(ROOT / name) for name in anchors_before}
    metadata["copied_configs_unchanged"] = all(safe_sha(out / f"{r['name']}_anchor.txt") == r["config_sha256"] for r in metadata["runs"])
    metadata["configs_unchanged"] = metadata["anchor_sources_unchanged"] and metadata["copied_configs_unchanged"]
    integrity_keys = ("source_unchanged", "binary_unchanged", "data_unchanged", "configs_unchanged")
    changed = [key for key in integrity_keys if not metadata[key]]
    if changed:
        metadata["operational_failures"].append({"kind": "post_run_integrity", "failed_checks": changed})
    if metadata["operational_failures"]:
        metadata["all_preregistered_checks_passed"] = False
        metadata["finished_utc"] = datetime.now(timezone.utc).isoformat()
        for run in metadata["runs"]:
            run.pop("result", None)
            if (out / run["file"]).exists():
                run["result_sha256"] = sha(out / run["file"])
        save(out / "receipt.json", metadata)
        return 1

    # All inference and replay subprocesses have now finished. Candidate
    # selection uses only their declared bounds; truth appears in scoring only.
    manifest = json.loads((ROOT / "data/manifest.json").read_text())
    truth = next(c["truth"] for c in manifest["cases"] if c["case_id"] == case_id)
    metadata["truth_manifest_sha256"] = sha(ROOT / "data/manifest.json")
    checks = []
    summary = []
    tol = plan["checks"]
    norm_tol = tol["observed_whitened_remainder_norm_absolute_tolerance"]
    nll_tol = tol["observed_absolute_NLL_error_bound_tolerance"]

    def check(name: str, passed: bool, **details: object) -> None:
        checks.append({"name": name, "passed": bool(passed), **details})

    for run in metadata["runs"]:
        prior = json.loads((PRIOR / f"{run['name']}.json").read_text())
        for checkpoint in run["result"]["checkpoints"]:
            label = f"{run['name']}/{checkpoint['label']}"
            old = next(c for c in prior["checkpoints"] if c["samples"] == checkpoint["samples"])
            check(label + "/candidate_count", len(checkpoint["candidates"]) == plan["candidate_policy"]["count_per_checkpoint"])
            check(label + "/paired_count", checkpoint["remainder_summary"]["next_sample_index"] == checkpoint["samples"])
            check(label + "/nonlinear_status", checkpoint["assessment_adapter_status"] == 1 and checkpoint["nonlinear_optimizer_status"] == "not_run")
            gram_error = math.sqrt(sum((a-b)**2 for a, b in zip(checkpoint["gram"], old["gram"], strict=True))) / max(1., math.sqrt(sum(x*x for x in old["gram"])))
            check(label + "/unchanged_reference_Gram", gram_error <= tol["factor_vs_reference_relative_Gram_tolerance"], relative_error=gram_error)
            for target in ("Q_Ah", "current_SOC"):
                check(label + "/unchanged_precision_availability/" + target,
                      checkpoint["targets"][target]["local_range_available"] == old["targets"][target]["local_range_available"])
            candidates = checkpoint["candidates"]
            by_name = {c["probe_name"]: c for c in candidates}
            for candidate in candidates:
                key = label + "/" + candidate["probe_name"]
                bound = candidate["remainder"]
                check(key + "/arithmetic_disclosure", bound["arithmetic_validated"] is False)
                relative_affine_error = abs(candidate["factor_minus_direct_affine"]) / max(1., abs(candidate["direct_affine_cost"]))
                check(key + "/affine_replay", relative_affine_error <= tol["factor_vs_direct_affine_relative_cost_tolerance"], relative_error=relative_affine_error)
                available = bound["status_code"] in (2, 3)
                if available:
                    check(key + "/query_inside_domain", bound["query_return"] == 0 and bound["domain_code"] == 0 and candidate["guard_code"] == 0)
                    actual_norm = candidate["actual_whitened_remainder_norm"]
                    actual_nll = candidate["exact_minus_affine_cost"]
                    check(key + "/prediction_bound", actual_norm is not None and actual_norm <= bound["E_bound"] + norm_tol,
                          actual_norm=actual_norm, E_bound=bound["E_bound"], numerical_audit_tolerance=norm_tol)
                    check(key + "/NLL_bound", actual_nll is not None and abs(actual_nll) <= bound["B_bound"] + nll_tol,
                          signed_observed_NLL_difference=actual_nll, B_bound=bound["B_bound"], numerical_audit_tolerance=nll_tol)
                    check(key + "/budget_status", (bound["status_code"] == 3) == (bound["B_bound"] <= budget))
                else:
                    check(key + "/outside_or_unavailable_has_no_bound", bound["E_bound"] is None and bound["B_bound"] is None and not bound["eligible_update"])
                if bound["eligible_update"]:
                    check(key + "/eligible_policy", candidate["candidate_generation_available"] and bound["is_nonzero_candidate"] and
                          bound["status_code"] == 3 and checkpoint["residual_monitor"]["flagged_events"] == 0 and
                          bound["descent_upper_nll"] < checkpoint["zero_cost"])
                    check(key + "/eligible_replay_descent", candidate["exact_nonlinear_cost"] is not None and
                          candidate["exact_nonlinear_cost"] < checkpoint["zero_cost"] + nll_tol)
            for exact_name in ("zero", "inside_R0"):
                b = by_name[exact_name]["remainder"]
                check(label + "/exact_affine/" + exact_name, b["E_bound"] == 0 and b["B_bound"] == 0)
            check(label + "/zero_not_descent", not by_name["zero"]["remainder"]["eligible_update"])
            check(label + "/outside_probes_unavailable", all(by_name[n]["remainder"]["status_code"] == 1 for n in ("outside_Q", "outside_SOC")))
            eligible = [c for c in candidates if c["remainder"]["eligible_update"]]
            selected = min(eligible, key=lambda c: c["remainder"]["descent_upper_nll"]) if eligible else None
            if selected:
                true_soc = truth["z0"] - checkpoint["charge_Ah"] / truth["Q_Ah"]
                selected["truth_scoring_only"] = {
                    "Q_relative_error_percent": 100*(selected["Q_Ah"]/truth["Q_Ah"]-1),
                    "current_SOC_error_pp": 100*(selected["current_SOC"]-true_soc)}
            summary.append({"run": run["name"], "checkpoint": checkpoint["label"],
                            "samples": checkpoint["samples"], "rank": checkpoint["numerical_rank"],
                            "Q_local": checkpoint["targets"]["Q_Ah"], "SOC_local": checkpoint["targets"]["current_SOC"],
                            "gamma_minus": checkpoint["gamma_minus_structural_status"],
                            "residual_flagged_events": checkpoint["residual_monitor"]["flagged_events"],
                            "budget_pass_candidates": sum(c["remainder"]["status_code"] == 3 for c in candidates),
                            "eligible_candidates": len(eligible), "selected_by_smallest_descent_upper_nll": selected,
                            "full_joint_step": by_name["full_joint_step"],
                            "conditional_SOC_Q_step": by_name["conditional_SOC_Q_step"],
                            "inside_SOC_Q_probe": by_name["inside_SOC_Q"], "region_bound": checkpoint["region_bound"]})
        save(out / run["file"], run["result"])

    early = metadata["runs"][0]["result"]["checkpoints"][-1]
    early_gamma = next(c for c in early["candidates"] if c["probe_name"] == "gamma_minus_half_radius")
    check("unexcited_400/gamma_control", early["gamma_minus_structural_status"] == "unexcited" and
          early_gamma["remainder"]["E_bound"] == 0 and early_gamma["remainder"]["B_bound"] == 0)
    check("unexcited_400/unknowns_preserved", not early["targets"]["Q_Ah"]["local_range_available"] and not early["targets"]["current_SOC"]["local_range_available"])
    tail = metadata["runs"][2]["result"]["checkpoints"][-1]
    tail_by = {c["probe_name"]: c for c in tail["candidates"]}
    check("tail/known_inside_probe_rejected", tail_by["inside_SOC_Q"]["guard_code"] == 0 and tail_by["inside_SOC_Q"]["remainder"]["status_code"] == 2)
    check("tail/full_step_conservatism_disclosed", tail_by["full_joint_step"]["remainder"]["status_code"] == 2)
    nominal = metadata["runs"][3]["result"]["checkpoints"][-1]
    check("nominal/residuals_block_updates", nominal["residual_monitor"]["flagged_events"] > 0 and not any(c["remainder"]["eligible_update"] for c in nominal["candidates"]))
    metadata["checks"] = checks
    metadata["summary"] = summary
    metadata["all_preregistered_checks_passed"] = all(c["passed"] for c in checks)
    metadata["interpretation"] = {
        "individual_or_region_budget_failure": "Sufficient bound fails to qualify; no conclusion that the actual candidate is inaccurate or excluded",
        "conditional_step": "Other candidate coordinates held at anchor; full joint uncertainty retained",
        "coverage": "Neither a passing local budget nor numerical falsification validates confidence coverage",
        "no_reanchor": "All full/scaled/conditional candidates refer to the same original anchor; none is applied",
    }
    for run in metadata["runs"]:
        run.pop("result")
        run["result_sha256"] = sha(out / run["file"])
    metadata["finished_utc"] = datetime.now(timezone.utc).isoformat()
    save(out / "receipt.json", metadata)
    print(json.dumps({"all_checks_passed": metadata["all_preregistered_checks_passed"],
                      "checks": len(checks), "arithmetic_validated": False,
                      "eligible_by_checkpoint": [{"run": s["run"], "checkpoint": s["checkpoint"], "eligible": s["eligible_candidates"]} for s in summary]}), flush=True)
    return 0 if metadata["all_preregistered_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
