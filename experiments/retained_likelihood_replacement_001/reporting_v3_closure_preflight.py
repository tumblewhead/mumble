#!/usr/bin/env python3
"""Validate v3's closed evidence only; never reduce a prior or open truth."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import resource
import sys
import time


AREA = Path(__file__).resolve().parent
ROOT = AREA.parents[1]
ADAPTER_SHA256 = "87b560e52a37b8ce56307b5b0650baf21da37f04359d5123381931a85acd1b5d"


def main() -> int:
    sys.dont_write_bytecode = True
    adapter_path = AREA / "reporting_continuation_v3.py"
    if hashlib.sha256(adapter_path.read_bytes()).hexdigest() != ADAPTER_SHA256:
        raise ValueError("Unreviewed v3 source change before closure preflight")
    output = AREA / "qualification/reporting_v3_closure_preflight.json"
    if output.exists():
        raise ValueError("Closure preflight already recorded; no overwrite")
    started = time.monotonic()
    spec = importlib.util.spec_from_file_location("retained_reporting_v3_preflight", adapter_path)
    if spec is None or spec.loader is None:
        raise ValueError("Cannot load v3 closure adapter")
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    core = adapter.load_core()
    activity = {
        "reporter_main_invocations": 0,
        "model_or_optimizer_or_learner_calls": 0,
        "prior_algebra_evaluations": 0,
        "truth_file_opens": 0,
        "truth_records_decoded": 0,
        "blocked_forbidden_calls": 0,
    }

    def forbidden(*args, **kwargs):
        activity["blocked_forbidden_calls"] += 1
        raise RuntimeError("Numerical reporting and truth are forbidden in closure preflight")

    for name in ("prior_algebra", "summarize_arm", "local_shape", "read_verified_endpoint_truth"):
        setattr(core, name, forbidden)

    def block_truth(event, args):
        if event == "open" and isinstance(args[0], (str, bytes)):
            path = args[0].decode() if isinstance(args[0], bytes) else args[0]
            if Path(path).name == "truth.bin":
                activity["blocked_forbidden_calls"] += 1
                raise RuntimeError("Truth file opens are forbidden in closure preflight")

    sys.addaudithook(block_truth)
    bindings = {str(path): core.identity(path) for path in (
        Path(__file__).resolve(), adapter_path, AREA / "reporting.py",
        AREA / "reporting_reservation.json", AREA / "reporting_receipt.json",
    )}
    failure = None
    result = None
    try:
        original = adapter.validate_original_attempt(core, ROOT, bindings)
        directory = AREA / "continuation001"
        closed = adapter.validate_closed_continuation(core, ROOT, directory, original, bindings)
        outer = adapter.validate_continuation_outer(core, ROOT, directory, closed, original, bindings)
        core.require("numpy" not in sys.modules and "scipy" not in sys.modules,
                     "Closure preflight unexpectedly loaded numerical packages")
        result = {
            "original_attempt_status": original["result"]["status"],
            "continuation_status": closed["result"]["status"],
            "continuation_outer_status": outer["status"],
            "source_revision": closed["result"]["source_revision"],
            "cumulative_counts": closed["receipt"]["cumulative_counts"],
            "cumulative_resources": outer["cumulative_resources"],
            "all_closed_output_bytes": outer["all_closed_output_bytes_including_outer_receipt"],
            "artifact_metadata_adaptation": outer["reporting_artifact_metadata_adaptation"],
        }
    except Exception as error:
        failure = {"type": type(error).__name__, "message": str(error)}
    after = {path: core.identity(Path(path)) for path in bindings}
    if after != bindings and failure is None:
        failure = {"type": "InputMutation", "message": "A bound file changed during closure preflight"}
    receipt = {
        "schema": "mumble_retained_reporting_closure_preflight_v1",
        "status": "passed" if failure is None else "failed",
        "command": [sys.executable, *sys.argv],
        "exception": failure,
        "result": result,
        "activity": activity,
        "before": bindings,
        "after": after,
        "all_bound_files_unchanged": after == bindings,
        "resources": {
            "wall_s_before_receipt": time.monotonic() - started,
            "own_peak_RSS_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
        },
        "scope": "Input/source identity, original failure preservation and cumulative closure checks only. No reporter main, NumPy, prior algebra, model, optimizer or truth access. Actual reporting still requires root authorization.",
    }
    core.write_new_json(output, receipt)
    print(json.dumps({"status": receipt["status"], "exception": failure,
                      "receipt": core.identity(output), "activity": activity,
                      "bound_files": len(bindings)}, allow_nan=False))
    return 0 if failure is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
