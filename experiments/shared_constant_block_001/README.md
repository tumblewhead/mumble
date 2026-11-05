# Shared segmented constant block

Base `28270c6`; experiment branch `experiment/shared-constant-block-001`.
The active numerical implementation remains the uncompressed response-base
candidate at `bbe8a8f`: 24608 static bytes. No mainline/campaign change.

## Executable experiments

One shared grammar and payload replaces six tables: mean16, scale16, centre5,
P39, V39 and OCV2 (117 binary64 values,936 bytes). Six unsigned16 offsets
(12 bytes) identify segments; one scalar decoder reads by segment and index.
No full table expansion, permanent decoded cache, heap or recursive decode.
The literal variants additionally move15 distinct explicit floating literals
from the numerical core and shared math source into the same payload. Duplicates
share one slot. The second layout transposes all bytes into eight byte planes.

| Variant | Payload + segment offsets | Linked static | Change |
|---|---:|---:|---:|
| Uncompressed baseline | — | 24608 B | — |
| Shared raw-byte grammar | 865 B | 24904 B | +296 B |
| Shared byte-plane grammar | 902 B | 24936 B | +328 B |
| Raw grammar + numerical literals | 947 B | 25216 B | +608 B |
| Byte planes + numerical literals | 1000 B | 25264 B | +656 B |

Payload sizes include grammar headers/rules. The table-only raw block saves71B
against936B. The literals variant encodes1056B into947B including descriptors,
but moving source constants to runtime loads changes code generation. Lost
constant folding, lookup code and call-site costs outweigh storage savings in
these compiled images. Exact individual compiler effects are not separately
attributed. All four candidates are rejected; this is not a proof that every
possible shared codec loses. No candidate stack sweep is needed for the size
rejection: static alone exceeds baseline. No total-stack bound is claimed.

## Full1642-byte envelope (offline only)

`audit.py` extracts the baseline984-byte rodata and658 bytes marked as data
inside text, preserving all bytes. These form30 regions (rodata plus29 literal
pools). Raw BPE gives1360B including six padding bytes before encoding; a120B
directory of uint16 decoded-offset/length pairs brings it to1480B:162B less than
the original1642. Byte planes total1586B:56B less.

This directory does not include original addresses or relocation handling.
Decoder code, scratch and executable access rewriting are also excluded from
that offline saving. The compiled literal variants pool explicit floating
literals, not every address, integer bit pattern, linker item or compiler-generated
constant within those658B. We have not produced an executable replacement of
all1642B. The offline result and actual linked candidates must not be conflated.

## Contracts and validation

The shared grammar inherits the trusted offline-generated acyclic grammar
contract from constant_codebook_001. Blob count fits one byte (1..255 values),
rule expansion lengths fit one byte, offsets/indices must be valid, and buffers
must remain immutable and live. Little-endian IEEE754 binary64 is required.
This is not a safe parser for malformed data. Configuration/stream V/OCV pointer
types change to segment descriptors; all callers must rebuild. No current Python
ctypes adapter is compatible. Existing response lifetime/no-alias contracts hold.

The literal transform skips comments and quoted strings and handles the present
unsuffixed decimal/hex floating tokens only. It does not rewrite general C
expressions, integer constants, float suffixes or arbitrary preprocessor uses.
Unary signs remain at the original expression. Original floating token bits are
retained in literals.json and independently checked by the compiled test.

`check.py` compares117 constants, every pooled literal, eight supported probes
of94 feature rows, eight stream samples, one refit,128 scalar queries, final
history/response/joint factor and common null-input rejections. UBSan is enabled.
All five114410-byte transcripts match. This targeted check is about lossless
implementation equivalence, not long-run statistical qualification. Independent
review also passes32-sample/512-query UBSan transcripts for all five variants,
arbitrary-bit shared decoder cases through255values, and15 original C literal
spellings compared directly against decoded values. Controls and hashes are
retained in provenance/shared_constant_block_001.

## Reproduction

Run from this worktree, with fresh output directories on reruns:

```
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.shared_constant_block_001.target --variant baseline --out experiments/shared_constant_block_001/baseline
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.shared_constant_block_001.target --variant raw --out experiments/shared_constant_block_001/raw
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.shared_constant_block_001.target --variant plane --out experiments/shared_constant_block_001/plane
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.shared_constant_block_001.target --variant raw_literals --out experiments/shared_constant_block_001/raw_literals
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.shared_constant_block_001.target --variant plane_literals --out experiments/shared_constant_block_001/plane_literals
python3 -B -m experiments.shared_constant_block_001.check --out experiments/shared_constant_block_001/check001
python3 -B -m experiments.shared_constant_block_001.audit --elf experiments/shared_constant_block_001/baseline/tiny_cardinal/probe.elf --out provenance/shared_constant_block_001/full_envelope.json
```
