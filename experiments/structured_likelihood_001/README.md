# Structured likelihood storage

The first storage comparison is complete. **Neither tested layout is qualified
for the 10,240-B target.** Exact product packing saves 1,776 B at K=9 and
4,752 B at K=13, while retaining all mixed terms and the represented
Gauss–Newton metric in exact arithmetic. Its raw moments fail a cancellation
control. A fixed-rank square-root summary saves more retained storage, but small
ranks lose substantial information, update workspace exceeds SRAM, and the
nominal PSD remainder certificate needs a floating-point error treatment.

This establishes a storage API and concrete tradeoffs without changing the
rolling solver, physical model, priors, parameter domains or aging law.
The [plan](plan.json) was frozen before evaluation. The [implementation](storage.py),
[receipt](attempt001/receipt.json), [summary](summary.json),
[memory review](memory_review.json) and [verification](verification.json)
preserve provenance and failures. The branch is
`experiments/structured-likelihood-001`; the revision plus archived source
copies identify the uncommitted implementation and dependencies.

## Fixed reference and what is being measured

The eight source cases use the previous joint time-kernel RC representation at
K=9 and K=13, two declared domains, and 64/4,096 fabricated observations. The
97 local and 129 full-public query points are unchanged. Hysteresis remains
degree-four in physical rates and OCV degree-twelve in accumulated charge.
Every represented reference cost reproduces the predecessor within its frozen
arithmetic allowance. There is no new optimizer or plant-truth access.

The full residual representation is `r(x)=D phi(x)`, with
`G=D^T D`, `L=phi^T G phi/2`, `g=J^T G phi` and `GN=J^T G J`.
There are **99 features at K=9** and **123 at K=13**. The full QR factor is the
numerical reference. These feature counts are larger than the sixteen physical
parameters because they encode uncertain nonlinear responses and their products.

All added errors below compare a storage candidate with this *same represented
likelihood*. They are separate from its physical-model representation discrepancy
(for example, 0.132954 NLL at 4,096/local/K9). Rank storage does not improve the
underlying RC/hysteresis/OCV approximation. These short fabricated prefixes test
history accumulation; they do not establish learning, aging or long-run stability.

## Exact product packing needs more than scalar likelihood coefficients

Within one RC mode the query features are `R z^n` and `v_initial z^n`.
For a Gram subblock indexed by `(n,m)`, define anti-diagonal sums at `s=n+m`:

```
H0[s]  = sum G[n,m]
Hn[s]  = sum n G[n,m]
Hnm[s] = sum n m G[n,m].
```

`Hm=s*H0-Hn`. For a symmetric self block, `Hn=Hm=s*H0/2`.
The implementation stores `H0,Hnm` for each forced/forced and free/free block,
and `H0,Hn,Hnm` for their forced/free cross block: seven arrays of length
`2K-1` per mode. They give all contractions between `z^n` and `n z^(n-1)`
needed by the original-coordinate gradients and GN. Every cross-mode and
cross-family entry remains explicit. This is one exact packing, not a proof
of the minimum possible storage.

OCV self products use the identity
`T_i(C)T_j(C)=[T_(i+j)(C)+T_|i-j|(C)]/2`; 25 charge moments replace its
13-by-13 symmetric self block. All OCV/dynamic/observed-voltage cross terms stay.
The packed coefficients add under globally aligned source concatenation.
The desktop constructor uses a temporary full Gram; a target streaming
implementation of the packed arithmetic is not supplied or measured.

Why retain the weighted moments? Consider `phi=(1,z,z^2)` and two positive
definite Gram matrices:

```
G1 = identity(3)
G2 = [[1, 0, .1], [0, .8, 0], [.1, 0, 1]].
```

For every z, `phi^T G1 phi = phi^T G2 phi`. Yet with `J=(0,1,2z)`,
`J^T(G2-G1)J = -0.2`. The same scalar likelihood polynomial can correspond
to different residual-Jacobian GN metrics. The study checks this explicit
counterexample. It is therefore insufficient to pack only the polynomial cost
and claim that the solver metric or all uncertainty diagnostics were preserved.

