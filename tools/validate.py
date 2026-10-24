#!/usr/bin/env python3
"""Independent validation and scoring for the fresh 35 Hz C campaign.

This predictor evaluates closed-form complete dwells, not C sample recurrences.
Truth is used only after estimation to score errors. Current-SOC error is the
endpoint error of each prefix; retrospective trajectory RMSE is separate.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
import re
import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np

from generate_cases import (ROOT, CELLS, SIGMA_V, samples, simulate,
                            physical_to_vectors, vectors_to_physical)


def _benchmark_binary_path(root):
    """Locate the preserved campaign binary after a source-only checkout."""
    for relative in ("build/scm_estimator_benchmark",
                     "reference_binaries/scm_estimator_benchmark"):
        candidate=root/relative
        if candidate.is_file():return candidate
    return root/"build/scm_estimator"


def json_safe(value):
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, np.ndarray):
        return json_safe(value.tolist())
    if isinstance(value, np.generic):
        return json_safe(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def assess_result(fit, truth, dt, current, y, sigma=SIGMA_V):
    """Score only the supplied observation window, without future samples.

    For a late-window-only control, caller supplies shifted scoring truth from
    advance_truth; those true entering states must not be passed to C fitting.
    """
    dt, current, y = (np.asarray(a, float) for a in (dt, current, y))
    if dt.shape != current.shape or y.shape != dt.shape:
        raise ValueError("Scoring arrays must have the same shape")
    n_reported = fit.get("samples", fit.get("n_samples"))
    if n_reported is not None and int(n_reported) != len(dt):
        raise ValueError("Result sample count differs from scoring window")
    p = vectors_to_physical(fit["theta"], fit["alpha"])
    mu, soc, hyst = simulate(dt, current, p, states=True)
    _, true_soc, _ = simulate(dt, current, truth, states=True)
    residual = mu-y
    objective = float(.5*np.sum((residual/sigma)**2))
    reported = fit.get("objective_full", fit.get("objective"))
    errors = {}
    for key in ("R0", "H", "gamma_plus", "gamma_minus", "Q_Ah"):
        errors[key] = 100.*(p[key]/truth[key]-1.)
    for key in ("R", "tau"):
        for i, (estimate, actual) in enumerate(zip(p[key], truth[key])):
            errors[f"{key}{i+1}"] = 100.*(estimate/actual-1.)
    absent = []
    if not np.any(current > 0):
        absent.append("gamma_plus")
    if not np.any(current < 0):
        absent.append("gamma_minus")
    if not np.any(current != 0):
        absent.extend(["Q_Ah", "R0"]+[f"R{i+1}" for i in range(len(p["R"]))])
    endpoint_error = float(100.*(soc[-1]-true_soc[-1]))
    return {
        "physical_parameters": p,
        "objective_full_independent": objective,
        "objective_reported": reported,
        "objective_abs_discrepancy": abs(objective-reported) if reported is not None else None,
        "voltage_rmse_mV": float(1000.*np.sqrt(np.mean(residual**2))),
        "capacity_relative_error_percent": errors["Q_Ah"],
        "capacity_abs_relative_error_percent": abs(errors["Q_Ah"]),
        "current_SOC_estimate": float(soc[-1]),
        "current_SOC_truth": float(true_soc[-1]),
        "current_SOC_error_pp": endpoint_error,
        "current_SOC_abs_error_pp": abs(endpoint_error),
        "soc_final_error_pp": endpoint_error,
        "soc_trajectory_rmse_pp": float(100.*np.sqrt(np.mean((soc-true_soc)**2))),
        "soc_trajectory_max_abs_pp": float(100.*np.max(np.abs(soc-true_soc))),
        "trajectory_metric_scope": "Retrospective reconstruction within this prefix; endpoint current-SOC metric is separate",
        "parameter_relative_errors_percent": errors,
        "h0_error": float(p["h0"]-truth["h0"]),
        "hysteresis_domain_valid": bool(np.all(np.abs(hyst)<=1.+1e-9)),
        "structurally_absent_parameters": absent,
        "identification_note": "Absence is a structural statement; presence of excitation does not by itself establish finite-noise identification",
        "scored_samples": len(dt),
    }


def load_records(path):
    text = Path(path).read_text()
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        obj = [json.loads(line) for line in text.splitlines() if line.strip()]
    if isinstance(obj, list):
        return obj
    for key in ("records", "fits", "results", "cases"):
        if key in obj and isinstance(obj[key], list):
            return obj[key]
    return [obj]


def flatten(record):
    if isinstance(record.get("result"), dict):
        fit = {k:v for k,v in record.items() if k not in ("result", "scores")}
        fit.update(record["result"])
        return fit
    return record


def reference_refinement(fit, dt, current, y, sigma=SIGMA_V, max_nfev=400):
    """Independent direct fit of all coordinates, initialized at C output.

    This is a local numerical check. It supplies neither a global optimum
    certificate nor confidence coverage. The C variable-projection/QP/Jacobian
    implementation is not called.
    """
    from scipy.optimize import least_squares

    th, aa = np.asarray(fit["theta"]), np.asarray(fit["alpha"])
    n = len(th)-4
    p = vectors_to_physical(th, aa)
    x0 = np.r_[th, aa[:n+2], aa[n+2:2*n+2]/.01, p["h0"]]
    tau_bounds = [(0.015,.15),(.15,1.5),(1.5,30.)][:n]
    lo = np.r_[np.log([a for a,b in tau_bounds]), np.log([5.,5.]), .2, np.log(.03),
               [0.]*(n+2), [-8.]*n, -1.]
    hi = np.r_[np.log([b for a,b in tau_bounds]), np.log([1200.,1200.]), .95, np.log(.10),
               [1.]*(n+1), .1, [8.]*n, 1.]
    x0 = np.clip(x0, lo+1e-11, hi-1e-11)
    nt = n+4

    def unpack(x):
        amps = np.r_[x[nt:nt+n+2], .01*x[nt+n+2:nt+2*n+2],
                     x[nt+n+1]*x[-1]]
        return vectors_to_physical(x[:nt], amps)

    def residual(x):
        mu, z, _ = simulate(dt, current, unpack(x), states=True, check_domain=False)
        return np.r_[(mu-y)/sigma, 1e6*max(0.,-float(z.min())),
                     1e6*max(0.,float(z.max())-1.)]

    before = float(.5*np.sum(residual(x0)**2))
    begin = time.perf_counter()
    answer = least_squares(residual, x0, bounds=(lo,hi), jac="3-point", method="trf",
                           x_scale="jac", ftol=2e-11, xtol=2e-11, gtol=2e-8,
                           max_nfev=max_nfev)
    pp = unpack(answer.x)
    theta, alpha = physical_to_vectors(pp)
    mu, z, _ = simulate(dt,current,pp,states=True,check_domain=False)
    _, c_z, _ = simulate(dt,current,p,states=True,check_domain=False)
    after = float(.5*np.sum(((mu-y)/sigma)**2))
    return {"case_id": fit.get("case_id"), "samples": len(dt),
            "scope": "Independent direct-coordinate local refinement from C output",
            "objective_before": before, "objective_after": after,
            "improvement": before-after,
            "relative_objective_improvement": (before-after)/max(abs(before),1.),
            "C_status": fit.get("status"), "success": bool(answer.success),
            "message": str(answer.message), "nfev": answer.nfev, "njev": answer.njev,
            "elapsed_s": time.perf_counter()-begin,
            "final_SOC_domain_valid": bool(np.all((z>=0)&(z<=1))),
            "theta": theta, "alpha": alpha,
            "capacity_change_from_C_percent": 100.*(pp["Q_Ah"]/p["Q_Ah"]-1.),
            "current_SOC_change_from_C_pp": 100.*float(z[-1]-c_z[-1]),
            "max_voltage_change_from_C_mV": float(1000*np.max(np.abs(mu-simulate(dt,current,p)))),
            "checkpoint_s": len(dt)/35.}


def check_c_model():
    header = (ROOT/"include/scm_model.h").read_text()
    max_modes = int(re.search(r"#define\s+SCM_MAX_MODES\s+(\d+)",header).group(1))
    if max_modes < 3:
        raise RuntimeError("Fresh campaign requires a compiled three-mode C model")
    class Physical(ctypes.Structure):
        _fields_ = [("modes",ctypes.c_int),("R0",ctypes.c_double),
                    ("R",ctypes.c_double*max_modes),("tau",ctypes.c_double*max_modes),
                    ("H",ctypes.c_double),("gamma_plus",ctypes.c_double),
                    ("gamma_minus",ctypes.c_double),("Q",ctypes.c_double)]
    class State(ctypes.Structure):
        _fields_ = [("z",ctypes.c_double),("v",ctypes.c_double*max_modes),("h",ctypes.c_double)]
    rows = []
    with tempfile.TemporaryDirectory(prefix="scm35_reference_") as directory:
        libpath = Path(directory)/"scm_model.so"
        subprocess.run(["cc","-std=c99","-O2","-shared","-fPIC","-I",str(ROOT/"include"),
                        str(ROOT/"src/scm_model.c"),"-lm","-o",str(libpath)],
                       check=True,capture_output=True,text=True)
        lib = ctypes.CDLL(str(libpath)); step = lib.scm_physical_step
        step.argtypes = [ctypes.POINTER(Physical),ctypes.POINTER(State),ctypes.c_void_p,
                         ctypes.c_double,ctypes.c_double,ctypes.POINTER(ctypes.c_double)]
        step.restype = ctypes.c_int
        dt,current,_ = samples()
        for cell,p in CELLS.items():
            pad = max_modes-len(p["R"])
            ph = Physical(len(p["R"]),p["R0"],(ctypes.c_double*max_modes)(*(p["R"]+[0.]*pad)),
                          (ctypes.c_double*max_modes)(*(p["tau"]+[1.]*pad)),p["H"],
                          p["gamma_plus"],p["gamma_minus"],p["Q_Ah"])
            st = State(p["z0"],(ctypes.c_double*max_modes)(*(p["v0"]+[0.]*pad)),p["h0"])
            v = ctypes.c_double(); values=[]; zs=[]
            for d,I in zip(dt,current):
                status=step(ctypes.byref(ph),ctypes.byref(st),None,float(d),float(I),ctypes.byref(v))
                if status!=0:
                    raise RuntimeError(f"C model returned {status}")
                values.append(v.value);zs.append(st.z)
            expected,z,_ = simulate(dt,current,p,states=True)
            rows.append({"cell":cell,"samples":len(dt),
                         "max_voltage_discrepancy_V":float(np.max(np.abs(expected-values))),
                         "max_SOC_discrepancy":float(np.max(np.abs(z-zs)))})
    maximum=max(r["max_voltage_discrepancy_V"] for r in rows)
    return {"cases":rows,"max_voltage_discrepancy_V":maximum,"pass":maximum<1e-9,
            "source_sha256":hashlib.sha256((ROOT/"src/scm_model.c").read_bytes()).hexdigest()}


def audit_profiles(profile_path, manifest_path):
    """Audit attained candidates independently; high cost is not an exclusion.

    Numerical status1/2 candidates remain valid attained-cost witnesses when
    their physical constraints pass. They cannot supply an optimized outside
    boundary. Even status0 finite-grid brackets lack a global exclusion proof.
    """
    source_bytes=Path(profile_path).read_bytes()
    document=json.loads(source_bytes)
    manifest=json.loads(Path(manifest_path).read_bytes())
    cases={c["case_id"]:c for c in manifest["cases"]}
    cache={};rows=[];profiles=[];errors=[];structural=[]
    max_target=0.;max_soc_target=0.;max_objective=0.;max_relative=0.
    for pi,profile in enumerate(document["profiles"]):
        cid=profile["case_id"];case=cases[cid]
        if cid not in cache:
            path=Path(manifest_path).parent/case["csv"]
            source_hash=hashlib.sha256(path.read_bytes()).hexdigest()
            if source_hash!=case["sha256"]:
                errors.append({"case_id":cid,"error":"CSV digest differs from manifest"})
            cache[cid]=np.loadtxt(path,delimiter=",",skiprows=1)
        n=int(round(float(profile["checkpoint_s"])*manifest["sampling_Hz"]))
        data=cache[cid][:n];dt,I,y=data[:,1],data[:,2],data[:,3]
        target_kind=profile["target"]
        if profile.get("status")=="structurally_unexcited":
            absent=((target_kind=="Q_Ah" and not np.any(I!=0)) or
                    (target_kind=="gamma_minus" and not np.any(I<0)) or
                    (target_kind=="gamma_plus" and not np.any(I>0)) or
                    (target_kind.startswith("R") and not np.any(I!=0)))
            structural.append({"profile_index":pi,"case_id":cid,"checkpoint_s":profile["checkpoint_s"],
                               "target":target_kind,"claim_verified":bool(absent),
                               "prior_support_retained":profile.get("support_bracket")==profile.get("prior_support")})
            if not absent:
                errors.append({"profile_index":pi,"error":"Unverified structural-absence claim"})
            continue
        evaluated=[];missing=0
        for ei,evaluation in enumerate(profile.get("evaluations",[])):
            result=evaluation.get("result")
            if not result or evaluation.get("returncode",0)!=0:
                missing+=1
                rows.append({"profile_index":pi,"evaluation_index":ei,"target_kind":target_kind,
                             "target":evaluation.get("target"),"operational_missing":True,
                             "used_as_exclusion":False})
                continue
            violations=[]
            try:
                if int(result["samples"])!=n:
                    violations.append("sample_count")
                if abs(result.get("sigma_V",manifest["sigma_V"])-manifest["sigma_V"])>1e-15:
                    violations.append("noise_scale")
                p=vectors_to_physical(result["theta"],result["alpha"])
                modes=len(p["R"])
                mu,z,h=simulate(dt,I,p,states=True,check_domain=False)
                objective=float(.5*np.sum(((mu-y)/manifest["sigma_V"])**2))
                discrepancy=abs(objective-result["objective_full"])
                relative=discrepancy/max(1.,abs(objective))
                max_objective=max(max_objective,discrepancy);max_relative=max(max_relative,relative)
                if discrepancy>max(1e-5,1e-10*abs(objective)):
                    violations.append("raw_objective")
                if target_kind=="current_soc":
                    actual=float(z[-1])
                    if result.get("fixed_current_soc") is None or abs(result["fixed_current_soc"]-evaluation["target"])>1e-12:
                        violations.append("fixed_current_SOC_flag")
                elif target_kind.startswith("tau"):
                    actual=p["tau"][int(target_kind[3:])-1]
                elif target_kind.startswith("R") and target_kind!="R0":
                    actual=p["R"][int(target_kind[1:])-1]
                else:
                    actual=p[target_kind]
                target_error=abs(actual-evaluation["target"])
                max_target=max(max_target,target_error)
                if target_kind=="current_soc":
                    max_soc_target=max(max_soc_target,target_error)
                if target_error>1e-9*max(1.,abs(evaluation["target"])):
                    violations.append("target_equality")
                for name,value,low,high in [
                    ("R0",p["R0"],0.,1.),("H",p["H"],0.,.1),
                    ("Q_Ah",p["Q_Ah"],.03,.10),("z0",p["z0"],.2,.95),
                    ("gamma_plus",p["gamma_plus"],5.,1200.),
                    ("gamma_minus",p["gamma_minus"],5.,1200.)]:
                    if value<low-1e-10*max(1.,abs(low)) or value>high+1e-10*max(1.,abs(high)):
                        violations.append(name+"_bound")
                for j,(value,(low,high)) in enumerate(zip(p["tau"],[(.015,.15),(.15,1.5),(1.5,30.)])):
                    if value<low-1e-10 or value>high+1e-10:
                        violations.append(f"tau{j+1}_bound")
                if any(v< -1e-10 or v>1.+1e-10 for v in p["R"]):
                    violations.append("R_branch_bound")
                if any(abs(v)>.08+1e-10 for v in p["v0"]):
                    violations.append("entering_polarization_bound")
                cone_excess=abs(float(result["alpha"][2+2*modes]))-p["H"]
                if cone_excess>1e-10:
                    violations.append("abs_u0_le_H")
                if np.any((z< -1e-10)|(z>1.+1e-10)):
                    violations.append("SOC_path_domain")
                if np.any(np.abs(h)>1.+1e-8):
                    violations.append("hysteresis_path_domain")
                row={"profile_index":pi,"evaluation_index":ei,"case_id":cid,
                     "checkpoint_s":profile["checkpoint_s"],"target_kind":target_kind,
                     "target":evaluation["target"],"actual_target":actual,"target_abs_error":target_error,
                     "objective_independent":objective,"objective_abs_discrepancy":discrepancy,
                     "objective_relative_discrepancy":relative,"C_status":result.get("status"),
                     "optimizer_converged":result.get("status")==0,"cone_excess_V":max(0.,cone_excess),
                     "H_V":p["H"],"u0_V":float(result["alpha"][2+2*modes]),
                     "h0_reportable":abs(p["H"])>1e-8,
                     "h0":p["h0"] if abs(p["H"])>1e-8 else None,
                     "raw_h0_ratio_for_audit":p["h0"] if abs(p["H"])<=1e-8 else None,
                     "near_zero_H_boundary_roundoff":bool(
                         violations==["hysteresis_path_domain"] and abs(p["H"])<=1e-8
                         and abs(float(result["alpha"][2+2*modes]))<=1e-8 and cone_excess<=1e-10),
                     "violations":violations}
                rows.append(row);evaluated.append(row)
                if violations:
                    errors.append({"profile_index":pi,"evaluation_index":ei,"violations":violations})
            except Exception as exc:
                errors.append({"profile_index":pi,"evaluation_index":ei,"error":str(exc)})
        valid=[e for e in evaluated if not e["violations"]]
        observed_min=min([profile["baseline_objective"]]+[e["objective_independent"] for e in valid])
        reported_min=profile.get("minimum_observed_objective")
        if reported_min is not None and abs(observed_min-reported_min)>max(1e-5,1e-10*abs(observed_min)):
            errors.append({"profile_index":pi,"error":"Minimum observed objective mismatch"})
        threshold=profile.get("likelihood_threshold_delta_NLL",2.)
        for entry in evaluated:
            entry["attained_cost_within_observed_threshold"]=(
                entry["objective_independent"]-observed_min<=threshold+1e-8)
        accepted=[e for e in valid if e["objective_independent"]-observed_min<=threshold+1e-8]
        unresolved=[e for e in valid if not e["optimizer_converged"]]
        bracket=profile.get("support_bracket")
        bad_sides=[]
        if bracket:
            for side,bound in enumerate(bracket):
                prior=profile["prior_support"][side]
                if abs(bound-prior)<=1e-10*max(1.,abs(prior)):
                    continue
                matches=[e for e in valid if abs(e["target"]-bound)<=1e-10*max(1.,abs(bound))]
                optimized_outside=[e for e in matches if e["optimizer_converged"] and
                                   e["objective_independent"]-observed_min>threshold]
                if not optimized_outside:
                    bad_sides.append("lower" if side==0 else "upper")
        profiles.append({"profile_index":pi,"case_id":cid,"checkpoint_s":profile["checkpoint_s"],
                         "target":target_kind,"valid_returned_candidates":len(valid),
                         "optimizer_converged":sum(e["optimizer_converged"] for e in valid),
                         "optimizer_unresolved":len(unresolved),"operational_missing":missing,
                         "attained_below_threshold":len(accepted),
                         "minimum_observed_objective_independent":observed_min,
                         "baseline_improvement_independent":profile["baseline_objective"]-observed_min,
                         "heuristic_bracket":bracket,
                         "bracket_sides_without_converged_outside_witness":bad_sides,
                         "coverage_certificate_claimed":profile.get("coverage_certificate",False)})
    numerical=[r for r in rows if "objective_independent" in r]
    boundary_roundoff=[r for r in numerical if r.get("near_zero_H_boundary_roundoff")]
    amplitude_failures=[r for r in numerical if any(
        v not in ("raw_objective","target_equality","fixed_current_SOC_flag",
                  "sample_count","noise_scale","hysteresis_path_domain") for v in r["violations"])]
    material_errors=[e for e in errors if not any(
        e.get("profile_index")==r["profile_index"] and
        e.get("evaluation_index")==r["evaluation_index"] for r in boundary_roundoff)]
    bracket_issues=[p for p in profiles if p["bracket_sides_without_converged_outside_witness"]]
    current_binary=ROOT/"build/scm_estimator"
    binary=_benchmark_binary_path(ROOT)
    binary_hash=hashlib.sha256(binary.read_bytes()).hexdigest() if binary.exists() else None
    current_hash=hashlib.sha256(current_binary.read_bytes()).hexdigest() if current_binary.exists() else None
    integration_path=ROOT/"results/c_integration_review.json"
    integration=None
    if integration_path.exists():
        integration_bytes=integration_path.read_bytes();review=json.loads(integration_bytes)
        core_hashes=review.get("core_source_sha256_after",{})
        integration={"path":str(integration_path),
                     "sha256":hashlib.sha256(integration_bytes).hexdigest(),
                     "failures":review.get("failures"),
                     "core_math_sources_unchanged_reported":review.get("core_math_sources_unchanged"),
                     "core_before_after_hashes_equal":review.get("core_source_sha256_before")==core_hashes,
                     "current_core_sources_match_review":all(
                         hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest
                         for path,digest in core_hashes.items()),
                     "benchmark_digest_matches_review":binary_hash==review.get("benchmark_executable_sha256"),
                     "current_cli_digest_matches_review":current_hash==review.get("integrated_executable_sha256"),
                     "representative_checks":[{
                         "checkpoint_s":c["checkpoint_s"],
                         "inference_fields_identical":c["inference_fields_identical"],
                         "preserved_executable_matches_stored_fit":c["preserved_executable_matches_stored_fit"]}
                         for c in review.get("representative_checks",[])],
                     "scope":"Read and cross-checked the separate integration receipt and current file digests; this profile audit did not repeat its executable comparison runs."}
    return {"schema":"scm_independent_profile_audit_v1",
            "source_profile_sha256":hashlib.sha256(source_bytes).hexdigest(),
            "source_binary_sha256":document.get("metadata",{}).get("binary_sha256"),
            "benchmark_binary_checked":str(binary),
            "benchmark_binary_sha256":binary_hash,
            "binary_matches_record":binary_hash==document.get("metadata",{}).get("binary_sha256"),
            "current_cli_binary_sha256":current_hash,
            "current_cli_matches_benchmark":current_hash==binary_hash,
            "poststudy_cli_integration_review":integration,
            "binary_provenance_note":"When present, scm_estimator_benchmark is the preserved study executable. The current CLI may be a post-study reporting revision; its separate equivalence review is results/c_integration_review.json. This candidate audit does not infer binary equivalence from matching output labels.",
            "profile_count":len(document["profiles"]),"numerical_candidates_audited":len(numerical),
            "operational_missing":sum(bool(r.get("operational_missing")) for r in rows),
            "optimizer_converged":sum(r["optimizer_converged"] for r in numerical),
            "optimizer_unresolved":sum(not r["optimizer_converged"] for r in numerical),
            "all_candidate_objective_target_and_constraint_checks_pass":not errors,
            "numerical_amplitude_feasibility_with_tolerance_pass":not amplitude_failures,
            "numerical_amplitude_feasibility_with_tolerance_count":len(numerical)-len(amplitude_failures),
            "amplitude_comparison_tolerance_V":1e-10,
            "h0_reporting_amplitude_floor_V":1e-8,
            "h0_unreportable_near_zero_H_count":sum(not r["h0_reportable"] for r in numerical),
            "raw_derived_h0_domain_failure_count":sum("hysteresis_path_domain" in r["violations"] for r in numerical),
            "near_zero_H_boundary_roundoff_cases":boundary_roundoff,
            "material_errors_beyond_documented_boundary_roundoff":material_errors,
            "boundary_roundoff_impacts_accepted_profile_points":any(
                r["attained_cost_within_observed_threshold"] for r in boundary_roundoff),
            "errors":errors,"max_target_abs_error":max_target,"max_current_SOC_target_abs_error":max_soc_target,
            "max_objective_abs_discrepancy":max_objective,"max_objective_relative_discrepancy":max_relative,
            "structural_claims":structural,"profiles":profiles,"candidate_checks":rows,
            "bracket_summary_pass":not bracket_issues,
            "bracket_summary_issues":bracket_issues,
            "interpretation":"Raw outputs are retained. One near-zero-H boundary tuple can pass amplitude tolerances while its raw u0/H ratio is outside[-1,1]; this is explicitly flagged, not an exact physical witness, and h0 is unavailable at |H|<=1e-8. Valid attained candidates are witnesses, not optimized profile lower bounds. Nonconverged high costs cannot supply outside boundaries. Converged finite-grid brackets remain heuristic, with no global exclusion or confidence coverage certificate."}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--manifest",type=Path,default=ROOT/"data/manifest.json")
    parser.add_argument("--results",type=Path)
    parser.add_argument("--profiles",type=Path)
    parser.add_argument("--output",type=Path,default=ROOT/"results/independent_validation.json")
    parser.add_argument("--reference-count",type=int,default=0)
    parser.add_argument("--reference-select",action="append",default=[],
                        help="Explicit case_id@checkpoint_seconds; repeatable")
    parser.add_argument("--reference-max-nfev",type=int,default=400)
    parser.add_argument("--check-c-model",action="store_true")
    args=parser.parse_args()
    if args.profiles:
        output=audit_profiles(args.profiles,args.manifest)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(json_safe(output),indent=2,allow_nan=False)+"\n")
        print(json.dumps({k:output[k] for k in ["profile_count","numerical_candidates_audited",
              "operational_missing","optimizer_unresolved","all_candidate_objective_target_and_constraint_checks_pass",
              "max_current_SOC_target_abs_error","max_objective_abs_discrepancy","bracket_summary_pass"]}))
        return
    manifest=json.loads(args.manifest.read_text());cases={c["case_id"]:c for c in manifest["cases"]}
    selected=set()
    for item in args.reference_select:
        cid,seconds=item.rsplit("@",1)
        selected.add((cid,int(round(float(seconds)*35))))
    records=load_records(args.results) if args.results else []
    scored=[];errors=[];references=[];cache={}
    for record in records:
        fit=flatten(record);cid=fit.get("case_id","")
        if cid not in cases:
            errors.append({"case_id":cid,"error":"No matching case metadata"});continue
        case=cases[cid]
        try:
            if cid not in cache:
                cache[cid]=np.loadtxt(args.manifest.parent/case["csv"],delimiter=",",skiprows=1)
            start=int(record.get("start_sample",record.get("window_start_index",0)))
            n=int(fit.get("samples",fit.get("n_samples",len(cache[cid]))))
            data=cache[cid][start:start+n]
            if len(data)!=n:
                raise ValueError("Requested window outside source data")
            truth=case["weak_tail_truth_start"] if start==1800*35 else case["truth"]
            if start not in (0,1800*35):
                raise ValueError("Unsupported shifted scoring window; provide its entering truth explicitly")
            score=assess_result(fit,truth,data[:,1],data[:,2],data[:,3],manifest["sigma_V"])
            score.update(case_id=cid,method=fit.get("method","full"),samples=n,start_sample=start,
                         time_s=float((start+n)/35),status=fit.get("status"))
            scored.append(score)
            automatic=(len(references)<args.reference_count and start==0 and n==case["n_samples"]
                    and not any(r["case_id"].split("_35hz_")[0]==cid.split("_35hz_")[0]
                                for r in references))
            if automatic or (start==0 and (cid,n) in selected):
                references.append(reference_refinement(fit,data[:,1],data[:,2],data[:,3],manifest["sigma_V"],
                                                        max_nfev=args.reference_max_nfev))
        except Exception as exc:
            errors.append({"case_id":cid,"error":str(exc)})
    discrepancies=[r["objective_abs_discrepancy"] for r in scored if r["objective_abs_discrepancy"] is not None]
    passed=(not errors and all(r["hysteresis_domain_valid"] and
                              (r["objective_abs_discrepancy"] is None or
                               r["objective_abs_discrepancy"]<=max(1e-5,1e-10*r["objective_full_independent"]))
                              for r in scored)) if records else None
    output={"schema":"scm_c_independent_validation_v2_35hz_fresh",
            "fit_count":len(records),"scored_count":len(scored),"errors":errors,
            "forward_recomputation_pass":passed,"scores":scored,
            "max_objective_abs_discrepancy":max(discrepancies,default=None),
            "reference_refinements":references,
            "explicit_reference_selection":args.reference_select,
            "max_reference_improvement":max((r["improvement"] for r in references),default=None),
            "c_model_comparison":check_c_model() if args.check_c_model else None,
            "input_manifest_sha256":hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
            "input_results_sha256":hashlib.sha256(args.results.read_bytes()).hexdigest() if args.results else None,
            "scope":"Fresh35Hz data; independent point/trajectory/objective checks; no formal uncertainty coverage certificate"}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(json_safe(output),indent=2,allow_nan=False)+"\n")
    print(json.dumps(json_safe({k:output[k] for k in ("fit_count","scored_count","errors",
          "forward_recomputation_pass","max_objective_abs_discrepancy","max_reference_improvement")})))


if __name__=="__main__":
    main()
