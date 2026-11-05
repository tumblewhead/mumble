# Remove obsolete spline metadata

The specialized cardinal-polynomial core no longer uses the old full spline
map pointer, knot pointer or knot-spacing scalar (`map`, `knots`, `hu`). They
occur only in the inherited model declaration and binding validation. The
candidate removes these fields and their checks from its specialized ABI.
It retains `projected_map`, all other pointer checks, and configuration/range/
finite/sample checks. The original model and Python adapter are unchanged.

This is an ABI change. Every caller of this candidate must compile against its
new declaration. The existing ctypes model/context structures MUST NOT load it;
this experiment uses freshly compiled C callers. No campaign option or mainline
default has been changed. Removed fields are absent from the new contract rather
than silently accepting malformed instances of the old model.

## Ownership argument

Full response weights use the fixed cardinal polynomial, not the removed map.
Reduced likelihood weights use retained `projected_map`. No calculation reads
`knots` or `hu` in this specialization. Removing those unused values does not
change any represented response, feature, prior or uncertainty calculation.
All retained pointers still require valid extents/lifetimes. Configuration arrays
remain immutable; carried response arrays remain mutable under one serialized
owner. This is not a generic spline-interface optimization.

## Measurements

Same observable-input harness and compiler, based on commit e464a01:

| Resource | Baseline | Compact |
|---|---:|---:|
| Text |16688B|16704B|
| Constants |1016B|996B|
| BSS |6976B|6960B|
| Vectors |28B|28B|
| Alignment |4B|8B|
| **Static total** |**24712B**|**24696B**|
| Separate target execution stack watermark |664B|664B|
| Static plus provisional1024B stack allowance |25736B|25720B|

The M23 model structure shrinks48->28B, while core shrinks2376->2360B because of
padding. The fixture allocation falls6912->6896B. Both target execution probes
return status0. Stack is an observed fixture watermark on M33 QEMU running M23
instructions, not a worst-case bound for the observable-input harness or final
silicon. Synthetic interface slots count in the static total.

The final saving is **16B**, not the sum of source-field sizes. More text and
changed padding offset part of the data/constants reduction.

## Checks

Freshly compiled baseline/compact host executables emit byte-identical1,308,190B
transcripts covering256 support/feature points (34 reduced feature rows),256
streamed samples,8refits and4096 scalar queries, including each return status.
Final history bytes, carried response and joint factor also match. All seven
retained model pointer omissions reject in both versions. The comparison does
not assert every scalar query succeeded; statuses and output sentinels are
included. The parent control uses reduced features; independent review also compared all94
full-feature rows, producing identical3,458,590B transcripts. Full-bank endpoint
transport is exercised by scalar queries.

Independent review reran the comparison and checked ARM layouts and generated
source closure. This is isolated acceptance; long campaigns, Python ABI migration,
timing, lifetime accuracy and worst-case stack are not qualified.

## Reproduction

Fresh output directories are required:

```
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.model_metadata_001.target --variant compact --out experiments/model_metadata_001/new_target
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.model_metadata_001.execution --variant compact --out experiments/model_metadata_001/new_stack
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.model_metadata_001.check --out experiments/model_metadata_001/new_checks
```

The host check reads preserved baseline001 and compact001 generated cores and
configuration, so generate those named controls first in a fresh checkout.
See provenance/model_metadata_001/receipt.json and review.json. Next inspect
whether one immutable configuration reference can replace multiple retained
configuration pointers, with explicit caller ownership and measured code cost.
