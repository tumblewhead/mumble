# Delivery roadmap: trajectories to Cortex-M23

## Decision

The user has authorized desktop discovery with retained observations and memory
above 10 KiB, followed by reduction toward the deployment target. The new
[desktop baseline](../experiments/desktop_history_001/README.md) passes the frozen
545-point fidelity gate with zero computed discrepancy and completes five
public-start prefix fits. The two-hour endpoint errors are +0.006627% capacity
and −0.002784 percentage points SOC. Three checkpoints pass the declared gradient
tolerance; two line-search stops remain explicit. History storage is 6.048 MB;
this is not bounded-memory firmware or a varied-trajectory stability result.

The next priority is to measure history-refresh/compression tradeoffs against
this preserved baseline. Desktop diagnostic storage is no longer constrained by
the deployment ceiling. Original prior/support, evidence ownership, chronology,
and the 0.1 NLL fidelity criterion remain unchanged. The results below preserve
the compact engine's earlier evidence and unresolved deployment discrepancy.

**The rolling engine is integrated; its first public-start point probe is complete.**
One four-hour, 504,000-record chronological run reached capacity error
−0.0628083% and current SOC error −0.00941675 percentage points. All 16 fitted
quantities and five current states are saved, including biased nuisance results.
The preferred capacity and SOC targets hold at every remaining saved point from
33.0057 and 17.76 minutes, respectively. Every update exhausted its one-round
budget, so this is finite point-accuracy evidence without a convergence certificate.

The candidate owns 8,680 bytes, sixteen working records, eight incoming records
and a compact history bank; it has no archive or truth dependency. A finite suite
passed 16 cases and 4,757 assertions. The compiled host project stack path is
760 bytes and the complete planning ledger remains 10,216 / 10,240 bytes, with
actual Cortex-M23 runtime/IRQ/caller memory and timing unmeasured.

**M2 remains open and M3 is not promoted.** The user-authorized non-aborting
parity census completed all 15,751 snapshots through the two-hour prefix. Only
likelihood/total cost differed, by at most 2.04e-10 NLL and 36 ULP; all saved
physical outputs, prior, elapsed time, support slacks and flags matched exactly.
The observed differences are negligible at application scales. Their cause and
full bank-coefficient equality remain unestablished.

**The joint-shape comparison is complete and selects repair.** All 545 frozen
points were available. Centered error oscillation is **252.960406 NLL**, versus
**0.1 NLL** registered, and remains **126.231763 NLL** at half radius. The
computed-arithmetic interval is [252.960264, 252.960548] NLL. The saved numerically
reconstructed bank has a large local slope discrepancy; this is separate from
tiny scalar replay drift. No new prefix reconstruction or inference occurred.
See the [comparison report](../experiments/joint_shape_comparison_001/README.md),
[decision](../experiments/joint_shape_comparison_001/decision.json),
[preserved census](../experiments/parity_census_001/README.md) and
[current handoff](../handoff/CONTINUE.json). Current branch:
`specifications/minimal-health-model-001`.

The requested repair is implemented and qualified, but the selected candidate
fails its controlled fidelity gate. Structured features alone give **193.291124
NLL**; the full candidate with analytic initial-state attenuation gives
**185.612242 NLL**, versus the unchanged **0.1 NLL** budget. Both arms evaluated
all 545 points. The full computed-arithmetic interval is
[185.590608, 185.633877] NLL. The gated causal probe was not started.

Qualification passed **5,260 checks**. Context remains **8,680 bytes**; the
conservative compiled host project path is 712 bytes, within its 768-byte
reservation, and the planning total remains **10,216 / 10,240 bytes**. These are
not actual Cortex-M23 measurements. See the
[candidate report](../experiments/structured_history_repair_001/README.md),
[decision](../experiments/structured_history_repair_001/decision.json) and
[preserved diagnosis](../experiments/history_shape_localization_001/README.md).

After development stabilizes, the user requests configurable cell/load/noise/
duration trajectories for longer-term variation. That campaign has not started.

### Previous primitive checkpoint

**The bounded causal-anchor design is selected and its critical C primitives pass.**
ADC12 transport, a support-aware joint proposal and in-place polynomial
translation passed 30 finite cases and 40,083 assertions. The selected design
retains sixteen current samples and queues eight incoming samples. Its compiled
host layout and explicit reservations total 10,216 bytes, including 56 B of RAM
calibration. The 24 B margin is not a
measured target allowance. File playback and saved history are permitted study
tools; the estimator owns only delivered samples and bounded state.

At that checkpoint, the next action was to integrate the rolling engine. Block derivatives,
approximate boundary transport, accepted-objective
checks, once-only evidence/prior transactions and actual call chains remained to
implement and qualify. That primitive checkpoint included no new battery-data
run or interval/M3 promotion.
Read the [report](../experiments/live_anchor_bootstrap_001/REPORT.md),
[design](../experiments/live_anchor_bootstrap_001/DESIGN.md),
[decision](../experiments/live_anchor_bootstrap_001/decision.json) and
[archived handoff](../handoff/archive/CONTINUE_live_anchor_bootstrap_001.json).
That checkpoint is preserved on `implementation/live-anchor-bootstrap-001`.

### Previous compact-history result

**Compact nonlinear history is now a useful local C component; causal cold start remains open.**
The single 294,000-sample experiment completed with two fixed-origin banks and
external reference checks at 7,200 and 8,400 s. Candidate history is a 37-feature
QR factor occupying 5,624 B; the core occupies 8,112 B with no heap or raw samples.
Full planned objects and reservations total 10,224 B, only 16 B below the 10,240 B
goal. Target stack, runtime, acquisition, recovery and timing are not measured.

