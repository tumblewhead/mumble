# Bounded nonlinear remainder experiment 002

## Outcome

The new `scm_remainder` component adds a history-independent, joint-parameter
Taylor remainder envelope to the fixed-chart evidence bank. It can qualify a
useful conditional SOC/capacity trial on the final quiet tail under a declared
**0.1 negative-log-likelihood-unit analytic budget**. It retains the original
16-parameter evidence and uncertainty, including earlier excitation and unknown
entering states.

The sufficient bound is too conservative for the complete quiet-tail joint
step and for the tested whole-region guarantee. The original four-case
falsification run passes **654 of 672 checks**. Its 18 failures concern
prediction differences near floating-point precision at already fitted
anchors. Every likelihood-error check passes at its preregistered numerical
audit allowance. The failed receipt remains the authoritative original result;
separate precision diagnostics investigate those failures without changing the
budget or tolerances.

The mathematical envelope is a **real-arithmetic statement**. This C99
implementation uses ordinary `double` and `libm`, reports
`arithmetic_validated=false`, and has no outward-rounding proof. No trial move
is applied, no chart is replaced, and no new nonlinear optimizer is run.

## Evidence and scope

The work starts at B001 published revision
`57f3293857d674096d9ed56d7fb875f16f1806b7`. The original 35 Hz study, B001
implementation, original failed B001 receipt and corrected B001 receipt remain
unchanged. The new work is on `experiment/bounded-event-002`.

The GitHub publication call was interrupted with `aborted by user`. A subsequent
read-only check found no remote B002 branch. The local branch is committed, and
its original development commits are preserved in a verified Git bundle.
Publication status and recovery provenance are recorded in
[the publication record](../provenance/bounded_event_002_publication.json).

| Evidence | Purpose |
| --- | --- |
| [Plan](../experiments/bounded_event_002/plan.json) | Committed budget, candidates, mathematical scope, failure semantics and gates |
| [Original receipt](../experiments/bounded_event_002/receipt/receipt.json) | Four runs, five checkpoints, 120 trial points; all outcomes, hashes and 18 failed checks |
| [Memory accounting](../experiments/bounded_event_002/memory_accounting.json) | Actual object sizes, compiler frames, named ELF symbols and unresolved external costs |
| [Precision diagnosis plan](../experiments/bounded_event_002/precision_diagnostic_plan.json) | Separate investigation of the observed arithmetic floor |
| [Long-double diagnosis](../experiments/bounded_event_002/precision_audit/receipt.json) | The same 18 failed candidates evaluated with higher-precision model arithmetic; original result unchanged |
| [Independent precision summary](../experiments/bounded_event_002/independent_precision/mp_remainder_diagnostic_summary.json) | Direct-state 50/80-digit spot checks and their numerical convergence |
| [Independent precision provenance](../experiments/bounded_event_002/independent_precision/provenance.json) | Exact diagnostic source copies, package hashes and reproduction commands |
| [Independent review](../experiments/bounded_event_002/independent_review.json) | Analytic proof review, resolved integrity findings and limits of the diagnosis |
| [Verification record](../experiments/bounded_event_002/verification.json) | Unit/sanitizer outcomes, original result integrity and preserved reference paths |
| [B001 report](BOUNDED_EVENT_001.md) | Fixed affine representation, retained-history comparison and earlier limitations |

The same four B001 anchor files are copied byte-for-byte. The 400 s and 900 s
fits are retrospective anchor choices. The carry case compresses the fitted
1800 s prefix retrospectively, then ingests the remaining 300 s in chronological
order. The nominal 900 s anchor is a failure control. This setup evaluates local
representation and validity; it does not demonstrate bounded cold-start learning.

Each observed interval is used with its actual duration and current, in sample
index order, with voltage at the interval end. Nominal acquisition is 35 Hz.
Current/time are exact in this matched synthetic experiment, and the likelihood
uses the same known independent 1 mV voltage noise. Truth enters only separate
post-inference scoring.

