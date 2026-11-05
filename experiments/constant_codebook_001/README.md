# Lossless constant codebooks: measured rejection

Base `bbe8a8f`; branch `experiment/constant-codebook-001`. This experiment tests
whether lossless constant compression reduces the complete SRAM image. The
selected implementation remains the uncompressed contiguous-response baseline.
Mainline/campaign defaults and numerical precision are unchanged.

## Candidates and results

| Encoding | Static bytes | Change vs baseline |
|---|---:|---:|
| Uncompressed baseline | 24608 | 0 |
| Byte-pair grammar | 24888 | +280 |
| Byte planes + byte-pair grammar | 24896 | +288 |
| Previous-word XOR + byte planes + grammar | 24920 | +312 |
| Exact scale dictionary, shared accessor | 24616 | +8 |
| Exact scale dictionary, inline accessor | 24624 | +16 |

The BPE variants encode 115 doubles (920 bytes): mean, scale, centre, polynomial
projection P and response projection V. Raw encoding stores 871 bytes including
headers/rules; planes store 874; XOR planes store 863. The two 312-byte coefficient
tables compress poorly. Complete linked rodata falls by only 44/44/52 bytes,
respectively, and text grows by 320/328/360 bytes (plus alignment effects).

The scale dictionary uses five exact doubles and 16 byte indices: 56 bytes instead
of128. Shared accessor code growth exceeds that72-byte table saving. An inline
accessor is worse. Both dictionary variants raise observed stack from672 to680 bytes, so their paired
static-plus-observed regressions are16 and24 bytes. Stack witnesses and ELF hashes
are in the receipt. Stack is
observed on a separate M23-code/M33-QEMU fixture, not a worst-case bound or timing
measurement. Losing BPE variants were not subjected to expensive QEMU stack runs;
their static footprint alone already exceeds baseline.

## Representation and boundary contracts

BPE uses spare byte values as production tokens. Each four-byte rule stores token,
left child, right child and decoded length; each blob begins with rule count and
word count. Replacement tokens cannot occur in original bytes or earlier rules,
so dependencies point backward. Rule lengths are additive and at most255.
The iterative decoder skips complete expansions using lengths and descends into
the selected subtree. It uses no recursion, heap or permanent decoded cache.
The scalar reader assembles eight bytes into a double with memcpy. Byte planes
are inverted by address calculation; XOR planes reconstruct the selected word's
prefix. This last operation is especially expensive for random accesses.

These are trusted, intact, immutable, offline-generated blobs with valid indices,
1..255 values and little-endian IEEE754 binary64 storage. The decoder is not a
parser for untrusted or corrupted byte streams: bounds/cycle validation is not
included. Both config and stream V pointer types change. Callers must rebuild;
existing ctypes interfaces are incompatible. All lifetime/no-alias obligations
from the response-base experiment remain in force. No new firmware claim is made.

The word dictionary is restricted to finite positive scales with exactly five
unique values. The generator asserts this; runtime indices must be less than5.
Numeric equality is sufficient under that restriction, not a general signed-zero
or NaN-payload compression contract. Existing finite/positive bind checks remain,
but do not authenticate malformed encodings before decoding.

## Validation and lessons

The bounded compiled check emits every one of the115 decoded constants and a
32-sample transcript: all94 feature rows at32 supported probes, one refit,
512 scalar queries, final history/response/joint factor, and common null-input
rejections. It compares all six variants bit-for-bit with UBSan enabled.
Independent review additionally tests decoder arrays with arbitrary binary64
bit patterns, zeros, repeated bytes and seeded data; see review evidence.

The initial BPE compilation attempts in raw/plane/xorplane failed because a V
pointer declaration used different whitespace. The generator now asserts exactly
two signature substitutions; successful evidence is in the *002 directories.
Initial failed artifacts remain separate. A longer256-sample test passed for baseline, all three BPE modes and the shared
word accessor; its3,459,502-byte transcripts are identical. The bounded test also
includes the inline accessor. Original generated test sources remain in check001;
the current check.py reproduces the bounded check002 protocol.

These results do not rule out better codecs or access restructuring. They show
that these concrete on-demand encodings do not repay their access-code cost.
The earlier combined1642-byte sketch also included658 bytes of literal pools,
addresses and padding. This experiment does not rewrite executable literal loads;
those need a separate compiler/access design, and are not claimed compressed here.

## Reproduce

From this worktree, create fresh output directories when rerunning:

```
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.constant_codebook_001.target --variant baseline --out experiments/constant_codebook_001/baseline
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.constant_codebook_001.target --variant raw --out experiments/constant_codebook_001/raw002
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.constant_codebook_001.target --variant plane --out experiments/constant_codebook_001/plane002
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.constant_codebook_001.target --variant xorplane --out experiments/constant_codebook_001/xorplane002
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.constant_codebook_001.target --variant word --out experiments/constant_codebook_001/word
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.constant_codebook_001.target --variant word_inline --out experiments/constant_codebook_001/word_inline
python3 -B -m experiments.constant_codebook_001.check --out experiments/constant_codebook_001/check002
python3 -B -m experiments.constant_codebook_001.execution --variant baseline --out experiments/constant_codebook_001/stack_baseline
python3 -B -m experiments.constant_codebook_001.execution --variant word --out experiments/constant_codebook_001/stack_word
python3 -B -m experiments.constant_codebook_001.execution --variant word_inline --out experiments/constant_codebook_001/stack_word_inline
```