Around saved autonomous generation 7, the same 41 joint-node likelihood-error
oscillations fall from affine 0.0261749 / 0.0227073 to quartic 0.0004693 /
0.0005214 at the two checkpoints. Two suffix steps improve the independently
audited common objective by 17.48326 relative to the unchanged saved anchor.
The public-origin arm gives 37,737.8 / 43,235.6 oscillation on those nodes and
also stalls against the initial-h bound. Search and representation defects are
distinct. The warm chart fails at the distant public node, so local success does
not establish global fidelity, calibrated intervals or autonomous cold start.

The reviewed decision is to keep the local quartic bank and next design bounded,
causal bootstrap/anchor transition with support-aware search and explicit earlier-
evidence ownership. Read the [report](../experiments/compact_nonlinear_history_001/REPORT.md),
[decision](../experiments/compact_nonlinear_history_001/decision.json),
[result review](../experiments/compact_nonlinear_history_001/result_review.json) and
[receipt review](../experiments/compact_nonlinear_history_001/receipt_review.json).
That comparison is preserved on `implementation/bounded-history-anchor-001`. The run used
6.866106 CPU s, 6.935785 active wall s, 19,169,280 B host peak RSS and 758,011 B
closed runtime output. All original/copy captures survived verification.

**Autonomous anchor refinement now has verified partial evidence from one failed finite run.**
Seven accepted full steps from the fixed public mean reached Q=64.703748 mAh and
SOC=51.602860%, agreeing with the earlier supplied-anchor feasible point. The
common-prior audited objective decreased from 4,068,160,781.516271 to
126,413.134107. No historical fit or truth entered inference. All seven accepted
generations retain one prior, one active likelihood block and cursor252000.

The invocation failed when one previously bound rejected-trial capture became
empty. Its exact bytes were recovered separately from a retained request and
matched the original hash; the mechanism remains unattributed. All failed
receipts and the empty capture remain preserved. Independent review and a
separate read-only partial report validate the accepted chain without restarting
inference. Eleven model passes, eight proposals and 11 prior evaluations used
28.310357 CPU s, 29.060402 active wall s and 63,991,808 B peak RSS; limits held.
See the [report](../experiments/autonomous_anchor_refinement_001/REPORT.md),
[decision](../experiments/autonomous_anchor_refinement_001/decision.json),
[summary](../experiments/autonomous_anchor_refinement_001/failure_reporting001/summary.json)
and [result review](../experiments/autonomous_anchor_refinement_001/result_review.json).

That result led to the capture-preservation qualification and compact-history
comparison above. Capture preservation passed eight fabricated real-child cases;
the C bank passed sixteen independent cases before its one canonical invocation.
The near-equal reference point still does not validate narrow uncertainty
intervals. If finer point resolution becomes necessary, derive a paired residual-
difference comparator rather than reduce an existing arithmetic guard after seeing
a result. No retry, longer campaign or promotion follows from the failed run.

**The finite retained-likelihood replacement prototype is complete.**
One replacement transaction at the fixed 7,200-second prefix improved the
audited common-prior nonlinear objective by 30,064,065.6144, with a computed
comparison allowance of 0.006786. Its feasible point is Q=64.703748 mAh and
SOC=51.602860%. The two saved anchor evaluations were reused after a reviewed
subnormal-parity correction; four model passes and two surrogate solves were
used in total. Exactly one prior and one active observation block remain.
See the [report](../experiments/retained_likelihood_replacement_001/REPORT.md),
[decision](../experiments/retained_likelihood_replacement_001/decision.json) and
[result review](../experiments/retained_likelihood_replacement_001/result_review.json).

The supplied historical-fit anchor makes this a mechanics and local-fidelity
test. It does not demonstrate autonomous anchor discovery or reconstruct the
earlier online approximation. Both independent KKT statuses remain unresolved;
any reported inverse-curvature scales are local shape diagnostics, not calibrated
uncertainty intervals. That decision led to the public-start autonomous refinement above, which retained
full joint dependencies and accepted replacements only after nonlinear-cost
audits under a frozen pass budget and stopping policy. No new
execution or longer campaign is queued by this result. Posterior fidelity and
coverage require their own qualification. The measured 10,680-byte C workspace
and 8,064,000-byte external prefix do not meet the complete near-10-KiB Cortex-M23
goal, and production estimator code is unchanged.

**The supported-reference decision and historical likelihood control are complete.**
The single-h-bound mathematical reference passed all 79 checks but is not a
general SOC/Q uncertainty repair. At the fixed 7,200-second prefix, the full
nonlinear history gives Q=64.703737 mAh and SOC=51.602859%, close to the archived
truth, while the recursive center is biased despite a similar capacity local
SD. The three declared fits all completed; no production estimator changed.
That result selected the retained-likelihood replacement prototype, now completed
above, with common prior/support semantics and full joint evidence ownership. See the
[control report](../experiments/historical_likelihood_control_001/REPORT.md),
[decision](../experiments/historical_likelihood_control_001/decision.json),
[review](../experiments/historical_likelihood_control_001/independent_review.json)
and [prototype design](../plans/retained_likelihood_replacement_001.json).
Local likelihood curvature and this one truth comparison do not establish
calibrated posterior intervals or identify one unique historical approximation.