## What is retained

The existing joint chart is `x = anchor + S delta`, where `S` contains the
reference coordinate scales. Its seven nonlinear coordinates are three log time
constants, two log hysteresis rates, initial SOC and log capacity. Its nine
amplitude coordinates include resistances, hysteresis magnitude and entering
states. All remain part of the joint likelihood.

B001's augmented QR preserves the complete affine residual objective,
including the orthogonal residual constant. One historical factor and one
active-event factor contain disjoint observations. B002 queries their costs
directly and adds no prior or duplicate historical observations.

Only 19 distinct upper-triangle Hessian entries can be nonzero for the present
model:

| Component | Entries | Count |
| --- | --- | ---: |
| Three RC modes | Per mode: log-time-constant squared, log-time-constant/resistance, log-time-constant/entering-voltage | 9 |
| Hysteresis | Three rate/rate pairs; four rate/magnitude or rate/entering-state pairs | 7 |
| OCV and charge | Initial-SOC squared, initial-SOC/log-capacity, log-capacity squared | 3 |

All amplitude/amplitude entries and all R0 curvature entries are zero. The
component streams one root-sum-square coefficient for each possible nonzero
entry. The 19 coefficients alone occupy 152 bytes, but that is only one part of
the implemented memory cost.

The supporting state consists of RC and hysteresis intervals and derivative
envelopes, elapsed time, signed charge and positive/negative throughput. It is
carried across event boundaries. No raw observations, explicit projection
basis, or growing event list is retained by the online component.

### Ingestion and history identity

`scm_remainder_evidence_push` advances the evidence and remainder banks together
from empty state. It stages the remainder, calls the existing atomic evidence
update, and commits the remainder only after both succeed. Both transactional
workspaces are explicitly counted.

A remainder bank binds to the exact evidence object after the first successful
paired update. A successful independent remainder push invalidates paired-query
eligibility until reinitialization. Matching count, time and total charge alone
cannot establish sample chronology: a regression uses reordered positive
currents with identical aggregates and verifies rejection. Swapping to a
separately populated evidence object also fails.

This is an in-process trusted-object contract. Source identity must denote
immutable ordered content; the host runner uses the observation-file SHA-256.
Public structures must not be edited or rebound by shallow copying after
ingestion. This prototype does not implement serialized restore or migration of
the paired objects.

## Why the analytic bound has this form

For observation `k`, let `M_ij,k` bound the absolute **scaled, whitened** model
Hessian entry throughout the entire configured coordinate rectangle. The online
statistic is

\[
C_{ij}=\sqrt{\sum_k M_{ij,k}^{2}}.
\]

Taylor's integral remainder and the triangle inequality in observation-space
Euclidean norm give

\[
\left\|\frac{\mu(x)-\mu_a-J_aS\delta}{\sigma}\right\|_2
\le E(\delta)
=\frac12\sum_i C_{ii}\delta_i^2
+\sum_{i<j}C_{ij}|\delta_i\delta_j|.
\]

With affine whitened residual `r` and whitened model remainder `e`,

\[
L_{\rm nonlinear}-L_{\rm affine}
=r^Te+\frac12\|e\|_2^2.
\]

The complete affine cost therefore yields the sufficient bound

\[
|L_{\rm nonlinear}-L_{\rm affine}|
\le B(\delta)
=\sqrt{2L_{\rm affine}(\delta)}E(\delta)+\frac12E(\delta)^2.
\]

The residual cross term is essential. A small voltage discrepancy can produce
a material likelihood discrepancy when it correlates with residuals over a long
history. Keeping only the squared-remainder term would miss the earlier
inside-radius failure witness.

### Component envelopes

For each RC mode, `f_next = I + exp(-dt/tau)(f-I)`. Intervals enclose `f`, while
absolute bounds propagate its first and second log-time-constant derivatives.
The exponential derivative extrema include the interior critical points of
`q exp(-q)` and `abs(q(q-1)exp(-q))`. The entering-state column and its
derivatives are bounded directly from elapsed time and the time-constant box.

