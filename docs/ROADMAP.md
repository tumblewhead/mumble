# Delivery roadmap: trajectories to Cortex-M23

## Decision

**M1's desktop lifecycle is complete, and the first autonomous bounded learner
has completed its small falsification.** Both have preserved performance
failures. The bounded learner passes functionality and its initial storage
gate, but fails capacity accuracy and uncertainty qualification; it is not
promoted. The next action is **one boundary-aware gain design and one repeat
of the same small two-cell harness**. Longer trajectories follow a qualified
candidate, then a runnable Cortex-M23 C subsystem near **10 KiB total SRAM**.

The original priority change put integration ahead of another uncertain-RC
refinement. That completed integration now supports the learner decision.
Proofs and small experiments remain essential when they resolve a
specific correctness obligation or design decision. They do not form an
open-ended sequence that must finish before the application can run.

This roadmap preserves the user's direction and original plan from 2026-10-24,
America/Los_Angeles, with the M1 and first A4 outcomes added on 2026-10-25 UTC.
The M2 duration campaign and Cortex-M23 target work have not run.
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

## Three deliverables and their finish lines

| Milestone | Deliverable | Finish line |
| --- | --- | --- |
| **M1: Basic operation — functionally complete** | Two existing synthetic cells, one short trajectory each, desktop C estimation plus lifecycle handling | Lifecycle gates pass; the separate cell B 900 s usefulness failure is retained and blocks performance promotion of the sparse baseline |
| **M2: Desktop performance — first A4 candidate rejected** | One bounded successor on the small harness, then short load/cell/noise comparisons and about one year per selected cell | Chosen candidate meets hard target, lifecycle, resource and honest-qualification gates before duration increases; numerical proofs and finite endurance evidence reported separately |
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

Two measured blockers remain. A single outward correction at a nuisance
boundary can set the common gain to zero for all coordinates: cell B's
control run has 71,928 zero-gain updates out of 73,500. Separately, capacity can
be wrong while the local uncertainty is narrow. Cell A's cold branch finishes
at **-7.485% capacity error** with a narrow local interval and a provisional
label, despite only **1,434/42,000** post-reset updates having zero gain. Fixing
the boundary stall is therefore not established as a cure for local-Gaussian
overconfidence. Both failures block promotion; no annual run follows this result.

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

### A4. Qualify one autonomous bounded learner — one successor next

The first full-factor candidate is complete and rejected for performance and
qualification. Preserve it, its plan and its first result. The next bounded
change addresses the measured common-gain stall: a **boundary-aware active-set
gain** should allow feasible coordinates to learn when a nuisance correction
points out of its permitted domain.

Freeze the exact gain rule and a numerically valid square-root implementation
before the next inference run. The chosen gain must be used consistently in
both the mean and the full Joseph covariance update, with cross-correlations
preserved. A coordinate-dependent gain cannot automatically reuse the old
single-scale factor formula. First account for all simultaneously live state,
workspace, staging and stack, and identify the fixed work per observation.
Then implement only the deterministic numerical and boundary tests needed
to establish this changed update and preserve the existing lifecycle contract.

Hold the public priors, noise/model assumptions, observation streams, reset
schedule and target thresholds fixed. Freeze one successor plan and run the
same small two-cell harness once. Compare hard target errors, availability,
local qualification, boundary stalls and resource costs against the preserved
first A4 result and frozen M1 reference. Fewer zero gains alone are not success.
Wrong narrow capacity beliefs remain an independent rejection reason; do not
promise that the gain change fixes them or retune priors/noise after scoring.

The finish line is a keep/change/drop decision from that one run. Promotion
requires the declared hard targets, lifecycle and resource gates and honest
uncertainty qualification. Report the preferred 0.5%/0.5 pp region separately;
do not pursue smaller errors while those practical gates remain unmet. If a
gate fails, stop, preserve the failure and name one measured blocker for the
next decision. No automatic attention search, extra proof program, parameter
sweep or duration campaign follows.

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

These steps are blocked until a candidate passes the small-harness hard
targets, lifecycle, resources and qualification gates. Neither M1 nor the
first A4 result authorizes increasing duration by itself.

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

Create a successor work branch from the latest completed A4 descendant.
Specify one boundary-aware active-set gain and its matching full Joseph
square-root update, with complete memory accounting and a small deterministic
verification contract. Freeze its plan, implement the change, then replay the
same two-cell harness once with unchanged public priors/model/data. Keep the
first result and decide against hard target and qualification gates. Day,
week and year runs remain blocked until that candidate qualifies.