**The three-checkpoint conditional-belief probe is complete.** Five admitted
component snapshots show only 1.15–1.22-microvolt nonlinear mean corrections.
At 8,400 s, component 0 has an h mean/variance pair incompatible with the
physical interval [-1,1], and half the prescribed nodes are outside that bound.
The subsequent supported-correction decision is complete and linked above.
Historical SOC/Q coverage and the earlier weight-switch cause remain open. See the [probe report](../experiments/conditional_belief_adequacy_001/REPORT.md),
[decision](../experiments/conditional_belief_adequacy_001/decision.json) and
[independent result review](../experiments/conditional_belief_adequacy_001/result_review.json).

**The saved-evidence weighting/interval audit is complete.** The 50,401-row,
1,445-query audit found no tested arithmetic, chronology or reporting mismatch.
The SOC output switch is driven by changed component weights, while narrow
wrong conditional beliefs remain. Its bookkeeping investigation is closed;
the subsequent three-checkpoint probe is now complete and linked above. See the
[current report](../experiments/weighting_output_diagnostic_001/REPORT.md),
[decision](../experiments/weighting_output_diagnostic_001/decision.json) and
[independent review](../experiments/weighting_output_diagnostic_001/independent_review.json).
The estimator source and owned SRAM remain unchanged.

**M1's desktop lifecycle is complete. The continuous learning/retention
diagnostic has now completed once under the unchanged two-component learner.**
All four arms are valid with 661,500 learner deliveries, zero rejected updates,
exact warm continuation and valid cold reset. Cell B ends four hours at
−0.408454% capacity error and −0.0118574 SOC percentage points; both preferred
targets hold at the entry and all 126,000 intervals of the final weak hour.

The candidate remains **unpromoted**. Preferred SOC accuracy regressed for
772.971 seconds during renewed excitation, with a component-weight/output
switch around 7,811 seconds. Cell A preferred capacity remains unresolved at
the finite endpoint, and local uncertainty remains unvalidated. The
[result report](../experiments/continuous_learning_validation_001/implementation/REPORT.md)
and [decision](../experiments/continuous_learning_validation_001/implementation/decision.json)
close this bounded experiment. Its weighting/output diagnosis is now complete;
the conditional-belief decision above is next. A longer campaign is not an
automatic remedy.

The owned core subtotal remains **7,152 bytes**. Recorded worker RSS and runtime
output limits passed, but the supervisor's own peak RSS was not saved. The
proposed complete target allocation remains **10,032 bytes**, including
unmeasured reserves; complete Cortex-M23 qualification near **10 KiB total SRAM**
remains open.

The [parameter/state sensitivity analysis](../experiments/parameter_sensitivity_001/REPORT.md)
is also complete: all sixteen saved coordinates, three anchors and six future
protocols, with no learner rerun or code change. A 19.24% τ₂ error has a 1.571 mV
isolated reversal effect; the final complete-vector sampled peak remains below
0.987 mV across the fixed set. Signed compensation matters. These point effects
support output-focused validation, not coverage, universal nuisance tolerances
or parameter removal. The [new decision](../experiments/parameter_sensitivity_001/decision.json)
carries the regime and charge-dependent consequences into that frozen contract.

The original priority change put integration ahead of another uncertain-RC
refinement. That completed integration now supports the learner decision.
Proofs and small experiments remain essential when they resolve a
specific correctness obligation or design decision. They do not form an
open-ended sequence that must finish before the application can run.

This roadmap preserves the user's direction and original plan from 2026-10-24,
America/Los_Angeles, with M1 and both A4 candidate outcomes added on 2026-10-25.
The nonlinear-evidence design and its first implementation comparison completed
on 2026-10-26 UTC. Before inference, the user clarified that capacity need not
be discovered immediately. The [timing amendment](../plans/capacity_learning_horizon_001.json)
therefore replaced the unexecuted 900-second stop with a predeclared 2100-second
comparison. The M2 duration campaign and Cortex-M23 target work have not run.
The executable work order is [trajectory_to_m23_001.json](../plans/trajectory_to_m23_001.json).

The active [estimation targets](../plans/estimation_targets_001.json) prioritize
capacity error at most **5% relative** and current SOC error at most
**10 percentage points**, then the preferred region of **0.5% capacity** and
**0.5 percentage points SOC**. Gains below that preferred region have diminishing
priority against memory, processing and robustness. There is no universal
0.5% goal for nuisance parameters. These product requirements are separate
from local covariance widths and validated coverage. M1's original 0.5%/0.5 pp
benchmark and its failed outcome remain unchanged; the
[full-belief supplement](../experiments/m1_belief_audit_001/summary.json)
applies the new interpretation without replacing the frozen M1 scores.
Capacity has **no startup deadline**. SOC should become useful as soon as the
observations support it; capacity learning, weak-use retention and later renewed
learning are assessed separately. Time without distinguishing information need
not improve capacity, and accurate points do not validate uncertainty ranges.

## Three deliverables and their finish lines

| Milestone | Deliverable | Finish line |
| --- | --- | --- |
| **M1: Basic operation — functionally complete** | Two existing synthetic cells, one short trajectory each, desktop C estimation plus lifecycle handling | Lifecycle gates pass; the separate cell B 900 s usefulness failure is retained and blocks performance promotion of the sparse baseline |
| **M2: Desktop performance — candidate retained for qualification** | Continuous diagnostic and supplied-anchor replacement complete; public-start anchor refinement has verified partial evidence from a failed run | Prompt SOC, later capacity learning/retention, lifecycle, resources, numerical health and honest uncertainty assessed separately; no capacity startup deadline or annual promotion from one trace |
| **M3: Embedded delivery** | The chosen algorithm running as Cortex-M23 C near 10 KiB | Complete SRAM and timing measured, target execution and reset behavior demonstrated, relevant lifetime obligations closed under the stated deployment contract |

