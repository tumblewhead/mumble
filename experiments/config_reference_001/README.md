# Shared immutable configuration reference

Selected experiment: `pointer_block`, based on `c432d91`. Four immutable array
pointers move into a shared configuration object. The model retains one pointer
to that object and three response pointers. Arithmetic and sample processing
remain unchanged. Mainline and campaign defaults are unchanged.

| Cortex-M23 observable-input image | Baseline | Pointer block | Inline arrays |
|---|---:|---:|---:|
| Text | 16704 | 16700 | 16716 |
| Read-only data | 996 | 1000 | 984 |
| BSS | 6960 | 6944 | 6944 |
| Vectors | 28 | 28 | 28 |
| Alignment gaps | 8 | 0 | 0 |
| Total static bytes | 24696 | 24672 | 24672 |
| Separate execution-probe observed stack | 664 | 680 | 680 |

The selected layout saves 24 static bytes, adds 16 observed stack bytes, and
therefore saves **8 bytes in the paired static-plus-observed comparison**.
The 1024-byte provisional stack reservation gives 25696 bytes, well above the
10240-byte target. The execution witness is a separate fixture on M33 QEMU
running M23 code; it is not a worst-case stack bound for the observable-input
image. Platform services remain outside the measured numerical core.

## Boundary contract

The configuration object and arrays must outlive every bound context. Both the
four pointer members and their pointee arrays must remain immutable after bind;
C's shallow const qualification alone does not enforce this. Valid extents are
16 means, 16 scales, 5 centres and 39 projected coefficients. Mutable response
storage must not alias configuration storage. Bind retains its original array
null and finite/positive checks and additionally rejects a null config object.
The specialized ABI requires rebuilt callers; old ctypes layouts are incompatible.

## Evidence and reproduction

Run from this worktree:

```
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.config_reference_001.target --variant baseline --out experiments/config_reference_001/baseline
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.config_reference_001.target --variant pointer_block --out experiments/config_reference_001/pointer_block002
python3 -B -m experiments.config_reference_001.execution --variant pointer_block --out experiments/config_reference_001/stack_pointer_block
python3 -B -m experiments.config_reference_001.check --out experiments/config_reference_001/check001
```

Use fresh output paths on rerun. The parity check needs the two target-generated
core/config files first. Standalone compiled C transcripts match byte-for-byte:
256 support/feature probes, 256 stream samples, 8 refits, 4096 scalar queries,
final history/response/joint factor and seven array-pointer rejections. The new
null configuration rejection is separately checked. No old ctypes ABI is used.

Initial pointer/inline builds failed because dot-style context accesses and the
included stream code were not rewritten; the generator now embeds and rewrites
both. Failed output directories are preserved and are not measurement evidence.
Inline arrays tie the static saving but are not selected for full qualification.
Independent review and compact receipts live in `provenance/config_reference_001`.