Hysteresis propagates the actual sign sequence. Its driven state carries two
first-derivative and three second-derivative bounds; its entering-state column
uses separate cumulative positive and negative throughput. Zero throughput
introduces no rate curvature. Before negative throughput, the gamma-minus
curvature entries stay exactly zero. That absence is consistent with an
unexcited parameter and supplies no precision for it.

For the smooth illustrative OCV, `abs(U') <= 1.79` and `abs(U'') <= 4` are global
bounds. With `w = transferred_Ah / Q`, the three OCV Hessian magnitudes are
bounded by `4`, `4 abs(w)` and `4 w^2 + 1.79 abs(w)`. The envelope uses the entire
original rectangle, including infeasible portions, through the smooth OCV
extension. Actual candidate support and the complete historical SOC endpoint
path are checked separately. Measured piecewise-linear OCV curves are explicitly
unsupported because ordinary smooth Hessian arguments do not cover their knots.

## Fixed decision policy

The 0.1 NLL budget was committed before the four-case run. It equals 5% of the
existing DeltaNLL=2 local profile screen and is an engineering comparison
restriction, with no coverage interpretation.

A nonzero trial is eligible under the analytic policy only if it:

1. Lies within the original coordinate radius and physical support.
2. Has `B <= 0.1`.
3. Has no flagged anchor-residual events.
4. Satisfies `L_affine + B < L_anchor`.

Every displacement is measured from the same original anchor. Dividing a step
does not renew its origin or permit repeated error-budget accumulation.
Eligibility is reported alongside `arithmetic_validated=false`; it is not an
automatic update or a machine-certified descent guarantee.

The 24 trials per checkpoint comprise the five original probes, the full joint
affine step, that step divided by 2 through 256, a conditional SOC/log-capacity
step, eight deterministic retained-eigenspace directions, and a gamma-minus
control. The conditional step solves its 2-by-2 normal-equation block with other
trial displacements set to zero. It retains the entire joint bank and its
uncertainty; it does not assert that the nuisance parameters are known.

## What the quiet tail supports

At 2100 s, the original-anchor affine cost is `36827.2323627462`. The main trial
comparisons are:

| Trial | Observed signed nonlinear-minus-affine NLL | Analytic absolute-error bound | Policy outcome |
| --- | ---: | ---: | --- |
| Earlier inside-radius SOC/Q witness | -133.9773816203 | 251.0564086817 | Exceeds budget |
| Full joint affine step | -0.0000506197 | 4.7942142328 | Exceeds budget |
| Joint step / 8 | +0.0000017974 | 0.0749074059 | Meets error budget, does not establish descent |
| Joint step / 16 | +0.0000004957 | 0.0187268520 | Eligible analytic trial |
| Conditional SOC/Q step | -0.0000000464 | 0.0041191955 | Eligible analytic trial; best upper-cost criterion |

The conditional step gives an affine cost of `36827.09681666858`, and its
analytic upper cost is `36827.10093586411`. The difference from the anchor is
**0.1314268821 NLL units** under the real-arithmetic error model. Its observed
nonlinear cost is `36827.096816621866`.

The conditional trial's point values are capacity `0.06000883069273305 Ah` and
current SOC `0.5736967974075351`. Post-inference synthetic scoring gives capacity
error `+0.0147178212%` and current-SOC error `-0.0013520053` percentage points.
These are point errors in this one matched synthetic case, not coverage or
real-cell accuracy claims.

Six tail trials satisfy the complete analytic eligibility policy: joint-step
fractions 1/16 through 1/256 and the conditional trial. The full joint step's
excellent observed agreement remains visible. Even if its prediction-remainder
norm were known exactly, the same Cauchy inequality would give roughly
**0.441 NLL units**, above the 0.1 budget. Better Hessian envelopes alone cannot
remove that particular limitation; a tighter likelihood treatment needs to
retain residual/remainder correlation.

