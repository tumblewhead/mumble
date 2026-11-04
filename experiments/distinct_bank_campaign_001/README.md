# Distinct-bank campaigns using the existing runner

The existing Foster campaign runner now accepts `--history distinct-bank` and
`--history compare-bank`. The first selects the experimental N13e RC bank;
the second runs the mainline `field64` control and `distinct_bank` on the same
observations. The default remains `joint-field`. This change is on the experiment
branch, not promoted to mainline.

Run from the worktree root:

```sh
python3 -B -m experiments.foster_campaign_001.run \
  --history compare-bank --hours 4 --jobs 2 \
  --cells B --loads embedded --load-seeds 7 --seeds 1100 1101 \
  --noise-v .002 --sample-rate-hz 35 \
  --temperature constant --temperature-mean-c 25 \
  --recording compact --summary-bins 2000 --checkpoint-hours 1
```

Omit `--out` for a timestamped directory printed by the runner, or choose a new
output directory. Use `--history distinct-bank` for a single estimator arm.
The current implementation requires **constant 25 C**; the CLI rejects variable
temperature before creating a run, and the backend rejects non-25 C rows before
advancing either history. Aging remains unimplemented.

The familiar controls are reused directly:

- `--hours`, `--sample-rate-hz` (dt=1/Fs), and `--jobs N` for independent cases.
- `--cells A B` or `--cell-file`; independent noise `--seeds` and `--load-seeds`.
- `--loads embedded`, `charge-discharge`, and the existing load profiles.
  CC/CV options such as `--charge-c 2 1 1.5` and `--discharge-c .2 .45 .7` remain
  harness settings. Load seeds apply to the embedded workload only.
- `--noise-v .002 .004` crosses noise levels with the selected cells/loads/seeds.
- `--field-refresh-seconds 60` controls full-history refits, rounded up to a
  16-record boundary. Rolling outputs remain every16 samples plus a final partial
  window. Every original observation contributes once to bank history.
- `--recording compact`, `--summary-bins`, and `--checkpoint-hours` retain
  bounded-resolution min/max/mean plots plus periodic full-state checkpoints.
  This reduces telemetry storage, not estimator inputs or simulated workload.
- Individual signals (V/I/T), true and estimated SOC and other states, parameters,
  parameter errors, voltage-fit errors and capacitances; automatic all-case
  overlays in `case_summary/`, with distinct seed/arm labels and colors.
  Comparison mode also produces per-parameter comparison pages.

Debug replay uses the same existing interface, for example after a four-hour run:

```sh
python3 -B -m experiments.foster_campaign_001.replay \
  /path/to/run/case_0000 --debug-start-hour 1 --debug-stop-hour 1.05 \
  --out /tmp/mumble-bank-debug
```

Replay restores the complete joint bank factor, three free and forced RC banks,
H/path states, pending observations, solver start, rolling context, plant,
controller and random states. It checks map, source, binary and host identities.
Use the same source revision and runtime as the original run; replay is not a
portable firmware checkpoint format. A new output directory is required.

The likelihood uses the original public prior and fixed centres. A successful
bank refit replaces the rolling joint distribution at the same prefix; it is
never multiplied by that prefix's rolling posterior. Between refreshes, this
mode uses the existing C rolling estimator. Rejected refits leave that committed
distribution intact and appear in `field_history` audit counts and reasons.
Completion means the stream completed; inspect those refresh counts as well.

This comparison changes both RC and H representation: the bank uses the existing
TaylorH2 response, while mainline field uses its collocation response. It is an
end-to-end comparison, not an isolated attribution of gains to RC alone.
Marginal widths remain provisional local Gaussian diagnostics; the supplied
symbolic bias-aware interval and uniform certificate are not implemented here.
A plot or a completed run cannot establish coverage or lifetime reliability.

Memory is still over budget: W94, a35,720 B packed bank factor and936 B response
state, plus the C rolling context, prior,4096-row buffer, tables, solver and QR
workspace. The backend also reports transaction-backup storage. This integration
adds usability, not a smaller estimator or M23 timing qualification. Large runs
still process every sample and may reveal known H approximation/support limits.

Targeted checks live in
`experiments.distinct_bank_integration_001.test_campaign`; the earlier bank
mechanics tests remain in `test_bank`. See the
[campaign receipt](../../provenance/distinct_bank_campaign_001/README.md).
