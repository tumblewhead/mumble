# Live anchor integration 001 — completed causal point-estimation probe

The integrated estimator completed one **504,000-sample, four-hour run from the public initial point**, using a bounded rolling block and compact older history. Its final capacity was **64.659363 mAh**, an error of **−0.0628083%**; current SOC was **42.3222974%**, an error of **−0.00941675 percentage points**. All 16 original quantities and the five current states were retained at every committed block. These are useful autonomous point-estimation results. Joint uncertainty fidelity and target-device readiness remain unvalidated. [Saved summary](reporting_continuation001/summary.json), [independent result review](review/result_review.json).

The scientific run completed once without retry. A later reporting-format error and a separate damaged publication export were preserved and handled through explicitly bounded, saved-data continuations. Neither recovery reran inference or changed a candidate. Their provenance is documented below.

## What was integrated

The candidate receives ordered live-style records containing 12-bit voltage, current and temperature codes, a 64-bit interval tick count, and sequence/source identity. The host supplies the archived study input chronologically; the candidate has no archive handle, truth input, saved fitted anchor or unbounded observation history. The initial point is the public mean. [Run contract](host_run_plan.json), [design](DESIGN.md).

The candidate retains 16 raw records and an eight-record ingress queue. Earlier records belong to one 37-feature, second-order-residual QR history bank. At each full block it makes one bounded proposal in the full 16-dimensional entering chart. The current block is reevaluated nonlinearly, conditional on the carried approximate boundary basis. The objective includes the original joint mixture prior once; the prior is never merged into the likelihood factor.

The support-aware proposal uses the complete gradient and a conservative diagonal majorizer derived from the full scaled GN-plus-prior metric. Reciprocal-capacity proposal coordinates make the coupled capacity/SOC support faces tractable. Those coordinates do not change the prior's original-coordinate density. Strict represented-point support checks and guarded objective decrease remain in force; no clipping, variance inflation or PSD repair is used. This metric is optimization geometry, not a posterior covariance.

A successful block commit translates the existing polynomial, transports its approximate boundary basis, appends each retained record once, and then retires the raw block. Translation preserves the older polynomial; it does not reconstruct the original nonlinear evidence. The approximate-history flags remain visible. The [engine](rolling_engine.c), [model kernels](rolling_model.c), [support primitive](../live_anchor_bootstrap_001/support_step.c) and [independent qualification](review/integration_qualification_review.json) document these semantics. The finite fabricated qualification passed 16 cases and 4,757 assertions before the primary invocation.

## Capacity, SOC and the whole trace

The run saved **31,501 snapshots**: the initial point and one row after each 16-sample block. The complete [CSV](reporting001/trajectory.csv.gz) retains original coordinates, physical estimates, available references, errors, costs, stop reasons, flags and counters. The [full capacity/SOC figure](reporting001/capacity_SOC_overview.png) and [fixed first-two-minute view](reporting001/early_capacity_SOC.png) use all saved points in their declared time ranges. No smoothing or retrospectively selected convergence window is used.

| Saved prefix | Capacity error | Current SOC error |
|---|---:|---:|
| 7,200 s / 252,000 samples | −0.1736489% | −0.1251853 pp |
| 8,400 s / 294,000 samples | −0.1582762% | −0.1572436 pp |
| 14,400 s / 504,000 samples | −0.0628083% | −0.00941675 pp |

The existing preferred capacity requirement, absolute error ≤0.5%, was first reached at 720 s, but was not satisfied at every later saved point until **1,980.342857 s (about 33.0057 minutes)**. The existing preferred current-SOC requirement, absolute error ≤0.5 pp, was satisfied at every saved point from **1,065.6 s (17.76 minutes)** onward. These are finite saved-grid statements, not guarantees between snapshots or beyond this four-hour study. Initial prior accuracy is reported separately. [Target definitions](../../plans/estimation_targets_001.json), [saved target screens](reporting_continuation001/summary.json).

Every one of the 31,500 blocks accepted its full proposal and then stopped at the **one-round limit**. No block supplied a stationarity or KKT certificate. A slowly changing or accurate trace therefore must not be described as proven convergence. The [search-status figure](reporting_continuation001/optimization_trace.png) makes that finite stopping policy explicit. [Independent saved-trace review](review/result_review.json).

## All 16 original quantities

The table reports the final estimate of each **original entering quantity**, separately from the evolving current state. Signed errors use the stated native unit. Relative errors are shown for the positive physical parameters; they are omitted for entering states where that comparison can be misleading. The full precision, initial errors, extrema, MAE and RMS are in the [summary](reporting_continuation001/summary.json).