| Layout | Packed evidence, B | Complete prospective reserve, B |
| --- | ---: | ---: |
| K=9 full QR | 39,600 | 48,520 |
| K=9 product packing | 37,824 | 46,744 |
| K=13 full QR | 61,008 | 70,792 |
| K=13 product packing | 56,256 | 66,040 |

The modest savings follow from retaining the large mixed blocks. Exact
algebraic structure alone does not remove those correlations. The numeric
ledger excludes index arrays that can be implicit loops or fixed ROM tables;
it is a prospective C layout, not Python process memory.

On ordinary queries, product-packed cost differences reach 3.25e-5 NLL,
and all mean-GN comparisons pass. In the zero represented-residual control:

| Evaluation | Cost |
| --- | ---: |
| Direct squared residual | 5.23e-22 |
| Full QR | 4.38e-19 |
| Product packing | **-7.41e-5** |

No result was clipped. This raw-moment form remains numerically unsuitable as
the replacement reference even though its contractions are correct in exact
arithmetic. It repeats the cancellation concern found in earlier moment storage.

## Rank-limited storage retains a discarded-information envelope

The second candidate keeps a fixed number of global square-root rows. Each row
can couple all parameter families; no cross block is declared independent or
silently zeroed. Ranks **1,2,4,8,16,32** were fixed before evaluation as storage
budgets, without a singular-value acceptance threshold or posterior tuning.

A fixed diagonal scale `W` bounds feature magnitudes over the declared support:
`phi=W psi`, with `|psi_j|<=1`. RC bounds use public amplitude support and
`rho^n`; hysteresis uses public amplitude bounds and bounded Chebyshev factors.
OCV uses `4.23 V` times absolute inverse-transform row sums divided by noise
scale. These are conservative bounds, not fitted centers. The inherited local
domain bounds nonlinear coordinates; amplitude support remains the full public
support. Original priors and joint uncertainty are unchanged.

For `A=D W`, retain a rank-r factor B and a nonnegative scalar delta such that,
in exact arithmetic,

```
0 <= A^T A - B^T B <= delta * identity.
```

A batch SVD retains r singular rows and takes delta as the square of the next
singular value. This is an offline comparison oracle, not a bounded-memory
construction. The streaming candidate appends each new scaled observation row
to B, truncates to r rows and adds the newly discarded largest squared singular
value to delta. PSD losses accumulate into the bound, without forgetting prior
observations or resetting state.

For any available original-coordinate query:

```
L_B = ||B psi||^2 / 2
L_B <= L <= L_B + delta ||psi||^2 / 2
|g_j-g_B,j| <= delta ||psi|| ||J_psi,j||
0 <= GN-GN_B <= delta J_psi^T J_psi.
```

The domain-wide cost width is at most `delta*F/2`. These formulas describe an
uncertain approximation to the *represented* likelihood. They are not calibrated
posterior coverage, a physical-noise model or a license to feed the smaller
metric to the solver as exact information. A usable inference integration must
carry the remainder uncertainty, in addition to physical representation error.

Adjacent globally aligned blocks merge by concatenating their factors,
truncating, and adding both inherited deltas plus the new discarded spectral
bound. Different merge trees need not give identical approximations; the
reference lies within the respective envelopes in exact arithmetic. Tests
reject overlapping, nonadjacent and incompatible source/configuration merges.
This does not establish transport between independently entered physical-state
domains or across aging transitions.

## Measured rank tradeoff

For the 4,096/local/K9 source case, streaming storage gave:

| Rank | Maximum absolute added cost error, NLL | Maximum queried nominal interval width, NLL | Retained factor plus inherited query/nonbank plan, B |
| --- | ---: | ---: | ---: |
| 1 | 805,635 | 1.90e11 | 9,720 |
| 2 | 649,008 | 1.16e10 | 10,512 |
| 4 | 244,581 | 7.61e7 | 12,096 |
| 8 | 8,971.73 | 155,932 | 15,264 |
| 16 | 3.58321 | 276.843 | 21,600 |
| 32 | 0.00010014 | 0.00062477 | 34,272 |

At rank 8, much of the absolute loss is nearly constant over these local
queries, but its error *oscillation* is still 1,032.42 NLL. Rank 16 oscillation
is 2.60244 NLL; rank 32 is 0.00017972 NLL. Thus a nearly constant offset must
not be confused with either a good full-likelihood representation or guaranteed
preservation of likelihood contrasts.

