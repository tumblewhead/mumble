# Calculation sharing: ordered RC pole sums

The selected `rc_tau_support` experiment shares one ordered pole-sum calculation
across coefficient evaluation, full-bank endpoint transport and support checking.
It saves **40 B static SRAM**. The same target execution probe uses **24 B more
observed stack**, leaving a **16 B reduction in static plus observed stack**.
This is a small, isolated improvement; mainline and campaign defaults are unchanged.

| Resource | Procedural-Horner / history48 baseline | Shared pole sum | Change |
|---|---:|---:|---:|
| Text | 17,100 B | 17,056 B | −44 B |
| Constants | 1,016 B | 1,016 B | 0 |
| BSS | 6,928 B | 6,928 B | 0 |
| Vectors | 28 B | 28 B | 0 |
| Alignment | 0 B | 4 B | +4 B |
| **Static SRAM** | **25,072 B** | **25,032 B** | **−40 B** |
| Observed probe stack | 672 B | 696 B | +24 B |
| **Static + observed stack** | **25,744 B** | **25,728 B** | **−16 B** |
| Static + provisional 1 KiB stack reservation | 26,096 B | 26,056 B | −40 B |

The stack watermark is not a worst-case bound. The execution witness runs M23
instructions on an M33 QEMU model; it is not a timing measurement. Platform code,
interrupts, actual device scheduling and full stack qualification remain outside
this numerical-core image. All code and constants count toward SRAM.

## Calculation and contract

For branch b, both the original and new paths compute, in increasing k order:

```
tau = 0
for k = 0 .. b:
    tau += exp(mean[8+2*k] + scale[8+2*k] * w[8+2*k])
```

`rc_tau()` contains that loop once. Its callers retain the original logarithm,
spline evaluation and multiply-then-divide derivative calculations. The helper
has no persistent state or table. Under the existing serialized API and compiler
floating-point settings, it repeats the original arithmetic sequence for each
prefix; sharing changes call structure rather than a numerical approximation.
The likelihood still uses the reduced basis and transport still uses all 13
poles. Prior, support limits, state chronology, history encoding and joint
uncertainty remain the same.

Previously support checking computed all three prefixes in one loop. Sharing
recomputes each prefix, requiring **six exp evaluations instead of three per
support check**. Feature and endpoint paths use the same exp counts as before.
This is an explicit processor-for-code tradeoff, plus function-call overhead.
The linked helper is 56 B; its local frame is 32 B, which is distinct from the
24 B change in the complete observed stack watermark.

## What failed before this small win

- Summing full feature rows saved 224 B static, but multiplied amplitudes before
  carried-state weights. A supported, large finite R with zero carried response
  caused intermediate derivative overflow and rejected a query the baseline
  accepted. Both weighted-row variants are rejected; the independent review
  includes a reproducible counterexample.
- A larger shared RC readout preserved association but added 120 B static.
- Caching pole geometry added 8 B static. Sharing the coordinate calculation in
  two paths broke even. Sharing it with support checks saved 40 B static but
  added 48 B observed stack: an 8 B combined regression, also rejected.
- Sharing only the pole sum in two paths saved 8 B static but added 24 B observed
  stack. Sharing it in all three paths is the selected variant above.
- Chart/positive-parameter wrapper controls did not establish a better total
  footprint. They are recorded as nonselected variants, not additional savings.

This experiment shows why code size alone is an insufficient acceptance test.
All measured variants are retained in the [receipt](../../provenance/calculation_sharing_001/receipt.json).

## Validation and limitations

The direct controls compared 4,160 endpoints and 8,840 feature rows with bitwise
identical results. Independent finite differences of RC transport gradients had
maximum absolute discrepancy 4.14e-11 (rounded upward). The large-amplitude,
zero-state counterexample passes. Invalid coordinates/nonfinite support checks
and query-before-stream/refit scratch reuse are covered.

One deliberately repetitive fixture eventually rejects a query in **both**
implementations. The lifecycle test preserves that matching rejection; it does
not treat the fixture as successful battery estimation. An initial test driver
incorrectly required success there; `qualification001` is preserved and superseded
by the driver that uses accepted-fit fallback and compares failure behavior.
The initial generated builds and failure log are preserved; the original Python
driver revision was not separately archived.

Two fresh one-hour, 50 Hz streams use 48-bit history storage in both arms, public
calibration/prior, embedded load 7 and noise seeds 1100/1101. Each arm accepted all
59 scheduled refits per case. Every checked endpoint and marginal standard
deviation matched exactly, with no mismatched zero standard deviations. No Q/SOC
3SD misses occurred within these short prefixes; this does not supersede known
later misses or establish calibrated coverage. Truth is used only by the plant
and reporting metrics. This is not lifetime qualification or a rate study.

Independent reviews cover the rejected weighted-row candidate (R1), rejected
coordinate/stack candidate (R2), and selected tau-only candidate (R3). Generated
source and ELF hashes preserve the versions reviewed even as the experiment
builder gained later variants. Only R3 applies to the selected implementation.

## Run the isolated controls

Use fresh output directories from this worktree:

```bash
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.calculation_sharing_001.target \
  --variant rc_tau_support --out experiments/calculation_sharing_001/my_target
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.calculation_sharing_001.target \
  --variant rc_tau_support --execute --out experiments/calculation_sharing_001/my_stack
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.calculation_sharing_001.qualify \
  --out experiments/calculation_sharing_001/my_controls
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.calculation_sharing_001.stream_test \
  --campaign /path/to/compatible/campaign --hours 1 \
  --out experiments/calculation_sharing_001/my_stream
```

The campaign argument supplies calibration and stimulus settings; the driver
creates a fresh stream. These are isolated experiment drivers, not a production
build cache or a new campaign option. The next candidate is sharing QR rotation
logic across history and local inference while preserving their different
storage-rounding rules. Keep this measured pole-sum variant as the comparison
baseline, and count stack as well as text for every further change.
