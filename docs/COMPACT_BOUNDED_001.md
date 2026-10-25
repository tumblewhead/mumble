# Compact bounded evidence implementation 001

## Decision and scope

**Implemented and verified.** The primary replay completed once with zero
differences in 31,458,346 stored floating-point comparisons, including bit
patterns, and all 206 diagnostic comparisons passing. No fit was rerun and
no truth file was loaded. Paired-ingestion objects shrink by **33.7%**.

This revision implements the proposed storage reductions in a separate C path.
It preserves the existing B001/B002 model, original fixed parameter chart,
history/event QR grouping, all joint coordinates, carried physical state and
remainder coefficients. The original implementations and frozen results remain
the comparison reference.

The implementation is a reusable component for the delivery roadmap. It does
not complete M1, supply autonomous nonlinear learning, or qualify a Cortex-M23
image. After the focused comparison, the next milestone remains the two-cell
lifecycle integration; another memory-compression study is not a prerequisite.

The verification result and exact source identity are recorded in
[summary.json](../experiments/compact_bounded_001/summary.json). The
[plan](../experiments/compact_bounded_001/plan.json) fixes the comparison and
tolerances before the primary replay. This report accompanies the implementation;
the receipt is authoritative for measured outcomes.

## What changed

| Change | Implementation | Evidence semantics |
| --- | --- | --- |
| Share configuration | Each bank points to one immutable caller-owned `scm_evidence_config` | The original chart, scales, radii, OCV and source identity remain unchanged |
| Construct the joint row directly | Generate the 17-value augmented row without a dense `scm_model_row` or separate theta Jacobian | All derivative products and additions retain the original order, including zero terms |
| Stage only changed data | One trial factor, prospective model, mutable metadata and row | Failed updates leave both public banks unchanged; history/event grouping remains intact |
| Focus diagnostic output | Report current SOC and capacity while diagonalizing the full joint matrix | Nuisance and entering-state null directions remain represented; other target reports are unassessed |
| Share phase scratch | An explicit union alternates ingestion and diagnostic storage | Calls are serialized; consume or copy a report before the next ingestion overwrites it |

The new APIs are in [scm_compact_evidence.h](../include/scm_compact_evidence.h),
[scm_compact_remainder.h](../include/scm_compact_remainder.h), and
[scm_compact_assess.h](../include/scm_compact_assess.h). They preserve the old
APIs as a directly executable comparator. The ordinary factor cost/RMS helpers,
OCV implementation and assessment options/status definitions are reused.

The configuration and its OCV backing storage must outlive the banks and stay
unchanged. Each remainder bank is still bound to the exact evidence object and
exclusively paired ancestry. A raw pointer-containing struct dump is not a
portable checkpoint. Those obligations are explicit in the headers.

## Measured storage

These sizes describe the current x86-64 host ABI with 8-byte doubles and
pointers. They are not M23 measurements. The owned aggregate is an actual C
type used by the replay probe, including alignment, rather than a sum of only
the most favorable arrays.

| Object | Bytes |
| --- | ---: |
| One backing configuration | 472 |
| Compact evidence bank, including both 1,240-byte factors | 2,872 |
| Compact remainder bank, including audit fields and pair maps | 736 |
| **Persistent objects** | **4,080** |
| Evidence update workspace | 1,760 |
| Remainder update workspace | 736 |
| Ingestion phase workspace | 2,496 |
| Full-joint focused assessment workspace | 2,432 |
| Two-target report | 296 |
| Assessment options | 56 |
| Query phase workspace/report/options | 2,784 |
| **Actual serialized phase union** | **2,784** |
| Sample, remainder result and 16-value trial vector | 200 |
| **Complete owned aggregate** | **7,064** |

The paired-ingestion comparison is **9,912 to 6,576 bytes**, a saving of 3,336
bytes or 33.7%. Its three nonoverlapping reductions are 1,384 bytes from shared
configuration, 704 from direct row construction, and 1,248 from selective
staging. The new figure charges the shared backing configuration to RAM.

The old 20,856-byte simultaneous diagnostic object set included full target
reports, a fit-result adapter, snapshots and additional vectors. The compact
7,064-byte aggregate instead supplies SOC/Q reports and serialized scratch.
It does not provide every nuisance report or a complete joint optimizer update.
The ingestion comparison above preserves the same ingestion functionality.

### Stack and the remaining budget

The host `-O3 -fstack-usage` reports and emitted call graph give these own-source
call-chain costs. Inlined functions are already included in their caller frames.

| Phase | Own-source stack bytes | Owned aggregate plus own-source stack |
| --- | ---: | ---: |
| Initialization | 920 | 7,984 |
| Paired ingestion, including event sealing | 552 | 7,616 |
| Focused SOC/Q query | 536 | 7,600 |
| Remainder query | 488 | 7,552 |

The largest partial subtotal leaves 2,256 bytes beneath the 10,240-byte planning
ceiling. This is remaining space to investigate, not a certified margin.
Caller frames, libm/libc and target runtime, interrupts, acquisition/backlog,
checkpoint staging and any persistent report copy remain additional. A future
nonlinear solver also needs an explicit work/storage account. A report stored
outside the phase union must be charged separately; a query that blocks live
acquisition requires its input backlog to be charged.

