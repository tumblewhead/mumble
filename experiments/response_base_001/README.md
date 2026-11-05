# One response-state base pointer

Experiment branch `experiment/response-base-001`, base `773c98e`. Replace the
three response pointers with one writable base pointer. Derive legacy, free RC
and forced RC regions at offsets 0, 15 and 54 doubles. The harness already uses
this layout; no numerical expressions, fitting rules or precision change.

| Cortex-M23 observable-input image | Baseline | Contiguous response |
|---|---:|---:|
| Text | 16700 | 16660 |
| Read-only data | 1000 | 984 |
| BSS | 6944 | 6936 |
| Vectors | 28 | 28 |
| Alignment gaps | 0 | 0 |
| Total static bytes | 24672 | 24608 |
| Separate execution-probe observed stack | 680 | 672 |

This saves **64 static bytes and 8 observed stack bytes**, a **72-byte paired
comparison reduction**. Static plus observed is 25280 bytes; with a provisional
1024-byte stack reservation it is 25632 bytes. The 10240-byte goal is still unmet.
The stack witness is a separate fixture executing M23 code on M33 QEMU, not a
worst-case stack bound or timing measurement. The size image includes the
numerical stream/fit/query path and synthetic I/O slots, not platform services.

## Contracts

The response base points to a single live, writable, properly aligned array
object containing at least 93 doubles: legacy [0,15), free RC [15,54), forced RC
[54,93). Three adjacent but separately allocated objects do not satisfy this C
pointer-arithmetic contract. The whole array outlives the bound context. It must
not overlap the core, history, or immutable configuration storage. Initialization
and chronology remain the caller's responsibility as before. Derived pointers
are never separately supplied or nullable; bind rejects a null base before use.

The configuration object, its pointer members and arrays retain their previous
immutable lifetime/extent contract. The specialized model ABI changes again;
callers must rebuild. Existing ctypes layouts and campaign defaults are untouched.
Arbitrary independent response allocations are no longer supported by this variant.

## Qualification

`check.py` compiles standalone baseline and candidate C programs. Transcripts
match byte for byte across 256 support probes, all 94 feature rows, 256 samples,
8 refits, 4096 scalar queries, final history, response and joint factor. Separate
159-case invalid-binding checks reject invalid finite/positive configuration,
null arrays/configuration/response, and verify the bound core remains unchanged.
Five common null-array cases are compared; removed free/forced pointer arguments
are no longer independent validation inputs. Tests require accepted support probes.

Independent review is required in `provenance/response_base_001/review.json`.
Source, compact receipts and review are retained; generated executables are not
committed. Mainline and campaign defaults remain unchanged.

Run from the worktree, using fresh output paths on reruns:

```
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.response_base_001.target --variant baseline --out experiments/response_base_001/baseline
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.response_base_001.target --variant contiguous --out experiments/response_base_001/contiguous
python3 -B -m experiments.response_base_001.execution --variant baseline --out experiments/response_base_001/stack_baseline
python3 -B -m experiments.response_base_001.execution --variant contiguous --out experiments/response_base_001/stack_contiguous
python3 -B -m experiments.response_base_001.check --out experiments/response_base_001/check001
```

Parity checks use the preceding target-generated cores/configurations. The
sample protocol and prior validation templates are retained from the reviewed
configuration-reference experiment, with only layout and null-input adaptations.
