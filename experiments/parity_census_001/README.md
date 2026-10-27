# Parity mismatch census

This separate diagnostic implements the user-requested continuation through
finite output mismatches. The previous exact-parity attempt and its failure
remain preserved in `../fixed_prefix_shape_001/attempt001`.

The pass covers all 15,751 saved snapshots in the original 252,000-record
two-hour prefix. It starts from the public mean and commits original decoded
records using each saved accepted estimate. It performs no optimization, truth
scoring or original-recurrence node comparison.

Every snapshot is retained in `actual_snapshots.bin`. The analysis emits a
lossless `mismatches.csv.gz`, per-field counts and worst cases, ULP histograms,
longest mismatch runs, and fixed 15-minute summaries. Absolute SOC differences
are also reported in percentage points and voltage differences relative to the
existing 1-mV likelihood sigma. These are descriptive scales, not acceptance
tolerances or physical-truth errors.

The numeric/flag comparisons never correct carried state or abort the pass.
Structural failures still stop it: invalid or changed input, wrong order,
nonfinite data, unusable bank, failed commit/query, or resource exhaustion.
The diagnostic bank uses a distinct checkpoint magic and does not satisfy the
previous exact-bank identity gate.

Qualification passed eight unit tests, eight continuation/preservation checks
and three structural-failure cases. Injected tiny, signed-zero, flag and large
late differences were all reported through the final snapshot, with identical
reconstructed output and bank bytes. See [plan](plan.json),
[qualification](qualification/development001/receipt.json) and
[source review](source_review.json). Review is by the same assistant.

Qualified source must be published before this invocation:

```sh
python3 -B experiments/parity_census_001/census.py \
  --qualification experiments/parity_census_001/qualification/development001/receipt.json \
  --publication experiments/parity_census_001/source_publication.json
```

The exclusive reservation prevents accidental repetition. The actual census
has not yet run at this source checkpoint.
