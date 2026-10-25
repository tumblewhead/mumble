# M1: two-cell estimator lifecycle

## Outcome

**M1's lifecycle demonstration passes. Its overall estimation-usefulness gate
fails, and that failure is retained.** The complete first run used 20 fits,
12 fresh host processes and the two existing 35-minute cell traces. Warm
restart reproduced the uninterrupted results exactly in the recorded numerical
comparisons, and both cold-reset branches recovered at their next scheduled
fit. No primary run was repeated or tuned after scoring.

The remaining quality problem is specific: **Cell B at 900 seconds** reached
the iteration limit, with a current-SOC error of **−3.96355 percentage points**
and capacity error of **+26.6298%**. Its SOC and capacity reports were correctly
marked unresolved, without local ranges. Both cells passed the declared
accuracy benchmarks at 1,800 and 2,100 seconds.

This closes the small lifecycle milestone and supplies a working comparison
harness. It does not promote this sparse retained-history schedule as the
long-run performance candidate. The next action is A4: one autonomous learner
with bounded storage/work and reliable learning from public starts.

The compact evidence entry points are the [summary](../experiments/trajectory_integration_001/summary.json),
[frozen plan](../experiments/trajectory_integration_001/plan.json),
[primary receipt](../experiments/trajectory_integration_001/primary/receipt.json),
[post-inference scores](../experiments/trajectory_integration_001/scores.json),
and [independent audit](../experiments/trajectory_integration_001/independent_review.json).
The source revision used by the run is `0cde298a204ff3a3347830c0fac0ba99e10918c8`;
its published equivalent is `1221298bd89730df7c6adb5e11d4d3669c22cbae`, with
the same Git tree. The [publication record](../provenance/trajectory_integration_001_publication.json)
maps original and published commits and links the verified development bundle.
It preserves the original source identity referenced by the frozen receipts.
The exact [Linux host executable](../reference_binaries/scm_session_probe_m1_001)
is retained with the receipt's binary hash; it is not an MCU image.

## What now works

The [session API](../include/scm_session.h) wraps the original full C reference.
It owns the ordered observation journal, input identity, actual elapsed time
and charge, fit schedule, last fit, carried model state, recovery flags and
resource counters. The original numerical model, fitting and assessment
sources are unchanged.

Each delivered sample retains its actual interval and order. A query reports
both the current propagated input position and the position of the last fitted
evidence. The current SOC target is transported through that earlier complete
joint matrix using the known charge since the epoch began. Later voltage
samples are not claimed assimilated until the next scheduled fit. The earlier
fit contributes a starting theta only; it is not also added as a posterior
factor alongside its replayed observations.

| Operation or fault | Implemented behavior |
| --- | --- |
| Initialization | Public configuration and starts; nominal model values are not advertised as estimates |
| Scheduled fit | Exactly at the declared sample count; ingestion cannot silently skip an unconsumed fit point |
| Warm restore | Complete journal and fit/schedule state; reconstruct dynamics without another optimizer call |
| Cold reset | Discard history, fit and warm start; preserve the known absolute input position and clock; report lost knowledge |
| Duplicate or out-of-order input | Reject without changing the session or earlier journal |
| Malformed interval, nonfinite input or counter exhaustion | Reject explicitly and atomically |
| Missing voltage, known current/time | Retain the known physical input and earlier evidence; expose that the unchanged full fitter cannot mask missing voltage in this epoch |
| Unknown current/time gap | Latch recovery required; do not invent zero input; use a valid checkpoint plus complete known replay, or explicit cold reset |
| Failed new fit | Keep the earlier result and its evidence position, and expose the failure |
| Optimizer iteration limit | Keep the numerical point with its status; withhold trusted local ranges |
| Point trajectory outside its domain | Keep the input journal and charge; do not silently revive the invalid state point before a valid refit |

The [checkpoint implementation](../include/scm_session_checkpoint.h) uses a
versioned explicit format with little-endian integers, checked binary64 values,
source/configuration/model identity, lengths and CRC32. It never dumps pointers
or struct padding. CPU timings are encoded as zero; causal state, allocation
capacity and deterministic requested-storage counters are retained. Save writes
a unique temporary file, flushes and synchronizes it, then renames it. Restore
validates a prospective session before replacing any live storage.

CRC detects accidental corruption; it is not authentication. Fresh-process
restart and rejection semantics are demonstrated here. Filesystem directory
durability under sudden power loss and an embedded flash protocol remain
outside this host implementation.

## Frozen experiment

Both selected traces contain 73,500 observations at nominal 35 Hz and represent
2,100 seconds. They retain the original hashes in the plan. The C estimator
uses the full sixteen-unknown model: three RC modes and hysteresis, known
illustrative OCV, exact current/time, fixed 25 C and matched synthetic 1 mV
voltage noise. Temperature variation and EOD outputs are unsupported.

