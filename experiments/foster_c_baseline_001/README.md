# Continuous Foster estimator: straightforward C baseline

The rolling fit, prior-free likelihood encoding and joint-history update now run
in portable C with the unchanged physical model. Dense matrices and double
arithmetic are retained. Both binary64 and binary32 token formats are supported;
the latter rounds token coefficients only. This is a functional/profile baseline,
not a near-10-KiB implementation or a firmware release.

## Results

The saved observations were replayed without regenerating stimuli or accessing
truth in the estimator. Each source retires once, in order, with carried state.

| Saved case | Records | C wall time per arm | Maximum Q difference from matching Python arm | Maximum SOC difference |
|---|---:|---:|---:|---:|
| Four-hour CC–CV, binary64 tokens | 504,000 | 0.840 s | 0.000000253% | 0.000000121 points |
| Four-hour CC–CV, binary32 tokens | 504,000 | 0.830 s | 0.0000602% | 0.0000276 points |
| Twelve-hour weak-excitation, binary64 tokens | 1,512,000 | 2.563 s | 0.0000000565% | 0.000000000690 points |
| Twelve-hour weak-excitation, binary32 tokens | 1,512,000 | 2.549 s | 0.0000148% | 0.000000709 points |

[CC–CV receipt](cccv002/summary.json) and [weak-excitation receipt](weak002/summary.json)
include every chart-coordinate and marginal-SD discrepancy, evidence differences,
solver stops, work counters and source hashes. Maximum accumulated log-evidence
difference is about9e-6 with binary64 tokens; with binary32 it is0.00312 on CC–CV
and0.000273 on weak excitation. Results are numerically close, not bit-identical;
strict descent tests sometimes make different last-iteration choices.

These comparisons verify preservation of the existing estimator. They do not
repair its weak-excitation bias, validate its uncertainty, add aging, or certify
indefinite history. The fixed public OCV/thermal calibration and initial prior are
unchanged. No new thresholds, forgetting or physical parameter discretization
were introduced.

## Profiling and memory

Timings are instrumented single-thread host replays on an AMD Ryzen7 9800X3D.
They include C ingestion, fitting, encoding, history, diagnostics and writing
numeric output buffers, but exclude compilation, disk I/O, plots and plant
simulation. They are individual measurements, not a statistical timing study.

Across the two cases, roughly **54–55%** of timed phase work is fitting,
**23–25%** history conditioning/transport, **11–12%** QR/token encoding and
**9%** the pre-fit diagnostic prediction. Model evaluation consumes roughly
36% of total wall time, nested inside those phases; do not add it again.
The Python implementation's duplicate preview/prepare history calculation is
performed once in this synchronous C integration, with staging before commit.

| Memory/resource | Bytes | Scope |
|---|---:|---|
| `sizeof(FBContext)` | 22,360 | Messages, raw block, three evaluation output sets, token, fit vectors, config and metadata/counters |
| Largest M23 own stack frame, `fb_history` | 11,440 | Dense generic Gaussian workspace; excludes called routines |
| Context plus that frame | **33,800** | Lower bound before callers, math-library stack, other runtime and acquisition |
| Linked M23 accounting probe `.text` | 25,688 | Includes linked math/software-double helpers |
| Probe `.data + .bss` | 25,344 | Includes context, separate initialization/input buffers and toolchain globals; excludes stack |

The core allocates no heap memory. Large function-local workspaces remain on the
stack in this baseline. [Target build](build_m23/build.json), compiler `.su` files,
link map and [qualification receipt](qualification.json) preserve the measurements.
The link probe has no startup/vector table or custom memory map and was not run.
It is an accounting artifact, not executable firmware qualification.

At16MHz the16-sample deadline permits approximately7.31million cycles at100%CPU.
No target cycle timing has been measured, and these host seconds cannot be
converted into Cortex-M23 cycles. Memory is already over3.3times the10,240B budget
on the stated lower bound. Next useful work is an RTL cycle benchmark and a
separate workspace-lifetime/sparse-layout optimization, retaining this baseline
as the comparison oracle.

## Qualification and the bug found by sustained replay

**Twelve targeted tests pass**, covering dense solves, QR likelihood preservation,
independent Gaussian conditioning with full cross covariance and normalization,
codec semantics, complete one-block message parity, short streams, irregular
intervals, partial flushes, chronology, invalid inputs and failure retention.
AddressSanitizer and UndefinedBehaviorSanitizer pass a standalone4,097-record
replay with a partial final window. LeakSanitizer is disabled because the traced
execution environment does not support it; this is not a leak-check result.
All68 frozen parent artifacts retain their hashes.

The initial weak-run replay caught a C QR bug: extremely small RC sensitivity
columns reached subnormal double values. Rounding their norm directly made a
Householder reflection nonorthogonal. Parameter means still matched, but the
orthogonal residual energy and evidence normalization drifted by hundreds of
log units. [Original diagnostic](qr_failure.txt), [initial weak result](weak001/summary.json)
and [pre-repair numerical source](numeric_before_qr_repair.c) remain available.

The repair scales subnormal columns before constructing the reflection, then
rescales its diagonal. It neither discards weak directions nor changes the
likelihood. A minimal subnormal-column regression now checks residual energy.
The repaired long replays above verify normalization as well as parameter means.
The separate first-block binary32 rounding discrepancy and the explicit tolerance
adaptation are recorded in [development.json](development.json).

## Run locally

From the repository root:

```bash
python3 -B -m experiments.foster_c_baseline_001.build
python3 -B -m experiments.foster_c_baseline_001.run \
  --case experiments/foster_cccv_stimulus_001/cycle001/case_0000 \
  --out experiments/foster_c_baseline_001/my_replay
```

Use a fresh output directory. `--encoding float64|float32|both` selects token
encoding; `--records N` limits the prefix. Inputs must use the frozen public
calibration/prior in `foster_feedback_001/calibration.json`. Existing campaign
cases provide `observations.npy`; their saved Python traces are compared when
present. Each C trace row contains mean16, marginal SD16, log evidence, retired
record count, stop code and successful fit-evaluation count. The final message
also saves the full16×16 covariance root. V/I/T remain in the original observation
file; physical parameters are decoded from the same continuous gap chart.

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python3 -B -m experiments.foster_c_baseline_001.qualify
```

This runs targeted tests, a Clang sanitizer harness and the ARM cross-build. It
requires NumPy, a host compiler, Clang and `arm-none-eabi-gcc`. It does not rerun
long replays or alter frozen parent results. GCC16's sanitizer build emitted a
`stringop-overread` diagnostic for the unchanged model; the successful sanitizer
run uses Clang without altering that model.

## API boundary

[baseline.h](baseline.h) exposes init, indexed offer, flush and generic history
conditioning. A context belongs to one caller-bound source/configuration session;
the harness records full source hashes. The caller serializes access and must not
mutate the context. `fb_history` requires distinct input/output messages and may
leave its staging output incomplete on failure; authoritative input is untouched.

A failed retirement preserves committed history and all pending samples. Retry
with `fb_flush`, not by reoffering the accepted final sample. A full pending block
applies backpressure. Empty flush is a no-op. Successful retirement publishes the
candidate and releases raw ownership together, with no fallible operation between.

This is a synchronous in-process baseline, not the complete external SHA-bound
prepare/commit/retry transport protocol. There is no concurrent reader, power-loss
recovery, ADC buffering or interrupt deadline contract. No external tokens are
accepted into a running context. The generic numerical backend has no battery
model, test-rig inputs, hidden deterioration or truth references.
