# Distinct-pole history inside the full battery-estimation problem

This is a symbolic reconstruction of the supplied N13e handoff, following its
instruction not to rerun the original programs. Numeric outputs and the hex
pickle are inputs from the conversation, not independently certified results.
The [numeric extraction](../../provenance/distinct_bank_symbolic_001/incoming_checkpoints.json)
records their status. No pickle is executed and no battery simulation is run.

The larger objective remains the [saved problem statement](../next_history_representation_001/PROBLEM.md):
a continuous three-branch Foster estimator with SOC, Q, H, gamma_plus,
gamma_minus and uncertain incoming states; actual intervals/order, one owner per
observation, and useful joint uncertainty through weak use and physical aging.
Our comparison ceilings remain W<=34 and response state<=312B. The target is
approximately10240B complete subsystem SRAM at16MHz, not factor payload alone.

## Reconstruction packets and dependency order

1. [B1](B1.md): stationary distinct-pole closure, shared free/forced response,
   derivatives, sufficient physical constraints, and rigorous certificate recipes.
2. [D1](D1.md): the separate thermal-model choice, reduced-time error scaling,
   unknown-energy rebasing and physical aging path dependence.
3. [U1](U1.md): conditional bias envelopes, full joint score/precision requirements,
   final-query statistics, nonlinear containment and sustained uncertainty limits.
4. [C1](C1.md): exact surrogate likelihood, algebraic merges, approximate history
   replacement, and resource consequences including a Laplace counterexample.

All packet claims are conditional on their explicit premises. Reviews and
bindings are in the [report](../../provenance/distinct_bank_symbolic_001/README.md).
A certificate recipe does not certify the supplied matrix without arithmetic
and artifact evidence. The signed bank is a proposed representation, not a
selected production replacement. Original centres/support/prior remain intact;
allowing nonexact central response is an explicit design choice for this family.

## Handoff claim disposition

| Incoming section | Reconstructed scope and required corrections |
|---|---|
| 1–2, definitions and bank | B1. Unknown b is a readout coefficient with separate free features; setting xi(0)=b/R is not parameter independent. |
| 3.1, complete monotonicity | Not required for our accepted construction. We prove monotonicity/energy directly under the column inequalities; no external Bernstein theorem is needed. |
| 3.2, nonnegative saturation | Moment obstruction retained; an O(h^2) interpolation upper bound is available. The stated positive lower bound for every point inside a gap is not established and vanishes near nodes. |
| 3.3, centre obstruction | Re-proved for smooth nonnegative normalized weights and exact central response. Signed weights avoid this obstruction. |
| 3.4–3.5, physical cones | B1 proves conditional monotonicity and zero-state energy. An explicit P satisfying the matrix conditions certifies stored energy at a fixed query; no time-varying conclusion follows. |
| 3.6, all structural cones inadequate | Finite LP observations remain NUM; no universal exclusion or exponential convergence theorem adopted. |
| 3.7, finite statistics iff polynomial | C1 proves polynomial sufficiency and a narrow fixed-feature obstruction. Arbitrary encodings/domain restrictions require a more precise theorem. |
| 3.8, shifted union | B1 counts N+max k-min k for a containing consecutive bank; disjoint index gaps can make the actual union smaller. |
| 3.9, reduced time | D1 chooses charge-continuity explicitly; error constants require transformed input a(t)I(t) and output prefactors. |
| 4, fitting and certification | LP defines candidate construction, not a global certificate. B1 supplies validated finite-cell and tail obligations, with exact normalization or an explicit defect. No map refit/run in this stage. |
| 5, feature Gram and frozen anchors | C1 exact for declared surrogate in real arithmetic. Frozen anchors, candidate-independent weights and original prior ownership are premises. |
| 6, feature groups | Algebraic merging is valid under exact coefficient ties. Known gamma is not our unknown gamma_plus/gamma_minus problem. Thermal corrections need old-state simultaneous updates; aging readout expansion is not aging dynamics. |
| 7.1, derivative envelopes | B1/U1 retain true-kernel-plus-defect approach. Fitted grid majorants with2% padding remain uncertified. Triangle-absolute bounds are mathematically valid but may be too loose; they are not forbidden identities. |
| 7.2–7.3, bias/moments | U1 proves frozen-design CS/L1/WCS. Posterior4SD plug-in boxes are conditional; final-query Jacobian moments must actually be retained or bounded, with full memory cost. |
| 7.4–7.5, model/nonlinear checks | SSR at a fitted model does not generally have chi-square n law. Small Hessian variation does not alone prove an interior minimizer or coverage; exact Hessian, containment and full error terms are needed. |
| 8, absorption | Source ownership and chronology remain mandatory. Raw/chunk buffering, repeated tentative fits and all accumulator live sets require complete allocation/timing accounting. |
| 9, accumulation | Response contraction retained conditionally. Full score includes E^T r; relative precision need not stay bounded in weak directions. Constant asymptotic bias floors require information-growth assumptions. |
| 10.1, exact merges | Analytic ties retained. The supplied inverse scaling is correct; sampled SVD rank is not an exact global coefficient identity. |
| 10.2–10.3, truncation/float32 | Approximation and arithmetic error must be separately bounded. Full physical state with compressed likelihood still needs transport/error consistency. |
| 10.4, Laplace collapse | C1 gives a counterexample to using a small local omega as a global future guarantee. Repeated collapse needs cumulative remainder/region/recovery semantics. |
| 11–12, pitfalls/checkpoints | Valuable reported evidence; no independent reproduction or validation. The reported7-day growth remains an open rounding concern, not a ten-year certificate. |
| 13, transfer guide | Construction patterns transfer conditionally. The list of all theorems transferring unchanged is not adopted. |

