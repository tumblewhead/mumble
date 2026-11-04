# SRAM-only size experiment

This branch counts instructions, constants, tables, working state and stack in
SRAM. The smallest tested candidate is **26,328 B (25.71 KiB)** with a provisional
1,024 B stack reservation. The target remains 10,240 B. This is not a target fit
or deployment qualification. Mainline and baseline defaults are unchanged.

The clean M23 link includes stationary 25C sample processing, charge integration,
three fixed RC banks, TaylorH2 hysteresis, history QR, joint refits and scalar
state/parameter uncertainty readouts. Device identity/sequence/normalization
code, scheduling, interrupts, persistent checkpoints and application integration
remain outside it; 160 B of identity/status storage is reserved, but that does
not account for their executable code. Desktop plot/covariance adapters are also
outside the embedded scalar interface. All retained binary64 software helpers
are included in the link. No flash or ROM exclusion is used.

| Native allocation | 64-bit history | 48-bit history |
|---|---:|---:|
| Instructions `.text` | see receipt | 17,224 B |
| Constants `.rodata` | 1,120 B | 1,120 B |
| Vectors + alignment | see receipt | 32 B |
| `.bss`, including numerical state and reservations | 8,112 B | 6,928 B |
| Actual allocated address span | 25,928 B | 25,304 B |
| With 1,024 B stack allowance | **26,952 B** | **26,328 B** |

The separate target execution probe observed 648 B of stack with the 48-bit
candidate. This is an exercised-path witness on M33 QEMU running M23-generated
instructions, **not** a worst-case bound or M23 timing measurement. The size
image has no saved history/observation fixtures and stores initialized data in
place. The older clean inference-only control was 37,416 B with the same stack
allowance; the still older 43,576 B probe also contained test fixtures.

## Changes and their limits

- Small binary64 math removes the general-purpose libm dependency and its runtime
  state. Tests check errors and estimator behavior; correct rounding and a
  decade-long floating-point bound are not established.
- A table-free degree12 cardinal polynomial replaces the 13-by-27 spline map.
  The reduced map uses the same polynomial expressed in Chebyshev coefficients;
  no additional degree truncation is applied. The pole bank, original parameter
  domain, priors and rank3 history projection remain fixed. The new map has a
  small negative relaxation tail and **does not inherit positivity/passivity
  certificates**. Independent finite grids found free-response error about
  1.49e-6, versus 7.61e-7 for the supplied full spline map. Existing rank3
  likelihood projection error is much larger, around 0.02 on that grid.
- The C stream keeps 15 H/path doubles instead of 39 legacy doubles and retains
  all 78 free/forced RC doubles: 744 B of response state. It consumes each sample
  once; the same row scratch feeds the tangent before destructive history QR.
- The optional six-byte history encoding rounds each coefficient write to 37
  significant binary digits; arithmetic and tangent storage remain binary64.
  It is **not** float32 history and is not a lifetime error certificate. Its
  1,190 B data saving costs additional code; net image saving is only 624 B.
  The default SRAM experiment therefore retains 64-bit history.
- Target subtraction reuses the existing addition helper through a sign-bit
  change, avoiding a duplicated software arithmetic implementation. The host
  campaign uses its normal machine arithmetic; the target probe checks the
  linked wrapper on M23 instructions.

Partial native streaming failure poisons the adapter permanently. The campaign
quarantines it rather than allowing a refit to make partially consumed evidence
look current. Build receipts bind source hashes, options and binary hashes;
stale binaries and source changes during compilation are rejected.

## Qualification

The [receipt](../../provenance/sram_size_001/receipt.json) preserves exact commands,
source/artifact hashes, intermediate failures and independent review decisions.
Two four-hour 50Hz cases with the 48-bit candidate each accepted all 239 refits.
Final Q differed from the rank3 control by less than 0.00001 percentage points.
The existing seed 1101 transient 41 SOC 3SD misses remained; none were hidden or
claimed repaired. The 64-bit paired control and immutable72-hour checkpoint
refits are recorded separately. The checkpoint study is a refit of common retained
evidence, **not** a replay or qualification of72-hour quantized accumulation.

Targeted tests cover the math grid, joint feature derivatives, transport,
scalar variances, irregular/rest/reversal input, packed history roundtrips,
partial failures, full/compact equivalence and exact debug replay. Source-bound
independent reviews cover core algebra, lifetime/alias contracts, quantization
and integration. These are local synthetic controls, not population coverage.

## Run locally

The normal runner still provides jobs, compact recording, per-arm and summary
plots, independent load/noise seeds and debug-window replay. From this worktree:

```sh
cd /home/easy/proj/mumble/.worktrees/sram-size
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.foster_campaign_001.run \
  --history compare-rowwise --rowwise-implementation sram \
  --sram-history-bits 48 --bank-rank 3 --bank-precision float64 \
  --hours 72 --sample-rate-hz 50 --temperature constant \
  --loads embedded --load-seeds 7 --seeds 1100 1101 --noise-v .002 \
  --jobs 2 --recording compact --checkpoint-hours 3 --summary-bins 1200
```

`small_bank` is the unchanged rank3 control; `rowwise_bank` is the selected SRAM
candidate. Use `--sram-history-bits 64` to isolate the other reductions without
quantizing accumulated history. `--sram-map spline` and `--sram-math libm` are
controls, not the smallest configuration. Variable temperature is rejected.
Keep the worktree sources unchanged during a run and its replay.

Reproduce the size and stack measurements in new output directories:

```sh
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.sram_size_001.measure \
  --history-bits 48 --out /tmp/mumble-sram-size-fresh
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.sram_size_001.stack \
  --history-bits 48 --out /tmp/mumble-sram-stack-fresh
OPENBLAS_NUM_THREADS=1 python3 -B -m unittest \
  experiments.sram_size_001.test_core experiments.sram_size_001.test_campaign -v
```

## Remaining obstacle

Instructions alone exceed 10 KiB. Working data, constants, observed stack and
software binary64 helpers alone account for 13,486 B in this implementation,
before most estimator instructions. This is measured component accounting, not
a universal lower bound for battery estimation. More scratch reuse cannot close the remaining
16,088 B gap, even before platform integration. The next architectural comparison
should measure (1) a matrix-free joint solve with explicit solve-error bounds,
and (2) a smaller arithmetic representation with compensated accumulation.
Neither is implemented or credited with savings here. Changing the objective,
dropping cross terms, posterior collapse or naive float32 accumulation is not an
accepted shortcut. Preserve this executable candidate as the accuracy/resource
control for that comparison.
