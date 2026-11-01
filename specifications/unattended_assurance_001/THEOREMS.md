# Conditional lemmas for unattended operation

These are handwritten proofs with explicit premises. Small exact examples in
`check_contracts.py` exercise the conclusions and negative cases. They do not
verify the full estimator, sensors, physical model or hardware.

## D0. Limits of a perfect trust classifier

Suppose two admitted physical situations induce observation laws P_good and
P_bad, but require different authorization decisions. For any data-based
authorization event A,

    P_bad(A) + P_good(not A) >= 1 - TV(P_good,P_bad).

Proof: the left side equals 1-[P_good(A)-P_bad(A)], and the bracket is at most
TV. The same argument includes randomized decisions by including their independent
randomness in the observation. If the observation laws are identical, the two
error rates sum to at least one. This can occur when a parameter is unexcited,
or sensor offset and model changes have indistinguishable effects.

An unresolved outcome belongs to not-A and is therefore an availability loss,
not a claim that the estimate is physically wrong. Perfect detection without
unnecessary refusal is impossible over such a class. Reduce the class through
validated assumptions, improve observability, use redundancy, or accept a declared
tradeoff. A good residual fit alone cannot remove this information limit.

## D1. Containment survives time propagation and compression

Let x_k include relevant physical states and parameters, and let admissible
evolution be x_(k+1) in F_k(x_k,u_k), where u_k ranges over an input uncertainty
set U_k. The set F_k includes allowed aging and model discrepancy. Let C_k be a
joint outer set of possible x_k, and let Y_(k+1) be the states compatible with the
new observation and declared measurement error. Use an outer reach enclosure R:

    R_k contains union_(x in C_k,u in U_k) F_k(x,u)
    C_(k+1) contains R_k intersect Y_(k+1).

Assume the true initial state is in C_0 and all physical/input/measurement
premises hold. If x_k is in C_k, the true successor is in R_k and Y_(k+1), hence
in C_(k+1). Induction proves containment at every step. Any compressed encoding
must decode to a superset of the required set, including rounding error.

This is a mathematical contract, not an instruction to replace the rolling
estimator with a huge interval solver. A smaller certificate must prove the
same necessary containment for its chosen queries. Intersecting incompatible
independently approximated marginals without their joint guarantee is unsafe.

Missing observations permit prediction without measurement contraction.
Missing current/temperature require larger U_k, not zero-current substitution.
An empty resulting set is a violated premise, inconsistent data, or a failed
enclosure computation; never normalize it into a trusted estimate. Clipping a
point into a physical range does not repair containment or calibration.

Bounded-error containment has no statistical failure probability *conditional
on its hard premises*. Gaussian sensor noise has no finite deterministic bound;
using a finite noise envelope requires a tail-risk allocation or a different
probabilistic containment construction. Do not mix these interpretations.

## D2. Sound query authorization and lifetime safety

Assume an event E of probability at least 1-alpha on which x_k is in C_k for
every relevant k. For a query f_k, obtain a validated enclosure [l_k,u_k] of
f_k(C_k), including query approximation and arithmetic error. Authorize point
q_k for absolute tolerance t_k only when

    max(|q_k-l_k|, |q_k-u_k|) <= t_k.

On E, every authorized point meets its tolerance. Therefore

    Pr(any authorized point violates its tolerance) <= alpha.

This remains true for data-dependent authorization times and multiple queries
derived from the same simultaneous joint set. No independence assumption or
new risk per query is needed. Additional separately calibrated certificates
require their own valid joint risk accounting.

For Q relative error measured against true Q, with 0<l<=Q<=u and t<1, authorize
only if q is in [(1-t)u,(1+t)l]. Proof: (1-t)Q<=q<=(1+t)Q for every Q in [l,u]
is equivalent to those two extreme inequalities. Absolute-error and relative-
error authorization are different contracts.

For a proposed load, form a validated lower bound on voltage over *all* states
in C_k, admitted future input/thermal/model perturbations, and every physical
time in the forecast horizon. If this bound is at least V_min plus the declared
system margin, the load is authorized on E. Checking only sampled endpoints or
an average resistance does not prove this lower bound. Fallback loads need their
own admissibility contract; unresolved estimation is not a universal safety action.

If numerical predicates, source/configuration identity, applicability domain or
freshness fail, no enclosure is authorized. A cached enclosure can be reused only
after valid transport to the current boundary. This theorem does not imply
Pr(error | authorized)=alpha; the bound is on any unsafe authorization over the
whole experiment. Conditional-on-selection claims need separate analysis.

## D3. Lifetime risk cannot be reset at each report

For failure events B_k with valid probabilities at most alpha_k, the union
bound gives Pr(any B_k)<=sum alpha_k. Independence is unnecessary. A constant
per-report alpha over billions of reports is not a useful lifetime bound.
Likewise, independent per-boot failures of probability a produce lifetime
failure probability 1-(1-a)^m over m boots; resetting counters does not reset risk.

A sufficient epoch contract allocates predictable a_e with sum_e a_e<=alpha_life
on every history, and proves Pr(B_e | epoch-start history)<=a_e. By conditional
expectation and the union bound, lifetime risk is at most alpha_life. Example
a_e=alpha_life/[e(e+1)] has partial sum alpha_life*m/(m+1). This is risk accounting,
not exponential forgetting or a physical aging law. Shrinking epoch budgets may
harm availability; they are not automatically the chosen implementation.

A second route is a nonnegative supermartingale M_t(theta), initially one, under
every admitted fixed theta. For any finite T, stop at its first crossing of
1/alpha or at T. The stopped expectation is at most one, so nonnegativity gives
Pr(cross by T)<=alpha. Taking increasing T gives the same bound for all time.
Thus C_t={theta: max_(s<=t) M_s(theta)<1/alpha} simultaneously contains the true
theta with probability at least 1-alpha.