The [memory accounting](../experiments/compact_bounded_001/memory_accounting.json)
records actual object sizes, compiler frames, call paths and host ELF costs.
The comparison program intentionally owns both implementations and validation
data. Its entire executable/static storage is reported separately from the
compact component. No target flash, latency or power reduction is claimed.

## Why the smaller transaction preserves the evidence

An ordinary sample stages the model and metadata, constructs the joint row,
and inserts it into a copy of the current event factor. History is untouched.
The live event/model/metadata are committed only after every fallible check.

When a sample seals the current event, the trial factor starts as history.
The old event is merged in precisely the original compressed-row order, before
the next model step. This preserves both the accumulation grouping and failure
precedence. The same row scratch then holds the next observation. Inserting a
single row into a zero factor has one nonzero pivot; the implementation uses
the same normalized Givens arithmetic, including leading-zero, residual-only,
all-zero and subnormal cases. It validates that row before materializing the
new event. The final writes cannot return a late numerical error.

The remainder transaction stages the complete smaller remainder bank, advances
it, calls the atomic evidence update and commits the remainder only on success.
Its arithmetic and 19 possible joint Hessian-envelope coefficients are unchanged.
No sample is replayed as an additional independent prior.

## Focused queries still account for nuisance uncertainty

The diagnostic workspace first contains the combined QR factor. It converts
that factor to the joint Gram matrix in place, then performs the same Jacobi
matrix rotations and eigenvalue ordering as the original assessment.

Descending QR-to-Gram writes preserve the earlier QR rows still needed by the
remaining products. One- and two-mode factors retain the original 17-column
packing, so they are first compacted into their active packing width before
backward expansion to a dense matrix. An explicit union provides the storage.

Instead of retaining a 16-by-16 eigenvector matrix, the code rotates just the
two target gradients. Their projections onto every retained and discarded
joint direction determine variance and null-space qualification. It therefore
does not replace the full joint problem with a conditional two-by-two solve.
The tests include observable SOC with unresolved capacity and a capacity
direction confounded with a nuisance coordinate.

Directly rotating gradients follows a different floating-point evaluation path
from forming the full eigenvector matrix and subsequently multiplying by the
gradients. Numerical comparisons use the frozen tolerances; decisions exactly
at a floating-point threshold are not promised identical on every platform.
The new assessment additionally rejects overflow of the squared target-gradient
norm. That is an explicit stricter guard, not a change to retained evidence.

The caller must report a nonzero optimizer status when no nonlinear fit was
performed. The primary comparison retains that status and unresolved returned
ranges. It separately compares raw full-joint local curvature, without treating
it as optimizer convergence, nonlinear truth accuracy or validated coverage.

## Focused verification

The unit checks exercise all supported mode counts, actual intervals including
zero, signs and reversals, PWL evidence-only behavior, very small responses,
source/order/counter errors, event-boundary failures, candidate guards and
paired ancestry. Rejected updates are checked byte-for-byte against each
implementation's own prior bank. The focused assessment tests cover rank/null
coupling, repeated eigenvalues, cutoff cases and reporting qualifications.

The primary replay uses the existing cell-A 35 Hz trace and frozen estimated
1800-second anchor. It processes all 73,500 observations in order, comparing
every retained field after every sample, with diagnostics at 1800 and 2100
seconds. No optimization or truth file is used. The prefix is a retrospective
fixed-chart representation; the final 300 seconds are its causal extension.
The exact source, input and anchor hashes, first run outcome and differences
are kept in the [primary receipt](../experiments/compact_bounded_001/primary/receipt.json).

The 12,163 compact unit checks and 3,464 focused assessment checks pass. The
existing integration/unit suite, strict C99 compilation and targeted address/
undefined-behavior sanitizers also pass; see the
[build checks](../experiments/compact_bounded_001/build_checks.json). Core unit
comparisons cover another 1,981,860 floating values with no bit differences.
The primary eigensystem eigenvalues match exactly; the largest target/projection
difference is 1.3878e-16. Both checkpoints retain numerical rank 16. The full
joint SOC and capacity curvature improves through the quiet tail identically
within the frozen tolerance, while returned ranges remain explicitly unresolved
because this replay does not perform a new nonlinear fit.

Reproduction writes new results rather than overwriting the frozen receipt:

```bash
make test-compact build/scm_compact_probe compact-stack
python3 tools/run_compact.py --output-dir experiments/compact_bounded_001/my_new_receipt
python3 tools/measure_compact_memory.py --output experiments/compact_bounded_001/my_new_memory.json
```

## What this enables, and what remains

The memory reduction is now implemented in the existing bounded evidence
representation. It does not require a learned token classifier, codebook,
Welford prototype, semi-Markov predictor, reduced rank or reduced precision.
Those proposals can still reduce a later representation or computation if a
measured cost justifies them. Adding a dictionary or predictor to this revision
would initially add state: this bounded path already retains zero raw history
and zero explicit projection basis.

The original limitations remain: a frozen affine chart, no autonomous nonlinear
cold start or historical relinearization, ordinary double/libm arithmetic,
growing-statistic and counter limits, and no general all-prefix fidelity proof.
The B002 near-roundoff failures and certificate004 usefulness failures retain
their original status. The separate restricted integer certificate's proofs
do not automatically apply to this full-model Gaussian path.

The next action is M1's desktop session, complete checkpoint/journal, recovery
and two-cell experiment from [the roadmap](ROADMAP.md). This compact component
is available for the later bounded-backend decision; it is not a reason to
defer that integration for another compression campaign.