## Earlier uncertainty and whole-region limitations

At 400 s, the bank remains rank 14, gamma-minus remains unexcited, and SOC and
capacity local precision remain unresolved. A tiny conditional trial can meet
the analytic descent policy without resolving those directions. Its SOC truth
error remains about -0.55 percentage points, illustrating why a valid local
move is not evidence of an identified initial SOC.

At 900 s, and at the retrospective 1800 s split, the fitted anchors are already
nearly stationary. No nonzero trial satisfies the complete descent policy.
The nominal 900 s control retains 214 flagged events and permits no update,
despite full numerical rank and narrow local ranges.

The existing local precision diagnostics are still evaluated at the **original
anchor**, not relinearized at a selected trial. At 2100 s the original chart's
local two-sigma capacity halfwidth is `0.0000221444738192 Ah` (about 0.03690%),
and current-SOC halfwidth is `0.0000561121816026` (about 0.005611 percentage
points). Those quantities retain their original fixed-chart interpretation and
unvalidated coverage.

The whole-region calculation uses the intersection of the original coordinate
box, physical support and `L_affine <= L_affine_step + 2`. `L_affine_step` is
the attained retained-eigenspace step cost; the numerical eigenvalue cutoff is
not a proof of a global affine minimum. Substituting the original radii into
the nonnegative remainder polynomial gives a sufficient uniform bound for
that intersection.

| Checkpoint/anchor | Uniform NLL error bound | Meets 0.1 budget |
| --- | ---: | --- |
| 400 s fitted | 1589.3239 | No |
| 900 s fitted | 6288.5098 | No |
| 1800 s fitted prefix | 14664.7608 | No |
| 2100 s carried from 1800 s | 17367.9709 | No |
| 900 s nominal | 5630.1514 | No |

This is a failed sufficient guarantee. It does not claim that every box point
is low-loss, that the intersection is nonempty, that its actual worst-case
error equals the bound, or that evidence excludes candidates outside the box.
Physical extents along unresolved directions are retained rather than replaced
by zero pseudoinverse variance.

## Numerical failure and precision diagnosis

The complete C and Python unit suite passes, as do the focused address and
undefined-behavior sanitizer checks. The four retained-trace comparisons have
120 candidates, of which 81 have available inside-domain bounds. All original
likelihood-error gates pass. Eighteen prediction-norm gates fail at the 900 s
and 1800 s fitted anchors, for the full step and its eight fractions.

At 900 s, the largest full-step coordinate is about `1.64e-8`; at the 1800 s
split it is about `6.17e-10`. Their theoretical remainder bounds decrease
quadratically with step size, while the double-state replay norm fluctuates
between `1.39e-10` and `4.87e-10`. Those norms correspond to voltage RMS
differences around `1e-15 V`. They exceed the fixed `1e-10` whitened-norm audit
allowance. The real-arithmetic bound does not include executable rounding error.

The original host audit already accumulates voltages and costs in long double
and evaluates the affine amplitude dependence in a common arithmetic order.
Its model states, OCV, Jacobian and displaced nonlinear coordinates remain
double. That distinction explains why a separate full-precision model replay
is needed to diagnose the failure. The original 18 failures are preserved;
higher-precision results are reported separately.

The independent long-double model uses a 64-bit mantissa on this host, compared
with binary64's 53 bits. For the same 18 fixed candidates, the replay norm falls
to `7.50e-14` through `4.63e-13`, an 821- to 2689-fold reduction. All 18 are below
the original bound plus the unchanged `1e-10` audit allowance. Many still exceed
their vanishing theoretical remainder because long double also has a finite
evaluation floor. This diagnostic does not change the original 654/672 result.

