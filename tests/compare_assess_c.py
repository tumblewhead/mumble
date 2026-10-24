#!/usr/bin/env python3
"""Compare allocation-free C assessment with Python on stored fit results.

No optimization is run. The C driver receives only fitted coordinates and the
likelihood Gram matrix, never physical truth. Tolerances below are explicit.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
from assess import assess_result


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=ROOT/"results"/"assessment_c_review.json")
    args=parser.parse_args()
    records=[]
    for name in ("streaming_results.json","tail_only_result.json"):
        path=ROOT/"results"/name
        if path.is_file():
            for record in json.loads(path.read_text())["records"]:
                if record.get("result"):
                    records.append((name,record))
    if not records:raise RuntimeError("No stored fits to assess")
    lines=[]
    for _,record in records:
        f=record["result"]
        linked=bool(f.get("has_current_soc",False) or f.get("fixed_current_soc") is not None)
        conditioned=bool(f.get("fixed_mask",0) or f.get("fixed_alpha_mask",0) or linked)
        header=[f["modes"],f["status"],f["active_linear_constraints"],f["active_outer_bounds"],
                f.get("unexcited_theta_mask",0),int(conditioned),int(linked),f["charge_Ah"]]
        values=header+f["theta"]+f["alpha"]+f["coordinate_scales"]+f["joint_normal"]
        lines.append(" ".join(format(x,".17g") for x in values))
    payload="\n".join(lines)+"\n"
    with tempfile.TemporaryDirectory(prefix="scm_assessment_compare_") as folder:
        binary=Path(folder)/"test_assess_c"
        command=["cc","-std=c99","-O3","-Wall","-Wextra","-Wpedantic","-I",str(ROOT/"include"),
                 str(ROOT/"src"/"scm_assess.c"),str(ROOT/"tests"/"test_assess_c.c"),"-lm","-o",str(binary)]
        built=subprocess.run(command,text=True,capture_output=True,check=True)
        unit=subprocess.run([str(binary)],text=True,capture_output=True,check=True)
        start=time.perf_counter()
        driver=subprocess.run([str(binary),"--driver"],input=payload,text=True,capture_output=True,check=True)
        elapsed=time.perf_counter()-start
        outputs=[json.loads(line) for line in driver.stdout.splitlines()]
    if len(outputs)!=len(records):raise RuntimeError("Driver result count mismatch")
    # Availability/status/rank must agree exactly. Numeric tolerances cover
    # alternative symmetric eigensolvers applied to a conditioned Gram matrix.
    range_rtol,range_atol,sd_rtol,null_atol=1e-6,1e-10,1e-5,2e-8
    failures=[];target_count=0;max_range_abs=0.;max_range_relative=0.;max_sd_relative=0.;max_null_abs=0.;max_point_abs=0.
    for (source,record),actual in zip(records,outputs):
        expected=assess_result(record["result"])
        ident={"source":source,"case_id":record["case_id"],"checkpoint_s":record.get("checkpoint_s")}
        if actual.get("error") or actual["rank"]!=expected["numerical_rank"] or actual["matrix_invalid"]!=expected["matrix_invalid"]:
            failures.append({**ident,"kind":"rank_or_matrix_status","actual":actual.get("rank"),"expected":expected["numerical_rank"]})
            continue
        for name,p in expected["parameters"].items():
            target_count+=1;c=actual["targets"][name]
            if (c["point"] is None)!=(p["point"] is None):
                failures.append({**ident,"target":name,"kind":"point_availability"})
            elif c["point"] is not None:
                max_point_abs=max(max_point_abs,abs(c["point"]-p["point"]))
                if not math.isclose(c["point"],p["point"],rel_tol=1e-12,abs_tol=1e-12):
                    failures.append({**ident,"target":name,"kind":"point","actual":c["point"],"expected":p["point"]})
            for field in ("status","passes_local_precision","eligible_for_profile_check"):
                if c[field]!=p[field]:failures.append({**ident,"target":name,"kind":field,"actual":c[field],"expected":p[field]})
            available=p["range_kind"]=="untruncated_local_two_sigma"
            if c["has_local_range"]!=available:failures.append({**ident,"target":name,"kind":"range_availability"})
            for cv,pv in zip(c["local_range"],p["local_range"]):
                error=abs(cv-pv);relative=error/max(abs(pv),range_atol)
                max_range_abs=max(max_range_abs,error);max_range_relative=max(max_range_relative,relative)
                if not math.isclose(cv,pv,rel_tol=range_rtol,abs_tol=range_atol):
                    failures.append({**ident,"target":name,"kind":"range","actual":cv,"expected":pv})
            for field in ("local_standard_deviation","local_halfwidth","relative_halfwidth"):
                cv,pv=c[field],p[field]
                if (cv is None)!=(pv is None):failures.append({**ident,"target":name,"kind":field+"_availability"})
                elif cv is not None:
                    relative=abs(cv-pv)/max(abs(pv),1e-15);max_sd_relative=max(max_sd_relative,relative)
                    if not math.isclose(cv,pv,rel_tol=sd_rtol,abs_tol=1e-12):
                        failures.append({**ident,"target":name,"kind":field,"actual":cv,"expected":pv})
            error=abs(c["null_projection"]-p["null_projection"]);max_null_abs=max(max_null_abs,error)
            if error>null_atol:failures.append({**ident,"target":name,"kind":"null_projection","actual":c["null_projection"],"expected":p["null_projection"]})
    report={
        "schema":"scm_c_assessment_comparison_v1","optimizer_rerun":False,"truth_supplied_to_assessment":False,
        "stored_fit_count":len(records),"target_comparisons":target_count,"failures":failures,
        "status_rank_and_availability_match":not any(f["kind"] in ("rank_or_matrix_status","status","passes_local_precision","eligible_for_profile_check","range_availability","point_availability") for f in failures),
        "tolerances":{"range_relative":range_rtol,"range_absolute":range_atol,"sd_halfwidth_relative":sd_rtol,"null_projection_absolute":null_atol},
        "max_range_absolute_difference":max_range_abs,"max_range_relative_difference":max_range_relative,
        "max_point_absolute_difference":max_point_abs,
        "max_sd_halfwidth_relative_difference":max_sd_relative,"max_null_projection_absolute_difference":max_null_abs,
        "C_unit_test":json.loads(unit.stdout),"compiler_diagnostics":built.stderr,
        "driver_total_wall_s":elapsed,"driver_timing_scope":"Includes process startup, text parsing and JSON printing; not isolated kernel time or MCU latency.",
        "source_sha256":{str(p.relative_to(ROOT)):sha(p) for p in [ROOT/"include"/"scm_assess.h",ROOT/"src"/"scm_assess.c",ROOT/"tests"/"test_assess_c.c",Path(__file__).resolve(),ROOT/"tools"/"assess.py"]},
        "input_sha256":{name:sha(ROOT/"results"/name) for name in ("streaming_results.json","tail_only_result.json") if (ROOT/"results"/name).is_file()},
        "caveat":"Local diagnostic only. Null directions retain supports; provisional local ranges are not nonlinear confidence certificates. Full inference core remains a host replay estimator."
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    print(json.dumps({k:report[k] for k in ("stored_fit_count","target_comparisons","status_rank_and_availability_match","max_range_absolute_difference","max_sd_halfwidth_relative_difference","max_null_projection_absolute_difference")},allow_nan=False))
    print(json.dumps({"failure_count":len(failures),"report":str(args.output)}))
    return 1 if failures else 0


if __name__=="__main__":raise SystemExit(main())
