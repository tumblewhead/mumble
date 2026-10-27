#!/usr/bin/env python3
"""One saved-CSV reporting continuation; the original failed report is immutable.

This does not rerun the frozen reporter.  It reads no original truth or observation
file, and calls no model, prior, optimizer, source generator, or interval routine.
"""
from __future__ import annotations
import argparse
import csv
import gzip
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import resource
import signal
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
EXP = "experiments/live_anchor_integration_001"
SELF = "tools/finish_live_anchor_report.py"
PLAN = EXP + "/reporting_plan.json"
RUNNER = "tools/run_live_anchor_integration.py"
SCHEMA = "mumble_live_anchor_reporting_continuation_v1"
OUTER_SHA = "338acf3c491baab5691239c2115f83a750d9422682d72ebb87f51db919452d08"
FAILED_SHA = "cf525bcf13d85365254b48b458f6fe93b5b730cc9d7c6e641c43f916efa63b0d"
CSV_SHA = "f1bdf31d27132cd9f95760fd98e9eb6721fc7208fc396f74370be3fde6ad259a"
ORIGINAL_SOURCE_SHA = "a2a043a548caa7173aab24fdf6af1409124409e67f7dca5f9d8033548a97ed8e"
PLAN_SHA = "a4a1916e0dc42349f8e067475b314522820efc3568e052804a37bd137d0f9a92"
LIMITS = {"CPU_s": 30, "wall_s": 60, "RSS_bytes": 268435456, "output_bytes": 8388608,
          "continuation_invocations": 1, "saved_rows": 31501}
STEMS = ("all16_parameters", "parameters_01_08", "parameters_09_16", "current_states",
         "capacity_SOC_overview", "early_capacity_SOC")
