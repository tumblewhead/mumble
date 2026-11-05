# Constant layout and compression study

Base `665a99b`; study branch `experiment/constant-layout-study-001`.
No estimator implementation is promoted. The active response-base implementation
remains `bbe8a8f`, at 24,608 static bytes. This study examines actual linked bytes,
not a claim about the entropy of all possible estimator configurations.

## Findings

The 1,642-byte envelope is 984 bytes of rodata plus 658 bytes in 29 text literal
pools. Five linked numerical tables occupy 920 bytes. The remaining 722 bytes
include index tables, configuration pointers, literals, address-like words and
padding. The source OCV pair is not a separate linked table in this accounting;
its compiled contribution stays in the remaining bytes.

The two projection tables P and V occupy 624 bytes. Each has 39 distinct doubles;
none of the tested generic codecs shrinks either table on its own. Their low
mantissa bytes vary substantially. Their highest byte has only eight distinct
values across the two tables, making exponent/sign packing more promising than
byte-pair replacement for this part.

Most available repetition is elsewhere. Scales contain only five distinct values
in 16 entries. The remaining 722 bytes contain 215 zero bytes and are substantially
more compressible. They also contain executable-literal access and relocation
constraints, so their payload savings are not automatically usable SRAM savings.

## Whole-block codec comparison

All stream headers and dictionary/codebook bytes are included below. A consistent
120-byte directory (30 uint16 offset/length pairs) is added for comparison with
the prior experiment. Original addresses, decoder code, access changes, runtime
state and scratch are excluded. Original order is the best tested layout for
LZSS, DEFLATE and LZMA. No transform selector is needed for this fixed layout.

| Codec | Self-contained stream | With directory | Gross saving vs 1642 |
|---|---:|---:|---:|
| LZMA alone format | 1179 B | 1299 B | 343 B (20.9%) |
| Raw DEFLATE plus 2-byte decoded length | 1222 B | 1342 B | 300 B (18.3%) |
| LZSS, 11-bit distance/5-bit length | 1322 B | 1442 B | 200 B (12.2%) |
| Expanded-alphabet 9-bit BPE | 1353 B | 1473 B | 169 B (10.3%) |
| Canonical Huffman | 1480 B | 1600 B | 42 B (2.6%) |
| bzip2 container | 1553 B | 1673 B | -31 B |

These are measured streams, not proofs of optimal compression. LZMA/DEFLATE are
reference comparisons, not proposed drop-in firmware libraries: their decoder
footprints and memory behavior have not been measured here. The LZMA preset9
header advertises a large dictionary. Even a tailored decoder must earn its code
and state costs from the modest gross saving.

The previous spare-byte BPE result was 1480 bytes including its directory. Giving
BPE the full 9-bit alphabet improves that to1473, only7 bytes. Its token limitation
was real, but removing it does not reveal a large hidden redundancy in this block.

## Arrangement experiments

We round-trip tested original order, global byte planes of widths2/4/8, the same
transforms within each original segment, and preceding-word XOR before each
plane transform:13 layouts in total. Byte planes preserve frequent bytes but
break repeated adjacent byte strings; the measured LZ-family results worsen.
For example raw DEFLATE grows from1222 to1362 bytes with global8-byte planes.
Preceding-word XOR is generally worse again. This coefficient sequence does not
behave like a smoothly changing series of neighboring bit patterns.

A type-aware split separates920 numerical bytes and722 other bytes. Extra20 bytes
model five uint16 source-span descriptors, with two codec selectors. The original
120-byte directory is still charged. The reviewer independently serialized those
spans and exactly reconstructed the full envelope. The reported partition plane
layouts do not beat whole-block original order. General sorting would also need
an inverse index map; we have not claimed free reordering.

Byte entropy in result.json is a fitted zero-order diagnostic. It excludes the
cost of learning/storing the model and is not a universal compression lower bound.

## Access and memory constraints

A conventional whole-block LZ decoder needs earlier decoded bytes for matches.
The winning LZSS stream uses backreferences as far as1116 bytes. That is an access
requirement, not a proof of minimum scratch: replay or recursive reconstruction
could trade much more CPU for memory. Neither strategy is target-qualified here.

We also implemented exact, independently decodable blocks with raw fallback,
per-block tags, a decoded-length/block-size header, and a uint16 offset directory.
The totals below include both this block directory and the original120-byte
segment directory:

| Maximum decoded block | Encoded total | Gross saving |
|---|---:|---:|
| 32 B | 1810 B | -168 B |
| 64 B | 1685 B | -43 B |
| 128 B | 1564 B | 78 B |
| 256 B | 1499 B | 143 B |

A dedicated128-byte decode buffer already exceeds its78-byte gross saving, before
code. Existing scratch might be reused, but that requires an explicit lifetime
contract at every constant read. These block sizes describe possible decoded
working sets, not measured native stack usage.

The120-byte directory is a comparison choice, not an irreducible requirement.
Fixed segment lengths could make some offsets implicit; replacing directory bytes
with indexing/control code must still be measured in the final image.

## Formats specialized to the projection coefficients

| Exact representation of P and V | Stored bytes | Gross saving |
|---|---:|---:|
| Original binary64 | 624 | — |
| Shared highest-byte dictionary; other7 bytes literal | 587 | 37 |
| Sign + 6-bit exponent offset + 52-bit fraction | 581 | 43 |

These figures include format headers, dictionary and indices and have exact
serialized reconstruction checks. They give bounded random-access layouts without
LZ history, but 37–43 bytes is a small budget for additional native readout code.
No target savings are claimed.

As a separate lossy option, storing the78 coefficients in binary32 would use312
bytes. On these coefficients, maximum absolute rounding error is5.78e-8 and maximum
relative error is5.36e-8. Those are coefficient errors, not voltage, posterior or
long-run estimation bounds. An actual variant must retain double computation if
specified, include conversion/access costs, propagate approximation error and
repeat system qualification. No coefficient quantization was applied here.

## Recommended direction

1. Preserve original order for any further LZ-style experiment; stop assuming a
   whole-block byte-plane transform improves this corpus.
2. Keep the high-entropy projection mantissas directly accessible. They dominate
   the numerical tables yet offer little lossless redundancy.
3. If remaining lossless work is desired, focus on low-overhead semantic packing
   of tiny index tables or fixed scalar fields, with a native-size test. The prior
   exact scale dictionary already lost after its access cost; do not repeat it
   without changing that cost.
4. For a meaningfully larger constant reduction, a separately qualified binary32
   coefficient-storage candidate is more promising than another general lossless
   decoder. This is a new accuracy tradeoff, not an accepted optimization.

## Reproduce and qualify

```
python3 -B -m experiments.constant_layout_study_001.study --elf experiments/shared_constant_block_001/baseline/tiny_cardinal/probe.elf --out experiments/constant_layout_study_001/run005
```

Use a fresh output directory on rerun. Standard-library codecs and our reference
LZSS/BPE/Huffman/dictionary/packing codecs are round-trip checked. Seeded random,
empty, zero, repeated and full-alphabet controls are included. Independent review
adds adversarial cases and reconstructs partition metadata. Results, exact source
hashes, findings and review are in `provenance/constant_layout_study_001`.