| Quantity | Unit | Reference | Final estimate | Signed error | Relative error |
|---|---|---:|---:|---:|---:|
| τ₁ | s | 0.075 | 0.0944973288 | +0.0194973288 | +25.9964% |
| τ₂ | s | 0.65 | 0.705143226 | +0.0551432256 | +8.4836% |
| τ₃ | s | 7.5 | 7.39698971 | -0.103010285 | -1.3735% |
| γ₊ | 1/Ah | 330 | 325.607275 | -4.39272476 | -1.3311% |
| γ₋ | 1/Ah | 500 | 497.843638 | -2.1563622 | -0.4313% |
| Capacity Q | Ah | 0.0647 | 0.064659363 | -4.06369619e-05 | -0.0628% |
| R₀ | ohm | 0.16 | 0.179997729 | +0.019997729 | +12.4986% |
| R₁ | ohm | 0.22 | 0.222404976 | +0.00240497581 | +1.0932% |
| R₂ | ohm | 0.27 | 0.247845113 | -0.0221548867 | -8.2055% |
| R₃ | ohm | 0.33 | 0.32876448 | -0.00123552036 | -0.3744% |
| H | V | 0.03 | 0.0299540693 | -4.59306761e-05 | -0.1531% |
| Entering SOC z₀ | fraction | 0.78 | 0.78013 | +0.000129999674 | — |
| Entering v₁ | V | -0.002 | 0.000386305882 | +0.00238630588 | — |
| Entering v₂ | V | 0.004 | 0.000805095084 | -0.00319490492 | — |
| Entering v₃ | V | 0.006 | 0.00913167313 | +0.00313167313 | — |
| Entering h₀ | dimensionless | 0.35 | 0.311546353 | -0.0384536472 | — |

Capacity and current SOC accuracy do not establish that all nuisance parameters are well identified. In particular, τ₁, R₀, τ₂ and R₂ retain substantial errors. The initial RC states and hysteresis state also retain bias. The [all-16 figure](reporting001/all16_parameters.png), [parameters 1–8](reporting001/parameters_01_08.png) and [parameters 9–16](reporting001/parameters_09_16.png) preserve those outcomes rather than replacing them with a target-only view.

Current SOC has a scalar reference at every saved point. The optional dense source-state journal was not locally available, so later current RC and hysteresis references remain explicitly unavailable; the [current-state figure](reporting001/current_states.png) shows their complete estimated trajectories and only the available initial reference. No later physical-truth RC/h error is asserted. Static parameter truth and indexed SOC/capacity truth were accessed only after candidate closure. [Reporting plan](reporting_plan.json), [reporting provenance](reporting_continuation001/receipt.json).

## ADC and temperature scope

The calibration was fixed before outcomes: voltage 1.5 + code/1024 V, current −0.256 + 0.000125·code A, temperature −40 + 0.0625·code °C, and a 1/7,000,000-second timer tick. These are declared synthetic-study settings, not specifications for the user's hardware. Temperature was supplied as 25°C; the model has no thermal adaptation.

The saved decoded-minus-original voltage quantization RMS is **0.281845 mV**, with maximum absolute error about **0.488280 mV**. Current error is only floating-point roundoff scale (RMS 4.32×10⁻¹⁸ A), and interval quantization error is zero for this stimulus. No channel rail or half-tie event occurred. Thus this run does not substantially test current/timer resolution, uncertain physical calibration or changing temperature. The likelihood kept its declared decoded-point Gaussian σ=1 mV; it is an approximation after quantization, and no post hoc noise inflation was introduced. [Terminal input statistics](attempt001/result.json), [independent interpretation](review/result_review.json).

## What the exact-history audits establish

After the candidate closed, three fixed saved points were audited using the unchanged original physical recurrence, the same decoded input, original entering coordinates and full history to the respective prefix. There was one audit per predetermined prefix, no optimization, no prior evaluation, no truth selection and no feedback to inference. [Audit contract](host_audit_plan.json), [audit results](postclosure_audit001/result.json).

| Samples | Represented likelihood cost | Original-recurrence cost | Represented minus original |
|---|---:|---:|---:|
| 252,000 | 145,301.917781 | 151,196.853870 | −5,894.936089 |
| 294,000 | 168,239.923611 | 174,103.560872 | −5,863.637261 |
| 504,000 | 292,996.706228 | 284,058.166521 | +8,938.539707 |

These are pointwise historical approximation discrepancies. The reference's naive-versus-compensated accumulation differences are only about 1.4×10⁻⁸ to 1.9×10⁻⁸ cost units, so simple summation order does not explain these offsets. The study did not separate older-factor approximation error from boundary-transport error.

