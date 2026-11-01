# Fused tangent response, QR update and joint readout

The first optimization selected by the
[full study](../../provenance/tangent_development_001/full_study_review.json)
is implemented in the tangent campaign backend on
`implementation/tangent-fused-001`. The existing `--history field-tangent` and
`--history compare-tangent` modes use it in this worktree. Field64, the campaign
default and mainline are unchanged.

The C entry point validates the whole input window and source boundary, then
generates each response row with the existing recurrence and folds it into the
existing QR factor in the original order. It reuses one row of existing scratch
instead of allocating a 16-by-82 lifted matrix. The same call computes the full
joint endpoint readout on ordinary windows. Python publishes from that reusable
output immediately; public query results still own their arrays by default.

No observation is skipped or reused as new evidence. The original prior, noise
normalization, joint root, state transport, domain checks, refresh schedule,
rejected-refresh handling and emergency recovery remain intact. A failed input
or update leaves the owned context/state unchanged; a failed readout retains the
new evidence for the existing recovery path. Irregular partial windows crossing
the field buffer boundary retain the previous response/flush/update ordering.

## Matched qualification

The [receipt](../../provenance/tangent_fused_001/receipt.json) binds sources,
commands, binaries and generated evidence. The comparison restores all 12
registered prefixes and processes 16,384 samples each. An isolated subprocess
in the frozen original worktree first validates the original replay binding and
exports a hash at every committed boundary. The in-process original adapter and
kernel, and the fused candidate, must both match every one of those hashes.

All **12,288 window boundaries / 196,608 unique samples** match bit for bit,
including carrier, factor, original-origin state, pending observations, noise
normalization, counters and refresh audits. The 36 forecast anchors therefore
have identical full joint messages and history geometry. The previous study's
deterministic forecasts are preserved; this optimization claims no accuracy gain
and does not rerun the 720 forecast tasks unnecessarily.

Five timing repetitions restore the complete starting state each time and
alternate reference/candidate order per window. Validation hashes, IO and
restoration are outside the timed region. BLAS has one thread.

| Matched host measurement | Original tangent | Fused tangent |
|---|---:|---:|
| Mean complete advance per 16 samples | 275.8 µs | 198.4 µs |
| Mean of the 12 per-prefix medians | 156.1 µs | 80.6 µs |
| Largest observed advance | 51.59 ms | 51.51 ms |

This is **1.39× throughput / 28.1% less host advance time** overall. Per-prefix
speedups range from 1.27× to 1.47×. Full-field solves and batch QR remain unchanged,
so refresh bursts limit the overall gain. These are matched measurements from
this run, not directly comparable clock-for-clock with the earlier owner run and
not Cortex-M23 cycle estimates.

The 51 targeted tests include native projection and joint uncertainty controls,
bitwise fused/unfused response/QR parity, zero and nonuniform intervals at
35/50/100 Hz, rejected input atomicity, query-domain recovery, output ownership,
nonfinite publication, irregular buffer overflow, fresh scratch accounting,
full/compact recording, checkpoint replay, and the proposed-load predictor.

## Storage and remaining limits

- Persistent native likelihood context remains **1,376 B**.
- Existing native workspace remains **5,880 B**; reusable fused scratch adds
  **3,360 B**, making explicit native workspace **9,240 B**. It is allocated
  before campaign storage accounting and timed updates.
- Ordinary windows no longer allocate the **10,496 B** lifted-row matrix or a
  fresh **888 B** live-state copy. The fused scratch contains trial state and
  joint output; do not count those as additional independent savings.
- Refresh work and the rare irregular-buffer fallback retain their allocation
  needs. The desktop 163,840 B raw batch and 53,792 B dense field matrix remain.
  The packed field factor alone remains 27,224 B in float64 / 13,612 B in float32.
- Host compiler reports an individual `ft_step` frame of 272 B and
  `response_rows` frame of 448 B. They can nest and exclude libm; neither is a
  complete stack bound or an ARM measurement.

The target still needs shared-history compaction and full target memory/timing
measurement. The shared uncertainty overconfidence, computational rate-box
support and low-SOC/power-path qualification remain open. No smoothing,
forgetting, variance inflation or reduced uncertainty readout is introduced.

## Reproduce

From this worktree, re-run the matched comparison in a fresh directory:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -B \
  experiments/tangent_fused_001/compare.py \
  experiments/tangent_development_001/run_20261031_204002_375373 \
  --out experiments/tangent_fused_001/local_comparison_001
```

`--prefixes case_0006_h3` and `--repetitions 3` select a smaller control. Original
run data and source worktree are read-only inputs. Qualification outputs remain
local and ignored; reviewed source and the small receipt are committed.

Normal campaigns require no new option:

```sh
python3 -B -m experiments.foster_campaign_001.run \
  --hours 4 --jobs 2 --sample-rate-hz 50 --cells A B \
  --loads embedded --load-seeds 7 --seeds 1103 --noise-v .002 \
  --history compare-tangent --recording compact
```

Existing checkpoints retain their original source/binary/runtime binding. Replay
old campaigns in their preserved worktree, not against the optimized sources.
