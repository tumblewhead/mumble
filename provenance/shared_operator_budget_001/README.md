# Fixed-budget shared operator: closure works, fidelity remains insufficient

We derived and tested one shared RC operator without growing the feature count,
native recurrence, factor or response state. It preserves constant-current
equilibrium and central value/slope/curvature. It does **not** resolve the rest
precision distortion, has a negative-free-response counterexample within the
original box, and provides only modest numerical changes. Do not promote this
candidate or increase its degree in response. This is a bounded feasibility
result, not evidence that every fixed-budget design is impossible.

Base 7522d27, branch experiment/shared-operator-budget-001. See the
[registered plan](../../specifications/shared_operator_budget_001/README.md),
[C1 derivation](../../specifications/shared_operator_budget_001/C1.md),
[compact refits](result.json), [probe and resource ledger](probe.json), and
[runner](../../experiments/shared_operator_budget_001/README.md).

## Concrete closed design

Keep the original exact centre jets (f,f_t,f_tt), streamed for both RC free and
forced response. For the physical query t=log(tau/tauc), use

    s=2*tanh(t/2),   fhat=f+s*f_t+s*s*f_tt/2.

This is a shared linear approximation functional. It preserves constants and
therefore uhat=I*(1-Fhat) for constant current, including shape derivatives. It
matches the original response's first two derivatives at the public centre.
It preserves the physical query/support and prior; only approximation weights
change. Both families continue through every interval, with no rest reset.

C1 gives an exact symbolic rational transfer remainder and duration-independent
response norm obligations. It does not supply useful numerical uniform constants
or a cumulative likelihood guarantee. The candidate and baseline have bitwise
identical streamed rows, states and joint factors in every case. Distinct query
maps mean their objective functions and fits differ despite identical factor bytes.

## Matched joint feasibility results

Six frozen cases, five arms, original two public starts and unchanged 60-round
solver: direct, TaylorRC/TaylorH2, CayleyRC/TaylorH2, TaylorRC/H7 and R5/H7. The two
larger H7 controls are diagnostic references, outside the candidate memory budget.
All 24 unchanged selected controls reproduce exactly. Candidate fits converge in
all six cases. Direct is still unresolved at one-hour rest; its fit-to-fit and
forecast comparisons remain withheld. All 60 attempts are retained, including
four unresolved direct attempts. No failed search is physical exclusion.

The following forecast RMS values are differences from the direct fitted
reference, taking the largest over both tasks and both direct/compressed state
transport paths. They are not physical truth errors or uncertainty coverage.

| Input | Taylor baseline (uV) | Shared Cayley (uV) |
|---|---:|---:|
| Short rest | 461.994 | 403.465 |
| Short multiscale | 0.3773 | 0.2943 |
| Short embedded | 3.5422 | 3.5371 |
| One-hour multiscale | 1.5305 | 1.5412 |
| One-hour embedded | 2.1408 | 1.9501 |

The short-rest improvement is about 12.7%, far from resolving the discrepancy.
At the candidate's own short/full rest anchors, combined sufficient epsilon is
7.071/7.015 (inconclusive), and actual relative precision spectra are
0.904–5.347 / 0.922–5.239. This shows substantial local joint distortion independently
of the conservative sufficient bound. Direct-gradient defect decreases from
2.118/2.060 to 1.803/1.737; it remains material. One-hour rest is an own-anchor local
diagnostic, not qualification against a converged direct fit.

The four active cases retain essentially the baseline's Q/SOC agreement: maximum
absolute Q/SOC differences from direct are 0.057993%/0.001599 pp, and Q/SOC SD ratios
span 0.993875–1.020767 / 0.994771–1.011568. All four active combined precision checks
pass locally, as they already did for the baseline. Active forecast SD ratios span
0.980643–1.050640. Small Q regressions and the one-hour multiscale forecast regression
remain visible. No uniform scalar dominance, physical coverage or lifetime claim.

## Physical and off-centre limits retained

