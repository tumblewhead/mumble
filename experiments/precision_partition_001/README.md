# Response/history precision partition

Base `04141f8`; branch `experiment/precision-partition-001`.
This experiment follows the binary32-history stagnation counterexample. Three
collector candidates separate response calculation/storage from growing history.
No candidate is promoted. The four capability-profile defaults remain unchanged.

## Measured local SRAM

All code and constants count as SRAM. Stack is an observed 512-sample QEMU witness,
not a worst-case bound; IPC, platform drivers/ISRs and recovery remain excluded.

| Collector | Static | Observed stack | Total | Decision |
|---|---:|---:|---:|---|
| Previous double arithmetic/history48 | 13528 | 424 | 13952 | Keep baseline |
| Float response + double QR/history48 | 15448 | 360 | 15808 | Larger: both arithmetic runtimes |
| Float response storage + double arithmetic/QR | 13808 | 432 | 14240 | Larger: conversion/comparison overhead |
| Float response + paired-float Gram | 10936 | 216 | 11152 | Invalid weak-direction information; also exceeds budget |

The mixed collector's bank allocation is4416B (versus4808B before), yet its code
cost outweighs that saving. The storage-only candidate has the same4416B bank;
its final link has no float add/subtract/multiply/divide helpers, but conversions,
comparisons and access changes still outweigh storage savings. The paired Gram
bank is5460B because595 eight-byte coefficient pairs replace3570B history48.
These are architecture measurements, not parameter-fit or coverage qualification.

Supplementary first-pass measurements: mixed SOC static15680B; mixed with shared
history local static11884B plus3570B external. They are exploratory and have no
new shared-placement execution/IPC qualification. Neither closes10KiB.

## Construction and contracts

`mixed`: immutable config, inputs,93 response values and34 feature values are
binary32. History insertion, math used by QR, and the595 packed48-bit entries are
unchanged. One272B union serves the float feature row and double QR row. Features
expand backwards with memcpy: for j descending, the double destination starts at
8j, while unread float values occupy offsets below4j. Thus expansion cannot
clobber an unread value. A float value converts exactly to double; the extra history
precision cannot recover information already lost in response/feature rounding.

`storage_only`: float config/input/response storage, but explicit double operands
and intermediates in row formation and state calculations, followed by rounding
back into response storage. It retains the original double QR and history48.
Early storage/storage002 builds accidentally retained several float intermediates;
storage003 and final_storage fix those promotions. Originals remain local.

`paired_gram`: same binary32 stream as the previous float collector. A coefficient
is stored as hi+lo; a two-sum-style correction carries small incoming additions.
The statistic is the normal matrix G=sum(phi phi^T), NOT a square-root factor.
The595 entries are upper-triangle Gram coefficients, including the response column.
They cannot be handed to the existing square-root decoder. Products round to
binary32 before compensated addition. This is a rejected diagnostic, not an API
migration for campaigns.

All variants retain ordered samples, actual dt, stationary25C/affine-OCV scope,
new-origin-only initialization and latched failure. No evidence replay or posterior
reinsertion is added. Failures after partial history insertion have no rollback.
No history forgetting or noise inflation is introduced. Unknown shared-SRAM access
and host lifecycle contracts are unchanged from the prior profile experiment.

## What the tests establish

- 32768 mixed updates match separate float-row generation followed by out-of-place
 double conversion and original QR, byte-for-byte in history and response.
 UBSan and invalid-dt/refusal controls pass.
- 20 million identical unit rows: mixed QR has relative information error1.376e-9
 and paired Gram reports exactly20 million. This repairs the tested scalar stall,
 not all possible lifetime or matrix failures.
- A single weak-direction control rejects paired Gram immediately (proof below).
- A separate32768-sample stream, using identical float-representable V/I/T/dt/noise
 across lanes, completes with relative Gram Frobenius differences5.124e-6 mixed,
 1.227e-5 storage-only, and5.124e-6 paired Gram versus the double baseline. These
 aggregate metrics do not validate weak directions; the counterexample matters
 even though the aggregate norm looks good. No parameters are fitted by this test.
- Independent review checks expansion, promoted storage formulas, linked runtime
 symbols, refusal and the negative-information counterexample.

## Why compensated Gram is rejected

Assume binary32 round-to-nearest, ties-to-even. Let d=2^-12 and let one exactly
representable feature row be x=(1,1+d). The exact Gram has rank one and gives zero
energy to v=(-(1+d),1). The squared second feature is1+2d+d²; d²=2^-24 is exactly
half an ulp here. Ties-to-even rounds it down to1+2d. Thus the stored Gram is

    [1,   1+d ]
    [1+d, 1+2d]

and v^T G v=-d²=-2^-24 < 0. Compensation of later sums cannot restore the product
term already rounded away in the first update. The independent control reproduces
this energy exactly. Square-root storage does not suffer this specific failure:
R^T R remains positive semidefinite in exact interpretation for any finite R.
This does not prove all square-root arithmetic error or uncertainty claims.

We do not patch this by flooring eigenvalues or adding an arbitrary ridge. An
exact-product accumulator might fix this example, but would still need conditioning,
finite-precision PSD and nonlinear-likelihood analysis; it is not implicitly safe.

## Decision and next mathematical target

Keep the existing binary64/history48 collector. Do not merge any trial into the
runner or replace the existing history format. Separating storage from computation
alone does not deliver savings on this soft-float target.

The next bounded experiment should retain square-root history and derive how to
carry small Givens-update increments without loading two complete arithmetic
runtimes. Candidate: a high/low square-root coefficient and increment-form update,
with explicit local error and representability bounds. All cross terms, weak
directions, rank deficiency and restart cases must be part of the contract before
size tuning. This is a proposal, not a proven solution. A hardware decision about
retained accessible SRAM remains a separate possible architectural lever.

## Reproduce

```sh
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.precision_partition_001.measure \
  --kind mixed --out experiments/precision_partition_001/my_mixed
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.precision_partition_001.measure \
  --kind storage_only --out experiments/precision_partition_001/my_storage
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.precision_partition_001.measure \
  --kind paired_gram --out experiments/precision_partition_001/my_gram
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.precision_partition_001.check \
  --mixed experiments/precision_partition_001/my_mixed \
  --gram experiments/precision_partition_001/my_gram \
  --out experiments/precision_partition_001/my_check
```

Use fresh directories. Add `--execute` to measure a separate stack witness. SOC is
implemented only for mixed/paired Gram; storage-only explicitly supports collector.
No full-profile precision change is available. Final measurement receipts capture
the effective compiler command including the injected double-subtraction wrapper;
earlier exploratory measurements omitted that injected argument in their metadata.
