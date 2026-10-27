#!/usr/bin/env python3
"""Public-start joint proposal algebra. No observation/model/truth entry point.

The exact mixture objective is evaluated only by prior_at. Proposal iterations
use its cached gradient and a positive definite prior-curvature majorizer.
All curvature here is optimization geometry, never uncertainty.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import warnings
from typing import Any, Callable

REFERENCE_SHA256 = "870583ec263f4bf4e69b80aa9fc06402336deb606aeaa88533389ddce715261b"
REFERENCE_PATH = Path(__file__).resolve().parents[1] / "retained_likelihood_replacement_001/replacement_math.py"
if hashlib.sha256(REFERENCE_PATH.read_bytes()).hexdigest() != REFERENCE_SHA256:
    raise RuntimeError("unchanged qualified prior module hash mismatch")
_spec = importlib.util.spec_from_file_location("_mumble_anchor_reference", REFERENCE_PATH)
rm = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = rm
_spec.loader.exec_module(rm)
np, scipy = rm.np, rm.scipy
from scipy.optimize import Bounds, NonlinearConstraint, minimize

if np.__version__ != "2.3.5" or scipy.__version__ != "1.17.0":
    raise RuntimeError("numerical dependency differs from frozen versions")

DIM = 16
EPS = float(np.finfo(np.float64).eps)
ETA = float.fromhex("0x0.0000000000001p-1022")
BASE_TOL = EPS ** (2.0 / 3.0)
KKT_TOL = 64.0 * BASE_TOL
MAX_ITERATIONS, MAX_EVALUATIONS = 100, 256
ALPHAS = tuple(2.0 ** -i for i in range(8))
EVALUATOR_SCHEMA = "mumble_retained_likelihood_stream_evaluator_v1"
EVALUATOR_COORDINATES = ["logtau1", "logtau2", "logtau3", "loggamma_plus", "loggamma_minus",
                         "logQ", "R0", "R1", "R2", "R3", "H", "z", "v1", "v2", "v3", "h"]
GRAM_LAYOUT = "lower-packed-row-major: i*(i+1)/2+j for j<=i"


def _number(value: Any, name: str) -> float:
    if isinstance(value, (bool, str)):
        raise ValueError(f"{name}: expected finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name}: nonfinite")
    return result


def _vector(value: Any, size: int, name: str):
    if not isinstance(value, (list, tuple, np.ndarray)) or len(value) != size:
        raise ValueError(f"{name}: wrong vector size")
    return np.array([_number(v, name) for v in value], dtype=np.float64)


def _same_vector(a, b) -> bool:
    return _vector(a, DIM, "vector a").tobytes() == _vector(b, DIM, "vector b").tobytes()


def _gamma(k: int) -> float:
    return (k * EPS) / (1.0 - k * EPS)


def _cost_gamma(k: int) -> float:
    # Preserve the original supervisor rule's unit roundoff, not EPS.
    ku = k * (EPS / 2.0)
    return ku / (1.0 - ku)


def _up(value: float) -> float:
    value = _number(value, "allowance")
    if value < 0.0:
        raise ValueError("negative allowance")
    return math.nextafter(value, math.inf)


def policy() -> dict[str, Any]:
    p = {
        "schema": "mumble_autonomous_anchor_policy_v1",
        "reference_math_sha256": REFERENCE_SHA256,
        "numpy": "2.3.5", "scipy": "1.17.0",
        "start": "PUBLIC_MEAN exactly; no fitted vector or alternate seed",
        "metric": "full G + diag(KERNEL_PRECISION); no eigenvalue or covariance repair",
        "scaled_metric": "B * outer(PUBLIC_SD,PUBLIC_SD), one symmetric outer-product scale",
        "objective_scale": "sqrt(max(1, ||scaled_metric||_infinity))",
        "step_box_public_SD": 1.0,
        "max_iterations": MAX_ITERATIONS, "max_combined_evaluations": MAX_EVALUATIONS,
        "gtol": KKT_TOL, "KKT_tolerance": KKT_TOL, "xtol": 128.0 * EPS,
        "barrier_tol": BASE_TOL, "initial_barrier_parameter": BASE_TOL,
        "initial_barrier_tolerance": KKT_TOL, "initial_tr_radius": 1.0,
        "initial_constr_penalty": 1.0, "factorization_method": "QRFactorization",
        "sparse_jacobian": False, "keep_feasible": True,
        "Armijo_c1": 0.25, "trial_fractions": list(ALPHAS),
        "dot_operation_allowance": 8 * DIM + 128,
        "model_operation_allowance": 8 * DIM * DIM + 128,
        "Armijo_combination_operation_allowance": 16,
        "cost_accumulation_operation_allowance": "8*N+64",
        "cost_combination_operation_allowance": 8,
        "rounding_units": {"inherited_cost_rule": EPS/2.0,
                           "direction_model_and_Armijo_guards": EPS},
        "arithmetic": "fsum of computed products; explicit eta terms and upward directional/model/final guards. Stored/computed operands only, no real-model/libm/derivative certificate.",
        "counts": "Every objective/gradient evaluation including one forced final verification; constant Hessian requests do not evaluate objective or prior.",
        "prior_evaluations_inside_proposal": 0,
        "uncertainty": "No posterior covariance, intervals, coverage or nonlinear stationarity inferred",
    }
    p["policy_sha256"] = hashlib.sha256(json.dumps(p, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    return p


def configuration() -> dict[str, Any]:
    return {"policy": policy(), "public_prior": rm.public_prior()}


def _check_policy(value):
    if value != policy():
        raise ValueError("request policy differs from frozen policy")


def prior_at(x) -> dict[str, Any]:
    """Exactly one mixture algebra evaluation, with no support normalization."""
    x = _vector(x, DIM, "prior x")
    value = rm.prior_cost_gradient_hessian(x)
    return {"schema": "mumble_autonomous_anchor_prior_v1", "x": x.tolist(),
            "cost": value["cost"], "gradient": value["gradient"].tolist(),
            "hessian_lower": rm.pack_lower(value["hessian"]),
            "responsibilities": value["responsibilities"].tolist(),
            "reference_math_sha256": REFERENCE_SHA256,
            "support_normalizer_included": False, "prior_evaluations": 1}


def _cached_prior(value, x):
    if not isinstance(value, dict) or value.get("schema") != "mumble_autonomous_anchor_prior_v1":
        raise ValueError("invalid cached prior schema")
    if value.get("reference_math_sha256") != REFERENCE_SHA256 or not _same_vector(value.get("x"), x):
        raise ValueError("cached prior identity mismatch")
    if value.get("support_normalizer_included") is not False or value.get("prior_evaluations") != 1:
        raise ValueError("cached prior semantics mismatch")
    cost = _number(value["cost"], "prior cost")
    gradient = _vector(value["gradient"], DIM, "prior gradient")
    _vector(value["hessian_lower"], 136, "prior Hessian")
    weights = _vector(value["responsibilities"], 2, "responsibilities")
    if np.any(weights < 0.) or np.any(weights > 1.) or abs(math.fsum(weights)-1.) > _gamma(64):
        raise ValueError("invalid cached mixture responsibilities")
    return cost, gradient


def _prefix(prefix):
    if not isinstance(prefix, dict) or set(prefix) != {"records", "charge_min_Ah", "charge_max_Ah"}:
        raise ValueError("prefix must contain only records and charge extrema")
    n = prefix["records"]
    if type(n) is not int or not 0 <= n <= 252000:
        raise ValueError("invalid prefix length")
    return n, rm.Support(_number(prefix["charge_min_Ah"], "charge min"),
                         _number(prefix["charge_max_Ah"], "charge max"))


def _block(payload, prefix):
    n, support = _prefix(prefix)
    expected = {"schema": EVALUATOR_SCHEMA, "status": "ok", "dimension": DIM,
                "coordinate_names": EVALUATOR_COORDINATES, "sigma_V": .001,
                "gram_layout": GRAM_LAYOUT, "charge_extrema_include_initial_zero": True}
    if not isinstance(payload, dict) or any(payload.get(k) != v for k,v in expected.items()):
        raise ValueError("evaluator identity mismatch")
    for k in ("prefix_requested", "records_read", "records_accumulated", "model_step_calls", "model_predict_calls"):
        if type(payload.get(k)) is not int or payload[k] != n:
            raise ValueError(f"evaluator prefix/count mismatch: {k}")
    for k in ("source_generations", "learner_ingests", "fit_calls", "truth_reads"):
        if type(payload.get(k)) is not int or payload[k] != 0:
            raise ValueError(f"forbidden evaluator activity: {k}")
    for k in ("charge_min_Ah", "charge_max_Ah"):
        if _number(payload.get(k), k) != prefix[k]:
            raise ValueError("evaluator prefix geometry mismatch")
    _vector(payload.get("x"), DIM, "block x")
    _vector(payload.get("gradient"), DIM, "block gradient")
    _vector(payload.get("gram"), 136, "block Gram")
    if _number(payload.get("cost"), "block cost") < 0.:
        raise ValueError("negative squared-residual cost")
    if _number(payload.get("absolute_summand_scales", {}).get("cost"), "absolute cost scale") < 0.:
        raise ValueError("negative cost accumulation scale")
    block = rm.QuadraticBlock.from_evaluator(payload)
    if not support.diagnostics(block.anchor)["strictly_feasible"]:
        raise ValueError("block anchor outside raw physical support")
    return block, support


def trial_vector(anchor, candidate, alpha):
    a, b = _vector(anchor, DIM, "anchor"), _vector(candidate, DIM, "candidate")
    alpha = _number(alpha, "alpha")
    if alpha not in ALPHAS:
        raise ValueError("trial fraction outside frozen schedule")
    if alpha == 1.0:
        return b.tolist()
    # Scalar order is shared with the stdlib parent; no fused operation/clipping.
    return [float(a[i]) + alpha * (float(b[i]) - float(a[i])) for i in range(DIM)]


def direction_checks(gradient, metric, anchor, candidate):
    g = _vector(gradient, DIM, "gradient")
    a, b = _vector(anchor, DIM, "anchor"), _vector(candidate, DIM, "candidate")
    B = np.asarray(metric, dtype=np.float64)
    if B.shape != (DIM,DIM) or not np.all(np.isfinite(B)) or not np.array_equal(B,B.T):
        raise ValueError("direction metric must be finite and exactly symmetric")
    d = b-a
    products = [float(g[i])*float(d[i]) for i in range(DIM)]
    dot = math.fsum(products)
    absolute_dot = math.fsum(abs(v) for v in products)
    kd, km = 8*DIM+128, 8*DIM*DIM+128
    A_dot = _up(math.fsum([_gamma(kd)*absolute_dot, kd*ETA]))
    # Fix multiply order: first d_i*B_ij, then bounded d_j, then off-diagonal 2.
    quadratic_terms = []
    for i in range(DIM):
        for j in range(i+1):
            value = (float(d[i])*float(B[i,j]))*float(d[j])
            quadratic_terms.append(value if i == j else 2.0*value)
    quadratic = math.fsum(quadratic_terms)
    absolute_model = math.fsum([absolute_dot, .5*math.fsum(abs(v) for v in quadratic_terms)])
    A_model = _up(math.fsum([_gamma(km)*absolute_model,
                            km*ETA*max(1.,float(np.max(np.abs(d))))]))
    reduction = math.fsum([-dot, -.5*quadratic])
    for value in (dot,absolute_dot,quadratic,absolute_model,reduction):
        _number(value,"direction arithmetic")
    return {"direction_x":d.tolist(), "directional_decrease":-dot,
            "directional_allowance":A_dot,"directional_absolute_product_scale":absolute_dot,
            "model_decrease":reduction,"model_allowance":A_model,
            "model_absolute_product_scale":absolute_model,"quadratic_form":quadratic,
            "direction_operation_allowance":kd,"model_operation_allowance":km,
            "resolved_descent":bool(-dot>A_dot),"resolved_model_decrease":bool(reduction>A_model)}


class _EvaluationLimit(RuntimeError):
    pass


class _Objective:
    def __init__(self, scaled_gradient, scaled_metric, scale, limit=MAX_EVALUATIONS):
        self.g, self.B, self.scale, self.limit = scaled_gradient,scaled_metric,scale,limit
        self.calls=0; self.final_calls=0; self.hessian_requests=0

    def evaluate(self,u,final=False):
        if self.calls >= (self.limit if final else self.limit-1):
            raise _EvaluationLimit("combined objective/gradient budget; final slot reserved")
        self.calls+=1; self.final_calls+=int(final)
        u=_vector(u,DIM,"proposal u")
        Bu=self.B@u
        model=math.fsum([math.fsum(float(self.g[i])*float(u[i]) for i in range(DIM)),
                         .5*math.fsum(float(u[i])*float(Bu[i]) for i in range(DIM))])
        gradient=(self.g+Bu)/self.scale
        if not math.isfinite(model) or not np.all(np.isfinite(gradient)):
            raise FloatingPointError("nonfinite quadratic objective")
        return {"u":u,"model_cost":model,"cost":model/self.scale,"gradient_u_scaled":gradient}

    def fun(self,u):
        value=self.evaluate(u)
        return value["cost"],value["gradient_u_scaled"]

    def hess(self,u):
        self.hessian_requests+=1
        return (self.B/self.scale).copy()


def _kkt(final,x,support,scale,multipliers,lower_u,upper_u):
    if multipliers is None or len(multipliers)!=2:
        return {"available":False,"passed":False,"reason":"quadratic solver multipliers unavailable"}
    pv=_vector(multipliers[0],2,"path multipliers")
    bv=_vector(multipliers[1],DIM,"bound multipliers")
    path,jac,_=support.path(x)
    ps=path/rm.PUBLIC_SD[11]
    ju=jac*rm.PUBLIC_SD[None,:]/rm.PUBLIC_SD[11]
    force=ju.T@pv+bv
    stationarity=final["gradient_u_scaled"]+force
    normalization=max(1.,float(np.max(np.abs(final["gradient_u_scaled"]))),float(np.max(np.abs(force))))
    relative=float(np.max(np.abs(stationarity)))/normalization
    # Signed-bound multiplier decomposition; not probability/covariance repair.
    lower_lambda=np.maximum(-bv,0.); upper_lambda=np.maximum(bv,0.)
    complements=np.concatenate((-pv*ps,lower_lambda*(final["u"]-lower_u),upper_lambda*(upper_u-final["u"])))
    complementarity=float(np.max(np.abs(complements)))
    dual=max(0.,float(np.max(pv)))
    return {"available":True,"passed":bool(relative<=KKT_TOL and complementarity<=KKT_TOL and dual<=KKT_TOL),
            "tolerance":KKT_TOL,"stationarity_relative":relative,
            "stationarity_u_scaled":stationarity.tolist(),"stationarity_normalization":normalization,
            "complementarity_scaled_max_abs":complementarity,"dual_violation_scaled":dual,
            "path_signed_multipliers_scaled":pv.tolist(),"bound_signed_multipliers_scaled":bv.tolist(),
            "actual_intersected_lower_u":lower_u.tolist(),"actual_intersected_upper_u":upper_u.tolist(),
            "scope":"Constrained quadratic including artificial step bounds; not nonlinear stationarity on original support"}


def propose(block_payload,prefix,cached_prior,policy_config,on_solver_start:Callable|None=None):
    _check_policy(policy_config)
    block,support=_block(block_payload,prefix)
    a=block.anchor.copy(); _,pg=_cached_prior(cached_prior,a)
    g=np.array([math.fsum([float(block.gradient[i]),float(pg[i])]) for i in range(DIM)])
    B=block.gram+np.diag(rm.KERNEL_PRECISION)
    scaled_B=B*np.outer(rm.PUBLIC_SD,rm.PUBLIC_SD)
    if not np.all(np.isfinite(scaled_B)) or not np.array_equal(scaled_B,scaled_B.T):
        raise FloatingPointError("scaled metric nonfinite or not exactly symmetric")
    scale=math.sqrt(max(1.,float(np.linalg.norm(scaled_B,ord=np.inf))))
    result={"schema":"mumble_autonomous_anchor_proposal_v1","anchor_x":a.tolist(),
            "candidate_x":a.tolist(),"gradient_x":g.tolist(),"metric_lower":rm.pack_lower(B),
            "prior_gradient_x":pg.tolist(),"prior_hessian_lower":cached_prior["hessian_lower"],
            "objective_scale":scale,"direction_admitted":False,
            "prior_evaluations":0,"policy_sha256":policy_config["policy_sha256"]}
    try:
        chol=np.linalg.cholesky(scaled_B)
    except np.linalg.LinAlgError:
        result.update({"status":"metric_not_positive_definite","raw_optimizer":None,
                       "KKT":{"available":False,"passed":False},"evaluation_counts":{
                       "combined_objective_gradient":0,"final_verification":0,"iterations":0,
                       "optimizer_calls_started":0,"optimizer_calls_completed":0},
                       "feasibility":support.diagnostics(a)})
        return result
    result["scaled_metric_Cholesky_diagonal"]=np.diag(chol).tolist()
    result["scaled_metric_Cholesky_relative_residual"]=float(np.linalg.norm(chol@chol.T-scaled_B,ord=np.inf))/max(1.,float(np.linalg.norm(scaled_B,ord=np.inf)))
    lower=np.maximum((rm.ENTERING_LOWER-a)/rm.PUBLIC_SD,-1.)
    upper=np.minimum((rm.ENTERING_UPPER-a)/rm.PUBLIC_SD,1.)
    obj=_Objective(rm.PUBLIC_SD*g,scaled_B,scale)
    constraint_calls={"value":0,"jacobian":0,"hessian":0}
    def cfun(u):
        constraint_calls["value"]+=1
        return support.path(a+rm.PUBLIC_SD*u)[0]/rm.PUBLIC_SD[11]
    def cjac(u):
        constraint_calls["jacobian"]+=1
        return support.path(a+rm.PUBLIC_SD*u)[1]*rm.PUBLIC_SD[None,:]/rm.PUBLIC_SD[11]
    def chess(u,v):
        constraint_calls["hessian"]+=1
        h=np.einsum("k,kij->ij",v,support.path(a+rm.PUBLIC_SD*u)[2])
        return h*np.outer(rm.PUBLIC_SD,rm.PUBLIC_SD)/rm.PUBLIC_SD[11]
    trace=[]; last_u=np.zeros(DIM); last_state=None
    def callback(u,state):
        nonlocal last_u,last_state
        last_u=np.array(u,copy=True); last_state=state
        trace.append({"iteration":int(state.nit),"combined_evaluations":obj.calls,
                      "scaled_model_cost":float(state.fun),"optimality":float(state.optimality),
                      "constraint_violation":float(state.constr_violation),"trust_radius":float(state.tr_radius)})
        return False
    options={k:policy_config[k] for k in ("gtol","xtol","barrier_tol","initial_barrier_parameter",
             "initial_barrier_tolerance","initial_tr_radius","initial_constr_penalty","factorization_method","sparse_jacobian")}
    options.update({"maxiter":MAX_ITERATIONS,"verbose":0})
    constraint=NonlinearConstraint(cfun,[0.,0.],[np.inf,np.inf],jac=cjac,hess=chess,keep_feasible=True)
    if on_solver_start:
        on_solver_start({"anchor_x":a.tolist(),"policy_sha256":policy_config["policy_sha256"],
                         "prefix":prefix,"max_iterations":MAX_ITERATIONS,"max_combined_evaluations":MAX_EVALUATIONS})
    budget_hit=False
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            opt=minimize(obj.fun,np.zeros(DIM),method="trust-constr",jac=True,hess=obj.hess,
                         bounds=Bounds(lower,upper,keep_feasible=True),constraints=[constraint],
                         callback=callback,options=options)
            u=opt.x
        except _EvaluationLimit:
            budget_hit=True; opt=last_state; u=last_u
    final=obj.evaluate(u,final=True)
    candidate=a+rm.PUBLIC_SD*final["u"]
    feasible=support.diagnostics(candidate)
    d=candidate-a
    step_slacks=np.concatenate((1.+d/rm.PUBLIC_SD,1.-d/rm.PUBLIC_SD))
    step_ok=bool(np.all(step_slacks>=0.))
    kkt=_kkt(final,candidate,support,scale,getattr(opt,"v",None),lower,upper)
    raw={}
    for k in ("status","success","message","nit","nfev","njev","nhev","cg_niter","cg_stop_cond",
              "optimality","constr_violation","tr_radius","barrier_parameter","barrier_tolerance","constr_penalty","method"):
        if hasattr(opt,k):
            v=getattr(opt,k);raw[k]=v.item() if isinstance(v,np.generic) else v
    if budget_hit:
        raw.update({"success":False,"external_stop":"combined_evaluation_budget"})
    checks=direction_checks(g,B,a,candidate)
    admitted=bool(feasible["strictly_feasible"] and step_ok and checks["resolved_descent"] and checks["resolved_model_decrease"])
    inner_converged=bool(raw.get("success",False) and not budget_hit and feasible["strictly_feasible"] and step_ok and kkt["passed"])
    result.update(checks)
    result.update({"status":"direction_admitted" if admitted else "unresolved_no_admissible_direction",
        "candidate_x":candidate.tolist(),"direction_admitted":admitted,"feasibility":feasible,
        "optimizer_u":final["u"].tolist(),
        "step_box_feasible":step_ok,"step_box_scaled_slacks":step_slacks.tolist(),
        "step_box_active_coordinates":[rm.COORDINATES[i%DIM] for i,s in enumerate(step_slacks) if s<=math.sqrt(EPS)],
        "physical_support_active_names":feasible["active_names"],
        "inner_solver_status":"converged" if inner_converged else "unresolved",
        "raw_optimizer":raw,"KKT":kkt,"budget_hit":budget_hit,
        "evaluation_counts":{"combined_objective_gradient":obj.calls,"final_verification":obj.final_calls,
          "Hessian_requests":obj.hessian_requests,"iterations":int(raw.get("nit",0)),
          "constraint_calls":constraint_calls,"optimizer_calls_started":1,"optimizer_calls_completed":1},
        "trace":trace,"warnings":[str(w.message) for w in caught],
        "scope":"Metric majorizes prior curvature only; all trial acceptance uses the actual nonlinear likelihood and exact mixture penalty"})
    if obj.calls>MAX_EVALUATIONS or obj.final_calls!=1 or int(raw.get("nit",0))>MAX_ITERATIONS:
        raise AssertionError("proposal exceeded frozen work bound")
    return result


def assess_trial(current_block,current_prior,trial_block,proposal,alpha,prefix,policy_config):
    """One trial prior evaluation; no proposal solve or observation access."""
    _check_policy(policy_config)
    current,support=_block(current_block,prefix); trial,_=_block(trial_block,prefix)
    pc,_=_cached_prior(current_prior,current.anchor)
    if not isinstance(proposal,dict) or proposal.get("schema")!="mumble_autonomous_anchor_proposal_v1" or proposal.get("direction_admitted") is not True:
        raise ValueError("trial lacks an admitted proposal")
    if proposal.get("policy_sha256")!=policy_config["policy_sha256"] or not _same_vector(proposal["anchor_x"],current.anchor):
        raise ValueError("proposal/current identity mismatch")
    expected=trial_vector(current.anchor,proposal["candidate_x"],alpha)
    if not _same_vector(trial.anchor,expected):
        raise ValueError("trial vector differs from frozen chord construction")
    # Reconstruct cheap stored-operand direction checks, not any prior/model.
    B=rm.unpack_lower(proposal["metric_lower"])
    checked=direction_checks(proposal["gradient_x"],B,current.anchor,proposal["candidate_x"])
    for k in ("directional_decrease","directional_allowance","model_decrease","model_allowance"):
        if checked[k]!=proposal.get(k):
            raise ValueError("proposal directional receipt mismatch")
    if not checked["resolved_descent"] or not checked["resolved_model_decrease"]:
        raise ValueError("proposal decrease is unresolved")
    pt=prior_at(trial.anchor)
    lf,lt,pf,pr=current.cost,trial.cost,pc,pt["cost"]
    n=prefix["records"]
    # Preserve the previous computed-cost comparison arithmetic and scope.
    accumulation=_cost_gamma(8*n+64)*(current_block["absolute_summand_scales"]["cost"]+trial_block["absolute_summand_scales"]["cost"])
    combination=_cost_gamma(8)*math.fsum([abs(lf),abs(lt),abs(pf),abs(pr)])
    A_cost=accumulation+combination
    delta=math.fsum([lf,pf,-lt,-pr])
    s,A_dot=checked["directional_decrease"],checked["directional_allowance"]
    required=.25*float(alpha)*(s+A_dot)
    A_combine=_up(math.fsum([_gamma(16)*math.fsum([abs(delta),A_cost,abs(required)]),16*ETA]))
    margin=math.fsum([delta,-A_cost,-required])
    accepted=bool(margin>A_combine)
    likelihood_change=direction_checks(current.gradient,current.gram,current.anchor,trial.anchor)
    quadratic_likelihood=math.fsum([lf,-likelihood_change["model_decrease"]])
    for value in (accumulation,combination,A_cost,delta,required,A_combine,margin):
        _number(value,"Armijo comparison")
    return {"schema":"mumble_autonomous_anchor_assessment_v1",
            "status":"accepted_resolved_Armijo_decrease" if accepted else "rejected_insufficient_or_unresolved_decrease",
            "accepted":accepted,"alpha":float(alpha),"trial_x":trial.anchor.tolist(),"trial_prior":pt,
            "F_current":math.fsum([lf,pf]),"F_trial":math.fsum([lt,pr]),"deltaF":delta,
            "cost_arithmetic_allowance":A_cost,"cost_accumulation_allowance":accumulation,
            "cost_four_term_allowance":combination,"directional_decrease":s,"directional_allowance":A_dot,
            "Armijo_c1":.25,"Armijo_required_decrease":required,"Armijo_combination_allowance":A_combine,
            "Armijo_margin_before_combination_guard":margin,"prior_evaluations":1,
            "anchor_quadratic_likelihood_at_trial":quadratic_likelihood,
            "anchor_quadratic_minus_nonlinear_trial_likelihood":math.fsum([quadratic_likelihood,-lt]),
            "feasibility":support.diagnostics(trial.anchor),
            "cost_operation_allowances":{"accumulation":8*n+64,"four_term":8,"Armijo_combination":16},
            "scope":"Computed summands and fixed reported prior values; no real-model/libm/derivative certificate or statistical accuracy gate"}
