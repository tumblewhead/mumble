# Shared math: first SRAM-first experiment

This isolated branch tests a common polynomial evaluator and stored Bernstein
control coefficients against coefficient-generating recurrences. It does not
change estimator/history defaults or claim a 10 KiB fit.

**Result:** the smallest qualified candidate is one explicitly shared,
out-of-line reverse-series evaluator with **no coefficient table**. It saves
224 B in the linked 64-bit-history numerical core. With the existing experimental
48-bit history, the linked saving is 232 B. This is a small, useful learning result.

## What was shared

Two reduced-domain functions underpin five public functions:

- `E(r) = (exp(r)-1)/r`, with its continuous value1 at zero, represented by
  `sum(k=0..14) r^k/(k+1)!`, on `|r|<=0.5`.
- `L(z) = atanh(sqrt(z))/sqrt(z)`, with continuous value1 at zero, represented by
  `sum(k=0..12) z^k/(2k+1)`, on `0<=z<=1/16`.

The existing range/sign wrappers use these for exp, expm1, log, tanh and atanh.
The smallest candidate retains the existing sqrt/hypot implementation. Separate
arms tried a degree7 normalized square-root seed followed by three Newton steps.
No reciprocal replacement, precision change, prior change or history projection
change is included. All primary comparisons use binary64 history.

The winning evaluator works backward from zero:

```
E: y = (1 + r*y)/(k+1), k descending14..0
L: y = 1/(2*k+1) + z*y, k descending12..0
```

Both recurrences live in one function. `noinline,noclone` prevents GCC from
replicating the engine into callers. This spends arithmetic to save SRAM. Those
attributes and resulting machine code are toolchain-dependent; this study uses
M23 GCC16.2 soft-float, size optimization and LTO, without fast-math.

## Measurements

Same native sample/history/refit/scalar workload and 1,024 B provisional stack
allowance in every row. Executable code, constants and working state count in SRAM.

| Variant | Total B with allowance | Change from baseline |
|---|---:|---:|
| Existing tiny math | 26,952 | — |
| Shared Bernstein E/L | 26,992 | +40 |
| Bernstein plus sqrt seed | 27,256 | +304 |
| Shared Horner plus sqrt seed | 27,176 | +224 |
| Procedural series, compiler free to inline | 26,984 | +32 |
| Shared Horner E/L | 26,904 | -48 |
| Procedural forward series, forced shared body | 26,744 | -208 |
| Bernstein E12/L10 | 26,960 | +8 |
| Bernstein E8/L6 | 26,896 | -56 |
| Bernstein E5/L5 | 26,856 | -96 |
| **Procedural reverse series, forced shared body** | **26,728** | **-224** |

All Bernstein controls have one polynomial segment per reduced-domain function;
this is a minimal single-segment starting point, not a search of arbitrary knot
placements. E/L transforms are matched across the full-degree evaluator arms.
The old baseline uses different truncation degrees in some paths, so baseline
comparison is not solely an evaluator substitution.

Forcing sharing saves240 B versus the unforced procedural arm; reverse evaluation
saves another16 B. A coefficient table can disappear while instruction count
still grows: generated divisions/conversions and compiler inlining explain why
"no LUT" alone did not initially help.

Target M23 instructions executed successfully on M33 QEMU. Exercised stack:
608 B baseline, 776 B Bernstein, 632 B winning reverse-series candidate. These
are separate fixture probes, not universal bounds on the clean image. Bernstein
introduces an automatic coefficient workspace; Horner/reverse-series retain only
scalar working values. The same1 KiB allowance is not evidence of equal stack use.

The separate 48-bit-history build is **25,072 B static +1,024 B allowance =26,096 B
(25.48 KiB)**. Its target probe observed672 B stack and status0. Long paired-stream
qualification below used64-bit history, not48-bit history.

The numerical kernel still excludes platform identity/normalization/scheduling/
ISR/application code. All variants retain about4,762 B of software binary64
helpers. No admission at10 KiB, real-device timing or lifetime guarantee is claimed.

## Qualification and preserved failures

- Initial attempt001 found no SRAM improvement. Attempt002 exposed compiler
  replication. Attempt003 added forced sharing, reverse generation and smaller
  Bernstein controls. Their generated source, maps and ELFs remain separate.
- Function grids include small increments and a wide exponent range. Independent
  review added boundary, exceptional-value, signed-zero and random-bit controls.
  The winner's independent controls observed at most2 ULP in their sampled set;
  this is not a uniform/correct-rounding certificate.
- Ten retained-history checkpoints from two72-hour runs were jointly refitted
  with the same evidence/prior/centres/start. All tested refits converged. This is
  not a72-hour test of new streaming arithmetic. Winner end values/SDs were
  identical in these checks; the small Bernstein arm shifted at most2.82e-6
  reference SD despite much larger standalone function error.
- Two paired four-hour50Hz streams, seeds1100/1101 and embedded load7, each
  accepted239/239 refits in both arms. Maximum chart-coordinate difference was
  below9.6e-13; maximum relative nonzero SD difference below1.33e-11. No zero-SD
  mismatches. Q3SD misses remained0; SOC misses remained0/41.
- The initial stream-reporting code divided zero SD by zero. Its results are
  preserved as stream001 and superseded by stream002, which separately counts
  zero-width mismatches and compares relative SD only where the reference is
  nonzero. The estimator arithmetic was unchanged.

Independent review and exact source/artifact identities are in the
[receipt](../../provenance/shared_math_001/receipt.json), with review_r1 for the
initial variants and review_r2 for the winning construction. Uncertainty remains
provisional, as in the parent estimator.

## Reproduce

Use fresh output directories. These are isolated experiment drivers, not a new
campaign/checkpoint format or a production build cache. Reusing a driver output
root is rejected. Do not rebuild a loaded shared library in place.

```sh
cd /home/easy/proj/mumble/.worktrees/shared-math
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.shared_math_001.run \
  --out /tmp/mumble-shared-math-fresh
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.shared_math_001.target \
  --variant procedural_horner --history-bits 48 \
  --out /tmp/mumble-shared-target-fresh
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.shared_math_001.target \
  --variant procedural_horner --history-bits 48 --execute \
  --out /tmp/mumble-shared-stack-fresh
```

`qualify.py --campaign PATH --out NEW` takes the original paired bank-rowwise
72-hour campaign. `stream_test.py --campaign PATH --out NEW --hours 4` takes a
compatible compact campaign as a source of public calibration and stimulus
settings; it generates a fresh stream. Truth is used only by the simulator and
error metrics, never by inference. Both drivers use the existing test harness.

## What this teaches the next design

1. Optimize total linked memory, not table size or source-line count.
2. Sharing must survive compilation. Function boundaries can matter more than
   algebraic operation counts on this target.
3. Store a generating rule when it costs less than the values it generates.
4. Count automatic scratch: a common Bernstein engine introduced extra stack.
5. Do not infer that all splines are unsuitable. Different ranges, precision,
   segments or a broader shared consumer set may change the result.
6. This224 B improvement does not resolve the dominant architecture constraint.
   Keep it as a measured candidate while studying the binary64 dependency and
   joint-solver storage. No predicted savings from those future changes are booked.