Start a target-build and memory-accounting skeleton during M1/M2. Final memory
optimization and target qualification follow the desktop algorithm decision.
This keeps portability visible without forcing every desktop experiment into
10 KiB immediately.

## Where we are

M1 now supplies the integrated desktop estimator lifecycle. The
[primary receipt](../experiments/trajectory_integration_001/primary/receipt.json)
records exactly 20 fits on the two existing 35-minute streams. Warm restarts
match uninterrupted numerical outputs and canonical checkpoint bytes exactly,
excluding timing fields. Cold reset clears inference while preserving the
known clock and input position. Deterministic probes cover invalid persistence,
delivery errors, missing voltage and unknown-input recovery.

The [independent scores](../experiments/trajectory_integration_001/scores.json)
separate functional acceptance from usefulness. At 900 seconds, cell B's
control and identical warm path hit the iteration limit: SOC error is
-3.96355 percentage points and capacity error is +26.6298%, with both targets
unresolved and no trusted local ranges. Both cells pass the accuracy thresholds
at 1,800 and 2,100 seconds, and both cold-reset branches pass those recovery
checkpoints. The failed checkpoint stays in the result; the sparse baseline
is not promoted as the long-run performance candidate.

The [M1 report](TRAJECTORY_INTEGRATION_001.md) and
[compact summary](../experiments/trajectory_integration_001/summary.json)
close A1-A3. The remaining decision is an autonomous learner with timely,
reliable learning and a declared bounded storage/work budget. No annual or
target qualification follows from this short integration result.

The first A4 candidate is now implemented at source revision
`b1004c16fcc4d8ee2acddb0a28e73c9b9e00f201` (identical published source
`28a543e163273975dd782b60fd803649955073a7`). The first result is published at
`bd2661336e72e84828b274010056ea5ea0b149b1`; original execution commits and
identical tree mappings are preserved in the [publication provenance](../provenance/bounded_online_001_publication.json).
It is a sixteen-coordinate joint square-root EKF that learns from
public priors, carries full state/parameter correlation, and retains no raw
history. Its [frozen plan](../experiments/bounded_online_001/plan.json),
[primary receipt](../experiments/bounded_online_001/primary/receipt.json) and
[independent review](../experiments/bounded_online_001/independent_review.json)
record one 12-process lifecycle experiment with 378,000 input deliveries and
no batch optimizer calls. Warm continuation is exact and functional/resource
gates pass. Across 16 scheduled arm/checkpoint pairs, SOC meets its hard limit
in **16/16**, capacity and joint hard limits in **6/16**, and both preferred
targets in **0/16**. Warm duplicates are paired continuity checks, not
independent accuracy evidence.

The [memory account](../experiments/bounded_online_001/memory_accounting.json)
reports **5,848 bytes** for state/workspace/query, **7,016 bytes** for the
named fixed host objects and **2,440 bytes** per complete checkpoint. These
are different scopes from M1's **49,470,676-byte** session-plus-fit ownership
and the earlier fixed-chart component's **7,064 bytes**. The new learner
compresses history into a local Gaussian belief; it no longer supports the
reference's nonlinear reevaluation of every retained observation. Host
storage and stack evidence do not qualify a complete M23 subsystem.

The first result exposed two blockers. A single outward correction at a nuisance
boundary can set the common gain to zero for all coordinates: cell B's
control run has 71,928 zero-gain updates out of 73,500. Separately, capacity can
be wrong while the local uncertainty is narrow. Cell A's cold branch finishes
at **-7.485% capacity error** with a narrow local interval and a provisional
label, despite only **1,434/42,000** post-reset updates having zero gain. Fixing
the boundary stall is therefore not established as a cure for local-Gaussian
overconfidence. Both failures prevented promotion of that first candidate.

The [component-wise successor, bounded_online_002](../experiments/bounded_online_002/REPORT.md),
is now complete at original source `4c59c2363bf8ebe81238b30af7b03d802a5e3e13`
and identical published source `bdfa692584911fb536b08c5f496188ec42d93ca2`.
It uses independent feasible coordinate gains with the matching full Joseph
covariance in a lower-triangular factor. One frozen run preserves exact warm
continuation, removes all observed global zero-gain updates and passes the
functional/resource gates. Core storage is **5,896 bytes**, named fixed host
storage **7,064 bytes**, and the host objects plus reviewed own-source stack
partial total **8,184 bytes**. Complete M23 costs remain unqualified.

The candidate still fails promotion: **16/16** scheduled SOC hard checks pass,
but only **8/16** capacity/joint hard checks and **0/16** joint preferred checks.
Excluding duplicate warm checks, joint hard passes are **6/10**. Cell B control
finishes at **-7.53789%** capacity error with a narrow provisional local range
despite no rejected corrections. Separately, cold-reset suffixes reject **7**
and **10** corrections. The saved queries associate those windows with R3 near
zero but do not identify the failed internal operation. The
[behavior review](../experiments/bounded_online_002/behavior_review.json) keeps
that cause unresolved. No annual run follows this result.

