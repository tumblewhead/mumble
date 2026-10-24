#!/usr/bin/env python3
"""Compare assessment-integrated CLI with the preserved campaign executable.

Uses the recorded fit options at three representative checkpoints, rebasing
executable and data paths to this checkout. Truth does not enter either process.
All numeric inference fields except CPU timing must remain identical. A separate
linked-chart invocation verifies withholding.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
CORE=["src/scm_estimator.c","src/scm_model.c","include/scm_estimator.h","include/scm_model.h"]


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command):
    start=time.perf_counter()
    p=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=60)
    if p.returncode:raise RuntimeError(f"CLI failed:{p.returncode}:{p.stderr}")
    return json.loads(p.stdout),time.perf_counter()-start


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=ROOT/"results/c_integration_review.json",
                        help="Receipt destination; use a new path to preserve the frozen study receipt.")
    args=parser.parse_args()
    source=ROOT/"results/streaming_results.json"
    stored=json.loads(source.read_text())
    before={"core_source_sha256_before":{p:stored["metadata"]["source_sha256_after"][p] for p in CORE}}
    old=ROOT/"build/scm_estimator_benchmark";new=ROOT/"build/scm_estimator"
    if not old.is_file():old=ROOT/"reference_binaries/scm_estimator_benchmark"
    if sha(old)!=stored["metadata"]["executable_sha256_after"]:raise RuntimeError("Preserved benchmark hash mismatch")
    first=stored["records"][0]["case_id"]
    checks=[];failures=[]
    ignored={"elapsed_cpu_s","basis_seconds"}
    for seconds in(10,600,2100):
        record=next(r for r in stored["records"] if r["case_id"]==first and r["checkpoint_s"]==seconds)
        old_command=list(record["command"]);old_command[0]=str(old)
        data_index=old_command.index("--data")+1
        old_command[data_index]=str(ROOT/"data"/f"{record['case_id']}.csv")
        new_command=list(old_command);new_command[0]=str(new)
        a,old_wall=run(old_command);b,new_wall=run(new_command)
        mismatches=[key for key in a if key not in ignored and a[key]!=b.get(key)]
        stored_mismatches=[key for key in record["result"] if key not in ignored and record["result"][key]!=a.get(key)]
        if mismatches or stored_mismatches:failures.append({"checkpoint_s":seconds,"old_new_mismatches":mismatches,"stored_old_mismatches":stored_mismatches})
        assessment=b.get("assessment",{})
        if assessment.get("implementation")!="C99" or not assessment.get("diagnostic_only") or assessment.get("coverage_certificate") is not False:
            failures.append({"checkpoint_s":seconds,"error":"Missing or incorrectly labeled C assessment"})
        selected={key:assessment.get("parameters",{}).get(key) for key in("Q_Ah","current_soc","gamma_minus")}
        checks.append({"checkpoint_s":seconds,"old_command":old_command,"new_command":new_command,
                       "inference_fields_identical":not mismatches,"preserved_executable_matches_stored_fit":not stored_mismatches,
                       "old_process_wall_s":old_wall,"new_process_wall_s":new_wall,
                       "optimizer_status":b["status"],"selected_assessment":selected})
    data=ROOT/"data"/"cell_a_35hz_s202610240.csv"
    linked_command=[str(new),"--data",str(data),"--case","linked_chart_integration_check","--method","full",
                    "--modes","3","--starts","1","--max-iter","5","--prefix","350","--fixed-current-soc",".75"]
    linked,_=run(linked_command)
    linked_assessment=linked["assessment"]
    rejected=(linked.get("has_current_soc") is True and linked.get("fixed_current_soc")==.75
              and linked_assessment["coordinate_chart_supported"] is False
              and all(t["status"]=="unresolved" and t["range_kind"]=="prior_support"
                      for t in linked_assessment["parameters"].values()))
    if not rejected:failures.append({"error":"Linked chart was not rejected as unrestricted uncertainty"})
    after={p:sha(ROOT/p) for p in CORE}
    unchanged=after==before["core_source_sha256_before"]
    if not unchanged:failures.append({"error":"Core numerical sources changed during integration"})
    report={"schema":"scm_c_assessment_integration_v1","failures":failures,
            "source_campaign_sha256":sha(source),"recorded_paths_rebased":True,
            "benchmark_executable":str(old.relative_to(ROOT)),"benchmark_executable_sha256":sha(old),
            "integrated_executable":"build/scm_estimator","integrated_executable_sha256":sha(new),
            "core_math_sources_unchanged":unchanged,"core_source_sha256_before":before["core_source_sha256_before"],
            "core_source_sha256_after":after,"representative_checks":checks,
            "linked_chart_check":{"command":linked_command,"all_targets_unresolved_with_support":rejected,
                                  "coordinate_chart_supported":linked_assessment["coordinate_chart_supported"],
                                  "optimizer_status":linked["status"]},
            "assessment_memory":{"caller_workspace_bytes":4224,"output_struct_bytes":2488,"options_bytes":56,
                                 "scope":"Reported host-ABI struct sizes; not whole-program or MCU stack high-water measurement."},
            "notes":["No 60-fit campaign rerun; recorded commands were copied and rebased without rewriting the source campaign.",
                     "Core numeric inference fields were compared exactly between the preserved benchmark and the current CLI.",
                     "CPU timing fields are deliberately excluded from equality; runtime varies with host conditions.",
                     "Finite C local uncertainty remains provisional and is not a confidence-coverage certificate."]}
    path=args.output;path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    print(json.dumps({"representative_fits":len(checks),"failures":len(failures),"core_math_sources_unchanged":unchanged,
                      "linked_chart_rejected":rejected,"benchmark_sha256":sha(old),"integrated_sha256":sha(new),"report":str(path)}))
    return 1 if failures else 0


if __name__=="__main__":raise SystemExit(main())
