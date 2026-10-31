# Rolling estimator with experimental joint-field refresh

Branch `experiment/rolling-joint-field-001` starts directly from main at
`b9731e89c7ef9ab969858fc969aecf1ac695b5db`. This branch adds an opt-in comparison
to the existing campaign runner. Mainline defaults remain unchanged.

## Run locally

```bash
cd /home/easy/proj/mumble/.worktrees/rolling-joint-field
python3 -B -m experiments.foster_campaign_001.run \
  --hours 720 --jobs 4 --sample-rate-hz 50 \
  --history compare --encoding float64 --field-refresh-seconds 60 \
  --cells A --loads embedded --load-seeds 7 8 \
  --seeds 1100 1103 --noise-v 0.002 0.02 \
  --recording compact --summary-bins 2000 --checkpoint-hours 3
```

This runs eight independent scenarios, each with two arms on identical samples:
`float64` is the unchanged C rolling estimator; `field64` adds joint-field
refreshes. `--history joint-field` runs only the experimental arm, while
`--history rolling` retains the original behavior and encoding options.
The field currently requires C, bounded hysteresis and `--encoding float64`.

Individual and combined plots include V/I/T, true and estimated SOC, other
states, reference/effective parameters, capacitances, and voltage/Q/SOC errors.
Compact recording preserves means and extrema in 2,000 bins without full raw
streams. The runner prints its output directory and final `summary.json` path.
For this 720-hour command, conservative uncompressed numeric planning is about
71 MB per case (about 568 MB across eight), before figures, source snapshots
and filesystem overhead; checkpoint compression usually reduces this.

Use the existing replay command from this same worktree/runtime:

```bash
python3 -B -m experiments.foster_campaign_001.replay \
  /absolute/path/to/run/case_0000 \
  --debug-start-hour 120 --debug-stop-hour 123 \
  --out /absolute/path/to/new_debug_directory
```

Checkpoints now include the field root, collocation state, original-chart warm
start, pending observations and bounded refresh diagnostics, as well as the C
context and harness state. Source/binary identities are checked before replay.
Do not change estimator/replay sources in this worktree while relying on it to
replay a long run; an archived-source environment is required after changes.

## Evidence ownership and state continuity

The C rolling estimator still consumes chronological 16-record windows with
the declared sample period. The experimental producer also advances a
fixed-origin response likelihood, retaining its QR root and state transport.
Each observation enters that field exactly once; at most 4,096 pending rows
are buffered for QR efficiency. No truth, plant state, load labels or seed
values enter the inference API.

At a refresh boundary, a deterministic local joint MAP/GN solver fits the
field plus the original public prior once. Its full joint initial-chart
uncertainty is transported analytically to the current boundary. The resulting
distribution **replaces** the rolling distribution for that same prefix.
It is not multiplied into the old rolling posterior. Stream counters, clock,
source identity and window chronology are preserved. Subsequent windows use
ordinary C rolling updates until the next refresh.

The refresh interval is a compute-scheduling choice, not forgetting, health
decay or an information threshold. At 50 Hz, 60 seconds rounds upward to
3,008 records (60.16 seconds) to align with complete windows. The same Fs
determines physical sample intervals and cadence conversion. History is not
discarded between refreshes. Static parameter estimates remain continuous-valued.

This is a fixed-origin, stationary-parameter field; it does not implement
arbitrary polynomial-map composition or battery aging. It demonstrates history
feedback without claiming those unresolved properties. Refreshes may correct
state and parameter means, just as ordinary inference updates do.

## Failure visibility and interpretation

Out-of-domain queries, unsupported native endpoints and unconverged fits do
not silently clip or modify the prior. A failed refresh leaves the committed
rolling distribution unchanged, records the reason and retries at the next
scheduled boundary. Failure of field accumulation or of the C estimator marks
the arm unresolved. A run marked completed means the sample stream completed;
it does not mean every refresh succeeded.

Inspect `arms.field64.field_history` in each case result or campaign summary:
`attempts`, `accepted`, `rejected`, `last_accepted_record`, `last_rejection` and
`status` distinguish successful refreshes from continued rolling fallback.
The CLI prints this object at case completion. Per-window stop counts also
include `field_refresh` and `field_refresh_unresolved`. Diagnostics are bounded;
debug replay reconstructs an interval if more detail is needed.

The field is degree 5 with the existing public-prior-centered log-rate domain.
No adaptive recentering is introduced. Local GN widths and the approximate
Laplace/GN log evidence are not calibrated coverage. Voltage plots use
assimilated endpoint fits, not withheld predictions. Prior studies found a
remaining likelihood-gradient defect at low noise; this integration does not
remove it. A successful long run is evidence about this experiment, not proof
of indefinite stability.

## Qualification and resources

[qualification.json](qualification.json) records source origins, hashes,
commands, tests, four-hour comparisons and debug replay. Tests cover unchanged
baseline behavior, original-prior replacement instead of double counting,
boundary guards, analytic transport derivatives, failure preservation, exact
full/compact agreement and exact replay with a partially filled field buffer.

All 63 targeted tests passed. Four newly generated four-hour cases completed,
with all 239 scheduled refreshes accepted per case. Final signed capacity errors:

| Load / noise seed | Rolling | Field feedback |
|---|---:|---:|
| Embedded, 2 mV / 1100 | +0.5040% | +0.0875% |
| Embedded, 2 mV / 1103 | +0.7888% | −0.0555% |
| Charge/discharge, 20 mV / 1000 | +0.0946% | +0.0047% |
| Charge/discharge, 20 mV / 1006 | +0.5598% | +0.0103% |

The embedded cases ran in parallel and produced all six individual plot families
and summary overlays. A 3.10–3.12 hour debug interval restored successfully from
the preceding checkpoint and produced both-arm plots. These short checks qualify
the integration mechanics; the owner's longer run remains to be evaluated.

The packed degree-5 field estimate remains 27,976 B plus 888 B live collocation
state. This desktop adapter additionally uses a 19,416 B C context, a 163,840 B
pending-observation buffer, a dense 53,792 B root, projection tables, priors,
solver/QR workspace and Python overhead. These are not a complete SRAM total
or an M23 deployment claim. Checkpoint sizing includes the extra field arrays.

Source imports are limited to `field.py`, `probe.c` and `numerics.py` from the
prior experiment; bulk data and unrelated review/design commits were not
merged. Campaign outputs remain ignored and local.
