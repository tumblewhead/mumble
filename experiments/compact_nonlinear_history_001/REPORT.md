# Compact nonlinear history: useful local maintenance, unresolved public-start acquisition

## Decision

**Keep the new C representation for local maintenance; change the bootstrap and constraint handling before treating it as an autonomous M3 estimator.** The finite experiment completed once, with all captures and resource accounts intact. One bank retains a full joint nonlinear likelihood approximation without raw observations or heap allocation. At the previously obtained autonomous anchor, it preserves the tested local likelihood ratios much better than the affine restriction and supports updates from 42,000 additional samples. A bank fixed at the public mean has large historical approximation errors near that same anchor. Its search also encounters a separate physical-bound limitation.

These findings qualify a concrete bounded component. They do not establish calibrated SOC/capacity intervals, global likelihood fidelity, nonlinear convergence or deployed Cortex-M23 operation. No truth was read. The [saved-output summary](reporting001/summary.json), [reporting receipt](reporting001/reporting_receipt.json), [receipt review](receipt_review.json) and [independent saved-algebra review](qualification/saved_algebra_review.json) preserve the evidence. The [decision](decision.json) records the selected scope.

## What was implemented

The [C bank and API](compact_history.h) use the original sixteen entering-state/parameter coordinates, including initial hysteresis state `h0`. At one immutable origin, each arriving observation supplies a signed second-order voltage-residual polynomial:

\[
\widehat r_k(\delta)=r_k+g_k^T\delta+
\frac12\delta^T H_k\delta,
\qquad x=x_a+\operatorname{diag}(S)\delta.
\]

The model has twenty nonzero Hessian pairs in this chart. Sixteen linear terms, those twenty quadratic terms and a residual constant form a 37-column augmented row. Incremental QR stores its summed squared residuals in **703 doubles, or 5,624 bytes**:

\[
\widehat L(x)=\tfrac12\|R\phi(\delta)\|^2.
\]

This is a nonnegative quartic likelihood approximation. It retains signed residual–Hessian, Jacobian–Hessian and Hessian–Hessian correlations, addressing information lost by the earlier norm-only remainder treatment. Every nuisance direction remains coupled to SOC and capacity. Zeroing the quadratic monomials gives an affine control using the same factor, without a second ingestion or second bank. See [implementation](compact_history.c), [frozen contract](../../plans/compact_nonlinear_history_001.json) and [earlier remainder analysis](../../docs/BOUNDED_EVENT_002.md).

The bank carries the model state and signed derivatives at its original origin. Each ADC-style sample advances them once, in source order, using its actual interval and current. Changing the estimated point does not replace this state, renew the approximation origin or relinearize discarded history. Current SOC is evaluated exactly from entering SOC, log capacity and cumulative charge; RC and hysteresis states away from the origin are labelled second-order approximations.

Queries support cost, full gradient, Gauss–Newton matrix and true polynomial Hessian. Refinement uses the full joint sketch Gauss–Newton matrix plus the public kernel precision as optimizer geometry. Unmodified scaled Cholesky, a one-public-SD step cap, physical-support checks and eight fixed trial fractions precede quarter-slope Armijo acceptance. Acceptance concerns the represented likelihood plus the exact common mixture prior. Exact-history audits cannot influence it. This metric is not a posterior covariance.

The original equal-weight Gaussian mixture is conditioned as one law on common support in the original `dx` measure. The prior occurs once, separately from the observation rows. Its common support normalizer cancels only in within-prefix objective contrasts. There is no previous-posterior duplication, variance inflation, covariance repair, parameter clipping or truth-selected threshold.

## Finite experiment and point results

Two separately accounted banks consumed 294,000 samples, with refinement at 252,000 and 294,000 samples—nominally 7,200 and 8,400 seconds. The public-origin arm starts at `PUBLIC_MEAN`. The autonomous-origin arm starts at the independently verified generation-seven point from the previous anchor experiment. Its first prefix encoding is retrospective; only the additional 42,000-sample suffix tests subsequent maintenance. The previous anchor invocation remains **failed**, with its verified partial result preserved.

Forty-two external original-model trajectories supplied fixed comparison points. Two additional children audited the four chosen candidates only after primary inference closed. These external arrays and evaluations are qualification machinery, not retained candidate history or runtime feedback. All fixed points were available; none was dropped or replaced. See [primary capture](attempt001/calls/primary/raw_probe.json), [7,200-second candidate audit](attempt001/calls/audit252000/raw_probe.json) and [8,400-second audit](attempt001/calls/audit294000/raw_probe.json).

| Origin | Time | Estimated Q, mAh | Endpoint SOC, % | Audited likelihood plus cached prior |
| --- | ---: | ---: | ---: | ---: |
| Public | 7,200 s | 73.720935 | 47.958019 | 230,043,811.165772 |
| Public | 8,400 s | 73.720935 | 27.611018 | 236,251,933.952089 |
| Autonomous | 7,200 s | 64.703748 | 51.602860 | 126,413.134104 |
| Autonomous | 8,400 s | 64.696861 | 28.419189 | 147,432.694532 |

These are estimates and objective comparisons, not truth errors. Every refinement ends `no_accepted_trial`, explicitly unresolved. The public bank accepts seven steps at the first checkpoint and none at the second. Its final entering `h0` is −0.9991571349; all eight final fractions at each checkpoint would cross the lower bound. No objective is evaluated for those infeasible trials. The eight-fraction search therefore does not establish constrained stationarity or the best represented point.

The distinction matters: at 7,200 seconds the public bank assigns about **18.917 million** likelihood cost to the declared autonomous anchor, below the **188.060 million** at its returned candidate. Search limitations remain visible. Independently, the public candidate's represented-minus-exact likelihood discrepancy is **−41,983,387.252**, and the fixed-node comparison below demonstrates substantial distortion even without relying on the chosen point.