| Path, per cell | Fit counts | Restart/reset behavior |
| --- | ---: | --- |
| Uninterrupted control | 4 | Fits at sample counts 350, 31,500, 63,000 and 73,500 |
| Warm continuation | 4 | Fresh processes restore after 12, 1,200 and 1,850 nominal seconds; same fit positions |
| Cold continuation | 2 | Restore the 900-second control checkpoint, then explicitly discard estimator knowledge; new fits at 1,800 and 2,100 seconds |

The total is `(4 + 4 + 2) × 2 = 20` optimizer calls. Every fit uses three starts
and a 120-iteration limit. There are no additional fits on restore. The sample
counts govern the schedule; actual accumulated time is retained, including
ordinary floating-point accumulation differences from the nominal seconds.

The executable sees only observations and public configuration. All C
processes finished before a separate scorer loaded synthetic truth. For a
cold suffix, entering-state truth is shifted only inside that scorer, never
passed to the estimator or restore path.

The fit schedule is deliberately sparser than the completed original study.
Its earlier ten-checkpoint results are not a bitwise target for this new
warm-start sequence. The original 60-fit campaign was not rerun.

## Lifecycle and restart results

All 12 processes completed their declared schedules. Ten matched checkpoint
pairs had identical file sizes and SHA256 hashes. The comparison included:

- 430 warm/control query records, covering 31,728 scalar fields;
- eight paired fit records, covering 2,640 scalar fields excluding timings;
- 2,150 resource scalar fields, compared exactly.

The maximum numerical difference was **zero**. The predeclared floating
tolerances were `atol=1e-12` and `rtol=1e-10`; integer fields, statuses, reasons
and canonical persistence were exact. All input, source and binary integrity
checks passed. The temporary full checkpoint journals were removed after the
run; their sizes, hashes, commands and raw checkpoint events remain in the
receipt, with committed source and input data available for reproduction.

The session suite passed 1,185 checks. The checkpoint suite passed 365 checks,
including 19 rejection cases. The full existing suite, strict build and focused
address/undefined-behavior sanitizer checks passed. Leak detection was disabled
in the hosted sanitizer environment. Session tests use two tiny optimizer calls
per invocation, one intentionally failing; those are separate lifecycle fixtures,
not extra primary fits. Persistence fixtures and smoke tests use no optimizer.
See the [build receipt](../experiments/trajectory_integration_001/build_checks.json).

The result audit performed 1,222 checks without rerunning inference. It also
recomputed the SOC/capacity scoring arithmetic independently, agreeing within
`4.56e-13` percentage points/percent. The reviewer authored the runner; this is
an independent arithmetic/result check, not an external validation claim.

## Estimation quality and recovery

The frozen benchmark requires current-SOC absolute error below 0.5 percentage
points and capacity absolute relative error below 0.5 percent. These are
synthetic performance thresholds, not product guarantees or coverage claims.

The warm values match the control exactly, so the table combines them. Errors
are signed; “converged” describes the optimizer, not global optimality.

| Cell/path | Nominal time | SOC error, percentage points | Capacity error, % | Optimizer / target reports | Benchmark |
| --- | ---: | ---: | ---: | --- | --- |
| A, control/warm | 900 s | −0.001115 | −0.011883 | Converged / provisional | Pass |
| A, control/warm | 1,800 s | −0.001181 | +0.016296 | Converged / provisional | Pass |
| A, control/warm | 2,100 s | −0.002013 | +0.010786 | Converged / provisional | Pass |
| B, control/warm | 900 s | **−3.963551** | **+26.629800** | **Iteration limit / unresolved** | **Fail** |
| B, control/warm | 1,800 s | +0.002295 | +0.007550 | Converged / provisional | Pass |
| B, control/warm | 2,100 s | +0.000256 | +0.000105 | Converged / provisional | Pass |
| A, cold | 1,800 s | −0.012227 | +0.001519 | Converged / provisional | Pass |
| A, cold | 2,100 s | −0.015580 | +0.007027 | Converged / provisional | Pass |
| B, cold | 1,800 s | −0.024361 | +0.134946 | Converged / provisional | Pass |
| B, cold | 2,100 s | −0.031367 | +0.126530 | Converged / provisional | Pass |

Fourteen of sixteen declared arm/checkpoint pairs pass; the two failures are
the same Cell B 900-second result in control and warm paths. Eighteen of twenty
fits report numerical convergence. Independent closed-form objective scoring
agrees with the reported objectives to a maximum absolute difference of
`1.23e-7`. That agreement checks evaluation consistency; it does not turn the
failed optimization into a good estimate.

At the sparse query points, Cell A first meets both accuracy benchmarks at
900 seconds and continues to do so. Cell B first does so at 1,800 seconds.
Before useful learning, point estimates can be very inaccurate: the largest
observed control SOC error is 7.51 percentage points for A and 9.05 for B;
capacity errors reach 41.67% and 26.63%, respectively. These earlier queries
are unresolved. A returned numerical point is therefore not a promise of
usefulness. The report does not require every nuisance parameter to be known.

Cold reset at 900 seconds immediately removes SOC/Q availability. Both paths
remain unknown until the first scheduled new fit at 1,800 seconds. That fit
passes both benchmarks, and the result remains useful through the weak tail
and the final fit. The observed unknown period is **900 seconds under this
schedule**; it is not the minimum time in which the estimator could relearn.

