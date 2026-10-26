# Frozen continuous learning and retention validation

## Decision

**Freeze one staged diagnostic study for the unchanged two-component learner:**
a short Cell A lifecycle gate, followed by one four-hour continuous Cell B
trajectory if the gate is valid. The [contract](../../plans/continuous_learning_validation_001.json)
is complete. **This design task generates no observations, executes no learner,
and changes no estimator source.** The candidate remains retained for
qualification, with application accuracy unresolved and coverage unvalidated.

The baseline is published commit `91105b2e1a367fdbb1570fb1b273d95806df6dca`.
The completed [learner comparison](../nonlinear_hypothesis_001/summary.json)
and [parameter sensitivity analysis](../parameter_sensitivity_001/summary.json)
remain unchanged. Their execution/publication identities remain in their
existing provenance maps. This contract asks whether useful learning survives
continuous use; it does not rerun either completed study.

Capacity retains its **5% hard and 0.5% preferred** point-error targets, with
**no startup deadline**. SOC retains **10 percentage points hard and 0.5 points
preferred**, and acquisition is measured from the first interval. Four hours
is a finite experiment budget chosen before new inference. It is not a promise
that capacity must become known within that time.

## Why a second-cell gate comes first

The new split learner has one Cell B primary. The earlier full two-cell
lifecycle results belong to other implementations. Its own checkpoint checks
and small CLI fixture are useful prerequisites, but do not establish full
second-cell or coupled generator/learner continuation. The
[source audit](implementation_audit.json) records that distinction.

Cell A uses the inherited 2100-second **current protocol**, newly generated
plant observations and a fixed new noise seed. Its three learner processes are:

| Arm | Operation | Delivered intervals |
| --- | --- | ---: |
| Uninterrupted | Public split initialization; run 0–2100 s; save a coupled checkpoint at 900 s | 73,500 |
| Warm suffix | Fresh process restores that checkpoint and runs 900–2100 s | 42,000 |
| Cold suffix | Restore the same learner checkpoint, call its public cold-reset API once, then consume the same 900–2100 s physical suffix | 42,000 |

The warm suffix must reproduce future observation bytes, generated physical/RNG
state, per-sample outputs and final canonical learner checkpoints. The cold
suffix deliberately loses estimator knowledge while retaining known input
position and clock. It never resets the physical cell or inserts true state.
These shared suffixes are lifecycle comparisons, not independent noise trials.

**Admission to the four-hour diagnostic requires numerical, accounting,
lifecycle and known-resource validity.** Cell A accuracy is scored and its
failures remain visible. An accuracy miss does not alter the frozen Cell B
experiment or create a new capacity deadline. It does prevent a broader
usefulness or campaign-promotion claim. This explicit diagnostic exception
does not waive the roadmap's qualification gates for day/week/annual campaigns.

## The four-hour continuous trajectory

Cell B starts once from the existing public prior, with its separately declared
synthetic plant initialization and fixed new noise seed. Every phase carries
both nonlinear components, both full covariance factors, predictive log
weights, plant states, RNG state, physical clock and global input index.

| Time from start | Prescribed use | Diagnostic purpose |
| --- | --- | --- |
| 0–35 min | Inherited current protocol with fresh observations | Prompt SOC and initial capacity acquisition |
| 35–50 min | Rest, 0 A | Retention through rest |
| 50–120 min | Weak discharge, +3 mA | Retention through weak use |
| 120–135 min | Sustained discharge, +60 mA | Renewed charge movement and load |
| 135–140 min | Rest | Relaxation after load |
| 140–155 min | Charge, −60 mA | Charge and direction reversal |
| 155–160 min | Rest | Relaxation after charge |
| 160–170 min | 30 cycles: +60 mA for 10 s, then 0 A for 10 s | Repeated transitions |
| 170–180 min | 10 cycles: −60 mA for 30 s, then +60 mA for 30 s | Balanced charge/discharge reversals |
| 180–240 min | Weak discharge, +1 mA | Final retention |

The stream has **504,000 intervals at 35 Hz**, with no phase reset or history
loop. Current is constant within each interval and voltage is sampled at its
end. The delivered binary64 interval remains the estimator's time authority;
integer sample counts define phase boundaries. This is a synthetic laboratory
input, not a hardware stimulus recommendation.

The independent rational accounting audit finds **23.077381 mAh net discharge**
and **71.410714 mAh absolute charge movement**. The prescribed Cell B SOC stays
between **28.4214% and 78%**. These are generator-domain calculations from the
frozen inputs and plant table, not estimator results. The contract introduces
no truth-dependent clipping, input feedback or tuned endpoints.

Four hours supplies an 85-minute first rest/weak period, a 60-minute renewed-use
period and a 60-minute final weak period. A single chronological schedule cannot
separate elapsed time, number of observations and changing stimulus causally.
The result can show learning or retention during those phases; it cannot prove
that time alone or renewed excitation caused improvement.

## What will be measured

Q and SOC are scored at **every 35 Hz interval end**. A compact scalar record
preserves the exact query resolution without storing full belief matrices at
every sample. Full component/aggregate diagnostics are saved at 1 Hz, event
boundaries, first samples after transitions, checkpoints and the first failure.

