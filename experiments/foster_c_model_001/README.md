# Sparse Foster derivatives and thermal reuse

The second C optimization pass reduces measured host runtime by another
**13.6–17.4%** relative to the previous optimized C version. Both saved full
replays, in both token encodings, preserve estimates, marginal uncertainty,
log evidence, stop/evaluation diagnostics and complete final joint messages
**bit-for-bit**. This is preservation on the tested controls, not a universal
floating-point equivalence proof or physical-accuracy qualification.

The [implementation](model.c) changes how the same continuous Foster model is
computed. It introduces no parameter thresholds, approximate exponentials,
forgetting, temperature rounding or sparse statistical covariance.

## Changes and derivation

The physical state Jacobian has18 potentially nonzero entries out of80:

| State | Incoming chart dependencies |
|---|---|
| SOC | SOC, logQ |
| RC1 voltage | RC1 voltage, logR1, logtau1 |
| RC2 voltage | RC2 voltage, logR2, logtau1, loggap2 |
| RC3 voltage | RC3 voltage, logR3, logtau1, loggap2, loggap3 |
| Hysteresis state | h, logQ, loggamma+, loggamma− |

Each time constant is the cumulative sum of positive reference-temperature gaps.
Its derivative with respect to a gap's log coordinate is that gap multiplied by
**that branch's** thermal factor. The implementation updates only the supported
state sensitivities and eliminates the two dense11×16 parameter-derivative
tables. The5×16 state sensitivity buffer is still dense for simple output
assembly. Full likelihood derivatives, joint covariance and transport outputs
retain their original interfaces and all statistical cross terms.

For a fixed observation block, the factors
`exp(A[k] * (1/T[i] - 1/Tref))` depend only on measured temperature and declared
calibration. They are computed once per flush and reused for every trial point.
All eleven factors are retained separately, including when their calibration
coefficients happen to coincide. Every sample's actual temperature is used;
there is no assumption of constant temperature or fixed sampling interval.

The cache is rebuilt for every attempted retirement, including retries and partial
windows. It is owned by each context, not global. Preparation failures leave
committed history and pending inputs intact. An empty outgoing-domain evaluation
uses no cached sample factors.

The1408B cache replaces the4352B initial-prediction output set: the initial
prediction now writes directly into `current`, which fitting already consumes.
This saves **2944B of context memory** without allocating another buffer.

## Repeated host timing

Three repetitions alternate stage order on the same saved observations. These
are medians; individual samples, ranges, counters and hashes are in the
[benchmark receipt](attempt001/summary.json).

| Saved case | Previous optimized C | Sparse derivatives | Also thermal cache | Total additional time reduction |
|---|---:|---:|---:|---:|
| Four-hour CC–CV, binary64 tokens | 0.713s | 0.622s | **0.589s** | **17.4%** |
| Four-hour CC–CV, binary32 tokens | 0.692s | 0.606s | **0.578s** | **16.4%** |
| Twelve-hour weak excitation, binary64 tokens | 2.149s | 1.939s | **1.856s** | **13.6%** |
| Twelve-hour weak excitation, binary32 tokens | 2.123s | 1.899s | **1.823s** | **14.2%** |

All12 case/encoding/stage combinations complete; repeated output hashes match.
Sparse derivatives alone save roughly9.8–12.8% of previous runtime. The cached
variant is also bit-identical to the uncached sparse variant. No rounding-induced
solver-stop differences appeared in these full comparisons.

Timings are instrumented single-thread host replays on the AMD Ryzen7 9800X3D.
They include ingestion, computation and output arrays, excluding initialization,
file I/O, compilation, plots and scoring. Thermal preparation is included in
`before_s`; nested `model_s` excludes that preparation in the cached variant.
Consequently nested model timings alone are not a fair total-work comparison.
The remaining phase work is roughly40–41% fitting,33–35% history updates,
15–18% token encoding and8–9% initial prediction/cache preparation.

These are host measurements, not Cortex-M23 cycles or16MHz CPU utilization.
Savings from separate experiments should not be added as percentage points.

## Qualification and resources

**Seventeen targeted tests pass**: twelve inherited baseline controls and five
new groups covering randomized dense/sparse comparisons, finite differences for
every chart coordinate, changing temperatures/irregular intervals, interleaved
contexts and partial windows, branch-specific calibration and domain acceptance.
The randomized comparison includes zero-length queries, rest, current reversals
and all16 coordinates. The inherited harness test exercises the unchanged replay
runner; the changed model and context use the new library in estimator tests.

The standalone4097-record AddressSanitizer/UndefinedBehaviorSanitizer control
passes, including a partial final block. LeakSanitizer remains disabled because
the traced environment does not support it. The core allocates no heap.

| Resource | Previous optimized C | New cached variant |
|---|---:|---:|
| Context | 22,360B | **19,416B** |
| Physical model own frame on M23 | 3,944B | **1,272B**, plus32B wrapper |
| Largest own frame: history | 11,440B | 11,440B |
| Context + largest own frame lower bound | 33,800B | **30,856B** |
| Linked accounting-probe text | 26,228B | 26,876B |
| Probe data + BSS, excluding stack | 25,344B | 22,400B |

The unchanged history workspace still determines this resource lower bound.
The10,240B target remains unmet. Caller/library stack, acquisition, interrupts
and other runtime are additional. The M23 soft-float cross-build succeeds, but
the link probe has no startup/vector table or custom memory map and is not an
executed firmware or timing qualification.

[qualification.json](qualification.json) records commands and verifies that all
98 first-pass optimization artifacts,83 original C-baseline artifacts and68
original Foster artifacts remain unchanged. Scientific limitations—stationary
reference parameters, weak-excitation bias, unvalidated local-Gaussian coverage
and unresolved aging/lifetime behavior—are unchanged.

## Use and rerun

The default stage2 includes both changes. Stage0 builds the previous optimized
C implementation; stage1 enables sparse derivatives without the cache.

```bash
python3 -B -m experiments.foster_c_model_001.build
python3 -B -m experiments.foster_c_baseline_001.run \
  --binary experiments/foster_c_model_001/build_host_2/baseline.so \
  --case experiments/foster_cccv_stimulus_001/cycle001/case_0000 \
  --out experiments/foster_c_model_001/my_replay
```

Use a fresh output directory. The campaign runner's default backend is unchanged.
The replay adapter allocates the context through its size query and supports the
new library. **C callers must rebuild using this experiment's [baseline.h](baseline.h):
the context layout changed.** The cached model entry point requires the factors
produced for its exact observation block and calibration; the rolling adapter
owns that preparation and lifetime.

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python3 -B -m experiments.foster_c_model_001.qualify
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python3 -B -m experiments.foster_c_model_001.benchmark \
    --out experiments/foster_c_model_001/my_benchmark --repeats 3
```

Qualification builds all variants, runs targeted tests and Clang sanitizers, and
cross-builds the cached variant. The benchmark then runs36 short host replays.

Next useful candidates are structured history matrix operations and workspace
reuse: history now accounts for roughly one third of host runtime and owns the
largest stack frame. RTL cycle measurements remain necessary before projecting
16MHz utilization.
