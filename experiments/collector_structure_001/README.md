# Collector structure: runtime sharing and scratch lifetime

Base `6ec07a5`; branch `experiment/collector-structure-001`.
Selected research variant: **combined**, sharing float subtraction with addition
and reusing the feature row as integer QR input. This preserves the tested
CORDIC/Q12 behavior, including its known accumulation failure. No production
estimator, campaign default or long-duration qualification is changed.

| Variant | Static SRAM | Observed stack | Combined |
|---|---:|---:|---:|
| Prior CORDIC collector | 9324 B | 408 B | 9732 B |
| Subtraction sharing | 8600 B | 408 B | 9008 B |
| Scratch reuse | 9320 B | 272 B | 9592 B |
| **Both (selected)** | **8596 B** | **272 B** | **8868 B** |
| Lazy RC, uint64 conversion clock | 13844 B | 288 B | 14132 B |
| Lazy RC, two-part integer clock | 8704 B | 272 B | 8976 B |

The selected pair saves **864 B** against the prior static-plus-observed budget.
With a provisional 1024 B stack reservation it occupies **9620 B**, leaving 620 B
of a 10240 B budget. These figures include code, constants, static data, vectors
and alignment. IPC, recovery, platform drivers/interrupts and host fitting are
still excluded. Stack witnesses execute M23 code on M33 QEMU; they are not
worst-case stack or target-cycle certificates. This is not a firmware admission.

## Selected changes and contracts

The software-float subtraction wrapper flips the sign bit of its second operand
and invokes the existing addition runtime. Linker wrapping removes the separate
subtraction routine. It follows the existing double-subtraction design. Finite
values, signed zeros, infinities and NaN classification are tested; NaN payload
and sign identity are not promised. Floating exception flags are not qualified.

The collector previously held a float feature row and allocated a second 34-entry
integer row for QR. Their lifetimes do not overlap: after featurization, the float
row is consumed. A named union now stores either representation. Each float slot
is read and converted before that slot is overwritten; only after conversion
finishes is the integer member passed to QR. This removes 136 B of observed stack
without increasing persistent allocation (3080 B bank in both cases).

The converted row is scratch, not an externally retained float-feature object.
Callers needing diagnostics must copy features before conversion. Range rejection
may leave scratch partially converted; existing collector validity latches refusal.
History failure remains nontransactional: no rollback copy is added. The existing
ordered-input, actual-interval, immutable configuration, stationary 25 C model,
new-origin-only initialization and host/history ownership contracts remain intact.

## Qualification

- All four non-lazy variants have identical 88064-byte transcripts: history and
  response checkpoints across 4096 varied-current samples, including zero dt,
  followed by invalid-dt and refusal/no-further-mutation checks. Host UBSan and
  strict-aliasing optimization are enabled.
- ARM original versus wrapped subtraction passes **33024 operand pairs**, covering
  random bit patterns and signed zero, subnormal, normal, infinity and NaN cases.
  Volatile function pointers prevent folding the comparison; both actual libgcc
  implementations are linked into the separate qualification image.
- Independent scratch testing covers **10002 cases**, widths 1..34, invalid
  dimensions, random prepopulated history and conversion boundaries. Status and
  history bytes match, including 1242 rejected cases. UBSan/float-cast-overflow
  checks pass.
- The 512-sample integrated execution witnesses require both successful emulator
  exit and printed status=0. The selected history/response state is unchanged.

These checks qualify the structural equivalence within their stated scope. They
DO NOT repair or requalify the Q12 history: repeated evidence still eventually
stalls. The default binary64/history48 estimator remains selected for reference.

## Rejected lazy reconstruction

For immutable poles and the original all-ones free-state initialization, free RC
response is exp(-elapsed/tau_j). We replaced 39 float states with a clock and
recomputed those responses while keeping all forced states and history columns.
This changes recurrence rounding and the response-state layout. It cannot restore
arbitrary saved free states without a compatible origin contract.

An exact 2^-32-second integer tick clock rejects intervals not exactly representable
on that grid and rejects overflow before clock mutation. The uint64-to/from-float
conversions pulled in large runtime routines: persistent bank allocation fell to
2936 B, but static footprint rose to 13844 B. A two-part seconds/fraction clock
avoids those large conversions; its bank is 2932 B (148 B saved), but extra code
leaves static size **108 B larger** than the selected pair. Both clock variants
pass 11 independent boundary cases, including zero, one tick, smaller rejected
intervals, dt=1, overflow, NaN and infinity.

The clock accumulates exactly on its grid, but conversion to float elapsed time
and reconstructed exponentials still round. The two clock representations can
differ through double rounding. No equality or general error-bound claim is made
against stored recurrence. Lazy recomputation also adds exponential evaluations.
It is rejected for this build; further numerical/timing qualification is not
justified by its measured footprint. The initial `lazy` directory used a coarser
2^-24-second clock; `lazy002` and `lazy_limb` are the final measurements above.

## Build

From this worktree, use a fresh output directory:

```sh
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.collector_structure_001.measure \
  --variant combined --out experiments/collector_structure_001/my_combined
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.collector_structure_001.measure \
  --variant combined --execute --out experiments/collector_structure_001/my_stack
```

The available variants isolate each change; the new generator adapts the original
integer collector sources without editing earlier artifacts. `check.py` runs
against the named baseline/sub/scratch/combined/lazy002 output directories.

## Next decision

Keep the recovered space available for retained rounding remainders or justified
scaling; do not treat it as permission to accept Q12 stagnation. Before implementing
an accumulation repair, derive its state and error budget against the 620 B
provisional margin, reserving room for real integration. Basis-rank reduction is
still a separate, unperformed model-accuracy experiment and should follow that
accounting, rather than silently discarding weak directions to force a size fit.