The [boundary transaction diagnostic](../experiments/boundary_transaction_diagnostic_001/REPORT.md)
is now complete. One fixed fixture reproduces the mean-domain defect at R3 and
checks a finite coordinate-only zero-gain fallback. All 625 baseline/remedy
assertions pass; the baseline success means its expected defect reproduced.
The maximum remedy-versus-dense-Joseph covariance error is 2.22e-16. A positive-dt
failure preserves the advanced prediction, duplicate inputs are byte-atomic,
and no cell histories or new two-cell primaries ran. Production source remains
unchanged; the historical 17 rejection causes still lack actual failed-step
records. The [numerical remedy](../experiments/boundary_transaction_diagnostic_001/decision.json)
and [separate uncertainty decision](../plans/local_uncertainty_decision_001.json)
are frozen. Neither repairs or qualifies the measured capacity bias.

The [nonlinear-evidence design](../experiments/nonlinear_evidence_design_001/REPORT.md)
selected two persistent components from one public log-capacity moment split.
Its saved-result audit exposed OCV/hysteresis compensation and a public
input-only reachability violation without identifying a unique bias cause.
The [new implementation](../experiments/nonlinear_hypothesis_001/REPORT.md) now
passes 7386 core and 188 checkpoint checks, then one frozen two-arm B 2100 s
comparison. Split capacity errors at 900/1800/2100 s are +13.16356%, +0.75176%
and +0.09523%; the control remains −7.53789% at the endpoint. This supports
continued learning, but 79 saved local-provisional capacity queries breach the
hard error target and final local ranges still miss truth. Complete target
memory/timing and trustworthy uncertainty remain open.

The user-requested compact-layout step is now implemented and checked in
[compact_bounded_001](COMPACT_BOUNDED_001.md). Its fixed-chart component owns
7,064 bytes, preserves the original evidence/remainder values on the focused
replay, and reports SOC/Q through the complete joint null space. This is an
available component for the streaming-backend decision. Its fixed chart and
remainder limitations remain; it does not by itself supply public cold-start
learning or safe historical chart changes. M1 was built from a descendant of
`implementation/compact-bounded-001`, preserving this component and its reference.

| Existing piece | What it supplies | What remains |
| --- | --- | --- |
| [Completed 35 Hz C study](../report/SCM-35Hz-Results.html) | Two cells, three noise seeds each; sixteen-quantity estimation, SOC/capacity learning and weak-use comparison | Growing-history replay; historical ten-prefix schedule remains distinct from M1's sparse schedule |
| [M1 session and checkpoint](TRAJECTORY_INTEGRATION_001.md) | Ordered ingestion, full journal, fresh-process continuation, cold reset, freshness and error semantics | Growing memory/work, masked-voltage fitting unsupported, cell B's early sparse-fit usefulness failure |
| [C model](../include/scm_model.h) and [estimator](../include/scm_estimator.h) | Chronological dynamics, public initialization and a working nonlinear fit | Reliable timely learning under the chosen work schedule and an autonomous bounded backend |
| [Target assessment](../include/scm_assess.h) | Unexcited, unresolved and provisional outputs; M1 labels evidence age and current-state propagation | Local likelihood diagnostics do not establish validated coverage; EOD/temperature targets remain unsupported |
| [Bounded certificate004](UNCERTAIN_RC_004.md) | Fixed-memory SOC/capacity support; conditional all-prefix containment and availability | Restricted model; three preserved strict-learning failures; no full-model or target qualification |
| [Bounded event/remainder work](BOUNDED_EVENT_002.md) | Sensitivity-aware summaries and concrete limits of local evidence compression | Nonlinear cold start, historical chart changes and validated arithmetic remain open |
| [Compact bounded layout](COMPACT_BOUNDED_001.md) | Shared config, selective atomic staging and SOC/Q reports from the full joint matrix; 33.7% smaller ingestion objects | Same fixed-chart/lifetime limitations; complete recovery, solver and target costs remain open |
| [First autonomous bounded learner](../experiments/bounded_online_001/independent_review.json) | Public cold start, fixed full state/parameter factor, complete checkpoint, exact warm continuation; functional/resource gates pass | Capacity fails 10/16 scheduled hard checks; common-gain stalls and wrong narrow capacity beliefs block promotion |

The original two-cell traces contain hysteresis and multiple unknown RC modes.
They are outside certificate004's known-other-dynamics/no-hysteresis contract.
The completed full-model lifecycle demonstration therefore uses the existing full C
reference. The certificate stays a separately labeled matched-contract lane.
Supplying generator truth as known parameters would not bridge that gap.

The restricted provider's 3,472-byte host object/own-stack subtotal is useful
resource evidence. It is not the memory figure for the full estimator or the
complete target subsystem. Earlier results and failures remain unchanged.

## Completed M1 action plan: original scope and acceptance gates

A1-A3 below preserve the implemented work order and its original acceptance
criteria. Their functional work is complete. The frozen experiment and
usefulness failure are linked above; further optional lifecycle refinements
are not prerequisites for A4.

### A1. Build the desktop session adapter — complete

Expose one lifecycle around the existing C reference: initialize, ingest,
advance state, query/status, checkpoint, restore and explicit cold reset.
The host adapter may retain a complete journal and schedule prefix fits. That
makes it a desktop integration baseline; accepting one sample at a time does
not make its retained storage bounded.

Use these existing cases, with their manifest hashes unchanged:

- `cell_a_35hz_s202610240`: 2,100 seconds, 73,500 observations.
- `cell_b_35hz_s202610240`: 2,100 seconds, 73,500 observations.

