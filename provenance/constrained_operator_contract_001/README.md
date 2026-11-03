# Structural constraints expose a limit before another repair

We specified the next physical, joint-inference and memory contracts without
changing estimator code, campaign defaults or history rank. The main discovery
is a lower bound: no query map on the current three central RC jets can make
its free response arbitrarily accurate AND monotone over the original support.
That makes another map-only tuning run unjustified as a route below this floor.
It does not show that all fixed-budget history representations are inadequate.

## Physical response: exact constraints and a concrete obstruction

[P1](../../specifications/constrained_operator_contract_001/P1.md) writes the
existing shared response as exp(-d)(1+alpha*d+beta*d^2). Nonnegative impulse
response and nonnegative real driven transfer reduce to explicit quadratic
inequalities on alpha,beta. These enforce monotone relaxation, bounded response,
unit DC gain and zero-state dissipativity for the stationary branch. They do not
certify the entire battery, arbitrary internal initial conditions, or inference.
Free and forced response use the same functional and chronological recurrence;
query derivatives retain the complete physical parameter chain.

[P4](../../specifications/constrained_operator_contract_001/P4.md) derives the
consequence. At the admitted fast endpoint tau=tau_c/e and elapsed age tau_c,
EVERY monotone response in this three-jet family has

    Fhat - F >= (3-sqrt(5))/(2e) - exp(-e) = approximately 0.0745294.

The symbolic positive floor is also proven greater than1/24 without relying on
floating evaluation. The derivative at age zero is limited too: normalized
impulse height cannot exceed2, while the reference requires e. The value bound,
not the slope observation alone, establishes a uniform-approximation limitation.
Adding the energy/central-matching constraints cannot remove that lower bound.

This is a7.45-percentage-point discrepancy in a dimensionless isolated free
kernel, NOT7.45% terminal-voltage, Q, SOC, fit or forecast error. Voltage scaling
requires the incoming branch voltage; multiple branches and refitting can alter
the system consequence. No application tolerance has been allocated to turn it
into a universal deployment cutoff. It is enough to stop trying to tune this
same family below the proven kernel floor.

A positive-weight bank of distinct fixed exponentials has a different conflict:
exact response at an interior centre forces all mass onto that centre pole, and
smooth nonnegative weights then have zero first query derivative there. It cannot
also match the physical centre sensitivity. Signed weights, repeated poles,
approximate central matching and other realizations are not ruled out. These
tradeoffs should be explicit before selecting the next fixed-rank realization.

## Joint objective: no hidden exchange between parameters

[P2](../../specifications/constrained_operator_contract_001/P2.md) keeps joint
whitened score error, relative precision error, same-anchor query error, fitted
query error and full transported covariance as separate criteria. It derives
conditional application bounds for affine stationary fits and a separate
nonlinear exact-Hessian condition. Small local SDs are not physical coverage.
A failed sufficient certificate is inconclusive; unresolved reference fits
cannot support fitted-error claims.

Original support/prior/centres, source identities and actual intervals remain.
Neither independent marginal fits nor a weighted sum that conceals a hard failure
is proposed. Application guidance such as approximately1% Q is not a compressor
error allocation. Voltage margin and proposed-load horizon still need application
requirements. Fixed per-record approximation error can outgrow statistical width;
aging, rounding and ten-year authorization remain separate unresolved obligations.

## Memory: an explicit conditional schedule

[P3](../../specifications/constrained_operator_contract_001/P3.md) proposes a
read-only QR validation pass, followed by deterministic replay into the same factor.
This avoids a second4760B history root. It preserves the complete old state on
anticipated validation failures. A mid-write fault has NO rollback copy: readers
must be revoked and the state quarantined until ownership-aware recovery.
This is a safety alternative allowed by A4, not an unattended availability proof.

Joint inference can generate derivative rows on demand and accumulate an augmented
17D QR root. This retains every parameter cross term and the original prior while
avoiding a stored34x16 derivative matrix. It trades extra derivative evaluation
for memory and must not be reported as a CPU improvement.

| Serialized phase | Named total, including persistent data |
|---|---:|
| Streaming | 6840 B |
| Joint fitting | 8424 B |
| Scalar query and transported sensitivities | 8568 B |

The maximum named subtotal is8568B, leaving1672B unallocated against10240B.
With a general packed prior instead of the fixture's diagonal prior it is9528B,
leaving712B. The history factor remains4760B and response state312B. No ROM
savings, omitted uncertainty or hypothetical width reduction is credited.
The earlier comparable streaming/fit named totals were11600/11912B.

These are paper counts, not measured free SRAM: actual response/feature helpers,
stack, alignment, queues/interrupts, synchronization metadata, outputs, recovery
storage and certificate machinery remain unqualified. Input service time must
also accommodate two QR passes and serialized queries. The design could fail
its complete memory, CPU or useful-recovery requirements despite these subtotals.

## Verification, review and decision

[Finite checks](checks_r2.json) include33 rational local feasibility points,
200 transfer identity checks,200 lower-envelope checks, retention of the Cayley
failure, four QR sizes, eight nonfinite prevalidation rejections,764 detected
post-write fault positions in a toy authority model, a dense joint QR/solve/
covariance comparison, and100 affine joint-bound cases. The original check result
and source are preserved; no battery trajectory was simulated in this stage.
Toy interruption checks do not implement a device's fault detection or reset logic.

Independent per-proof reviews are recorded in [P1 r1](p1_review_r1.json),
[P1 r2](p1_review_r2.json), [P2 r1](p2_review_r1.json), [P2 r2](p2_review_r2.json),
[P3](p3_review_r1.json) and [P4](p4_review_r1.json). Review removed an unsupported
minimal-storage assertion from P1 and added the missing candidate-stationarity
premise to P2. Original drafts and the nonconvex-support counterexample are kept;
revisions received fresh independent review. [Integration review](integration_review_r1.json)
checks the checker, report, source bindings and resource scope. The
[receipt](receipt.json) records final disposition and exact artifact identities.

Next: an isolated P3 memory feasibility kernel, without choosing a new physical
approximation. Measure real scratch/stack and computation, compare against a
copied-factor reference, and inject ownership/failure cases. Before a later
response experiment, derive a different fixed-rank realization's shared closure
and physical bounds, then register P2's joint selection and held-out streams.
Do not add history features, hide discarded uncertainty, narrow support, or waive
physical constraints to improve one trace. No implementation or promotion of
these proposed savings has occurred in this stage.