Batch and online constructions also differ. Local K9 rank 16 has batch maximum
cost error 0.44082 NLL versus 3.58321 online. At rank 32 the batch difference is
1.33e-6 NLL versus about 1.00e-4 online, where arithmetic is material. Batch SVD
is optimal for the scaled matrix's spectral approximation, not necessarily for
these particular nonlinear query costs; individual sampled errors need not order.

Broad support remains harder. Rank 32 at 4,096/full/K9 gives a 0.40711-NLL
maximum added cost error and up to 56.74 NLL nominal queried width. At K13,
these are 1.19294 and 119.41 NLL. This is added to an already imperfect physical
response representation. Repeated fabricated inputs can have special low-rank
structure; these results cannot establish compressibility of varied cell/load
histories or long-duration operation.

**The retained-only column is not a deployment budget.** Even rank 1 needs
append/SVD workspace. The primary receipt gives explicit workspace lower
ledgers; the [separate memory audit](memory_review.json) adds a simultaneously
live old/new factor allocation omitted from those lower ledgers. At K9/rank1,
the known-array subsystem lower bound is **13,728 B**, before numerical-library
workspace. At rank8 it is **36,576 B**; at rank32 **120,864 B**. Every tested
layout exceeds the complete target with update storage accounted for.
No Cortex-M23 SVD implementation, speed or measured stack footprint is claimed.

## Numerical failures and limits of the envelope

The run completed all eight source cases, 48 batch/stream rank pairs and eight
rank-8 merge controls in 7.30 s on this host. It performed 1,125 checks and
retained **26 aggregate numerical flags**:

- 16 global scaled-Gram PSD envelope comparisons.
- 3 rank-32 gradient envelope comparisons.
- 2 ordinary product-packed cost and 4 product-packed gradient comparisons.
- The product-packed zero-residual cancellation failure.

The PSD theorem is exact-arithmetic; the present floating-point implementation
does not yet provide its certificate. At local K9/rank32, the nominal queried
interval width reaches 0.00062477 NLL, but some computed lower endpoints exceed
the direct cost by about **0.00010014 NLL**. The raw violation is explicitly
saved even when it falls within the inherited finite regression allowance.
In scaled coordinates the global remainder has minimum eigenvalue about
**-0.12936**, versus a nominal delta of **0.00044891** and the frozen numerical
allowance **0.023236**. It therefore cannot be called PSD at this precision.

Source hashes, domains and work caps passed. No numerical tolerance was relaxed
and no candidate was silently repaired. Work counts were 540,800 model-node
steps, 6,240,000 full convolution products and a reserved upper count of 119,952
SVD calls, within the frozen limits. SVD dominates a prospective update and must
be measured on its own; study runtime is not firmware throughput.

## Decision and next concrete design

Retain the product-moment derivation and the factor-plus-remainder query contract
as useful reference objects. Do not adopt either current storage implementation.
The complete resource ledger and numerical failures prevent that decision,
without inventing a new NLL threshold.

The next bounded design should exploit the residual's large common voltage
component before compressing it: an invertible translation about a fixed public
reference, preserving the constant residual energy and its cross terms, can be
compared with the present coordinates. It must not substitute the fitted answer
for earlier evidence or center on truth. Protecting that component may improve
conditioning and make a block-specific remainder more informative than the
single global spectral bound. This is a hypothesis, not an established saving.

Before another rank sweep, derive its complete live-workspace layout and an
explicit two-sided floating-point remainder bound. Keep the reference queries,
uncertain parameter support and source ownership. A candidate that requires
dense SVD workspace beyond SRAM is not a deployment proposal, regardless of its
retained factor size. No long-trajectory qualification or aging integration is
implied by this storage study.

Reproduce only into a fresh exclusive directory:

```sh
python3 -B experiments/structured_likelihood_001/analyze.py experiments/structured_likelihood_001/new_attempt
```

The completed study exits nonzero when numerical flags remain; its receipt
distinguishes completion from a hard failure. Archived inputs and source hashes
are authoritative.