An independent direct-physical-state calculation further evaluates the worst
1800 s failure, the joint step divided by 128, at 50 and 80 decimal digits. It
finds a real-model whitened remainder norm of **`4.6393510564e-20`**, below the
recorded envelope **`1.6232163606e-19`**. The two precisions agree to about
`1.99e-25` relative in that norm. The original double-state replay had reported
`4.8650103812e-10`, about ten billion times larger than the real-model remainder.
The meaningful tail conditional trial also lies below its recorded envelope
when evaluated at 50 digits: norm `7.8832199737e-6` versus bound
`1.5177968804e-5`.

These independent checks support a floating-point evaluation-floor diagnosis
for the selected failures. They do not provide a rounding-error bound for the
deployed C computation, prove enclosure at every candidate, or replace the
original failed gates. The model constants and all input/anchor/scale/delta
values are lifted from their original binary64 values before high-precision
evaluation; no fitted parameter or truth is changed.

## Complete host memory accounting

All following counts are host ABI/compiler measurements, independent of sample
or event count. No workspace overlay is implemented or credited.

| Implemented object or live set | Bytes |
| --- | ---: |
| Existing evidence bank | 3336 |
| Existing atomic evidence workspace | 4176 |
| New remainder bank, including chart copy, bounds, metadata and paired binding | 1200 |
| New atomic remainder workspace | 1200 |
| Paired ingestion object subtotal | **9912** |
| Remainder query result | 48 |
| Incoming sample | 24 |
| Ingestion, query result, retained snapshot, diagnostics and local vectors | **20856** |
| Same plus retained input configuration and sample | 21352 |
| Whole host probe's named static objects | 36145 |
| Whole host probe's ELF data plus BSS | 37608 |

The source-derived paired-ingestion path adds 736 bytes of reported project
stack to ingestion objects plus the sample, reaching **10672 bytes** before
external library or application costs. The implemented diagnostic objects plus
the assessment path reach **21720 bytes**. The largest listed whole-probe
project call path is 1664 bytes; these are compiler-based estimates, not runtime
high-water measurements.

Consequently, even ingestion plus its listed own-source stack exceeds the
10 KiB goal. `libm`/`libc` frames, calling application and interrupt state,
acquisition buffers, target ABI, soft-float code, latency, flash and power remain
unqualified. The current remainder module has no external curve storage because
it supports only the illustrative smooth OCV.

## Reproduction and continuation

The main 60-fit study and profiles do not need to be rerun. On the work branch:

```bash
make test-remainder build/scm_remainder_probe
python3 tools/run_remainder.py \
  --output-dir experiments/bounded_event_002/my_new_receipt
python3 tools/measure_remainder_memory.py \
  --probe-result experiments/bounded_event_002/my_new_receipt/carry_1800_to_2100.json \
  --output experiments/bounded_event_002/my_new_memory.json
```

Helpers refuse existing output locations. The original runner is expected to
report the preserved numerical gate failures on this host; its nonzero exit is
part of the result, not a request to relax a threshold.

The short long-double diagnosis can be reproduced separately:

```bash
python3 tools/audit_remainder_precision.py \
  --receipt experiments/bounded_event_002/receipt/receipt.json \
  --output-dir experiments/bounded_event_002/my_precision_diagnosis
```

The arbitrary-precision spot checker uses `mpmath==1.4.1`; this is a diagnostic
dependency and is not required by the C estimator. Its recorded source and
commands accompany the independent precision results.

The next statistical design to evaluate is a signed residual/curvature summary
with a bounded higher-order remainder. It should target the demonstrated
Cauchy loss of cancellation and be tested on the same full-step and
whole-region witnesses before another sweep. Complete state/workspace accounting
and floating-point error handling remain part of that design.

A valid error envelope for the old polynomial still does not supply a changed
historical Jacobian or exact carried RC/hysteresis state at new parameters.
Actual chart initialization or transition requires a separate bounded carried-
state error contract, retained excitation window, or finite alternate charts.
Earlier evidence must remain source-disjoint and be used once. Nonlinear
convergence, local precision, truth accuracy and validated coverage remain
separate claims.
