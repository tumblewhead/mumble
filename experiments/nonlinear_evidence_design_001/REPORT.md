# Nonlinear evidence design 001

## Decision

**Select exactly two persistent nonlinear components, initialized by one public
capacity split, as the next falsifiable bounded learner design.** Each component
carries its own physical state and full joint local covariance. Predictive
likelihoods determine their relative weights. Neither component is pruned or
restarted, and their moments are never collapsed back into the inference state.

The [design contract](../../plans/nonlinear_evidence_design_001.json) and
[small comparison plan](../../plans/nonlinear_hypothesis_falsification_001.json)
are frozen. This study completed one selective saved-evidence audit and one
host C layout probe. It performed **zero estimator inference runs, zero raw
trace replays and zero new primary comparisons**. Production
`src/scm_online.c` is unchanged. No capacity improvement has yet been measured.

The proposed complete SRAM allocation is **10,032 bytes**, including a full
staged bank, acquisition, persistence buffer and stack/runtime reserves. The
host layout declarations match that arithmetic; the implementation and actual
Cortex-M23 resource/timing qualification remain open.

## What the frozen failure tells us

The [new audit](primary/evidence_audit.json) reads selected saved queries and
scoring vectors from `bounded_online_002`. It hashes every evidence input and
does not run the estimator. The control arm's wrong, narrow capacity belief
appears before its first current reversal at 400 seconds:

| Time | Capacity estimate | Scored capacity error | Largest local two-SD halfwidth, relative to estimate |
| --- | ---: | ---: | ---: |
| 120 s | 60.1715 mAh | -6.9993% | 4.5735% |
| 400 s | 74.4008 mAh | +14.9935% | 1.0846% |
| 600 s | 40.3857 mAh | -37.5801% | 0.8127% |
| 900 s | 50.1277 mAh | -22.5229% | 0.07936% |
| 2100 s | 59.8230 mAh | -7.5379% | 0.03375% |

These widths are local Gaussian diagnostics, not coverage statements. The
first negative dwell coincides with strong nuisance-boundary activity and a
large capacity movement. That association does not establish causal direction,
and reversal behavior cannot be the sole origin of the earlier wrong belief.

At the final saved endpoint, evaluating the observation equation at the
estimated and scored true vectors gives this voltage-error decomposition:

| Contribution | Estimated minus true contribution |
| --- | ---: |
| OCV from SOC | -57.44054 mV |
| Ohmic drop | -0.26380 mV |
| RC voltages | -0.05789 mV |
| Hysteresis | +57.58047 mV |
| Total model voltage | -0.18175 mV |

The large OCV and hysteresis errors nearly cancel. A small terminal voltage
error can therefore coexist with a wrong hidden-state combination. The final
innovation EWMA near one does not resolve that ambiguity or erase its earlier
large values. This is a measurement-equation evaluation of saved results, not
an inverse fit, a new trajectory or evidence supplied to initialization.

### A consistency witness that does not use truth

There is also a stronger model-consistency issue. From 1500 to 2100 seconds,
the prescribed current remains positive. For the inherited deterministic
hysteresis model, any entering state in `[-1,1]` and any allowed
`gamma_plus >= 5` imply

\[
h(t) = 1 + (h_{1500}-1)e^{-\gamma_+q(t)}
\quad\Longrightarrow\quad
h(t) \geq 1-2e^{-5q(t)}.
\]

The positive charge in that interval is 0.00525 Ah. The resulting final lower
bound is approximately **-0.94818307**, but the saved mean is **-0.96078193**,
below it by **0.01259886**. The saved 1800-second point also violates its bound.
The bound uses public model supports and the prescribed input schedule, not
synthetic state truth. It assumes the frozen primary consumed that schedule,
as recorded by its existing provenance. This audit does not reopen raw CSVs.

This is an analytic real-arithmetic bound evaluated with ordinary double/libm,
not an outward-rounded C certificate. It shows that the approximate belief
can leave even a broad model-reachable hull. Enforcing this particular hull
would trim only a small part of the much larger SOC/hysteresis compensation
error; it is not established as a capacity remedy. The two-component proposal
also does **not** automatically enforce global physical-history consistency.

Existing full-history M1 results eventually find accurate targets at 1800 and
2100 seconds, while M1 itself is unresolved and inaccurate at 900 seconds.
Those saved results argue against declaring the complete trace uninformative.
They do not establish that two local components, or any particular small
window of raw data, can reproduce the full-history result.

## The selected representation

