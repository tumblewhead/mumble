# C CPU optimization, first pass

The first three proposed changes reduce measured host replay time by **14.8–17.8%**
against the frozen C baseline. The implementation retains the physical model,
prior, full joint uncertainty, token encoding, solver tolerances and double
precision. This experiment does not change the campaign runner's default backend.

[rolling.c](rolling.c) implements three cumulative stages:

1. Reuse the incoming-mean prediction and its derivatives as the fitter's initial
   evaluation. The initial predictive diagnostic is still available. Exactly one
   full model call per retired block is removed.
2. Check the gradient stopping condition before constructing `I + BᵀB`. This
   avoids matrix construction on roughly one third of iterations in these cases.
3. Construct only the lower triangle of that symmetric positive-definite matrix
   and solve with Cholesky and triangular substitutions instead of general LU.
   No covariance cross terms, physical parameters or likelihood terms are removed.

`FB_OPT_STAGE=1|2|3` selects the cumulative stage; the default is3. The build script's
stage0 compiles the unchanged baseline as a fresh timing control. History, QR,
the subnormal-column repair, model and public API header are reused unchanged.

## Paired timings

Three repetitions per case, encoding and stage alternate stage execution order.
The table reports medians. All16 case/encoding/stage combinations completed,
and repeat output hashes were identical. Runs use the same saved observations;
no new plant simulation or truth-dependent fitting occurs.

| Case and token encoding | Baseline | Reuse prediction | Also defer matrix | Also Cholesky | Total time reduction |
|---|---:|---:|---:|---:|---:|
| Four-hour CC–CV, binary64 | 0.853s | 0.778s | 0.742s | **0.716s** | **16.0%** |
| Four-hour CC–CV, binary32 | 0.828s | 0.753s | 0.736s | **0.705s** | **14.8%** |
| Twelve-hour weak excitation, binary64 | 2.635s | 2.358s | 2.279s | **2.167s** | **17.8%** |
| Twelve-hour weak excitation, binary32 | 2.595s | 2.298s | 2.193s | **2.149s** | **17.2%** |

These instrumented single-thread host measurements include ingestion, computation
and output arrays, excluding initialization, file I/O, compilation, plotting and
scoring. They are from the AMD Ryzen7 9800X3D host, not M23 cycle measurements.
The [benchmark receipt](attempt001/summary.json) records all individual timings,
ranges, phase counters, output hashes and input identities. Savings are cumulative;
do not add the percentages across stages.

## Numerical preservation

Stages1 and2 produce **bit-identical estimates, marginal standard deviations,
log evidence, stop codes and complete final messages** on both full cases and both
encodings. Evaluation-count diagnostics correctly decrease by one per token.

Cholesky changes floating-point rounding and occasionally the strict line-search
or stopping decision. There are16–58 stop-code differences per arm, out of31,500
or94,500 retirements. The sustained comparisons against the C baseline are:

| Quantity | Maximum over both cases and encodings |
|---|---:|
| Capacity difference | **0.0000229%** |
| SOC difference | **0.00000744 percentage points** |
| Accumulated log-evidence difference | **0.001344** |
| Relative Frobenius difference of final full covariance | **0.000002402** |

The receipt also reports all eleven decoded parameter differences and all chart
mean/SD differences. These are port-preservation diagnostics, not physical error
against truth or calibrated uncertainty coverage. Existing weak-excitation bias,
stationary-reference assumptions and aging/lifetime limitations remain unchanged.

**Fifteen targeted tests pass**: the inherited twelve baseline controls plus
exact reuse/defer comparisons, independent SPD backward-error checks, and a
zero-trial gradient-stop control. The independent solve test poisons the unused
upper triangle to verify lower-triangle ownership. The inherited failed-replay
harness control exercises the unchanged runner. AddressSanitizer and
UndefinedBehaviorSanitizer pass the standalone4,097-record partial-window control.
LeakSanitizer remains disabled because the tracing environment does not support it.

## Target resources

The Cortex-M23 soft-float build and accounting link succeed. Context size remains
**22,360B** and the largest own stack frame remains the unchanged **11,440B**
history routine. Their **33,800B lower bound** still excludes callers, math-library
stack, acquisition and other runtime; the10,240B target is not met.

The new linked probe has26,228B text,296B data and25,048B BSS. Text is540B larger
than the baseline probe; fitter own stack is4,744B versus4,632B previously, partly
affected by compiler inlining. This was a CPU pass, not a memory optimization.
The probe lacks target startup and the custom memory map and was not executed.
No16MHz utilization or deadline guarantee is inferred from host timing.

The [qualification receipt](qualification.json) preserves compiler commands,
sanitizer output, target sizing and verification that all83 C-baseline artifacts
and68 original Foster artifacts remain unchanged.

## Rerun

From the repository root, build the default optimized stage:

```bash
python3 -B -m experiments.foster_c_cpu_001.build
python3 -B -m experiments.foster_c_baseline_001.run \
  --binary experiments/foster_c_cpu_001/build_host_3/baseline.so \
  --case experiments/foster_cccv_stimulus_001/cycle001/case_0000 \
  --out experiments/foster_c_cpu_001/my_replay
```

The unchanged replay adapter accepts the optimized library through `--binary`.
Use a fresh output directory. Public calibration and input schema are identical
to the frozen baseline.

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python3 -B -m experiments.foster_c_cpu_001.qualify
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python3 -B -m experiments.foster_c_cpu_001.benchmark \
    --out experiments/foster_c_cpu_001/my_benchmark --repeats 3
```

Qualification builds all four host variants, runs targeted tests and Clang
sanitizers, and cross-builds stage3. The benchmark then runs the paired saved
controls; its default repetitions total48 short host replays.

Next is a separately measured pass on sparse physical derivatives and reuse of
known thermal factors, while obtaining actual RTL cycle measurements. Precision,
update frequency, stopping tolerances and physical history semantics remain
outside this optimization pass.