![M1 errors, reset behavior and stimulus](../report/M1-Two-Cell-Lifecycle.png)

The figure uses deduplicated nominal ten-second queries and actual accumulated
time, with extra lifecycle event points. The shaded region is the benchmark,
the dotted line marks cold reset, and the missing cold line represents
unavailable estimates. The vertical scale is linear near zero and logarithmic
outside ±0.5 so early failures remain visible. These sparse query metrics do
not bound every intervening sample. The vector version is
[M1-Two-Cell-Lifecycle.svg](../report/M1-Two-Cell-Lifecycle.svg).

“Provisional” ranges come from local likelihood geometry. Numerical
convergence, synthetic truth error, local precision, hard support and validated
coverage remain separate. This run provides no new hard-support or coverage
certificate. An iteration limit is not evidence of physical unidentifiability.

## Resource cost and limits

The [memory account](../experiments/trajectory_integration_001/memory_accounting.json)
matches every recorded query, all 20 completed fits and every checkpoint size.
For this host ABI, with retained count `N` and allocated capacity `C`:

- session ownership is `3,104 + 25*C` bytes;
- full-fit auxiliary allocation is `2,072 + 648*N` bytes;
- a checkpoint occupies `2,808 + 25*N` bytes.

The solver borrows the session's sample buffer. Its raw-data accounting is
subtracted before adding solver auxiliary storage, avoiding double counting.

| Measured storage, per process | Control/warm maximum | Cold maximum |
| --- | ---: | ---: |
| Steady session ownership | 1,840,604 B | 1,641,504 B |
| Session during journal growth | 3,479,004 B | 2,460,704 B |
| Session plus successful solver auxiliary allocation | **49,470,676 B** | **28,859,576 B** |
| Final complete control checkpoint | 1,840,308 B | Not saved in the cold arm |

The full requested session/solver allocation is about **47.18 MiB**. It is a
desktop reference. The earlier **7,064-byte compact component** is a different
implementation component and is not the memory consumption of this M1 model.

Journal growth temporarily retains old and new buffers. A restore over a live
session also temporarily owns both journals: `25*(C_old+C_new)` bytes, plus
the destination object, candidate/codec stack and runtime. Fresh-process
restore only needs the new journal. Those restore transients are separate from
the saved historical growth/fit counters.

The driver enumerates 14,280 bytes of fixed objects, including the session,
assessment/workspace, query and CSV buffer. That subtotal does not include all
driver locals or call-chain stack, and the session must not be counted twice.
Measured compiler frames include 4,640 bytes for driver main, 3,856 for session
fit and 3,712 for checkpoint restore; nested calls remain additional. Allocator
overhead, stdio/libm/runtime stack, failed-fit allocations and process RSS are
not included in the requested-allocation figures. No complete target SRAM
bound is claimed.

The primary took 28.24 seconds of host wall time with two cell workers; total
reported fit CPU time was 53.65 seconds. These are host results, not M23 timing
or energy measurements. The capped 73,500-sample journal fails explicitly at
its limit. It does not become an indefinite-runtime learner merely because
the allocation limit is finite.

## Decision and next action

Close M1 with **functional=true, usefulness=false, cold usefulness=true**.
Retain the complete first results and the Cell B failure. No additional starts,
iteration changes, schedule tuning or optional campaigns are part of this
milestone.

For A4, select one learner that starts from public information, updates its own
state and evidence, and declares a finite memory and work budget. Run it through
this same small lifecycle harness against the retained-history reference.
The first measured quality issue to address is timely reliable learning,
including Cell B at 900 seconds. Preserve earlier information without adding a
posterior twice or silently treating a local chart as globally valid.

The semi-Markov/codebook ideas and attention policies remain possible resource
optimizations. This experiment does not measure them. Introduce one only when
it resolves the selected candidate's concrete memory or processing constraint.
The next deliverable is an autonomous bounded candidate, not another general
compression study.

Short variation tests, then day/week throughput and recovery pilots, precede
the planned annual streams. The full-model indefinite-runtime proof and
actual Cortex-M23 execution near 10 KiB remain open. The existing restricted
integer proofs retain their original premises; finite M1 success cannot extend
them to this full model.

## Reproduction

```sh
make test build/scm_session_probe
python3 tools/run_trajectory_integration.py --output-dir /tmp/mumble-m1-reproduction
MPLCONFIGDIR=/tmp/mumble-mpl python3 tools/score_trajectory_integration.py \
  --primary /tmp/mumble-m1-reproduction \
  --output /tmp/mumble-m1-reproduction-scores.json \
  --figure /tmp/mumble-m1-reproduction.png
```

The runner requires committed clean numerical sources and the frozen plan,
snapshots the executable, and refuses an existing output directory. These
commands reproduce the experiment; do not rerun it merely to resume work.
Use the [roadmap](ROADMAP.md), [project state](../PROJECT_STATE.json) and compact
[handoff](../handoff/CONTINUE.json) to continue from the latest branch descendant.
