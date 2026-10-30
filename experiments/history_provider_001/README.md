# History provider boundary and algebra

The rolling optimizer and history representation now have a separately testable
**desktop query boundary**. The original solver, prior, model and compressed
history sources are unchanged. This is the first increment of the approved
four-step sequence, not a new compressor or firmware implementation.

[contract.json](contract.json) was written before the fabricated qualification.
[provider.h](provider.h) defines a common result object, and
[provider.c](provider.c) adapts exact C replay and the legacy compact bank.

## Two different objects

An **estimate view** says what the solver currently selected: a candidate point,
physical endpoint, numerical stop and uncertainty status. A **history message**
describes what the observations imply across possible candidates and how physical
state propagates through their interval. Only the latter owns evidence.

The point alone is not sufficient. For example, losses x² and 100x² share their
optimum but carry different local information. Even x² and x²+x⁴ share the
optimum and Hessian at zero while differing elsewhere. Combining either with
future observations need not produce the same answer. Reporting a point and
curvature is therefore not a general replacement for retained evidence.

The query result contains likelihood cost, the original16-coordinate gradient,
a packed Gauss–Newton matrix, five current physical states, evidence counts,
provider identity and native status/flags. GN is solver geometry, not a posterior
precision certificate. The original prior is excluded and belongs to the solver
once. Endpoint Jacobians and certified approximation bounds are not supplied by
these legacy adapters. Successful arithmetic is not a physical-fidelity claim.

The compact adapter clones the old context into host scratch before querying,
so even work counters and query workspace in the authoritative object remain
unchanged. Fixture append/commit helpers do not invoke the optimizer. The exact
adapter reuses the original C replay, without quantizing or changing observations
again. The harness supplies identically decoded and validated fixture inputs to
both providers. This adapter is not yet a generic callback inside `re_refine`.

## Algebra before representation

For a stationary deterministic block, the exact conceptual object includes
state transport Phi, evidence L, legal entry domain D and source ownership.
With A preceding B:

```
Phi_AB = Phi_B o Phi_A
L_AB(x) = L_A(x) + L_B(Phi_A(x))
D_AB = D_A intersect inverse_image(Phi_A, D_B)
```

Parameters are included in x; stationary parameters carry through unchanged.
Composition requires adjacent, nonoverlapping intervals, compatible state
epochs, model/calibration and charts. Identity, source-once ownership and
associativity are mathematical requirements. Chronological order cannot be
exchanged. Finite-precision error remains separate.

This function-level algebra does **not** prove a bounded coefficient object is
closed. A new representation must preserve both response transport and evidence
to its declared accuracy. The present increment specifies this algebra; it does
not implement a generic merge operator for the old compact factor.

Stochastic health evolution needs boundary-kernel composition integrating over
the shared state for marginal semantics. Minimizing over it instead is a profile
objective. Neither operation may be substituted silently. Aging and nuisance
correlations therefore remain later explicit design obligations.

## Complex analysis as a representation candidate

The stationary linear RC part has the rational response

```
Z_RC(s) = R0 + sum_i R_i / (1 + s*tau_i)
```

Its three negative-real poles and nonnegative RC resistances are physical model
structure. A complex-domain or rational approximation can be investigated as a
response basis. The model already has a compact three-pole response; the open
question is representing accumulated evidence over **uncertain** responses and
states, not merely writing a compact transfer function.

[AAA rational approximation](https://arxiv.org/abs/1612.00337) is a primary
reference for approximating functions on real/complex domains. It is not a
battery-history compression theorem, and no AAA dependency or implementation
has been introduced. Any candidate must preserve stability/passivity where the
model requires it, real outputs, support, input chronology, boundary-state
dependence and likelihood contrasts. A fit on a frequency grid alone cannot
qualify time-domain uncertainty or history ownership.

The transfer function does not encode the observations, nonlinear OCV,
sign-dependent hysteresis, initial-state ambiguity or aging. A real likelihood
does not automatically become a holomorphic function; any analytic continuation
would need a defined domain and approximation analysis. Complex coordinates do
not recover information already discarded by a point estimate.

The proposed geometry is distinguishability of physical responses and evidence
over declared candidate/continuation domains. It is distinct from solver GN
geometry and posterior uncertainty. No SCM/NAIA/D2 proof claim is made.

## Executed qualification

[development001/receipt.json](qualification/development001/receipt.json):
**776 checks passed**,236 queries,13264 conservatively counted model steps,
zero optimizer calls, no canonical observations and no truth reads. The strict
C build and source hashes are retained. Fabricated voltage codes are test data,
not a simulated accurate battery trajectory. These are interface checks and a
small representation diagnostic, not a new physical accuracy test.

Checks cover raw-block costs/gradients/GN/endpoints, bitwise exact-adapter parity
with native replay, public-scaled finite differences, at-anchor commit behavior,
source/order validation, evidence ownership, query immutability and atomic error
paths. Numerical allowances are finite host regression tolerances, not sensor
noise floors or coverage claims.

The33 query points and64 observations were frozen before evaluation. Measured
legacy representation errors were reported without aborting or passing them:

| Legacy construction | Centered cost-error oscillation |
| --- | ---: |
| Fixed anchor,8-record blocks | 71.903973 NLL |
| Fixed anchor,16-record blocks | 71.903973 NLL |
| Prescribed moving rate anchor,16-record blocks | 73.900940 NLL |

The two fixed-anchor arms give identical likelihoods at all sampled nodes, yet
both differ from exact replay away from the anchor. This separates consistent
composition from physical fidelity. The values depend on this fabricated fixture
and must not be equated with errors in the earlier four-hour trajectory.

The1296B query object, cloned8680B context and full replay/metric storage are
explicit desktop overhead. They are not added to a claimed10240B firmware budget.

## Progression

1. Common query object and first adapters: implemented and finitely qualified.
   General message composition remains a specified contract.
2. Representation-only harness: implemented and exercised on existing providers.
   The new bounded representation is not yet selected or qualified.
3. Reconnect the selected provider to the unchanged rolling policy only after
   fidelity and full memory/work feasibility. No new four-hour run yet.
4. Add explicit health transitions after fixing inference semantics and the
   physical model. No aging shortcut or automatic forgetting has been added.

Next: derive a coefficient/transport layout for the unknown3RC model, compare
the fixed response-basis and rational-response candidates on the same interface,
and reject a candidate that cannot fit or preserve the required dependence.
Repeated cost doubling of the full-path particle solver is not part of this task.