The autonomous bank accepts one initial tiny refinement and two full suffix steps. At 8,400 seconds its audited common objective improves by **17.48326345** relative to keeping the original autonomous point at that same prefix. Its represented-minus-exact candidate likelihood discrepancy is **+0.0000045665**. The last eight warm trial decreases remain below the declared arithmetic acceptance allowances; that stop establishes neither a KKT result nor nonlinear convergence. At the final candidate, represented SOC equals the exact model's SOC, and the hysteresis approximation differs by **−1.5064×10⁻¹¹**. The public candidate's hysteresis discrepancies are much larger: −0.08053 and +0.06366 at the two checkpoints. These compare state approximations with the same candidate's exact trajectory, not with truth.

## What the fidelity comparison establishes

For each saved point, define `e = L_compact − L_exact`. A constant error offset cancels from likelihood ratios. The variation `max(e) − min(e)` measures the largest pairwise log-likelihood-ratio distortion on the specified finite node set. The report retains raw offsets, errors centred at each bank's origin, errors centred at the common autonomous anchor, and every node/status.

| Origin | Time | Set | Affine error oscillation | Quartic error oscillation |
| --- | ---: | --- | ---: | ---: |
| Autonomous | 7,200 s | 41 local nodes | 0.026174861 | 0.000469334 |
| Autonomous | 8,400 s | 41 local nodes | 0.022707280 | 0.000521386 |
| Autonomous | 7,200 s | Eight target nodes plus anchor | 0.013862358 | 0.0000134304 |
| Autonomous | 8,400 s | Eight target nodes plus anchor | 0.014301231 | 0.0000427769 |
| Public | 7,200 s | 41 nodes around autonomous anchor | 96,890.080 | 37,737.811 |
| Public | 8,400 s | 41 nodes around autonomous anchor | 128,592.138 | 43,235.598 |

The local set contains the autonomous anchor, both signs of sixteen full-joint metric-whitened directions, and four steps on each coupled logQ/SOC direction. These were frozen before execution. They are curvature-predicted paths, not exact nonlinear profiles, posterior samples or credible-interval endpoints.

The quartic extension materially improves the measured local representation. It does not rescue distant-origin compression: the public bank's large error oscillation cannot be explained by an irrelevant constant offset. Conversely, evaluating the warm quartic sketch at the distant public point produces an all-42-node oscillation of about **589 million** at 7,200 seconds and **584 million** at 8,400 seconds. Local success must not be promoted to global posterior fidelity. No continuous-region error bound, tail-mass calculation or coverage test was performed.

## Work, memory and M3 limits

[Independent fabricated qualification](qualification/attempt001/receipt.json) passed all sixteen cases and 6,066 assertions before the canonical run. It checked full sixteen-dimensional automatic-differentiation oracles, sparse Hessian signs, QR polynomial identities, prior derivatives, source chronology, failure invalidation and bounded refinement. A pre-execution status-propagation defect was repaired while preserving the earlier source/build; unexpected numerical errors cannot masquerade as ordinary unresolved stops.

The once-only scientific invocation used **14,028,000 model steps**, fourteen proposal rounds, 48 attempted trial fractions, 384 compact queries and 48 exact-prior evaluations. Twenty-six fractions required a cost evaluation; the remaining trials were infeasible. Only 588,000 model steps belong to the two live banks. External qualification accounts for the rest. Whole-process CPU was **6.866106 s**, active wall **6.935785 s**, wait4 peak RSS **19,169,280 bytes**, and closed runtime output **758,011 bytes**. All four original/independent-copy capture pairs remain intact. Reporting added no model, prior, optimizer, observation or truth access.

| Single-candidate allocation | Bytes |
| --- | ---: |
| Persistent bank, including the 5,624-byte factor | 6,368 |
| Shared ingestion/query/refinement workspace | 1,600 |
| Result and incoming sample | 144 |
| **Implemented core** | **8,112** |
| ADC reserve: sixteen decoded samples plus metadata | 448 |
| Checkpoint codec reserve | 128 |
| **Owned operational layout** | **8,688** |
| Own-source stack planning cap | 768 |
| Caller, libm and interrupt reserve | 768 |
| **Planned complete subtotal** | **10,224** |

Only **16 bytes** remain under 10,240. The reserves are explicit obligations, not implemented drivers or measured target stack. Sixteen samples cover about 0.457 nominal seconds; this is not proof that worst-case refinement fits the delivery horizon. Host compiler call-chain evidence fits the own-stack cap, but M23 ABI, software-floating-point latency, interruption, checkpointing and actual acquisition scheduling remain unqualified. The external host harness owns 203,768 static bytes, including both banks, oracles and traces; its RSS is reported separately. This candidate replaces the earlier learner rather than being added to its allocation.

## Next bounded engineering decision

Retain the local quartic bank and its qualified C implementation. Change public-start acquisition and the handling of active constraints. A support-aware full-joint direction is needed before treating the current boundary stop as an optimization result, but a better solver alone cannot restore nonlinear information lost at an unsuitable fixed origin.

The next bounded design should specify a causal bootstrap/transition, the ownership and approximation of every pre-origin observation, and a feasible constrained proposal within the same complete allocation. Qualify that transition on finite fabricated cases before one newly frozen live comparison. It must preserve old evidence once, expose unresolved approximation error, and never present polynomial translation as fresh historical relinearization. This completed experiment is not extended or retried, and no further run is queued by this decision. Honest SOC/Q intervals and measured M3 operation remain explicit requirements.