The proposal is a conventional Gaussian-mixture filtering approximation, with
exactly two retained components. The general use of weighted Gaussian sums
for nonlinear Bayesian filtering dates to
[Sorenson and Alspach (1971)](https://doi.org/10.1016/0005-1098(71)90097-5).
That methodological reference does not establish this project's accuracy,
resource fit or the adequacy of two components.

For each component, retain all sixteen existing coordinates, including
capacity, SOC, the RC states and hysteresis, with a full lower covariance
factor. This keeps local correlations within each component. The two
components follow distinct nonlinear trajectories from initialization, rather
than branching only after the first local belief has become narrow.

### One fixed public split

Let the inherited public log-capacity prior have mean `mu` and standard
deviation `sigma`. Use equal weights and

\[
\mu_\pm=\mu\pm\sqrt{2/\pi}\,\sigma,
\qquad
\sigma_\pm^2=(1-2/\pi)\sigma^2.
\]

These are Gaussian moment approximations to the two half-Gaussian conditionals.
All other public initial means and variances remain unchanged. Their
within-component variance plus between-component variance recovers the
original log-state mean and covariance in real arithmetic. The audit finds
zero mean difference and a variance difference of `-8.33e-17` from rounding.

The two capacity points are **45.4692 mAh** and **79.1746 mAh**. Both come solely
from the existing public 60 mAh center and public support width. Their initial
aggregate point, defined below, remains 60 mAh. No scored cell capacity or
saved fitted state selects either starting point.

Matching two moments does not preserve the original prior density. The
Gaussian approximations overlap, change higher moments and are not disjoint
hard capacity regions. The comparison therefore tests a representation change
together with its nonlinear filtering paths. A positive result would not
uniquely attribute improvement to retained historical nonlinearity.

Capacity is the split direction because it is the declared failing target and
enters transport through `1/Q`. There is no search over directions, component
counts, offsets, hysteresis anchors or starts against Cell B's scores.

### Evidence enters once

For each voltage, component `j` first predicts an innovation `r_j` and its
variance `S_j`. Its score is

\[
\ell_j=-\tfrac12\left(\log S_j+r_j^2/S_j\right),
\qquad
\log w'_j=\log w_j+\ell_j-\operatorname{logsumexp}_k(\log w_k+\ell_k).
\]

The implementation contract computes the score from the pre-correction
innovation standard deviation and standardized residual, avoiding a premature
`r*r` overflow. It uses neither a corrected residual nor the clipped innovation
EWMA. Each conditional state then receives that voltage once.

The conditional state update and weight update are the two factors of
`p(j,x|y) = p(j|y) p(x|j,y)`. Components are alternatives combined by a weighted
sum. Adding their precisions, multiplying their posteriors, or assimilating
the mixture summary again would double-count evidence and is prohibited.

The scores remain approximations: local linearization and feasible-gain
corrections do not produce exact marginal likelihoods. Both components may
develop the same bias, or the approximate weights may favor the wrong one.
There is no pruning, merging, rejuvenation, inflation or weight floor. Both
states and normalized log weights remain stored even if conversion to linear
weights underflows. Nonfinite weight arithmetic explicitly rejects the bank's
voltage update. Indefinite weight stability is not proved.

## Transactions, freshness and reporting

A complete staged bank leaves the live bank immutable until a validated
commit. The same final selected gain updates each mean and its full Joseph
covariance. Both future arms integrate the already
[frozen numerical remedy](../boundary_transaction_diagnostic_001/decision.json).
If either conditional correction or weight calculation fails, both physical
predictions are regenerated from immutable old states, old weights are kept,
and that voltage is rejected for the whole bank. A numerical failure does not
exclude a physical hypothesis.

All-zero gain requires restoring both the mean and factor before identical
prediction; reusing the factor already modified by correction rotations is
invalid. Any initial or required regenerated prediction failure consumes the
known interval once and enters whole-bank recovery, with the last valid belief
retained but unavailable as a current point. The conservative fixed work cap
is **six predictions, two conditional corrections and two likelihood scores
per input**, including reconstruction paths. This is not a measured deadline.

Physical chronology and input-event counts are common. Conditional evidence
cursors may differ. A separate bank cursor advances when a successful voltage
causes a nonzero selected conditional gain, or a represented relative-weight
change from unequal predictive scores. Missing/rejected observations and an
all-zero/no-weight-change update do not advance it. This distinction prevents
either duplicate input accounting or falsely identical component freshness.

The query contract exposes both components and their log weights. The
aggregate capacity point is `exp(weighted mean logQ)`, a geometric center of
component point estimates; it is not a physical-space posterior expectation.
SOC uses the weighted mean. Local moment variance includes both within- and
between-component terms. A second diagnostic hull includes both components'
local two-SD target ranges even when one weight is tiny. Neither output is a
hard support set or validated coverage interval.

The prior [uncertainty decision](../../plans/local_uncertainty_decision_001.json)
continues to apply uniformly: application SOC/Q accuracy is unresolved,
coverage is unvalidated, and local precision remains visible. Changed labels,
wider ranges or withheld estimates cannot manufacture a point-accuracy pass.

## Complete resource allocation

Packing the lower factor stores all 136 required doubles instead of a full
256-entry square array. It saves 960 bytes per component without deleting
joint covariance terms. This change is specified and layout-probed, but the
packed filtering kernel has not been implemented.

| Simultaneously owned allocation | Bytes |
| --- | ---: |
| Live two-component bank, weights and header | 2,976 |
| Complete staged bank for updates and restore | 2,976 |
| Four vector scratch arrays and two scores | 528 |
| One serialized component/aggregate query arena | 592 |
| External configuration and current input | 80 |
| **Owned-object subtotal** | **7,152** |
| Checkpoint codec buffer | 128 |
| Sixteen-sample acquisition ring and metadata | 448 |
| Both support arrays charged to RAM | 256 |
| All stack, software math, caller and ISR reserve | 2,048 |
| **Complete design allocation** | **10,032** |
| **Remaining to 10,240** | **208** |

The [C layout probe](primary/layout_probe.json) passes all **15 checks** for
these proposed host declarations. The 2048-byte stack/runtime allocation and
448-byte acquisition allocation remain requirements, not measured target
costs. No heap, raw history, second simultaneous query or hidden rollback
state is allowed outside this account. If actual target costs exceed a
reserve or the total cap, the resource gate fails.

The proposed new checkpoint contains 3004 bytes, with two NVM slots requiring
6008 bytes outside SRAM. Restore decodes into the already counted stage,
validates the complete bank and commits only on success. It does not replay
observations. The first candidate rejects old single-component formats rather
than silently converting them. Persistence pauses must fit the remaining ring
capacity; an empty sixteen-sample ring spans only about 0.457 seconds at 35 Hz.

The desktop adapter has its own parser/path/stdio costs. They must be reported
for desktop ownership and must not be confused with an embedded acquisition
implementation. Neither host `sizeof` nor the reserve budget qualifies the
Cortex-M23 toolchain, linker RAM, interrupt stack, software math or execution
time.

## One discriminating next test

The [frozen plan](../../plans/nonlinear_hypothesis_falsification_001.json) uses
only the existing **Cell B prefix through 900 seconds: 31,500 original samples
per arm**. One arm has two identical components at the inherited public prior;
the other has the two public log-capacity components. Both use the same packed
kernel, numerical remedy, transaction wrapper and reporting conventions.
Identical control components must not halve covariance or double evidence.

Before those two executions, implementation must pass targeted factor,
transaction, weight, evidence-cursor and checkpoint checks. Source, commands,
binary, plan and resource receipt are frozen before inference. Both arms keep
the original sample order, actual intervals, noise and model. A separate
scorer opens truth only after outputs are frozen.

At 900 seconds, retaining this candidate requires available aggregate points
within **5% capacity error and 10 percentage points SOC error**, together with
numerical/accounting gates and no known resource-budget excess. Preferred
targets remain 0.5% and 0.5 points. Target timing/complete SRAM remains an
explicit open qualification gate until measured. If both arms pass without a
declared discriminating difference, split-specific benefit remains unresolved.

The result must distinguish three useful failure cases: neither component
represents a useful capacity; a useful component exists but the causal weights
give an inaccurate aggregate; or both components become similarly wrong and
narrow. A post-inference oracle-best component can help classify those cases
but cannot choose the runtime estimate. The planned 900-second limit is an
inherited timely-learning requirement, not a claim that M1 already solved that
prefix or that the prefix uniquely identifies all parameters.

One comparison ends the experiment. There is no automatic extension to 1800
seconds, alternate split, noise change, additional component or third full
two-cell lifecycle primary after seeing the outcome. A passing point result
would retain a candidate for later qualification, not establish coverage or
promote it directly.

## Provenance and continuation

The design and audit sources were frozen at original execution commit
`4c451ac1d1844c09b5be2cc281c02373efa9bef7`. The
[receipt](primary/receipt.json), [independent review](independent_review.json),
[verification](verification.json) and
[publication mapping](../../provenance/nonlinear_evidence_design_001_publication.json)
keep source, evidence and published identities separate. Previous bounded
results, diagnostic outputs, failed gates and production code remain intact.

The next work branch is `implementation/nonlinear-hypothesis-001`. Its task is
to implement this contract and perform the targeted prerequisite checks,
then execute only the frozen prefix comparison when its source and receipt
are ready. The original 17 cold correction causes, application uncertainty,
complete Cortex-M23 qualification, full-model indefinite stability and annual
behavior remain open. Mumble remains distinct from SpanishCastleMagic, NAIA
and D2/D2E proof claims.
