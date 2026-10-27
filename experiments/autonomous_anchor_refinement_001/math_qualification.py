#!/usr/bin/env python3
"""Finite fabricated algebra/proposal qualification; no canonical inputs.

Exactly four optimizer invocations are declared: dense interior, physical box,
curved SOC support, artificial step box. All other checks are saved algebra or
worker orchestration without an optimizer. A failure is preserved, not retried.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import resource
import sys
import tempfile
import time
import traceback
from unittest.mock import patch


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    return module


def qualify(output:Path):
    wall,cpu=time.monotonic(),time.process_time()
    base=Path(__file__).resolve().parent
    if output.exists():
        raise FileExistsError("qualification destination already exists; no overwrite")
    if any(os.environ.get(k)!="1" for k in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS")):
        raise ValueError("set single-thread environment before qualification")
    am=load("_qual_anchor_math",base/"anchor_math.py"); np=am.np
    worker=load("_qual_anchor_worker",base/"proposal_worker.py")
    source_before={n:hashlib.sha256((base/n).read_bytes()).hexdigest() for n in ("anchor_math.py","proposal_worker.py","math_qualification.py")}
    checks=[];cases=[];starts=[];prior_calls=0;worker_prior_calls=0
    def check(name,condition,**detail):
        checks.append({"name":name,"passed":bool(condition),**detail})
    def prior(x):
        nonlocal prior_calls
        prior_calls+=1
        return am.prior_at(x)
    def block(x,G,g,cost,prefix):
        n=prefix["records"]
        return {"schema":am.EVALUATOR_SCHEMA,"status":"ok","dimension":16,
            "coordinate_names":am.EVALUATOR_COORDINATES,"sigma_V":.001,"gram_layout":am.GRAM_LAYOUT,
            "charge_extrema_include_initial_zero":True,"x":list(x),"cost":float(cost),
            "gradient":list(g),"gram":am.rm.pack_lower(G),"prefix_requested":n,
            "records_read":n,"records_accumulated":n,"model_step_calls":n,"model_predict_calls":n,
            "source_generations":0,"learner_ingests":0,"fit_calls":0,"truth_reads":0,
            "charge_min_Ah":prefix["charge_min_Ah"],"charge_max_Ah":prefix["charge_max_Ah"],
            "absolute_summand_scales":{"cost":abs(float(cost))}}
    a=am.rm.PUBLIC_MEAN.copy();D=am.rm.PUBLIC_SD
    cached=prior(a);p=am.policy()
    # Dense deterministic Gram, independent of any data or previous solution.
    A=np.array([[math.sin((i+1)*(j+2))*.08 for j in range(16)] for i in range(16)])
    scaled_G=A.T@A+np.eye(16)*.5
    G=scaled_G/np.outer(D,D)
    B=G+np.diag(am.rm.KERNEL_PRECISION)
    M=B*np.outer(D,D)
    point_limit=64.*math.sqrt(am.EPS)
    prefix0={"records":1024,"charge_min_Ah":0.,"charge_max_Ah":0.}
    designs=[]
    target=np.array([.04*math.sin(i+1) for i in range(16)])
    designs.append(("dense_interior",target.copy(),prefix0,np.zeros(16)))
    target=np.zeros(16);target[6]=-a[6]/D[6]
    force=np.zeros(16);force[6]=1.
    designs.append(("physical_lower_R0",target.copy(),prefix0,force))
    prefix_soc={"records":1024,"charge_min_Ah":0.,"charge_max_Ah":.03}
    target=np.zeros(16);target[11]=(.5-a[11])/D[11]
    point=a+D*target
    path_jac=am.rm.Support(0.,.03).path(point)[1][0]*D/D[11]
    designs.append(("curved_SOC_lower",target.copy(),prefix_soc,.25*path_jac))
    target=np.zeros(16);target[0]=1.
    force=np.zeros(16);force[0]=-1.
    designs.append(("artificial_upper_step_box",target.copy(),prefix0,force))
    first=None
    for name,target,prefix,force in designs:
        total_scaled_gradient=-M@target+force
        like_gradient=total_scaled_gradient/D-np.array(cached["gradient"])
        payload=block(a,G,like_gradient,100.,prefix)
        def started(event,name=name):
            starts.append({"name":name,"event":event})
        try:
            with (patch.object(am,"prior_at",side_effect=AssertionError("prior forbidden inside proposal")) as pg1,
                  patch.object(am.rm,"prior_cost_gradient_hessian",side_effect=AssertionError("mixture forbidden inside proposal")) as pg2):
                result=am.propose(payload,prefix,cached,p,started)
            error=float(np.max(np.abs((np.array(result["candidate_x"])-a)/D-target)))
            check(name+":known_point",error<=point_limit,scaled_max_error=error,limit=point_limit)
            check(name+":feasible_descent",result["feasibility"]["strictly_feasible"] and result["step_box_feasible"] and result["direction_admitted"])
            count=result["evaluation_counts"]
            check(name+":finite_counted_work",0<count["combined_objective_gradient"]<=256 and count["iterations"]<=100 and count["final_verification"]==1)
            check(name+":no_mixture_inside_proposal",pg1.call_count==0 and pg2.call_count==0)
            check(name+":metric_exact",np.array_equal(am.rm.unpack_lower(result["metric_lower"]),B))
            if name=="artificial_upper_step_box":
                check(name+":actual_bound_KKT",result["KKT"]["actual_intersected_upper_u"][0]==1. and result["KKT"]["passed"],KKT=result["KKT"])
                check(name+":activity_distinct","log_tau1" in result["step_box_active_coordinates"] and "upper:log_tau1" not in result["physical_support_active_names"])
            if name=="dense_interior":first=(payload,prefix,result)
            cases.append({"name":name,"known_scaled_optimum":target.tolist(),"scaled_point_error":error,
                          "proposal":result,"raw_return_status_retained":True})
        except Exception as error:
            check(name+":returned",False,exception=repr(error),traceback=traceback.format_exc())
            cases.append({"name":name,"exception":repr(error)})
    check("exactly_four_declared_optimizer_starts",len(starts)==4,starts=len(starts))

    # Unmodified Cholesky must stop an invalid positive-diagonal indefinite Gram.
    badG=np.eye(16);badG[0,1]=badG[1,0]=1e6
    guarded=am.propose(block(a,badG,np.zeros(16),1.,prefix0),prefix0,cached,p,
                       lambda _:check("indefinite_metric_must_not_start_optimizer",False))
    check("metric_failure_not_repaired",guarded["status"]=="metric_not_positive_definite" and not guarded["direction_admitted"] and guarded["evaluation_counts"]["combined_objective_gradient"]==0)

    # Full-step identity: a+(b-a) would lose this representable endpoint.
    av=a.copy();bv=a.copy();av[6]=1.;bv[6]=2.**-54
    check("full_step_preserves_returned_bits",am._same_vector(am.trial_vector(av,bv,1.),bv) and av[6]+(bv[6]-av[6])!=bv[6])
    for alpha in am.ALPHAS:
        x=am.trial_vector(av,bv,alpha)
        check(f"feasible_chord_{alpha}",am.rm.Support(0.,0.).diagnostics(x)["strictly_feasible"])
    negative=a.copy();negative[6]=-am.ETA
    check("negative_slack_not_admitted",not am.rm.Support(0.,0.).diagnostics(negative)["strictly_feasible"])
    boundary_rounding=[]
    for sign in [-1.,1.]:
        represented=a+D*sign
        ratios=(represented-a)/D
        boundary_rounding.append({"solver_u":sign,"represented_x":represented.tolist(),
            "recomputed_direction_ratio":ratios.tolist(),
            "strict_step_rejections":[am.rm.COORDINATES[i] for i in range(16) if abs(ratios[i])>1.]})
    check("actual_step_fixture_strictly_checked",all(c.get("proposal",{}).get("step_box_feasible",False) for c in cases))

    # Reserved final verification remains counted when the normal budget stops.
    obj=am._Objective(np.ones(16),np.eye(16),1.,limit=3)
    obj.fun(np.zeros(16));obj.fun(np.ones(16));obj.hess(np.zeros(16))
    try:
        obj.fun(np.zeros(16));limited=False
    except am._EvaluationLimit:limited=True
    obj.evaluate(np.zeros(16),final=True)
    check("final_verification_slot_reserved",limited and obj.calls==3 and obj.final_calls==1 and obj.hessian_requests==1)

    assessments=[]
    if first:
        current,prefix,proposal=first
        trial_x=proposal["candidate_x"]
        for label,cost in [("positive",0.),("negative",200.)]:
            trial=block(trial_x,G,np.zeros(16),cost,prefix)
            prior_calls+=1
            result=am.assess_trial(current,cached,trial,proposal,1.,prefix,p)
            check("Armijo_"+label,result["accepted"]==(label=="positive"))
            assessments.append({"case":label,"assessment":result})
        # Use the already returned prior value only to construct an equal-cost
        # fabricated observation objective, never an inference point/threshold.
        equal_cost=math.fsum([current["cost"],cached["cost"],-assessments[0]["assessment"]["trial_prior"]["cost"]])
        prior_calls+=1
        result=am.assess_trial(current,cached,block(trial_x,G,np.zeros(16),equal_cost,prefix),proposal,1.,prefix,p)
        check("Armijo_unresolved_equal_cost_rejected",not result["accepted"])
        assessments.append({"case":"equal_computed_cost","assessment":result})
        # Independent inherited allowance oracle uses the original u=2^-53.
        n=prefix["records"];ku=(8*n+64)*2.**-53;g1=ku/(1.-ku);ku=8*2.**-53;g2=ku/(1.-ku)
        expected=g1*(100.+equal_cost)+g2*math.fsum([100.,equal_cost,abs(cached["cost"]),abs(result["trial_prior"]["cost"])])
        check("inherited_cost_rule_exact",result["cost_arithmetic_allowance"]==expected)
        mismatch=block(trial_x,G,np.zeros(16),0.,prefix);mismatch["x"]=a.tolist()
        try:
            with patch.object(am,"prior_at",side_effect=AssertionError("must reject before prior")) as guard:
                am.assess_trial(current,cached,mismatch,proposal,1.,prefix,p)
            rejected=False
        except ValueError:rejected=True
        check("wrong_trial_identity_rejected_before_prior",rejected and guard.call_count==0)

    # Worker receipt/path/parser checks are fabricated and invoke no optimizer.
    with tempfile.TemporaryDirectory(prefix="mumble_anchor_math_") as td:
        t=Path(td);request=t/"request.json";out=t/"output"
        req={"schema":worker.REQUEST_SCHEMA,"action":"prior","x":a.tolist(),"policy":p}
        request.write_text(json.dumps(req,allow_nan=False))
        result,code=worker.run(request,out)
        worker_prior_calls+=result["counts"]["prior_evaluations"]
        check("worker_prior_once",code==0 and result["counts"]["prior_evaluations"]==1 and result["counts"]["optimizer_calls_started"]==0 and (out/"result.json").is_file())
        before=(out/"result.json").read_bytes()
        again,code=worker.run(request,out)
        check("worker_destination_no_overwrite",code!=0 and (out/"result.json").read_bytes()==before)
        for name,data in [("duplicate",b'{"x":1,"x":2}'),("nonfinite",b'{"x":1e999}'),("NaN",b'{"x":NaN}')]:
            try:worker.strict_json(data);bad=False
            except ValueError:bad=True
            check("strict_parser_"+name,bad)
        req["observation_path"]="forbidden.bin";request.write_text(json.dumps(req))
        invalid,code=worker.run(request,t/"invalid")
        check("unknown_path_field_rejected",code!=0 and invalid["counts"]["prior_evaluations"]==0 and invalid["counts"]["optimizer_calls_started"]==0)
    check("source_unchanged",all(hashlib.sha256((base/n).read_bytes()).hexdigest()==h for n,h in source_before.items()))
    result={"schema":"mumble_autonomous_anchor_math_qualification_v1",
        "status":"passed" if all(c["passed"] for c in checks) else "failed",
        "scope":"Fabricated quadratic/support/worker cases only. No canonical observations, old results, truth, evaluator or model calls.",
        "configuration":am.configuration(),"source_sha256":source_before,
        "checks":checks,"check_count":len(checks),"failed_count":sum(not c["passed"] for c in checks),
        "optimizer_invocations":len(starts),"optimizer_started_events":starts,
        "cases":cases,"assessments":assessments,"represented_step_boundary_diagnostic":boundary_rounding,
        "counts":{"real_optimizer_calls":len(starts),"direct_prior_evaluations":prior_calls,
                  "worker_prior_evaluations":worker_prior_calls,"new_model_calls":0,"canonical_data_reads":0,"truth_reads":0},
        "limits":"Inner numerical status and KKT retained exactly; finite accurate fixtures do not certify global discovery or canonical convergence.",
        "resources":{"wall_s_before_encoding":time.monotonic()-wall,"CPU_s_before_encoding":time.process_time()-cpu,
                     "own_peak_RSS_bytes":int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)*1024}}
    data=(json.dumps(result,indent=2,allow_nan=False)+"\n").encode()
    if len(data)>1048576:raise ValueError("qualification output exceeds1MiB")
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open("xb") as f:f.write(data);f.flush();os.fsync(f.fileno())
    return result


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args();result=qualify(args.output)
    print(json.dumps({"status":result["status"],"checks":result["check_count"],"failed":result["failed_count"],
                      "optimizer_calls":result["optimizer_invocations"],"output":str(args.output)},sort_keys=True))
    raise SystemExit(0 if result["status"]=="passed" else 1)