For each hard/preferred target, the scorer reports first attainment separately
from the earliest sample after which every remaining required sample in the
declared finite window passes. It also reports signed error, duration-weighted
RMS, maximum absolute error and its time, target-excursion durations and
availability. A small early error does not by itself mean the target was learned.

Retention has a precise meaning: the target passes at window entry and at every
following required interval end through window exit, with current-point
availability maintained. If it misses on entry, the outcome is
`not_acquired_at_entry`; errors and later acquisition are still reported. If
renewed excitation begins inside the preferred region, retaining preferred
accuracy is a success. Small error changes that stay inside a retained target
are descriptive drift, not a failure or a reason to seek still smaller errors.

The source review caught an important output detail. The existing query's
`predicted_voltage_V` is a **post-correction filtered fit**. The new host adapter
will record a separate causal one-step forecast from the old normalized
component weights and the actual pre-correction innovations. Clean-voltage
forecast error, noisy innovation residual and filtered-fit error will have
separate peak, signed-bias and duration-weighted RMS summaries. No universal
voltage or nuisance-parameter tolerance is introduced.

The contract also fixes exact source semantics for mixture weight
renormalization and the geometric capacity center. Unavailable convenience
fields can contain zero placeholders; raw finite SOC/Q diagnostics instead
come from the aggregate coordinate means and retain the original availability
masks. Local status labels cannot hide point errors or turn placeholders into
measurements.

All sixteen coordinates remain present. Saved component errors, log weights,
gain limits and evidence ages can distinguish a suppressed useful alternative
from two inaccurate alternatives. Post-inference truth may describe these
outcomes; it cannot select the runtime output. Component-versus-aggregate
diagnostics use declared hard/preferred target disagreements, not an unspecified
materiality threshold.

## Continuity and uncertainty

The original endpoint estimator checkpoint is not used to start the new stream:
it has no matching saved generator/RNG state and belongs to the old CSV source
identity. A fresh public-initialized trajectory avoids an unsupported bridge.
The new coupled envelope includes the full 3004-byte learner record, physical
event state, complete RNG state, index and configuration/source identities.
Checkpointing and querying never assimilate an observation.

Fresh voltage noise is drawn once per global input index. Initial component
weights are one half each; their predictive updates then continue throughout
the stream. No component removal, weight reset, forgetting, covariance
inflation or truth-derived prior is permitted. A resumable hash chain and
ordinary whole/suffix observation hashes have distinct, explicit roles.

There is one uncertainty audit on the saved full-query grid: local ranges and
all-component hulls, widths, availability, truth inclusion and raw
local-provisional hard-error breaches. The prior failed uncertainty results
are preserved. Inclusion among serially dependent samples is descriptive;
it is not calibrated coverage or hard support. A more accurate endpoint cannot
certify its uncertainty interval.

## Bounded work and stop rules

The complete staged study has at most **661,500 learner deliveries**, four
learner processes, **577,500 unique physical observations** and one fixed noise
seed per cell. Warm generator replay for parity brings source evaluations to
619,500; it supplies no additional independent evidence.

The 80-byte per-sample records have a maximum 52,920,000-byte payload. The
declared full-query grid has 19,337 records before a possible failure record,
within a 24,000-record cap. Total output is limited to 512 MiB, and each host
process has a 512 MiB RSS limit. Arm timeouts total at most 3600 seconds,
including generator/I/O helpers; scoring and short preflight each have a
separate 600-second ceiling. These are caps, not measured runtime predictions.

The measured owned estimator ceiling stays **7152 bytes**. The proposed
complete target budget remains **10,032 bytes**, including **2880 bytes of
unmeasured reserves**, with **208 bytes** below 10 KiB. Host observation and
scoring resources are separate. No new target-memory measurement is claimed.

The first numerical, source/order/accounting, rejection, recovery, warm-parity,
generator-domain, I/O or budget failure stops the affected study and preserves
its entering checkpoint, input excerpt, stage/flags and partial receipt. A zero
ingest return does not alone establish success: rejected voltage must be
checked separately. Legitimate lagging conditional evidence cursors and normal
unexcited/unresolved/provisional transitions are allowed.

Finite accuracy misses, narrow wrong intervals or limited gains are recorded;
they do not silently shorten or modify the stream. No failure or endpoint
automatically starts a longer run, changes a seed or repairs a prior.

## Verification and next action

The [design verification](design_verification.json) checks source blob identity,
contiguous rational schedule arithmetic, domain feasibility, process/delivery
counts, query limits and budget arithmetic. It performs no voltage propagation,
noise draw, fit or learner run. The [independent review](independent_review.json)
passes after the exact-normalization, unavailable-center, retention-drift and
budget-scope amendments; the original review draft and first audit are retained.

Next, use `implementation/continuous-learning-validation-001` to build only the
new host generator, continuous adapter, scorer and bounded interface fixtures.
The existing probe is capped at 73,500 samples and is preserved. Before any
primary, freeze the new executable sources, environment, binaries and contract
hash; verify coupled continuation and scoring conformance; obtain the declared
independent implementation review. Then execute this staged contract once under
its gates and close its learning/retention decision. Day/week/annual operation,
full-model indefinite stability, calibrated uncertainty and actual Cortex-M23
qualification remain separate work.
