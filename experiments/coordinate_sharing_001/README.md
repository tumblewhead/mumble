# Shared physical-coordinate calculations

Base `751a5ff`; branch `experiment/coordinate-sharing-001`. Baseline is the exact
byte-index candidate. All coefficients remain binary64; the provisional float32
coefficient experiment is not included. Selected variant: `combined_scalar`.
Mainline/campaign defaults and caller ABI remain unchanged.

## Measurements

| Variant | Static bytes | Observed stack | Static + observed | Change vs baseline |
|---|---:|---:|---:|---:|
| Baseline | 24568 | 664 | 25232 | — |
| Single hysteresis-coordinate helper | 24440 | 680 | 25120 | -112 |
| Two-coordinate helper | 24576 | 704 | 25280 | +48 |
| Exponential-chart helper | 24560 | 672 | 25232 | 0 |
| Both single-coordinate helpers | 24400 | 680 | 25080 | **-152** |

The selected combination saves168 static bytes and adds16 observed stack bytes.
Its provisional total with1024 bytes of stack is25424 bytes. This remains above
10KiB. The complete numerical image includes code, constants, in-place data,
synthetic I/O slots and alignment; platform services are still outside its scope.
Stack is a separate execution fixture running M23 code on M33 QEMU, not a
worst-case bound or target timing measurement. No persistent storage is added.

Selected sections: text16480, rodata948, BSS6936, vectors28, alignment8 bytes.
Baseline text16652 with4 alignment bytes. The combined linked result saves32 more
static bytes than the sum of the individual static savings; do not assume
independent compiler changes combine additively. The two-output helper loses and
is retained only as experimental evidence.

## Changes and contracts

The selected hysteresis helper computes one coordinate:

```
chart(m,w,14+j) - chart(m,w,5) - log(m->config->center[3+j])
```

It replaces the same expression in support checks, feature evaluation and endpoint
transport. Callers supply j=0 or1, so all configuration/parameter indices remain
inside their existing extents. Subtractions, logarithm and chart operations retain
their original expression order. The pair helper was separately tested only in
feature/transport; its pointer outputs are distinct caller-local doubles.

The exponential helper replaces nine `exp(chart(m,w,j))` source occurrences with
a shared noinline/noclone function returning that exact expression. It does not
replace negative-chart exponentials or rewrite other math. Existing binary64
arithmetic, non-fast-math flags and shared tiny-math implementation are retained.
The change shares code, not a persistent value cache, and introduces no registry,
parameter invalidation or sample-lifecycle rules.

Inputs and immutable configuration obey existing lifetime/no-alias/serialized-call
contracts. Helpers do not mutate input or estimator state. No truth, chronology,
evidence ownership, fitting rule, uncertainty rule or support threshold changes.
Existing invalid-input rejection is preserved; NaN payload/sign bits are not a
public contract. No new errno/floating-exception-environment guarantee is made.

## Validation

All five variants match exactly under host UBSan controls:

- 256 support probes,94 full feature rows,256 samples,8 refits,4096 scalar queries,
  final history/response/joint factor:3,458,582 transcript bytes.
- 159 invalid bindings reject and leave the bound core unchanged.
- 257 projected-map points,64 projected-feature probes,4096 samples,32 refits,
  512 scalar-query attempts and final response:322,584 transcript bytes.

Some scalar attempts in the synthetic numerical control fail identically. This
is equivalence evidence, not a claim of512 successful estimates or calibrated
accuracy. No new approximation is introduced and no long campaign sweep was run.

Independent review additionally sweeps extreme/nonfinite/signed-zero inputs and
hysteresis support boundaries, exercises all16 transported outputs and derivatives
for supported inputs, repeats the selected target build and QEMU stack witness,
and checks source transformations. Those381,880-byte edge transcripts match.

check001 and the initial reviewer check retained a descriptive typo mentioning128
scalar queries in the second control; the source executes16 queries on each of32
frames, hence512 attempts. check002 fixes the metadata without changing the test.
Old result files are preserved. An unmeasured combined-pair option was removed
from the generator before final review; no measured variant's generated code changed.

## Reproduce

From this worktree, use fresh output directories on reruns:

```
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.coordinate_sharing_001.target --variant baseline --out experiments/coordinate_sharing_001/baseline
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.coordinate_sharing_001.target --variant hys_scalar --out experiments/coordinate_sharing_001/hys_scalar
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.coordinate_sharing_001.target --variant hys_pair --out experiments/coordinate_sharing_001/hys_pair
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.coordinate_sharing_001.target --variant exp_chart --out experiments/coordinate_sharing_001/exp_chart
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.coordinate_sharing_001.target --variant combined_scalar --out experiments/coordinate_sharing_001/combined_scalar
python3 -B -m experiments.coordinate_sharing_001.check --out experiments/coordinate_sharing_001/check002
python3 -B -m experiments.coordinate_sharing_001.execution --variant combined_scalar --out experiments/coordinate_sharing_001/stack_combined_scalar
```

Full resource receipts, ELF/source hashes and independent review are retained in
`provenance/coordinate_sharing_001`. This experiment is isolated from the campaign
adapter and does not qualify the previous float32 storage candidate.
