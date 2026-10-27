#!/usr/bin/env python3
"""Isolated bounded JSON prior/proposal/admission child.

Only the request JSON and new output directory are CLI inputs. No model,
observation, historical-result or truth path is accepted in any action schema.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import resource
import sys
import time
import traceback

REQUEST_SCHEMA="mumble_autonomous_anchor_worker_request_v1"
RESULT_SCHEMA="mumble_autonomous_anchor_worker_result_v1"
MAX_REQUEST_BYTES=524288
MAX_OWN_OUTPUT_BYTES=524288
ACTION_FIELDS={
    "prior":{"schema","action","policy","x"},
    "propose":{"schema","action","policy","block","prior","prefix"},
    "assess":{"schema","action","policy","current_block","current_prior","trial_block","proposal","alpha","prefix"},
}


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _duplicates(pairs):
    out={}
    for key,value in pairs:
        if key in out:
            raise ValueError("duplicate JSON key")
        out[key]=value
    return out


def _float(token):
    value=float(token)
    if not math.isfinite(value):
        raise ValueError("nonfinite JSON float")
    return value


def _constant(token):
    raise ValueError("nonfinite JSON constant")


def strict_json(data):
    return json.loads(data,object_pairs_hook=_duplicates,parse_float=_float,parse_constant=_constant)


def _bounded_read(path,limit):
    with path.open("rb") as f:
        data=f.read(limit+1)
    if len(data)>limit:
        raise ValueError("request exceeds fixed byte cap")
    return data


def _safe(value):
    if isinstance(value,float) and not math.isfinite(value):
        return repr(value)
    if isinstance(value,dict):
        return {str(k):_safe(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):
        return [_safe(v) for v in value]
    return value


def _resources(wall,cpu):
    return {"wall_s_before_encoding":time.monotonic()-wall,"CPU_s_before_encoding":time.process_time()-cpu,
            "own_peak_RSS_bytes":int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)*1024}


def _fsync_directory(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def run(input_path:Path,output_dir:Path):
    wall,cpu=time.monotonic(),time.process_time()
    counts={"prior_evaluations":0,"prior_evaluations_completed":0,
            "optimizer_calls_started":0,"optimizer_calls_completed":0,
            "combined_evaluations":0,"optimizer_evaluation_count_complete":True}
    action=None; payload=None; stage="reserve_output"; files={}; total_bytes=0
    try:
        output_dir.mkdir(exist_ok=False)
        _fsync_directory(output_dir.parent)
    except Exception as error:
        return {"schema":RESULT_SCHEMA,"status":"failed","action":None,"counts":counts,
                "stage":stage,"exception":{"type":type(error).__name__,"message":str(error)},
                "output_directory_reserved":False},1

    def write(name,value):
        nonlocal total_bytes
        data=(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+"\n").encode()
        if total_bytes+len(data)>MAX_OWN_OUTPUT_BYTES:
            raise ValueError("worker own output cap exceeded")
        path=output_dir/name
        with path.open("xb") as f:
            f.write(data);f.flush();os.fsync(f.fileno())
        _fsync_directory(output_dir)
        total_bytes+=len(data)
        files[name]={"bytes":len(data),"sha256":_hash(data)}

    try:
        source=Path(__file__).resolve(); math_path=source.with_name("anchor_math.py")
        bindings={"worker":{"bytes":source.stat().st_size,"sha256":_hash(source.read_bytes())},
                  "math":{"bytes":math_path.stat().st_size,"sha256":_hash(math_path.read_bytes())}}
        write("worker_started.json",{"schema":"mumble_autonomous_anchor_worker_started_v1",
            "utc":datetime.now(timezone.utc).isoformat(),"pid":os.getpid(),"source":bindings,
            "request_path":str(input_path),"counts":counts.copy(),
            "semantics":"Missing completion retains reserved/unknown work; never retry or infer zero."})
        stage="validate_request"
        raw=_bounded_read(input_path,MAX_REQUEST_BYTES)
        request=strict_json(raw)
        if not isinstance(request,dict) or request.get("schema")!=REQUEST_SCHEMA:
            raise ValueError("invalid worker request schema")
        action=request.get("action")
        if action not in ACTION_FIELDS or set(request)!=ACTION_FIELDS[action]:
            raise ValueError("unknown action or request field")
        if any(os.environ.get(k)!="1" for k in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS")):
            raise ValueError("single-thread numerical environment required before import")
        spec=importlib.util.spec_from_file_location("_mumble_anchor_math_worker",math_path)
        am=importlib.util.module_from_spec(spec);sys.modules[spec.name]=am;spec.loader.exec_module(am)
        am._check_policy(request["policy"])
        original_prior=am.prior_at
        def counted_prior(x):
            counts["prior_evaluations"]+=1
            value=original_prior(x)
            counts["prior_evaluations_completed"]+=1
            return value
        am.prior_at=counted_prior
        def started(event):
            if counts["optimizer_calls_started"]:
                raise AssertionError("second optimizer call forbidden")
            counts["optimizer_calls_started"]=1
            counts["optimizer_evaluation_count_complete"]=False
            counts["combined_evaluations"]=None
            write("solve_started.json",{"schema":"mumble_autonomous_anchor_solve_started_v1",
                "utc":datetime.now(timezone.utc).isoformat(),"request_sha256":_hash(raw),
                "event":event,"counts":counts.copy(),
                "semantics":"Durably recorded immediately before minimize. If interrupted, entry/progress remains reserved and unknown."})
        stage=f"execute_{action}"
        if action=="prior":
            payload={"prior":am.prior_at(request["x"])}
        elif action=="propose":
            value=am.propose(request["block"],request["prefix"],request["prior"],request["policy"],started)
            counts["optimizer_calls_completed"]=value["evaluation_counts"]["optimizer_calls_completed"]
            counts["combined_evaluations"]=value["evaluation_counts"]["combined_objective_gradient"]
            counts["optimizer_evaluation_count_complete"]=True
            if counts["optimizer_calls_started"]!=value["evaluation_counts"]["optimizer_calls_started"]:
                raise AssertionError("optimizer marker/result accounting mismatch")
            payload={"proposal":value}
        else:
            payload={"assessment":am.assess_trial(request["current_block"],request["current_prior"],request["trial_block"],
                request["proposal"],request["alpha"],request["prefix"],request["policy"])}
        stage="verify_bindings"
        if _bounded_read(input_path,MAX_REQUEST_BYTES)!=raw:
            raise ValueError("worker request changed")
        if _hash(source.read_bytes())!=bindings["worker"]["sha256"] or _hash(math_path.read_bytes())!=bindings["math"]["sha256"]:
            raise ValueError("worker or math source changed")
        if _hash(am.REFERENCE_PATH.read_bytes())!=am.REFERENCE_SHA256:
            raise ValueError("reference prior source changed")
        expected_prior=0 if action=="propose" else 1
        if counts["prior_evaluations"]!=expected_prior or counts["prior_evaluations_completed"]!=expected_prior:
            raise AssertionError("prior evaluation accounting mismatch")
        result={"schema":RESULT_SCHEMA,"status":"completed","action":action,"payload":payload,
            "counts":counts.copy(),"input":{"bytes":len(raw),"sha256":_hash(raw)},"source":bindings,
            "input_and_sources_unchanged":True,"resources":_resources(wall,cpu),
            "files_before_result":files.copy(),"new_model_calls":0,"observation_reads":0,"truth_reads":0,
            "optimizer_counts_scope":"Proposal only; completed status does not mean inner KKT convergence or an accepted nonlinear step"}
        stage="save_result"
        write("result.json",result)
        return result,0
    except BaseException as error:
        result={"schema":RESULT_SCHEMA,"status":"failed","action":action,"payload":None,"counts":counts.copy(),
                "stage":stage,"exception":{"type":type(error).__name__,"message":str(error),
                "traceback":traceback.format_exc()[-12000:]},"resources":_resources(wall,cpu),
                "files_before_result":files.copy(),"new_model_calls":0,"observation_reads":0,"truth_reads":0,
                "no_retry":True,"partial_count_semantics":"A reserved optimizer without returned accounting has unknown evaluations, never zero."}
        try:
            write("result.json",_safe(result))
        except Exception as receipt_error:
            result["receipt_error"]={"type":type(receipt_error).__name__,"message":str(receipt_error)}
        return result,1


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--input",required=True,type=Path)
    parser.add_argument("--output-dir",required=True,type=Path)
    args=parser.parse_args()
    result,code=run(args.input,args.output_dir)
    compact={"schema":RESULT_SCHEMA,"status":result["status"],"action":result.get("action"),
             "payload_path":"result.json","counts":result["counts"]}
    if result["status"]!="completed":
        compact.update({"stage":result.get("stage"),"exception":result.get("exception"),"receipt_error":result.get("receipt_error")})
    print(json.dumps(_safe(compact),sort_keys=True,separators=(",",":"),allow_nan=False))
    raise SystemExit(code)


if __name__=="__main__":
    main()