**Absolute cost offsets alone do not establish covariance or interval distortion.** A parameter-independent additive offset cancels from posterior normalization. The three audits use different prefixes and one point per prefix, so they do not measure variation of the approximation error over a joint neighborhood at any fixed prefix. Current endpoint SOC matched the exact recurrence at all three estimated points; the reported RC/h endpoint differences also compare two computations at the same estimated point, not estimates against physical truth. [Independent numerical review](review/result_review.json).

## Memory and finite work

| Candidate memory category | Bytes |
|---|---:|
| History bank | 6,368 |
| Shared phase workspace | 1,600 |
| Result object | 120 |
| Retained/ingress records and metadata | 408 |
| Calibration | 56 |
| Mutually exclusive refinement/checkpoint auxiliary space | 128 |
| **Candidate context** | **8,680** |
| Reserved project stack | 768 |
| Reserved runtime/IRQ/caller space | 768 |
| **Planned subsystem total** | **10,216 / 10,240** |

The compiled own-project call path is 760 bytes, within its 768-byte reservation. The complete target runtime/IRQ/caller requirement, target stack behavior, ADC service latency and Cortex-M23 timing remain unmeasured. The 24-byte planning margin is small. Host archive, trace, plotting storage and host RSS are external to this candidate ledger. [Memory plan](plan.json), [build accounting review](review/build_accounting_review.json).

Primary work was 2,016,000 model steps, 504,000 appended history rows, 126,001 queries, 94,501 prior evaluations and 31,500 proposals. The three external audits added their separately declared 1,050,000 original-model steps. The exact primary wait4 scope—inner supervisor, its scientific child and inner closure—used **12.720086 CPU seconds**, **12.496388 wall seconds** and **84,135,936 bytes peak host RSS**. Including outer bookkeeping through its pre-receipt snapshot, the recorded totals were 13.329468 CPU seconds and 13.037296 wall seconds. These host figures are not embedded timing measurements. [Primary receipt](execution_process/receipt.json), [audit receipt](postclosure_audit001/receipt.json).

## Reporting, preservation and reproducibility

The reviewed inference source was published at `6e60b8f98a2f122b61fc8932c3762a7592999de3`. The [executable receipt](executable_receipt.json) binds source, binary, configuration and qualification. The primary [inner receipt](attempt001/receipt.json) and [outer receipt](execution_process/receipt.json) preserve one completed invocation and its original/independent capture roles.

The original [reporting receipt](reporting001/reporting_receipt.json) remains **failed**: the final categorical chart called a numeric-axis formatter. Before that failure, the complete CSV and six PNG/SVG pairs were saved. A [separately reviewed continuation](review/reporting_continuation_source_review.json) read only those receipt-hashed saved outputs and closed primary metadata, generated the missing categorical chart, and wrote the [selected summary](reporting_continuation001/summary.json). Its [completed receipt](reporting_continuation001/receipt.json) records zero additional original-truth, observation, model, prior or optimizer calls. Across reporting, the original single static-literal extraction and 31,500 scalar-truth record reads remain explicit.

Separately, a derived independent-copy gzip was later found truncated. Its cause remains unattributed. The damaged artifact, original packaging receipt and failed first execution review remain preserved. The intact original gzip and a new gzip recompressed once from the still-verified **independent raw capture** are selected by [publication_selection.json](publication_selection.json). The [recovery receipt](publication_recovery001/receipt.json) and [passed execution review v2](review/execution_receipt_review_v2.json) bind those roles. This was byte-only publication recovery; the canonical raw captures and scientific status were unchanged. Restoration must create both raw roles separately and verify their raw identities and original capture metadata.

## Decision and next finite step

**Keep the integrated public-start architecture as an experimental point estimator.** This run demonstrates causal operation, bounded retained state, chronological evidence ownership and useful SOC/capacity accuracy on the declared synthetic input. It does not justify uncertainty intervals, all-parameter convergence, hardware deployment or a temperature/calibration claim.

The next useful design is one small **joint local likelihood-shape comparison at a fixed prefix around an internally learned anchor**. Retain the required bank/query state explicitly, freeze a finite set of coupled directions before evaluation, and compare centered likelihood differences against the original recurrence under identical decoded input, prior, support and entering-state ownership. Centering removes an arbitrary common cost offset. Report local directional/curvature discrepancies and numerical resolution without using truth to select directions, widen uncertainty or discard nuisance coupling. A finite local comparison still cannot certify unexamined tails or global coverage; it determines whether the retained representation is suitable for the subsequent uncertainty work. No additional experiment is initiated by this report. [Machine-readable decision](decision.json).