## Resource and quality decisions

For the existing Taylor hysteresis block (12 features), affine OCV/charge/R0
block (3), and y coordinate (1), a shared bank and free rank give the illustrative
allocation W=N_union+r_free+16. Already N_union=13,r_free=7 yields W36,
a5328B binary64 root or2664B binary32 root. This is an example allocation, not a
minimum: different hysteresis/free representations may change it. Three branches
can share driven poles via summed output coefficients; their incoming states and
joint parameter coupling must still be represented. The table cannot establish
that13poles cover all three branch ranges to the supplied single-range error.

The13x27 map alone uses2808B binary64 or1404B binary32, before other tables.
Each packed p16 sensitivity accumulator is1088B in binary64. Keeping one per
error component, or a larger lifted-feature moment for final-query evaluation,
can dominate the factor. CS/L1-only envelopes are therefore a relevant lower-cost
option, subject to useful uncertainty rather than assumed equivalence to WCS.
These counts exclude helpers, stack, queues, prior, transactions and recovery.
A shared bank is not a full-device size estimate.

There are two independent compression questions:
- Can a smaller physical response/feature family meet application error budgets?
- Can reduced-precision arithmetic and repeated history replacement keep their
  accumulated defect within a useful admitted budget?

The stationary N13e checkpoint addresses the first only provisionally. A local
Laplace collapse or finite7-day float32 shift does not answer the second.

## Next concrete mathematical gate

Before porting this candidate, close a stationary full-model contract: a shared
union bank over the declared three RC ranges, explicit incoming-state representation,
unknown directional hysteresis closure, full joint query sensitivities, and a
complete error-statistic budget. Compare CS/L1 and WCS costs at identical scope.
Then specify reduction/quantization with a cumulative certificate, not a local
omega trigger. P3's isolated memory-schedule implementation remains useful and
independent of the chosen response family.

Known gaps are not filled by simulator truth, posterior-box shrinkage, dropping
nuisance uncertainty, or enlarging W after each failure. User-supplied coefficient
and result artifacts can later bind a separately authorized certificate audit;
this symbolic task neither requires nor reruns their original experiment.