Keep one noise seed per cell. Their existing phases already exercise rest,
pulses, sustained load, reversals and a weak tail. Do not rerun the original
60-fit campaign. The new sparse fit schedule is 10, 900, 1,800 and 2,100 seconds.
A restored run is compared with its own uninterrupted control using that same
schedule. The older ten-checkpoint warm-start results remain useful context;
they are not an exact numerical target for a different schedule.

Each query must identify the target value or range, its uncertainty semantics,
qualification/reason, input position and freshness. A stale fitted point is not
a fresh current-state estimate. Unsupported targets remain explicit. EOD and
temperature behavior must not be advertised as implemented merely because an
output field exists.

### A2. Implement complete checkpoint and recovery behavior — complete

Persist the configuration/model identity, all required evidence and carried
state, fit-start/schedule state, and last-consumed input identity. For this
host baseline, a complete durable journal plus reconstruction metadata is
acceptable. A pointer-containing struct dump or the latest point estimate
alone is not a complete portable checkpoint.

| Event | Required behavior |
| --- | --- |
| Warm restart with valid state | Continue without extra initialization or duplicate evidence |
| Restore from an older valid checkpoint with a complete journal | Replay intervening inputs exactly once; reproduce uninterrupted state and queries |
| Cold reset with lost history | Keep the simulated battery running; restart inference from public priors, expose lost knowledge and measure relearning |
| Corrupt, truncated or incompatible checkpoint | Reject explicitly; do not continue with silently altered state |
| Duplicate, out-of-order input or exhausted sequence representation | Reject or follow a documented idempotent rule without double ingestion; no silent wrap |
| Unknown current/time gap | Use an implemented valid uncertainty envelope or report recovery required; never invent zero current or zero RC state |
| Missing voltage with known current/time | Preserve physical propagation; omit only the unavailable voltage evidence when supported, otherwise expose the backend limitation |

Freeze numerical comparison tolerances before the paired run. Serialized and
integer state should agree exactly for deterministic continuation. Compare
floating numerical outputs under the same build and declared tolerances;
exclude timing measurements. The estimator never receives the plant's hidden
state at reset.

### A3. Run the two cells and publish one integrated result — complete

For each cell, run an uninterrupted control and one paired path with warm
restores after 12, 1,200 and 1,850 seconds. These cover a transient, learned
state and weak use. Add one cold-reset branch at 900 seconds with at most two
later fits. Check invalid persistence and delivery with small deterministic
API probes, without launching further optimization sweeps. The planned upper
budget is 20 fit calls across both cells, including paired and cold-reset runs.
Warm checkpoints retain fit/schedule state; any recomputed scheduled fit also
counts against that cap.

The report needs SOC/capacity trajectories and statuses, first and sustained
usefulness, retention through weak use, restart divergence, relearning,
resource costs and every failed or unsupported requirement. Synthetic truth
belongs only in scoring after inference.

Report the inherited synthetic benchmark of SOC error below 0.5 percentage
points and capacity relative error below 0.5 percent at informative suffix
checkpoints. These are regression/performance targets for this matched-model
experiment, not product accuracy or coverage guarantees. Cold-reset recovery
is assessed separately; do not hide its unknown period in a global average.

**Functional acceptance and useful estimation are separate results.** A
correct lifecycle can be demonstrated even when a quality target fails, but
that estimator is not promoted as the long-run performance candidate. Record
one concrete blocker and address it. Do not require all nuisance parameters
to become precise or every historical strict-narrowing assertion to pass.

M1 ends with one compact receipt, one human report and a short blocker list.
A new framework or a comprehensive fault Cartesian product is not required.

## M2 action plan: establish desktop performance, then extend duration

### A4. Qualify one autonomous bounded learner — later learning observed

Both frozen candidates remain complete and preserved. Keep the successor's
component-wise gain mechanism and the selected numerical remedy; reject
candidate promotion. The full factor must continue to use the actual selected
gain in both the mean and full Joseph covariance.

The [boundary diagnostic](../experiments/boundary_transaction_diagnostic_001/summary.json)
has stopped at its declared finish line: one minimal binary64 witness and a
frozen finite-mean zero-gain fallback. The fixture confirms that a subnormal
feasibility multiplier can round upward while its relative backoff has no
representable effect. Stage/coordinate capture identifies the constructed
failure as `mean_domain`, R3. This does not attribute the original 17 events,
whose actual failure operands were not saved.

The original remedy study changed a diagnostic variant only. The subsequent
two-component candidate integrates that remedy in both new arms; the prior
online candidates remain unchanged. Committed prediction on rejection,
exactly-once accounting and all-zero-gain identity are tested. The diagnostic
fixture's 80-byte capture records and host oracle remain outside the embedded
implementation; new learner storage is accounted separately.

The [local uncertainty decision](../plans/local_uncertainty_decision_001.json)
keeps the full covariance and local ranges as precision diagnostics.
Application SOC/Q accuracy stays unresolved uniformly for this learner,
coverage stays unvalidated, and the local Gaussian supplies no hard support.
Original raw statuses, failed qualification audits, point-error limits and
useful-availability gates stay unchanged. An all-unresolved reporting policy
cannot manufacture a performance pass.

