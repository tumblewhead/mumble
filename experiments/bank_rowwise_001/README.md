# Native rowwise solver and scalar readouts

Branch `experiment/bank-rowwise-001` is isolated in `.worktrees/bank-rowwise`.
The earlier running campaign in `.worktrees/h7-campaign` is unchanged.

The new `rowwise_bank` arm replaces the reduced bank's dense solver with native C:
analytic feature derivatives emitted one row at a time, packed QR joint refits,
fixed-anchor incremental tangent updates, full-bank state transport, and scalar
means/variances. It uses the same rank3 float64 uncentered representation, original
prior, support, stopping rules and scheduling. It does not improve the underlying
model approximation or change its uncertainty claims.

```sh
cd /home/easy/proj/mumble/.worktrees/bank-rowwise
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -B -m experiments.foster_campaign_001.run \
  --history compare-rowwise --bank-rank 3 --bank-precision float64 \
  --hours 24 --sample-rate-hz 50 --jobs 2 \
  --cells B --loads embedded --load-seeds 7 --seeds 1100 1101 --noise-v .002 \
  --temperature constant --recording compact --summary-bins 2000 --checkpoint-hours 3
```

`compare-rowwise` compares the previous `small_bank` with `rowwise_bank`. Use
`rowwise-bank` for only the new arm. Individual and overlay plots, compact
recording and debug replay remain available. Mainline defaults are unchanged.
The desktop adapter still reconstructs covariance-root rows for legacy plots and
checkpoints; those host arrays are not part of the embedded scalar interface.

Two paired four-hour runs at50Hz completed all239 scheduled refits per arm/case.
Maximum final parameter-chart differences were1.33e-15 and7.11e-15; uncertainty
classifications match, including the previous41 SOC3SD misses for seed1101.
Thirteen targeted tests and independent reviews cover derivatives, fits, scalar
variance, full/compact replay, malformed buffers, invalid endpoint support and
failure handling. This is numerical equivalence evidence, not new coverage.

The actual Cortex-M23 soft-float build was executed on a Cortex-M33 QEMU board
using the M23 instruction target. Stack bytes are meaningful for that linked
program; this is not M23 timing or hardware/Verilog verification.

| Final inference probe allocation | Bytes |
|---|---:|
| Native solver context | 2,376 |
| Packed history | 4,760 |
| Full carried response | 936 |
| Streaming row, input, identity/status allowance and scalar output | 488 |
| Named estimator allocation | **8,560** |
| Total linked static SRAM, including runtime/probe storage | **9,184** |
| Observed stack high-water mark | **632** |
| Observed static + stack | **9,816** |

The original public prior, centres and map/projection tables are immutable ROM
configuration. History stays in SRAM. Runtime-configurable priors/centres require
additional storage. Future streaming calibration is assumed ROM; it is not
instantiated by this inference-only probe. The first allocation with configuration
copies in RAM exceeded10KiB by32B; shortening initialization lifetimes and removing
those unnecessary copies produced the final result. Failed/earlier attempts remain
separate under target_probe001–004; probe005 binds the final code.

A1024B stack reservation would total10,208B, leaving only32B under10KiB. That is
planning arithmetic, not a universal stack bound. The632B watermark exercised
refits, scalar queries, invalid candidates/recovery and a zero-row incremental
update, including linked math libraries. It does not cover every nonzero append,
error path or input. Startup, interrupts, queues and additional application runtime
need their own budget. The Python sample-to-history generator is not yet replaced
by a fully bounded native streaming/commit implementation. This is a verified
inference-core measurement, not a complete deployable estimator size certificate.

Reproduce targeted tests and the target probe in fresh output directories:

```sh
OPENBLAS_NUM_THREADS=1 python3 -B -m unittest \
  experiments.bank_rowwise_001.test_core \
  experiments.bank_rowwise_001.test_campaign -v
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.bank_rowwise_001.measure \
  --out /tmp/mumble-rowwise-target-fresh
```

The probe requires `arm-none-eabi-gcc` and `qemu-system-arm`. Its linker map,
per-function `.su` files, ELF and measurement JSON remain local generated evidence.
[The receipt](../../provenance/bank_rowwise_001/receipt.json) records hashes,
independent reviews and the scope of the footprint claim.
