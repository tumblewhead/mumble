# Symbolic reconstruction of the N13e history proposal

The shared stationary bank is a viable mathematical construction under explicit
column inequalities and error certificates. It removes parameter dependence from
streamed driven states while keeping continuous parameters in the readout. Its
exact Gram factor is an exact likelihood for the declared surrogate, with full
cross terms. These are conditional algebraic results; no supplied numerical bound
or complete estimator size is independently verified by this reconstruction.

The user requested symbolic recreation inside the larger problem, not a rerun.
We did not execute the hex pickle, original programs, map fitting, or simulations.
The [checkpoint extraction](incoming_checkpoints.json) records selected reported
N13e values:13poles,27control columns, free-response error7.7349e-7 and the reported
first/second derivative and L1 bounds. Those values remain NUM. The extraction
is not a byte-for-byte archive of the pasted certificate or coefficient artifact.

## What the reconstruction establishes

[The integrated specification](../../specifications/distinct_bank_symbolic_001/README.md)
maps every incoming section to accepted conditional algebra, required corrections,
or unresolved numerical/physical premises. Four proof packets support it:

- [B1](../../specifications/distinct_bank_symbolic_001/B1.md): parameter-independent
  driven states plus free-response features; shared equilibrium/chronology;
  sensitivities including unknown incoming voltage; column-wise physical conditions;
  interval finite-cell/tail certificate procedures and shift reuse.
- [D1](../../specifications/distinct_bank_symbolic_001/D1.md): charge-continuity versus
  voltage-state thermal models, reduced-time bounds, unknown activation-energy
  relinearization, physical aging convolution and response-defect propagation.
- [U1](../../specifications/distinct_bank_symbolic_001/U1.md): conditional CS/L1/WCS
  bias bounds, full score/precision error, final-query sufficient statistics,
  nonlinear containment and sustained uncertainty limitations.
- [C1](../../specifications/distinct_bank_symbolic_001/C1.md): exact surrogate
  likelihood and algebraic transforms, narrow OCV closure results, cumulative
  likelihood/posterior comparison, and the limitation of a local Laplace trigger.

## Corrections with architectural consequences

The full score defect still contains E^T r. A residual envelope alone cannot
bound the shift between two fitted nonlinear models. The conditional frozen-design
bias bound is useful, but is a different claim. Precision distortion can grow
with duration when false sensitivities enter an unexcited direction.

Weighted bias accumulators require Jacobians at the final query. Accumulating
Jacobians at changing online estimates and relabelling them as final derivatives
is not exact. Exact feature-moment contractions may supply those derivatives,
but their storage must be paid for. A posterior4SD box is not a deterministic
parameter bound; a self-consistent, qualified joint region is needed.

Thermal charge continuity adds a Cdot term when written in voltage coordinates.
The reduced-time error bound includes ||a_T I|| and output/initial-state thermal
prefactors. Unknown E_tau rebasing has a sequence of local errors to propagate.
Physical aging changes the whole convolution path. Endpoint drift features alone
do not supply that dynamic model or its discrepancy certificate.

A small local Hessian-variation number does not establish an interior minimizer
or authorize irreversible deletion of old nonlinear likelihood shape. C1's quartic
example proves that new evidence can move a fit outside the old local region,
where the deleted shape matters. A Laplace collapse needs a region/remainder/tail
and cumulative replacement contract, or a recoverable representation.

Fitted SSR is not generally chi-square n; nuisance fitting, priors, nonlinear
constraints and estimated noise change its law. No residual test universally
reveals wrong behavior in unexcited directions. A fixed single-check threshold
also needs a separate repeated-use false-alarm argument.

These points do not reject the distinct-pole family. They distinguish the useful
stationary construction from the additional promises needed for sustained use.

## Memory implications

Our full model retains three branches and unknown directional hysteresis rates.
Using the existing12-feature H block,3affine features and y, an illustrative
shared-bank allocation has W=N_union+r_free+16. N_union13 and free rank7 already
produce W36:5328B binary64 or2664B binary32. This example is not a lower bound or
proof that a smaller joint representation is impossible, and13poles are not
assumed to cover all branch ranges at the single-range error constant.

The13x27 weight table alone costs2808B binary64 or1404B binary32. A packed16D
sensitivity matrix costs1088B binary64 per retained component; lifted final-query
moments can cost more. Selecting lean CS/L1 accounting may trade interval width
for memory, but it needs the same validity premises and a useful application
budget. Response state, tables, prior, buffers, scratch, stack, transactions and
recovery still share the approximately10KiB SRAM target.

The user-reported7-day float32 drift and unbounded parameter-space collapse
error directly motivate keeping arithmetic and replacement errors explicit.
Neither is resolved by the stationary kernel certificate. No total estimator
size or target speed is claimed here.

## Review, preservation and next step

Individual fresh-context reviews are [B1](b1_review_r1.json), [D1](d1_review_r1.json),
[U1](u1_review_r1.json), and [C1](c1_review_r1.json). C1's phrase "scaling correction"
is a nonblocking wording issue: the incoming ALG10.1 already has the correct
inverse scaling. This reconstruction verifies that direction; it does not identify
a scaling-sign defect in the user's formula. No source rewrite is needed for the
mathematical disposition, and the reviewed proof hashes are preserved.

[Integration review](integration_review_r1.json) and [receipt](receipt.json) bind
the final artifacts. Earlier study results and their source bindings remain
unchanged; updated root metadata resolves older snapshots at the base revision.
No new estimator kernels, experiments, default changes or promotion occurred.

Next close the stationary FULL-model representation and cost contract: common
RC bank domain, uncertain free states, unknown hysteresis-rate closure, joint
query sensitivities, and lean versus weighted error statistics. Define the
cumulative arithmetic/replacement certificate before reducing stored precision or
collapsing the old factor. The independently useful P3 memory-schedule kernel
remains available as an implementation experiment after its existing gate.