The frozen contract is implemented on `implementation/nonlinear-hypothesis-001`.
Packed factors, causal weights, full staging, separate evidence cursors and
the 3004-byte atomic checkpoint format pass targeted tests. Source and resource
hashes were committed before either primary arm. The user's timing amendment
was also frozen before inference; the original 900 s test remains unexecuted.
The [one declared 2100 s comparison](../experiments/nonlinear_hypothesis_001/summary.json)
is complete. Keep the fixed public split for further qualification, while
preserving local uncertainty failures and the historical candidates. At 900 s
a useful alternative has negligible predictive weight; late aggregate gains
come from the dominant component continuing to learn. Two-component necessity
and trustworthy weighting/coverage remain unresolved.

Promotion still requires hard targets, lifecycle, resources, numerical health
and honest uncertainty qualification. Report the preferred 0.5%/0.5 pp region
separately. Each experiment must close one named delivery decision; attention,
variations and duration campaigns follow a qualified small candidate.

The desktop result is an empirical performance reference for the stated
models and scenarios. Calling it "ultimate performance" does not establish a
global optimum or measured-cell coverage.

### Keep attention as one decision experiment

First qualify the plain candidate on the small harness. Then compare it with a
regular/no-attention work schedule and one concrete attention policy. Include
the existing sensitivity/event-summary method when its model/chart assumptions
match; keep the full retained-history C result as an external reference.

Use identical inputs, public priors, reset schedules and a declared per-arm
compute/storage budget. Every arm advances charge and dynamics through every
actual interval. Attention may schedule costly work or choose a documented
evidence representation. It cannot silently skip physical evolution, obtain
truth, or treat reweighted/dropped observations as unchanged likelihood or
hard support.

Freeze the policy and a practical benefit threshold before held-out scoring.
Measure target quality/availability alongside CPU and memory. Keep attention
if it earns the declared benefit without unacceptable losses. Otherwise keep
the simpler baseline and close that comparison. No broad architecture search
is implied.

### Use a short variation matrix and a duration ladder

The candidate now has the earlier finite learning comparison and the completed
continuous diagnostic; broader performance and uncertainty qualification remain
open. The declared continuous lifecycle checks passed. The
[continuous validation design](../experiments/continuous_learning_validation_001/REPORT.md)
required a short A lifecycle validity gate before one four-hour B diagnostic; both stages have now completed once.
This is explicitly a bounded learning/retention diagnostic: A accuracy is scored
observationally, while numerical, accounting, lifecycle and known-resource
failures block B. An A accuracy miss cannot create a capacity startup deadline
or disappear from usefulness assessment. This diagnostic exception does not
promote the candidate or waive the hard-target/uncertainty gates for the later
day/week/annual campaign. Historical failures remain preserved.

| Step | Purpose | Scope control |
| --- | --- | --- |
| Short paired variations | Separate cell, load and noise effects | Informative/reversal use, repetitive weak use and long rest; a few noise levels/correlation cases; avoid their full Cartesian product |
| One-day pilot | Measure actual update cost, logging and checkpoint behavior | Stop and diagnose a reproducible failure before increasing duration |
| One-week pilot | Check repeated recovery and bounded resources | Use the already chosen candidate and schedule |
| Two annual streams | Observe long-term estimation and numerical behavior | One selected stream per cell; predefined load/noise changes, carried state and reset events |

At exactly 35 Hz, a 365-day stream contains **1,103,760,000 updates**. Two streams
contain **2,207,520,000 updates**. Select annual scenarios by declared regime
and stress coverage, and freeze held-out annual noise seeds before scoring
them. Short screening may select the algorithm and reveal failure regimes;
it must not select seeds for favorable accuracy. The pilot must produce a
wall-time and output storage estimate before annual execution. Faster-than-real-time simulation is
fine; changing sample order, skipping intervals or algebraically advancing a
long rest needs separate equivalence evidence. Actual intervals remain the
inference authority.

Generate deterministic chunks, retain bounded metrics/checkpoints, and save
failure excerpts with their entering state and source/seed/configuration
identity. Full-history C fitting belongs on selected short causal histories.
A limited-window comparison must disclose what earlier evidence it lacks and
how entering state is treated; it is not a full-year oracle.

Separate matched-model numerical tests from sensor bias, outliers, OCV error,
temperature and aging/drift tests. The latter require explicit plant laws and
estimator behavior. A year with static parameters is not aging validation.
When a premise fails, the result must show degraded, unresolved or inconsistent
behavior rather than silently inheriting the old certificate. Different cells
are separate streams unless battery replacement is an explicit event.

M2 reports error and uncertainty by regime, convergence and useful-time
fraction, retention/recovery, memory/latency, checkpoint-write cost, numerical
range diagnostics and reproducible failures. Freeze acceptance thresholds
before the campaign. A finite year supplies endurance evidence; the relevant
all-prefix proofs remain a separate requirement.

## M3 action plan: make the selected model fit and run

Use 10,240 bytes as the initial subsystem SRAM planning ceiling. Count all
simultaneously live estimator state, RAM-resident configuration, workspace,
acquisition/delivery buffers, checkpoint staging and attributable stack,
interrupt and runtime use. Report flash and nonvolatile persistence separately.
Do not hide an overrun by leaving required buffers or helper costs outside the
boundary. Unrelated application RAM is outside this estimator subsystem.

Identify the actual Cortex-M23 device, clock, compiler/ABI and scheduling
budget. Build and run the chosen C implementation, measure worst-case update
and scheduled-work latency, and compare outputs/statuses with the desktop
contract. The nominal 35 Hz rate alone does not specify the CPU budget.

