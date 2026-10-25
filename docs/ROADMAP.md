# Delivery roadmap: trajectories to Cortex-M23

## Decision

The next milestone is a **two-cell end-to-end desktop demonstration**. After it
works, select a streaming estimator and evaluate it across varied trajectories,
including two one-year streams. Then deliver a runnable Cortex-M23 C subsystem
with an approximately **10 KiB total SRAM budget**.

This changes the immediate priority from another uncertain-RC refinement to
integration. Proofs and small experiments remain essential when they resolve a
specific correctness obligation or design decision. They do not form an
open-ended sequence that must finish before the application can run.

This roadmap records the user's direction on 2026-10-24, America/Los_Angeles.
It is a plan, not a claim that the new trajectory or target tests have run.
The executable work order is [trajectory_to_m23_001.json](../plans/trajectory_to_m23_001.json).

## Three deliverables and their finish lines

| Milestone | Deliverable | Finish line |
| --- | --- | --- |
| **M1: Basic operation** | Two existing synthetic cells, one short trajectory each, desktop C estimation plus lifecycle handling | Estimation, chronological ingestion, query/status, checkpoint/restore, cold reset and explicit error/gap handling demonstrated together; usefulness reported separately |
| **M2: Desktop performance** | An autonomous streaming candidate, short load/cell/noise comparisons, then about one year per selected cell | Chosen candidate meets frozen usefulness and resource gates; no unexplained age-driven failure; numerical proofs and finite endurance evidence reported separately |
| **M3: Embedded delivery** | The chosen algorithm running as Cortex-M23 C near 10 KiB | Complete SRAM and timing measured, target execution and reset behavior demonstrated, relevant lifetime obligations closed under the stated deployment contract |

Start a target-build and memory-accounting skeleton during M1/M2. Final memory
optimization and target qualification follow the desktop algorithm decision.
This keeps portability visible without forcing every desktop experiment into
10 KiB immediately.

## Where we are

We are at the entrance to M1. The repository already supplies substantial
pieces, but they have not been assembled into a complete estimator lifecycle.

The user-requested compact-layout step is now implemented and checked in
[compact_bounded_001](COMPACT_BOUNDED_001.md). Its fixed-chart component owns
7,064 bytes, preserves the original evidence/remainder values on the focused
replay, and reports SOC/Q through the complete joint null space. This is an
available component for the later streaming-backend decision. It does not
complete M1 or change its first action. Start integration from the latest
`implementation/compact-bounded-001` branch or a newer descendant so this work
and its preserved reference remain available.

| Existing piece | What it supplies | What remains |
| --- | --- | --- |
| [Completed 35 Hz C study](../report/SCM-35Hz-Results.html) | Two cells, three noise seeds each; sixteen-quantity estimation, SOC/capacity learning and weak-use comparison | Growing-history replay; no complete persistent streaming session |
| [C model](../include/scm_model.h) and [estimator](../include/scm_estimator.h) | Chronological dynamics, public initialization and a working nonlinear fit | Session lifecycle, complete recovery and an autonomous bounded-work/storage backend |
| [Target assessment](../include/scm_assess.h) | Unexcited, unresolved and provisional outputs with reasons | Product-level availability/freshness and recovery semantics |
| [Bounded certificate004](UNCERTAIN_RC_004.md) | Fixed-memory SOC/capacity support; conditional all-prefix containment and availability | Restricted model; three preserved strict-learning failures; no full-model or target qualification |
| [Bounded event/remainder work](BOUNDED_EVENT_002.md) | Sensitivity-aware summaries and concrete limits of local evidence compression | Nonlinear cold start, historical chart changes and validated arithmetic remain open |
| [Compact bounded layout](COMPACT_BOUNDED_001.md) | Shared config, selective atomic staging and SOC/Q reports from the full joint matrix; 33.7% smaller ingestion objects | Same fixed-chart/lifetime limitations; complete recovery, solver and target costs remain open |

The original two-cell traces contain hysteresis and multiple unknown RC modes.
They are outside certificate004's known-other-dynamics/no-hysteresis contract.
The first full-model lifecycle demonstration therefore uses the existing full C
reference. The certificate stays a separately labeled matched-contract lane.
Supplying generator truth as known parameters would not bridge that gap.

The restricted provider's 3,472-byte host object/own-stack subtotal is useful
resource evidence. It is not the memory figure for the full estimator or the
complete target subsystem. Earlier results and failures remain unchanged.

## M1 action plan: make the whole path work

### A1. Build the desktop session adapter

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

### A2. Implement complete checkpoint and recovery behavior

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

### A3. Run the two cells and publish one integrated result

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

### A4. Select one actual streaming learner

The full C replay reference remains the short-run comparison. Before an annual
run, choose a candidate that learns from public priors, carries its own state
and evidence, and has a declared finite storage/work budget. This is a real
remaining algorithmic gap; the session wrapper alone does not solve it.

Use the M1 harness to make that decision. Desktop memory and arithmetic can be
more generous than the final target, but their costs and eventual target path
must be visible. Preserve the same input, public assumptions and scoring when
comparing candidates. Warm starts are not independent evidence.

The desktop result is an empirical performance reference for the stated
models and scenarios. Calling it "ultimate performance" does not establish a
global optimum or measured-cell coverage.

### Keep attention as one decision experiment

First obtain the plain pipeline. Then compare the same candidate with a
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

Create `integration/two-cell-lifecycle-001` from the latest canonical planning
checkpoint. Implement A1 and A2 with their small deterministic checks, then run
A3. Use the frozen reference and certificate evidence selectively. Publish the
integrated result before selecting the next estimator refinement.
