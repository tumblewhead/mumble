# Constrained operator and memory contract

This stage resolves what the next approximation must preserve before another
candidate fit. It retains W<=34, the 4760B likelihood factor and 312B response
state, the full joint likelihood, original support/centres/prior and actual sample
intervals. Production kernels and campaigns are unchanged. Prior evidence:
[shared operator study](../../provenance/shared_operator_budget_001/README.md).

Four individually reviewed packets are required:
- [P1](P1.md): a shared three-jet family, exact all-age nonnegative relaxation and
  zero-state dissipativity conditions, central matching, and a limitation of
  smooth positive exponential banks.
- [P2](P2.md): joint score/precision/transport objectives, conditional fitted-query
  and covariance bounds, honest failure states and sustained-use obligations.
- [P3](P3.md): deterministic prevalidation/replay insertion, rowwise joint QR and
  concrete phase lifetimes, with explicit fault/recovery and resource exclusions.

- [P4](P4.md): a structural lower bound discovered during constraint derivation;
  at the fast support edge every monotone three-jet response has at least0.0745294
  absolute free-kernel discrepancy at age tau_c. This is not a fitted battery error.

Decision: stop map-only tuning for a uniformly small monotone free-kernel error
below that floor; retain this family as a reference. A different fixed-rank
realization needs a new closure/constraint proof. Do not select it from one
parameter's fit improvement. The first
next experiment is an isolated scratch-memory feasibility kernel for P3, independent
of any new physical approximation. Its successful path must match a copied-factor
reference, and its failure path must preserve rejection/quarantine ownership.
It must report real allocated scratch, helper stack and CPU cost before memory
savings are credited. This does not authorize promotion or weaken recovery needs.

Only after a different fixed-rank family has a proved shared closure and physical
constraints should a finite search be registered with P2's joint/application
criteria, fixed code/constants budget and held-out streams chosen before
optimization. Hard constraints are proved over original support, not judged on
samples. No new degrees/history features are a fallback. If relaxing central
exactness is needed, compare explicitly rather than silently changing its contract.
The P1 bank obstruction and P4 floor make these tradeoffs reviewable in advance.

Ages, temperature and cumulative approximation/rounding require separate closure.
The proposed schedule's8568B named peak (9528B with generic full prior) excludes
unqualified buffers and fault recovery; it is not a10KiB deployment claim.
An extra codebook or geometry layer is not needed for this stage. All proposed
error allowances remain unallocated; the user application's brownout margin and
forecast horizon are still needed before a deployment-oriented acceptance test.