Replay M1 and selected M2 excerpts, especially failures and recovery events,
through the target build. Demonstrate reset/restore and delivery behavior on
the declared target hardware or explicitly qualified execution environment.
Compile-only success is an intermediate result. Close the arithmetic,
evidence-retention and lifecycle obligations applicable to the deployed path;
keep physical assumptions and unsupported behaviors visible.

## Rules that keep the work moving

1. **Name the decision before starting research.** Every proof or experiment
   must resolve a milestone gate or change an algorithm choice.
2. **Use one bounded iteration.** One concrete design, one small falsification,
   then a keep/change/drop decision. Expand only for a named remaining question.
3. **Treat defects according to their effect.** Arithmetic/containment defects
   block the claim they invalidate. A precision plateau triggers work when it
   prevents the declared SOC/capacity objective; a universal precision theorem
   is not a prerequisite for a useful demonstration.
4. **Carry the evidence forward.** Preserve failures and provenance. Do not
   retune old gates, shrink domains around truth, silently reset uncertainty,
   double-count history or rerun old campaigns merely to resume.
5. **Advance at the finish line.** Once a milestone's gates are met, move to
   the next deliverable rather than adding optional refinements.

The proposed fixed R/tau partition is now parked as a possible targeted remedy.
It is not automatically the next study. Broad attention searches, complete
identification of every nuisance parameter and theorem extensions beyond the
chosen implementation's needs are also outside the immediate critical path.

## Next executable action

The [minimal aging-aware model](../specifications/minimal_health_model_001/model.json)
is specified. It has five physical states, two evolving health quantities
(log-capacity and ohmic resistance), and nine uncertain static parameters.
The initial public prior remains once-only. Each actual input interval has a
normalized health transition; rate/noise values must be declared explicitly.
The supplied numeric profiles are synthetic test assumptions, not calibrated
cell-aging laws.

Implement a separate desktop kernel for the declared update order, path density
and SOC-continuous accessible-capacity convention. Account for the change in
accessible charge explicitly. Qualify zero drift, mixed-current charge balance,
zero-duration/order behavior, transition normalization and derivatives, support
boundaries, weak input and low-dimensional marginal controls within the stated
finite budgets. Twenty-nine completed consistency checks cover specification
arithmetic and source bindings only; no aging implementation has run.

The chosen inference target is the Bayesian joint marginal of current physical
state, health and static nuisance quantities. Joint-path MAP may help debug the
model but cannot stand in for that marginal or its uncertainty. Select and
register a numerically checked full-history posterior reference before any
canonical aging inference. The old stationary desktop remains a zero-drift
control; its 545-point pass does not validate aging.

Only then compare fixed response bases and multiple local summaries against
the same dynamic target. The user requires SRAM-only deployment history within
roughly 10 KiB for the complete subsystem; no flash/FRAM/archive replay fallback.
Desktop diagnostic memory remains explicitly exempt. Keep physical aging-rate
calibration, useful uncertainty, varied cell/load/noise/duration stability and
actual Cortex-M23 execution as distinct later gates.

### What the current memory figures mean

The preserved compact schema owns 8,088 B core, 408 B input store, 56 B calibration and
128 B codec reservation: 8,680 B objects. Add 768 B project stack and 768 B
runtime/IRQ/caller reservations for **10,216 B planned**. The query phase fits a
224 B first-order state and 32 B decoded input within its shared 1,600 B workspace.
The standalone 304 B ADC FIFO is not additionally owned. See the concrete
[layout](../experiments/live_anchor_bootstrap_001/live_layout.h); full integration,
actual target stack and timing remain unqualified.

The following figures describe preserved earlier components.

The new experimental bank owns 6,368 B of retained factor/state/metadata, inside
an 8,112 B core with serialized workspace, report and one ADC sample. The factor
alone is 5,624 B. Add 448 B ADC queue, 128 B checkpoint-codec reservation,
768 B project-stack cap and 768 B runtime/IRQ/caller reservation: 10,224 B planned
total. Compiler-reviewed project call chains fit their cap on this host; target
runtime and timing remain unknown. The old learner is not present simultaneously.
The 42 reference models, two experimental banks, audit replay and host snapshots
are qualification machinery and are included in measured host RSS, not this
one-candidate target ledger.

The earlier streaming C candidate owns 7,152 bytes and retains no raw history,
but its uncertainty and performance qualification remain open. The latest
anchor experiment is a separate host reference: its C likelihood evaluator has
a 10,680-byte fixed workspace inside an 11,072-byte compiler-reported main
frame. Those overlapping figures are not complete estimator RAM and exclude
the host proposal solver, other call-chain/runtime costs and stored observations.

The external 8,064,000 bytes are the first 252,000 raw measurement records from
the existing observation archive: a uint64 sample index followed by binary64
actual interval, current and voltage, 32 bytes per record. At the nominal 35 Hz this
is two hours of input history. The evaluator reads it through a 4,096-byte
buffer and reevaluates it at each trial point. Fixed evaluation workspace does
not bound the retained-history size or the work needed for later replay.
The [C evaluator](../experiments/retained_likelihood_replacement_001/stream_evaluator.c)
and [frozen input contract](../plans/autonomous_anchor_refinement_001.json)
define these scopes.

A deployable solution must combine useful nonlinear inference and honest
uncertainty with bounded retained evidence and a measured complete C resource
budget. Capacity still has no startup deadline. The M2 varied-duration campaign
and M3 Cortex-M23 execution, timing and complete SRAM qualification remain ahead.