For a correct causal stationary likelihood p_theta(y_i | past,action_i), a
normalized, past-measurable predictive density q_i gives the example

    M_t(theta) = product_i q_i(y_i | past,action_i) /
                            p_theta(y_i | past,action_i).

If q_i is supported where p_theta is positive, each conditional ratio has mean
one, establishing the martingale premise. Actions may depend on recorded past
data; q_i must be selected before y_i is observed. Exact ADC/noise likelihood,
current-sensor uncertainty, support and finite-precision error are obligations.
Unmodeled aging invalidates this stationary construction. This is an existence
argument, not an implemented or resource-qualified Mumble confidence sequence.
Computing a conservative outer set from it is also an open obligation.

The standard confidence-sequence framework provides time-uniform rather than
fixed-time inference. See [Howard et al.](https://arxiv.org/abs/1810.08240v9).
The proof above states the specific sufficient premise used here. Reusing a
pointwise posterior TV bound at every time does not establish this premise.

## D4. Availability needs an information and recovery premise

If the valid scalar query enclosure has width at most 2t, its midpoint meets the
absolute tolerance t throughout that enclosure, by D2. If the *exact attainable*
query range has width greater than 2t, no one point can meet tolerance t at both
extremes (triangle inequality). A loose computed enclosure wider than 2t merely
fails to certify; it does not prove that the observations are uninformative.

A sufficient availability contract is: after N_star admitted informative samples
following a reset or recoverable fault, a verified procedure returns a valid
enclosure of width <=2t and finishes within L cycles; sensors, power and evolution
premises remain valid. It then authorizes by the stated deadline. If the enclosure
width event fails with probability at most beta, this gives availability at least
1-beta on that scenario class. With D2, correct and available operation has
probability at least 1-alpha-beta. For an H7 point rather than the midpoint, use
its actual worst-endpoint error; narrow width alone is insufficient.

H7 has no proved N_star, L or beta yet. Local GN curvature alone does not prove
global identification or this width guarantee. Define excitation via observable
inputs and validated information/query bounds, not truth or a convenient seed.
Admissible recovery stimuli must obey the device's power/load constraints.

## D5. Quiet intervals and aging do not renew trust

For parameter drift |p_(k+1)-p_k|<=d_k and a valid enclosure [l_k,u_k], prediction
gives [l_k-d_k,u_k+d_k]. For monotone increase it gives [l_k,u_k+d_k]; for decrease,
[l_k-d_k,u_k]. Intersect with independently valid physical support, and apply the
measurement enclosure when available. Proof is direct interval addition and
induction. Multiple correlated parameters require their joint reachable set.

Without a qualified drift-rate bound, monotonicity plus a global envelope permits
an arbitrarily fast change toward its permitted endpoint. A small time gap does
not justify carrying a narrow current-state interval unchanged. A spline or
codebook does not establish a derivative bound unless its admitted family and
approximation remainder are independently justified. Old observations remain
evidence about old states; a valid transport/evolution model is what relates
them to the current battery. Neither arbitrary decay nor an arbitrary uncertainty
floor discharges this proof.

## D6. Numerical error accounting survives a finite lifetime

Suppose an exact update T_k is Lipschitz with constant L_k on the admitted domain
and its computed update has certified defect at most e_k there. If current error
is bounded by b_k, then

    b_(k+1) = L_k b_k + e_k

is a valid next bound: insert T_k(computed state) and use the triangle inequality.
This requires the numerical enclosure/domain premise to remain valid at each
step. Evaluation of b itself must round outward and detect range exhaustion.
A bound exceeding the available query budget revokes authorization before the
next output; it does not justify resetting b or relabeling it as sensor noise.

For L_k<=rho<1 and e_k<=e, b_k<=rho^k b_0+e(1-rho^k)/(1-rho).
For an integrator L=1, b_k<=b_0+sum e_i. Both are induction results. Fixed state
dimension does not distinguish these growth laws. A reset/recentering can reduce
the bound only if its replacement certificate includes the inherited evidence
and error. Discarded raw observations cannot later certify themselves.

This lemma composes with the earlier joint precision/center bounds; its constants
for actual H7 recurrences, features, QR, solves and libm remain open. A residual
of the compressed factor only checks that representation, not its agreement
with the original likelihood. Source approximation and accumulation defects need
separate accounting. A proof of a monitor must include the monitor's arithmetic.

## D7. Fault containment and autonomous recovery compose

Assume each public update either (a) commits one complete evidence/state object,
(b) leaves the previous committed object unchanged, or (c) enters quarantine
before publishing any affected authorization. Assume publication verifies a
matching prefix/configuration and valid query certificate. Induction on updates
then shows that no authorized output comes from a partially committed object.
Restoring a previous object does not make it current; gaps must be replayed once
or represented as uncertain propagation before authorization resumes.

Bound each recovery attempt in time and retries. If a verified cold-start or
restore path returns to D1 premises and D4's informative-use conditions hold,
the composition returns to useful authorization without external intervention.
Otherwise it remains explicitly unresolved and the system uses a qualified
fallback. This is a conditional recovery theorem, not a promise of availability
under permanent failure. Native failures, allocation faults, corrupted storage,
power loss and interrupted writes require a declared fault model and separate
implementation correspondence. Checksums alone do not prove correct provenance
or immunity to all corruption.

The observed H7 field flush violates alternative (b) without locally enforcing
(c); caller containment exists for selected exceptions. Therefore this lemma's
backend premise is currently open. Bounded retries, restart risk, SRAM loss and
fallback behavior also require implementation before deployment certification.