The public constant-current checks preserve complement and slope identities to
6.25e-17 A and 3.13e-17 A per log-tau respectively. This removes the structural
inconsistency of the previous mixed free5/forced2 approximation without its extra
storage. It is only one necessary condition.

C1 also proves the candidate free response is negative at log-tau offset -1 and
dimensionless centre dose 1.5819767: Fhat=-0.0141623 while true F=+0.0135651.
Stable repeated poles and unit DC gain therefore do not make this a positive or
passive physical realization. This failure was recorded before fitting. It rules
out an unqualified physical-response claim, even though the representation can
still be studied as a bounded approximation.

The untuned signed-current probe at nine original offsets shows mixed value
results: at -1 total RC voltage defect improves 1359.65→1341.28 uV; at +1 it improves
1145.55→1069.77 uV. Near-centre value defects slightly worsen at +/-.13, despite
improved slope metrics. Centre matching is unchanged to rounding. These are
finite sampled probes, not bounds over all histories/support. H's known off-centre
limitations and loose uniform envelope are unchanged.

## Resource ledger: a factor budget is not a device budget

The candidate retains W34, packed factor 4760 B, native response 312 B and prior
domain/scalar allowance 96 B: **5168B partial subtotal**. Actual retained NumPy arrays
are 10408 B, unchanged from the baseline, with dense factor and separate large desktop
workspace/observations. There is no new native code, persistent numeric allocation,
per-sample work or claimed speedup; tanh/chain arithmetic is added at query time.

The separate provisional packed-C ledger charges immutable tables to SRAM and
uses the frozen fixture's diagonal public prior. It does not diagonalize the
retained likelihood or generic prior. The ledger is an illustrative layout, not
compiled C allocations or a general lower bound on every possible implementation.

| Named live set | Subtotal (B) | Important assumption |
|---|---:|---|
| Persistent factor/state/config/prior/tables | 6216 | Includes an assumed 32 B source digest |
| Streaming phase | 11600 | Persistent plus complete staged factor/state, sample, QR row |
| Inference phase | 11912 | Persistent plus materialized 34×16 Jacobian, packed 16D precision, gradient/trial |

The two phases are assumed serialized; do not add their totals. Both already exceed
10240 B before alignment, stack/scalar temporaries, library workspaces, recovery,
interrupt/input queues and several other costs. A general packed prior root would
add 960 B relative to the fixture diagonal scale. Actual peak memory is not qualified.
Avoiding duplicate factors or streaming derivatives may help, but must preserve
transactionality, evidence ownership and numerical behavior under separate proof
and implementation review. Such savings are not implemented or credited here.

## Decision and next requirements

The test followed the fixed-budget rule: derive one closed candidate, evaluate the
full joint behavior, retain failures and stop without raising rank. The conclusion
is **insufficient as the replacement**, not a return to independent repairs.

Before another candidate, formulate the shared-operator selection problem with
equilibrium, central derivative and physical-response constraints, joint score/
precision/query objectives, and W<=34. Pair it with a concrete transactional
stream/solve memory schedule. Explicitly decide which physical properties must
hold exactly and which can have rigorously bounded approximation error; do not
silently waive the negative-response failure. If no design meets the stated
constraints, expose that conflict rather than growing the factor.

Useful absolute Q/SOC/proposed-load accuracy and honest uncertainty remain the
application objectives. No new arbitrary error allowance, forgetting factor,
support restriction or lifetime promise is introduced. A physical aging model
and cumulative error argument remain separate obligations.

## Verification

Five focused tests cover native row/state/factor equality, storage, central jets,
equilibrium, full feature/transport chains, support, symbolic transfer and negative
witness, and joint QR/gating. [C1](c1_review_r1.json) and
[implementation](implementation_review_r1.json) have independent reviews. The
[result/probe/resource review](results_review_r1.json) independently reproduces the
study and checks the ledger's scope. [Validation](validation.json) and
[receipt](receipt.json) record final bindings. Production/defaults and mainline are
unchanged; generated runs remain local and ignored.
