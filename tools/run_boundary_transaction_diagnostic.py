#!/usr/bin/env python3
"""Run one frozen, tiny boundary/transaction diagnostic without cell histories.

The baseline is an instrumented copy of the hash-checked production source.
The remedy differs only in finite rounded-mean fallback. Both scalar entry
points extract their selector loops from those generated sources. No deployed
source, persistent object layout, observation stream, or prior is modified.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
FROZEN_SOURCE = "b07c2147a281026b9cd22ef9d8470d383147c0fd48bfe27ec90c4599ba7dd730"
FLAGS = ["-std=c99", "-O3", "-Wall", "-Wextra", "-Wpedantic", "-Werror",
         "-fno-fast-math", "-ffp-contract=off"]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def replace_one(source: str, before: str, after: str, label: str,
                edits: list[dict]) -> str:
    count = source.count(before)
    if count != 1:
        raise ValueError(f"{label}: expected exactly one frozen-source match, got {count}")
    edits.append({"label": label, "matches": count})
    return source.replace(before, after, 1)


CAPTURE_HELPERS = r'''
void fixture_capture_reset(boundary_capture *capture)
{
    if(!capture)return;
    memset(capture,0,sizeof(*capture));
    capture->coordinate=capture->column=capture->boundary_coordinate=-1;
}

static int fixture_capture_fail(boundary_capture *capture,int stage,int coordinate,int column)
{
    if(capture) {
        capture->stage=stage;capture->coordinate=coordinate;capture->column=column;
    }
    return -1;
}

static void fixture_record_boundary(boundary_capture *capture,int coordinate,
    double mean,double gain,double standard,double change,double scale,double selected,double proposed)
{
    if(!capture)return;
    capture->boundary_coordinate=coordinate;capture->mean_before=mean;
    capture->raw_gain=gain;capture->standard=standard;capture->raw_change=change;
    capture->scale=scale;capture->selected_gain=selected;capture->proposed_mean=proposed;
}
'''

MEAN_CAPTURE = '''        value=s->mean[i]+t*standard;
        if(i==9||!isfinite(value)||value<lower[i]||value>upper[i])
            fixture_record_boundary(capture,i,s->mean[i],gain,standard,change,lambda,t,value);
        if(!isfinite(value)||value<lower[i]||value>upper[i])
            return fixture_capture_fail(capture,BOUNDARY_STAGE_MEAN_DOMAIN,i,-1);
'''

REMEDY_SELECT = '''        t=lambda*gain;
        value=s->mean[i]+t*standard;
        if(i==9||!isfinite(value)||value<lower[i]||value>upper[i])
            fixture_record_boundary(capture,i,s->mean[i],gain,standard,change,lambda,t,value);
        if(!isfinite(value))return fixture_capture_fail(capture,BOUNDARY_STAGE_MEAN_DOMAIN,i,-1);
        if(value<lower[i]||value>upper[i]) {
            if(capture)capture->fallback_mask|=1u<<i;
            lambda=0.;t=0.;value=s->mean[i];
        }
        w->correction[i]=t;
'''


def instrument(original: str) -> tuple[str, list[dict]]:
    """Assert every edit against the frozen correct()/ingest() text."""
    edits: list[dict] = []
    start = original.index("static int correct(")
    end = original.index("\nint scm_online_ingest(", start)
    correct = original[start:end]
    substitutions = [
        ("static int correct(const scm_online *predicted,scm_online *s,double voltage,scm_online_workspace *w)",
         "static int correct(const scm_online *predicted,scm_online *s,double voltage,scm_online_workspace *w,boundary_capture *capture)",
         "correction_capture_argument"),
        ("if(observation(s,s->last_current_A,&prediction,w->observation_gradient))return -1;",
         "if(observation(s,s->last_current_A,&prediction,w->observation_gradient))return fixture_capture_fail(capture,BOUNDARY_STAGE_OBSERVATION,-1,-1);",
         "stage_observation"),
        ("innovation=voltage-prediction;if(!isfinite(innovation))return -1;",
         "innovation=voltage-prediction;if(!isfinite(innovation))return fixture_capture_fail(capture,BOUNDARY_STAGE_INNOVATION,-1,-1);",
         "stage_innovation"),
        ("if(!isfinite(value))return -1;",
         "if(!isfinite(value))return fixture_capture_fail(capture,BOUNDARY_STAGE_PROJECTION,-1,j);",
         "stage_projection"),
        ("if(!isfinite(r)||r<=0||r>sqrt(DBL_MAX))return -1;",
         "if(!isfinite(r)||r<=0||r>sqrt(DBL_MAX))return fixture_capture_fail(capture,BOUNDARY_STAGE_INNOVATION_SD,-1,j);",
         "stage_innovation_sd"),
        ("if(!isfinite(gain)||!isfinite(factor))return -1;",
         "if(!isfinite(gain)||!isfinite(factor))return fixture_capture_fail(capture,BOUNDARY_STAGE_OPTIMAL_ROTATION,i,j);",
         "stage_optimal_rotation"),
        ("standard=innovation/sd;if(!isfinite(standard))return -1;",
         "standard=innovation/sd;if(!isfinite(standard))return fixture_capture_fail(capture,BOUNDARY_STAGE_STANDARD,-1,-1);",
         "stage_standard"),
        ("if(!isfinite(change))return -1;",
         "if(!isfinite(change))return fixture_capture_fail(capture,BOUNDARY_STAGE_RAW_CHANGE,i,-1);",
         "stage_raw_change"),
        ("        value=s->mean[i]+t*standard;\n        if(!isfinite(value)||value<lower[i]||value>upper[i])return -1;\n",
         MEAN_CAPTURE, "stage_mean_domain_and_attempt_capture"),
        ("if(!isfinite(r)||r<=0)return -1;",
         "if(!isfinite(r)||r<=0)return fixture_capture_fail(capture,BOUNDARY_STAGE_JOSEPH_SD,j,j);",
         "stage_joseph_sd"),
        ("if(!isfinite(factor)||!isfinite(remainder))return -1;",
         "if(!isfinite(factor)||!isfinite(remainder))return fixture_capture_fail(capture,BOUNDARY_STAGE_JOSEPH_ROTATION,i,j);",
         "stage_joseph_rotation"),
        ("if(observation(s,s->last_current_A,&s->last_prediction_V,NULL))return -1;",
         "if(observation(s,s->last_current_A,&s->last_prediction_V,NULL))return fixture_capture_fail(capture,BOUNDARY_STAGE_FINAL_OBSERVATION,-1,-1);",
         "stage_final_observation"),
        ("return scm_online_validate(s)?-1:0;",
         "if(scm_online_validate(s))return fixture_capture_fail(capture,BOUNDARY_STAGE_VALIDATION,-1,-1);\n    return 0;",
         "stage_validation")
    ]
    for before, after, label in substitutions:
        correct = replace_one(correct, before, after, label, edits)
    if "return -1;" in correct:
        raise ValueError("An uninstrumented correction rejection remains")
    source = original[:start] + CAPTURE_HELPERS + "\n" + correct + original[end:]
    source = replace_one(source, '#include "scm_online.h"',
                         '#include "boundary_transaction_capture.h"', "capture_header", edits)
    source = replace_one(source,
        "int scm_online_ingest(scm_online *s,const unsigned char id[SCM_ONLINE_SOURCE_BYTES],\n"
        "    uint64_t index,const scm_sample *input,int voltage_present,scm_online_workspace *w)",
        "int fixture_ingest(scm_online *s,const unsigned char id[SCM_ONLINE_SOURCE_BYTES],\n"
        "    uint64_t index,const scm_sample *input,int voltage_present,scm_online_workspace *w,boundary_capture *capture)",
        "fixture_ingest_name_and_capture_argument", edits)
    source = replace_one(source,
        "    scm_online *next;double elapsed,epoch_elapsed;int failed;\n",
        "    scm_online *next;double elapsed,epoch_elapsed;int failed;\n    fixture_capture_reset(capture);\n",
        "ingest_capture_reset", edits)
    source = replace_one(source, "if(correct(s,next,input->voltage,w))",
                         "if(correct(s,next,input->voltage,w,capture))", "pass_capture_to_correct", edits)
    return source, edits


def remedy(baseline: str) -> tuple[str, list[dict]]:
    edits: list[dict] = []
    source = replace_one(baseline, "        t=lambda*gain;w->correction[i]=t;\n",
                         REMEDY_SELECT, "finite_actual_mean_coordinate_fallback", edits)
    source = replace_one(source, MEAN_CAPTURE, "", "remove_old_mean_check_after_masks", edits)
    return source, edits


def add_scalar_entry(source: str) -> tuple[str, str]:
    """Extract the exact generated selector; never transcribe another limiter."""
    marker = "    for(i=0;i<D;i++) {\n        double gain=w->covariance_gradient[i],change=gain*standard"
    if source.count(marker) != 1:
        raise ValueError("Expected exactly one generated selector loop")
    start = source.index(marker)
    end = source.index("    if(!active)maximum=1.;", start)
    loop = source[start:end]
    entry = "\nint fixture_select(scm_online *s,scm_online_workspace *w,double standard,boundary_capture *capture)\n" \
        "{\n    int i,active=0,any_gain=0;unsigned limited=0,blocked=0;\n" \
        "    double minimum=1.,maximum=0.;\n    fixture_capture_reset(capture);\n" + loop + \
        "    if(!active)maximum=1.;\n    s->last_gain_scale=minimum;s->last_max_gain_scale=maximum;\n" \
        "    s->last_limited_mask=limited;s->last_blocked_mask=blocked;\n" \
        "    (void)any_gain;\n    return 0;\n}\n"
    return source + entry, hashlib.sha256(loop.encode()).hexdigest()


def run(command: list[str], stdout: Path, stderr: Path) -> dict:
    record: dict = {"command": command, "returncode": None, "timeout_s": 60,
                    "stdout": stdout.name, "stderr": stderr.name}
    with stdout.open("wb") as out, stderr.open("wb") as err:
        try:
            process = subprocess.run(command, cwd=ROOT, stdout=out, stderr=err,
                                     timeout=60, check=False)
            record["returncode"] = process.returncode
        except (OSError, subprocess.TimeoutExpired) as error:
            record["execution_error"] = str(error)
    record["stdout_sha256"], record["stderr_sha256"] = sha(stdout), sha(stderr)
    return record


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--cc", default="cc", help="C compiler executable")
    args = parser.parse_args()
    out = args.output_dir.resolve()
    if out.exists():
        raise SystemExit(f"Refusing existing output directory: {out}")
    original_path = ROOT / "src/scm_online.c"
    if sha(original_path) != FROZEN_SOURCE:
        raise SystemExit("Production source differs from frozen bounded_online_002 hash")
    baseline, baseline_edits = instrument(original_path.read_text(encoding="utf-8"))
    changed, remedy_edits = remedy(baseline)
    baseline, baseline_loop_hash = add_scalar_entry(baseline)
    changed, remedy_loop_hash = add_scalar_entry(changed)
    fixture = ROOT / "tools/boundary_transaction_diagnostic.c"
    if not fixture.is_file():
        raise SystemExit(f"Required fixture is absent: {fixture}")
    compiler = shutil.which(args.cc)
    if compiler is None:
        raise SystemExit(f"Compiler executable was not found: {args.cc}")
    source_paths = [original_path, ROOT / "src/scm_model.c", ROOT / "include/scm_online.h",
                    ROOT / "include/scm_model.h", fixture, Path(__file__).resolve(),
                    ROOT / "tools/boundary_transaction_capture.h"]
    source_hashes = {str(p.relative_to(ROOT)): sha(p) for p in source_paths}
    revision, source_tree = git("rev-parse", "HEAD"), git("rev-parse", "HEAD^{tree}")
    initial_status = git("status", "--short")
    out.mkdir(parents=True, exist_ok=False)
    baseline_path, remedy_path = out / "baseline.instrumented.c", out / "remedy.instrumented.c"
    baseline_path.write_text(baseline, encoding="utf-8")
    remedy_path.write_text(changed, encoding="utf-8")
    diff = "".join(difflib.unified_diff(baseline.splitlines(True), changed.splitlines(True),
        fromfile=baseline_path.name, tofile=remedy_path.name))
    (out / "remedy.diff").write_text(diff, encoding="utf-8")
    receipt: dict = {
        "schema": "mumble_boundary_transaction_diagnostic_receipt_v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_revision": revision,
        "source_tree": source_tree,
        "branch": git("branch", "--show-current"),
        "working_tree_status_at_start": initial_status,
        "host": {"system": platform.system(), "release": platform.release(),
                 "machine": platform.machine(), "python": platform.python_version()},
        "compiler": {"requested": args.cc, "resolved": compiler},
        "source_hashes": source_hashes,
        "frozen_production_source_sha256": FROZEN_SOURCE,
        "generated_sources": {
            "baseline": {"path": baseline_path.name, "sha256": sha(baseline_path),
                         "scalar_loop_sha256": baseline_loop_hash},
            "remedy": {"path": remedy_path.name, "sha256": sha(remedy_path),
                       "scalar_loop_sha256": remedy_loop_hash}},
        "asserted_instrumentation_edits": baseline_edits,
        "asserted_remedy_edits": remedy_edits,
        "remedy_diff": {"path": "remedy.diff", "sha256": sha(out / "remedy.diff")},
        "production_source_modified": False,
        "persistent_state_or_checkpoint_ABI_modified": False,
        "cell_histories_opened": 0,
        "primary_runs": 0,
        "truth_input": False,
        "processes": [],
        "limitations": ["Constructed finite host fixtures; historical rejection attribution remains open.",
                        "No full-model indefinite-stability, accuracy, coverage or Cortex-M23 qualification."]
    }
    receipt["compiler"]["version_process"] = run([compiler, "--version"],
        out / "compiler_version.txt", out / "compiler_version.stderr.txt")
    receipt["compiler"]["version"] = (out / "compiler_version.txt").read_text(encoding="utf-8", errors="replace")
    save(out / "receipt.json", receipt)
    with tempfile.TemporaryDirectory(prefix="mumble-boundary-001-") as temporary:
        for name, source, variant in (("baseline", baseline_path, 0), ("remedy", remedy_path, 1)):
            binary = Path(temporary) / name
            command = [compiler, *FLAGS, "-Iinclude", "-Itools", f"-DFIXTURE_REMEDY={variant}",
                       str(source), str(fixture), "src/scm_model.c", "-lm", "-o", str(binary)]
            print(json.dumps({"event": "fixture_begin", "variant": name}), flush=True)
            process: dict = {"variant": name,
                "build": run(command, out / f"{name}.build.stdout.txt", out / f"{name}.build.stderr.txt")}
            process["passed"] = False
            if process["build"]["returncode"] == 0:
                process["binary_sha256"] = sha(binary)
                process["run"] = run([str(binary)], out / f"{name}.json", out / f"{name}.stderr.txt")
                try:
                    def reject_constant(value: str) -> None:
                        raise ValueError(f"Non-JSON numeric constant: {value}")
                    result = json.loads((out / f"{name}.json").read_text(encoding="utf-8"),
                                        parse_constant=reject_constant)
                    if not isinstance(result, dict) or not {"schema", "checks", "failed_checks", "result"}.issubset(result):
                        raise ValueError("Fixture stdout lacks its required summary fields")
                    process["summary"] = {k: result[k] for k in ("schema", "checks", "failed_checks", "result")}
                    process["passed"] = process["run"]["returncode"] == 0 and not result["failed_checks"]
                except (ValueError, UnicodeError) as error:
                    process["parse_error"] = str(error)
            receipt["processes"].append(process)
            save(out / "receipt.json", receipt)
            print(json.dumps({"event": "fixture_complete", "variant": name,
                              "passed": process["passed"]}), flush=True)
    receipt["production_hash_unchanged_after"] = sha(original_path) == FROZEN_SOURCE
    receipt["source_hashes_unchanged_after"] = all(sha(ROOT / p) == h for p, h in source_hashes.items())
    receipt["passed"] = len(receipt["processes"]) == 2 and all(p["passed"] for p in receipt["processes"]) and \
        receipt["production_hash_unchanged_after"] and receipt["source_hashes_unchanged_after"]
    receipt["completed_utc"] = datetime.now(timezone.utc).isoformat()
    save(out / "receipt.json", receipt)
    print(json.dumps({"receipt": str(out / "receipt.json"), "passed": receipt["passed"]}), flush=True)
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