WORK = ("model_steps", "qr_rows", "query_evaluations", "prior_evaluations", "proposal_rounds", "accepted_steps")
STOP = {0: "none", 1: "round_limit", 2: "direction_unresolved", 3: "no_admitted_trial",
        4: "metric_unresolved", 5: "query_unavailable", 6: "counter_limit", 7: "rounding_unresolved"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def pairs(values):
    result = {}
    for key, value in values:
        require(key not in result, "Duplicate JSON key")
        result[key] = value
    return result


def read_json(path):
    def bad(value):
        raise ValueError("Nonfinite JSON: " + value)
    return json.loads(Path(path).read_bytes(), object_pairs_hook=pairs, parse_constant=bad)


def encode(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def identity(path):
    sha, size = hashlib.sha256(), 0
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            sha.update(block)
            size += len(block)
    return {"bytes": size, "sha256": sha.hexdigest()}


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)


def write_json(path, value):
    with Path(path).open("xb") as stream:
        stream.write(encode(value)); stream.flush(); os.fsync(stream.fileno())
    sync_dir(Path(path).parent)


def import_bound(path, expected):
    require(identity(path) == expected, "Runner source differs")
    spec = importlib.util.spec_from_file_location("closed_live_runner_for_csv_continuation", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def binding(rows, path):
    found = [r for r in rows if Path(r["path"]).resolve() == path.resolve()]
    require(len(found) == 1, "Missing/ambiguous source binding")
    return {k: found[0][k] for k in ("bytes", "sha256")}


class Continuation:
    def __init__(self, args):
        self.args, self.root = args, Path(args.root).resolve()
        require(self.root == ROOT, "Wrong repository root")
        require(args.outer_sha256 == OUTER_SHA and args.failed_report_sha256 == FAILED_SHA,
                "Continuation authority differs from the fixed saved attempt")
        self.output = self.root / EXP / "reporting_continuation001"
        require(not self.output.exists(), "Continuation destination exists; no overwrite/retry")
        self.output.mkdir(); sync_dir(self.output.parent)
        self.start, self.cpu = time.monotonic(), time.process_time()
        self.stage, self.errors, self.inputs = "reservation", [], {}
        self.gate, self.summary = None, None
        self.counts = {"continuation_invocations": 1, "saved_CSV_rows": 0,
            "original_truth_file_opens": 0, "truth_literal_evaluations": 0, "observation_archive_opens": 0,
            "model_calls": 0, "prior_calls": 0, "optimizer_calls": 0, "source_generation_calls": 0,
            "RNG_draws": 0, "interval_calculations": 0}
        self.np, self.plt = None, None
        write_json(self.output / "reservation.json", {"schema": SCHEMA, "limits": LIMITS,
            "source": identity(Path(__file__)), "outer_sha256": OUTER_SHA, "failed_report_sha256": FAILED_SHA,
            "scope": "Saved CSV statistics and missing categorical figure only; original report/source immutable."})

    def remember(self, path, expected=None):
        path = Path(path).resolve()
        actual = identity(path)
        if expected is not None: require(actual == expected, "Bound saved input changed: " + str(path))
        row = {"path": str(path), **actual}
        require(str(path) not in self.inputs or self.inputs[str(path)] == row, "Conflicting input binding")
        self.inputs[str(path)] = row
        return actual

    def resources(self):
        return {"CPU_s": time.process_time()-self.cpu, "wall_s": time.monotonic()-self.start,
            "own_peak_RSS_bytes": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) *
                (1 if sys.platform == "darwin" else 1024)}

    def check_resources(self):
        r = self.resources()
        require(r["CPU_s"] <= LIMITS["CPU_s"] and r["wall_s"] <= LIMITS["wall_s"] and
                r["own_peak_RSS_bytes"] <= LIMITS["RSS_bytes"], "Continuation resource cap exceeded")
        require(sum(p.stat().st_size for p in self.output.rglob("*") if p.is_file()) <= LIMITS["output_bytes"],
                "Continuation output cap exceeded")

    def gate_inputs(self):
        self.stage = "review_and_saved_capture_gate"
        own = self.remember(self.root / SELF)
        review_path = Path(self.args.review).resolve()
        require(review_path.is_relative_to(self.root / EXP), "Review must be in the experiment")
        self.remember(review_path)
        review = read_json(review_path)
        require(review["status"] == "passed" and review["source_sha256"] == own["sha256"], "Continuation review is not passed/source-bound")
        plan_id = self.remember(self.root / PLAN)
        require(plan_id["sha256"] == PLAN_SHA, "Original reporting plan changed")
        self.plan = read_json(self.root / PLAN)
        original_id = self.remember(self.root / "tools/report_live_anchor_integration.py")
        require(original_id["sha256"] == ORIGINAL_SOURCE_SHA, "Original frozen reporter changed")
        outer_path = self.root / EXP / "execution_process/receipt.json"
        self.outer_id = self.remember(outer_path)
        require(self.outer_id == {"bytes": 5999, "sha256": OUTER_SHA}, "Closed parent outer identity differs")
        outer = read_json(outer_path)
        expected = binding(outer["source_bindings"], self.root / RUNNER)
        self.remember(self.root / RUNNER, expected)
        self.run = import_bound(self.root / RUNNER, expected)
        self.gate = self.run.validate_closed_run(self.root, self.outer_id, read_observations=False)
        require(self.gate["observations_reopened"] is False, "Observation archive was reopened")
        require(binding(self.gate["inner"]["source_bindings"], self.root / PLAN) == plan_id and
            binding(self.gate["inner"]["source_bindings"], self.root / "tools/report_live_anchor_integration.py") == original_id,
            "Original report/plan pre-inference bindings differ")
        for name in ("receipt.json", "result.json"):
            self.remember(self.root / EXP / "attempt001" / name)
        failed_dir = self.root / EXP / "reporting001"
        failed_id = self.remember(failed_dir / "reporting_receipt.json")
        require(failed_id == {"bytes": 6851, "sha256": FAILED_SHA}, "Original failed reporting receipt changed")
        self.failed = read_json(failed_dir / "reporting_receipt.json")
        require(self.failed["status"] == "failed" and self.failed["stage"] == "saved_trace_figures" and
            self.failed["errors"] == [{"message": "This method only works with the ScalarFormatter",
                "stage": "saved_trace_figures", "type": "AttributeError"}], "Failure is outside the narrow continuation scope")
        expected_names = {"reservation.json", "trajectory.csv.gz"} | {s+ext for s in STEMS for ext in (".png", ".svg")}
        require(set(self.failed["files"]) == expected_names and
            {p.name for p in failed_dir.iterdir()} == expected_names | {"reporting_receipt.json"},
            "Original partial-output inventory changed")
        for name, expected in self.failed["files"].items():
            self.remember(failed_dir / name, expected)
        require(sum(r["bytes"] for r in self.failed["files"].values()) + failed_id["bytes"] ==
            self.failed["closed_output_bytes_including_receipt"], "Original reporting byte accounting differs")
        self.csv_path = failed_dir / "trajectory.csv.gz"
        require(self.failed["files"]["trajectory.csv.gz"] == {"bytes": 14400050, "sha256": CSV_SHA}, "CSV identity differs")
        activity = self.failed["reporting_activity"]
        require(activity["reporting_invocations"] == 1 and activity["saved_snapshot_decodes"] == 31501 and
            activity["truth_literal_evaluations"] == 1 and activity["scalar_truth_record_reads"] == 31500 and
            all(activity[k] == 0 for k in ("model_calls", "prior_calls", "optimizer_calls", "journal_record_reads",
                                          "closed_form_reference_evaluations", "observation_archive_opens")),
            "Original reporting work scope differs")
        self.check_resources()

    def decode(self):
        self.stage = "saved_CSV_only_decode"
        import numpy as np
        self.np = np
        n = LIMITS["saved_rows"]
        self.index = np.empty(n, dtype=np.int64)
        self.source_time, self.time_s = np.empty(n), np.empty(n)
        self.x, self.physical = np.empty((n, 16)), np.empty((n, 16))
        self.current, self.reference = np.empty((n, 5)), np.full((n, 5), np.nan)
        self.static_truth = np.empty(16)
        self.flags, self.work = np.empty((n, 5), dtype=np.int64), np.empty((n, 6), dtype=np.int64)
        self.costs, self.slacks = np.empty((n, 3)), np.empty((n, 2))
        original = [q["name"] for q in self.plan["original_quantities"]]
        current = [q["name"] for q in self.plan["current_quantities"]]
        names = ["next_index", "source_elapsed_s", "decoded_elapsed_s"] + ["entering_x_"+str(j) for j in range(16)]
        for name in original+current: names += [name+"_estimate", name+"_truth", name+"_signed_error"]
        tail = ["likelihood_cost", "prior_cost", "total_cost", "min_support_slack", "min_endpoint_slack",
                "flags", "search_stop_reason", "last_fraction", "accepted_steps_in_block", "phase_and_flags", *WORK]
        names += tail
        with gzip.open(self.csv_path, "rt", newline="") as stream:
            rows = csv.DictReader(stream)
            require(rows.fieldnames == names, "Saved CSV column schema differs")
            for k, row in enumerate(rows):
                require(k < n and None not in row and all(value is not None for value in row.values()), "Malformed/extra saved CSV row")
                self.index[k] = int(row["next_index"])
                require(self.index[k] == 16*k, "Saved CSV chronology differs")
                self.source_time[k], self.time_s[k] = float(row["source_elapsed_s"]), float(row["decoded_elapsed_s"])
                self.x[k] = [float(row["entering_x_"+str(j)]) for j in range(16)]
                for j, name in enumerate(original):
                    a, b, e = (float(row[name+suffix]) for suffix in ("_estimate", "_truth", "_signed_error"))
                    require(all(math.isfinite(v) for v in (a,b,e)) and e == a-b, "Saved original error arithmetic differs")
                    self.physical[k,j] = a
                    if k == 0: self.static_truth[j] = b
                    require(b == self.static_truth[j], "Saved static reference changed across snapshots")
                for j, name in enumerate(current):
                    a = float(row[name+"_estimate"])
                    require(math.isfinite(a), "Nonfinite current estimate")
                    self.current[k,j] = a
                    if row[name+"_truth"] != "":
                        b, e = float(row[name+"_truth"]), float(row[name+"_signed_error"])
                        require(math.isfinite(b) and math.isfinite(e) and e == a-b, "Saved current error arithmetic differs")
                        self.reference[k,j] = b
                    else: require(row[name+"_signed_error"] == "", "Unavailable truth has an error")
                self.costs[k] = [float(row[key]) for key in tail[:3]]
                self.slacks[k] = [float(row[key]) for key in tail[3:5]]
                self.flags[k] = [int(row[key]) for key in tail[5:10]]
                self.work[k] = [int(row[key]) for key in WORK]
                require(0 <= self.flags[k,1] <= 7 and -1 <= self.flags[k,2] <= 7 and self.flags[k,3] in (0,1), "Saved search flags differ")
                self.counts["saved_CSV_rows"] += 1
        require(self.counts["saved_CSV_rows"] == n and all(np.isfinite(a).all() for a in
            (self.x,self.physical,self.current,self.source_time,self.time_s,self.costs,self.slacks)), "Incomplete/nonfinite saved CSV")
        require(np.isfinite(self.reference[:,0]).all() and np.isfinite(self.reference[0]).all() and
            np.isnan(self.reference[1:,1:]).all(), "Saved missing-journal reference scope differs")
        require((self.physical[:,:6] > 0).all() and (np.diff(self.source_time) > 0).all() and
            (np.diff(self.time_s) > 0).all(), "Saved physical/time domain differs")
        # The primary capture is already validated; compare CSV endpoints and counters to its retained rows.
        for k, snapshot in ((0,self.gate["result"]["trace"]["initial"]), (-1,self.gate["result"]["trace"]["final_snapshot"])):
            require(self.x[k].tolist() == snapshot["x"] and self.current[k].tolist() ==
                [snapshot["endpoint"]["SOC"],*snapshot["endpoint"]["v_V"],snapshot["endpoint"]["h"]] and
                self.work[k].tolist() == [snapshot["counts"][key] for key in WORK], "CSV endpoint differs from closed primary")
        self.check_resources()

    def at(self, k):
        return {"next_index": int(self.index[k]), "source_elapsed_s": float(self.source_time[k]),
                "decoded_elapsed_s": float(self.time_s[k])}

    def stats(self, estimates, references, relative=False):
        np = self.np
        ref = np.broadcast_to(references, estimates.shape)
        error = 100.*(estimates/ref-1.) if relative else estimates-ref
        good = np.isfinite(error); chosen = np.flatnonzero(good & (self.index > 0))
        value = {"reference_count_all": int(good.sum()), "reference_count_postinitial": int(len(chosen)),
            "initial_error": float(error[0]) if good[0] else None, "final_error": float(error[-1]) if good[-1] else None,
            "initial_estimate": float(estimates[0]), "final_estimate": float(estimates[-1]),
            "initial_reference": float(ref[0]) if math.isfinite(ref[0]) else None,
            "final_reference": float(ref[-1]) if math.isfinite(ref[-1]) else None,
            "exactly_unchanged_adjacent_estimate_count": int((estimates[1:]==estimates[:-1]).sum()),
            "unchanged_count_is_not_convergence": True, "postinitial": None}
        if len(chosen):
            e = error[chosen]
            lo,hi,ab = int(chosen[np.argmin(e)]),int(chosen[np.argmax(e)]),int(chosen[np.argmax(np.abs(e))])
            value["postinitial"] = {"minimum_signed": {"value":float(error[lo]),**self.at(lo)},
                "maximum_signed": {"value":float(error[hi]),**self.at(hi)},
                "maximum_absolute": {"value":float(abs(error[ab])),"signed":float(error[ab]),**self.at(ab)},
                "mean_absolute": math.fsum(abs(float(v)) for v in e)/len(e),
                "RMS": math.sqrt(math.fsum(float(v)**2 for v in e)/len(e))}
        return value

    def target(self, error, threshold):
        np = self.np; mask = np.isfinite(error) & (np.abs(error) <= threshold)
        hits = np.flatnonzero(mask & (self.index>0)); bad = np.flatnonzero(~mask & (self.index>0))
        tail = int(bad[-1])+1 if len(bad) else 1
        return {"inclusive_limit":threshold,"initial_prior_passes":bool(mask[0]),"postinitial_pass_count":int(mask[1:].sum()),
            "postinitial_points":31500,"final_passes":bool(mask[-1]),"first_saved_hit":self.at(int(hits[0])) if len(hits) else None,
            "first_all_remaining_saved_points_pass":self.at(tail) if tail<len(mask) else None,
            "interpretation":"Finite saved-grid screen only; no between-snapshot or eventual-convergence assertion."}

    def summarize(self):
        self.stage = "saved_CSV_statistics"
        np = self.np; original, current = [],[]
        for j,spec in enumerate(self.plan["original_quantities"]):
            row = {**spec,"native_error":self.stats(self.physical[:,j],self.static_truth[j])}
            if j<=10 and self.static_truth[j]>0: row["relative_percent_error"]=self.stats(self.physical[:,j],self.static_truth[j],True)
            original.append(row)
        for j,spec in enumerate(self.plan["current_quantities"]):
            current.append({**spec,"native_error":self.stats(self.current[:,j],self.reference[:,j])})
        q_error = 100.*(self.physical[:,5]/self.static_truth[5]-1.)
        z_error = 100.*(self.current[:,0]-self.reference[:,0])
        requirements = self.plan["point_error_requirements"]
        targets = {"Q_absolute_relative_percent":{key:self.target(q_error,value) for key,value in requirements["Q_absolute_relative_percent"].items()},
            "current_SOC_absolute_pp":{key:self.target(z_error,value) for key,value in requirements["current_SOC_absolute_pp"].items()}}
        def point(k):
            return {**self.at(k),"physical_parameters":self.physical[k].tolist(),"current_state":self.current[k].tolist(),
                "current_truth":[None if not math.isfinite(v) else float(v) for v in self.reference[k]],
                "Q_error_percent":float(q_error[k]),"current_SOC_error_pp":float(z_error[k])}
        self.summary = {"schema":"mumble_live_anchor_reporting_v1","status":"completed_via_saved_CSV_continuation",
            "valid_only_with_completed_continuation_receipt":True,"inference_status":"completed",
            "source_revision":self.gate["source_revision"],"source_id":self.gate["source_id"],
            "snapshot_count":31501,"grid":"0,16,...,504000; no interpolation","initial_prior_reported_separately":True,
            "time":{"axis":"saved original source elapsed time","final_source_s":float(self.source_time[-1]),
                "final_decoded_s":float(self.time_s[-1]),"max_abs_decoded_minus_source_s":float(np.max(np.abs(self.time_s-self.source_time)))},
            "original_quantities":original,"current_quantities":current,"static_reference":self.static_truth.tolist(),
            "current_reference_availability":{"SOC":"all_saved_points_from_previously_decoded_scalar_truth",
                "v1_v2_v3_h":"initial_only_local_journal_unavailable","journal_used":False,
                "reference_model":"original physical source, not redefined for decoded input"},
            "targets":targets,"initial":point(0),"final":point(-1),
            "fixed_checkpoint_points":[point(index//16) for index in (252000,294000,504000)],
            "final_capacity_error_percent":float(q_error[-1]),"final_current_SOC_error_pp":float(z_error[-1]),
            "search":{"stop_reason_counts":{str(key):{"name":name,"postinitial_count":int((self.flags[1:,1]==key).sum())} for key,name in STOP.items()},
                "accepted_blocks":int(self.flags[1:,3].sum()),"blocks_without_accepted_step":int((self.flags[1:,3]==0).sum()),
                "final_work_counts":dict(zip(WORK,map(int,self.work[-1]))),
                "flags_histogram":{str(int(v)):int((self.flags[:,0]==v).sum()) for v in np.unique(self.flags[:,0])},
                "phase_flags_histogram":{str(int(v)):int((self.flags[:,4]==v).sum()) for v in np.unique(self.flags[:,4])}},
            "interpretation":self.plan["interpretation"],"coverage_validated":False,"candidate_promoted":False,
            "model_audits":"Separate frozen fixed-candidate audits; not invoked or inferred by this reporting continuation.",
            "closure":{"outer":self.outer_id,"inner":identity(self.root/EXP/"attempt001/receipt.json"),
                "result":identity(self.root/EXP/"attempt001/result.json"),"trace_commit_identity":self.gate["trace_commit_identity"],
                "both_capture_copies_verified":True,"observations_reopened":False},
            "original_reporting":{"status":"failed_preserved","receipt_path":EXP+"/reporting001/reporting_receipt.json",
                "receipt":{"bytes":6851,"sha256":FAILED_SHA},"errors":self.failed["errors"],
                "activity":self.failed["reporting_activity"],"resources":self.failed["resources_before_final_encoding"],
                "closed_output_bytes":self.failed["closed_output_bytes_including_receipt"]},
            "trajectory":{"path":EXP+"/reporting001/trajectory.csv.gz","bytes":14400050,"sha256":CSV_SHA,
                "all_saved_rows_retained":True,"new_truth_reads":0},
            "figures":[{"stem":stem,"path_prefix":EXP+"/reporting001/"+stem,
                "source":"complete preserved original figure pair","PNG":self.failed["files"][stem+".png"],
                "SVG":self.failed["files"][stem+".svg"]} for stem in STEMS],
            "continuation_activity":dict(self.counts)}

    def figure(self):
        self.stage = "categorical_figure_only"
        # New cache is temporary, not part of the estimator or retained output.
        import tempfile
        cache = tempfile.TemporaryDirectory(prefix="mumble-report-mpl-")
        os.environ["MPLCONFIGDIR"] = cache.name
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        self.plt = plt
        plt.rcParams.update({"font.family":"DejaVu Sans","font.size":10,"axes.spines.top":False,
            "axes.spines.right":False,"axes.grid":True,"grid.alpha":.2,"path.simplify":False,"svg.fonttype":"none"})
        fig,axes = plt.subplots(2,1,figsize=(15,8))
        x = self.source_time/60.
        axes[0].plot(x,self.work[:,5],color="#1665A7",linewidth=1.2)
        axes[0].set_ylabel("Cumulative accepted steps")
        axes[0].set_title("Saved acceptance count; a plateau is not a convergence test",loc="left")
        axes[0].ticklabel_format(axis="y",style="plain",useOffset=False)
        axes[1].plot(x,self.flags[:,1],".",color="#1665A7",markersize=1.7)
        axes[1].set_yticks(list(STOP),[str(k)+": "+v.replace("_"," ") for k,v in STOP.items()],fontsize=8)
        axes[1].set_ylabel("Per-block stop reason")
        # Deliberately do not apply ScalarFormatter operations to the categorical axis.
        for ax in axes:
            ax.set_xlabel("Source elapsed time (min)"); ax.set_xlim(0,240)
        fig.suptitle("Finite per-block search behavior",fontsize=17,y=.995)
        fig.text(.01,.006,"Public initialization · all 31,501 saved block endpoints · full four-hour source timeline · no convergence or interval claim",fontsize=9,color="#444444")
        fig.tight_layout(rect=(0,.027,1,.945))
        fig.savefig(self.output/"optimization_trace.png",dpi=220)
        fig.savefig(self.output/"optimization_trace.svg")
        plt.close(fig)
        self.summary["figures"].append({"stem":"optimization_trace","path_prefix":EXP+"/reporting_continuation001/optimization_trace",
            "source":"saved-CSV-only continuation","PNG":identity(self.output/"optimization_trace.png"),
            "SVG":identity(self.output/"optimization_trace.svg"),"snapshots_supplied":31501,"smoothing":False})
        self.summary["environment"]={"python":sys.version,"platform":platform.platform(),"numpy":self.np.__version__,
            "matplotlib":matplotlib.__version__,"backend":matplotlib.get_backend()}
        cache.cleanup()
        self.check_resources()

    def finish(self):
        self.stage = "unchanged_saved_input_closure"
        for row in self.inputs.values():
            require(identity(row["path"]) == {k:row[k] for k in ("bytes","sha256")},"Continuation input changed")
        self.run.validate_closed_run(self.root,self.outer_id,read_observations=False)
        self.check_resources()
        self.summary["inputs"] = list(self.inputs.values())
        self.summary["resources_before_summary_encoding"] = self.resources()
        write_json(self.output/"summary.json",self.summary)

    def receipt(self):
        if self.plt is not None: self.plt.close("all")
        try: self.check_resources()
        except Exception as error: self.errors.append({"stage":"final_resources","type":type(error).__name__,"message":str(error)})
        files={p.relative_to(self.output).as_posix():identity(p) for p in sorted(self.output.rglob("*")) if p.is_file()}
        receipt={"schema":SCHEMA,"status":"failed" if self.errors else "completed","stage":self.stage,"errors":self.errors,
            "limits":LIMITS,"activity":self.counts,"original_reporting_status":"failed_preserved",
            "original_reporting_receipt":{"bytes":6851,"sha256":FAILED_SHA},
            "original_reporting_counts":None if not hasattr(self,"failed") else self.failed["reporting_activity"],
            "inputs":list(self.inputs.values()),"files":files,"resources_before_final_encoding":self.resources(),
            "resource_scope":"Own process through final receipt assembly; final encode/write/print latency excluded.",
            "closed_output_bytes_including_receipt":0,"inference_or_reference_rerun":False,"coverage_validated":False}
        base=sum(value["bytes"] for value in files.values())
        for _ in range(8):
            size=base+len(encode(receipt))
            if size==receipt["closed_output_bytes_including_receipt"]: break
            receipt["closed_output_bytes_including_receipt"]=size
        require(receipt["closed_output_bytes_including_receipt"]==base+len(encode(receipt)),"Receipt size did not stabilize")
        if receipt["closed_output_bytes_including_receipt"]>LIMITS["output_bytes"]:
            receipt["status"]="failed";receipt["failure_only_emergency_closure"]=True
            receipt["errors"].append({"stage":"closure","type":"OutputCap","message":"Continuation output cap exceeded"})
            for _ in range(8): receipt["closed_output_bytes_including_receipt"]=base+len(encode(receipt))
        write_json(self.output/"receipt.json",receipt)
        print(json.dumps({"schema":SCHEMA,"status":receipt["status"],"receipt":identity(self.output/"receipt.json"),
            "summary":identity(self.output/"summary.json") if (self.output/"summary.json").exists() else None,
            "activity":self.counts},sort_keys=True,allow_nan=False))
        return 0 if receipt["status"]=="completed" else 1


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",default=str(ROOT));parser.add_argument("--outer-sha256",required=True)
    parser.add_argument("--failed-report-sha256",required=True);parser.add_argument("--review",required=True)
    report=Continuation(parser.parse_args())
    def timeout(signum,frame): raise TimeoutError("Continuation wall cap reached")
    signal.signal(signal.SIGALRM,timeout);signal.setitimer(signal.ITIMER_REAL,LIMITS["wall_s"])
    try:
        report.gate_inputs();report.decode();report.summarize();report.figure();report.finish()
    except Exception as error:
        report.errors.append({"stage":report.stage,"type":type(error).__name__,"message":str(error)[:4096]})
    finally: signal.setitimer(signal.ITIMER_REAL,0)
    return report.receipt()


if __name__=="__main__":
    raise SystemExit(main())
