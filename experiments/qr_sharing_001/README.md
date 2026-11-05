# Shared QR insertion experiment

A single Givens-rotation loop now serves the six-byte history factor and the
binary64 local inference factor in this isolated candidate. Against the reviewed
RC pole-sum baseline (`1f2f04c`), it saves **352 B static SRAM** and **32 B observed
stack**, a **384 B reduction in static plus observed stack**. Mainline and
campaign defaults remain unchanged.

| Resource | Pole-sum baseline | Shared QR | Change |
|---|---:|---:|---:|
| Text | 17,056 B | 16,704 B | −352 B |
| Constants | 1,016 B | 1,016 B | 0 |
| BSS | 6,928 B | 6,928 B | 0 |
| Vectors | 28 B | 28 B | 0 |
| Alignment | 4 B | 4 B | 0 |
| **Static SRAM** | **25,032 B** | **24,680 B** | **−352 B** |
| Observed probe stack | 696 B | 664 B | −32 B |
| **Static + observed stack** | **25,728 B** | **25,344 B** | **−384 B** |
| Static + provisional 1 KiB stack reservation | 26,056 B | 25,704 B | −352 B |

Code and constants count toward SRAM. The stack is an observed watermark, not a
worst-case bound. M23 instructions execute on the M33 QEMU model for this witness;
it does not measure 16 MHz M23 timing. Platform, interrupt and device integration
costs remain outside this numerical-core image. The estimator remains above10KiB.

## What is shared

Previously `qr_insert()` and `history_insert()` each implemented the same pivot,
hypot, rotation and trailing-row update loops. They differed in coefficient
storage. `shared_insert()` now implements the loop once, with a fixed mode for
each invocation:

- Local inference: directly read/write binary64 coefficients.
- History: read/write the original six-byte encoding, rounding to37 significant
  binary digits on **every write**, then read it back for the same finite check.

There is no new table, persistent state, registry, factor copy or scratch row.
The caller still owns its existing factor and destructively updated input row.
The loop is marked `noinline,noclone` to prevent compiler specialization from
recreating two bodies. A variant explicitly sharing the storage accessors linked
to the same static size; it is retained as a control, not an additional saving.

## Boundary contract

Valid callers supply disjoint factor/row buffers of the declared extents. The
local factor is double-aligned; packed history can be byte-aligned. The integrated
widths remain17 and34. Calls retain the existing serialized-owner and scratch-lifetime contract.

Each iteration preserves this sequence:

1. Read diagonal and row element; compute the original hypot; reject nonfinite h.
2. If h is zero, skip exactly the same packed triangular span.
3. Compute c and s from the unrounded h; write the diagonal; read it back and
   reject if its stored representation is nonfinite.
4. Read the old coefficient and row element; write the rotated coefficient;
   update the row from the **old** coefficient; check stored coefficient then row.

Thus the represented update, rounding points and partial-mutation boundaries
are unchanged. In exact arithmetic it is the same orthogonal insertion. Finite
floating-point parity is tested with the existing `-fno-fast-math` and
`-ffp-contract=off` settings; this extraction is not a new lifetime rounding proof.
Higher-level invalidation and adapter quarantine are retained. Failed partial
updates are not exposed as valid evidence or silently repaired by a refit.

Compiler-produced NaN sign/payload bits are not part of the failure contract.
Independent stress tests found five already-rejected exceptional cases with
only such differences. Status and every non-NaN byte agreed. No such difference
occurred in that probe's finite-input cases. We do not claim universal byte
identity for rejected NaN-containing buffers.

## Evidence

- Parent direct controls: **8,920 paired insertions**, including135 matched
  failures; all tested status, stored-factor and modified-row bytes identical.
  Canaries stayed intact, including byte-unaligned packed storage. Widths0,1,2,3,
  17,34; scales1e-300 through1e300; zeros, signed zeros, NaNs, infinities, packed
  rounding overflow and late row overflow were covered.
- Independent ASan/UBSan probe: **4,800 cases**, including1,299 matched rejections,
  widths through94 and exact allocation extents; no sanitizer diagnostics.
  NaN-representation-only differences are recorded separately as described above.
- Independent mathematical check: after500 well-scaled rows, binary64 factors
  satisfy the retained Gram identity with relative error below2.8e-15.
- Quarantine controls: a late history failure after a valid local update poisons
  both adapters, invalidates inference, and blocks query, refit and further input.
- Paired target execution: both return status0, with696/664B stack watermarks.
- Two fresh one-hour streams at50Hz with48-bit history, embedded load7 and noise
  seeds1100/1101: each arm accepts all59 scheduled refits per case. Checked
  endpoints and marginal SDs match exactly every16samples. This does not claim
  full covariance/state byte identity, calibrated coverage or lifetime behavior.
  Truth is confined to the plant and reporting; the public prior is unchanged.

`qualification001` passed the initial controls; `qualification002` added named
finite-overflow assertions; `qualification003` additionally checks quarantine.
These are additive test revisions with no implementation changes between them.
The reviewer refined the exceptional-input comparator to distinguish NaN payloads;
that also did not change the implementation. Large generated artifacts remain
ignored; source, compact receipts and independent review are retained.

See the [receipt](../../provenance/qr_sharing_001/receipt.json) and
[independent review](../../provenance/qr_sharing_001/review_r1.json).

## Reproduction

From this worktree, use new output directories:

```bash
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.qr_sharing_001.target \
  --variant shared_loop --out experiments/qr_sharing_001/my_target
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.qr_sharing_001.target \
  --variant shared_loop --execute --out experiments/qr_sharing_001/my_stack
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.qr_sharing_001.qualify \
  --out experiments/qr_sharing_001/my_controls
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.qr_sharing_001.stream_test \
  --campaign /path/to/compatible/campaign --hours 1 \
  --out experiments/qr_sharing_001/my_stream
```

These drivers are isolated experiments, not a production cache or campaign option.
The shared loop adds storage-mode dispatch while retaining the same floating-point
operation counts; target CPU impact remains unmeasured. The next size candidate
is sharing forward/transposed triangular solves for fit steps and scalar variance,
with the shared QR variant as the baseline and the same total-memory accounting.
