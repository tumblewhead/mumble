# Field-assisted desktop mainline promotion

The campaign now defaults to `--history joint-field --encoding float64`.
The optimized C rolling estimator receives periodic whole-history joint-field
replacements using the original prior once. The validated numerical algorithms,
60-second requested refresh cadence and failure behavior are unchanged.

The [720-hour review](../rolling_field_720h_20261031/README.md) is the primary
promotion evidence: eight stationary-cell cases, both estimator arms, sustained
field Q/SOC accuracy and substantially improved RC inference. Low-noise local
uncertainty remains overconfident; this is a better desktop baseline, not a
coverage, aging or firmware qualification.

Use `/home/easy/proj/mumble/.worktrees/mainline-foster` for mainline runs:

```bash
python3 -B -m experiments.foster_campaign_001.run \
  --hours 720 --jobs 4 --sample-rate-hz 50 \
  --cells A --loads embedded --load-seeds 7 8 \
  --seeds 1100 1103 --noise-v 0.002 0.02 \
  --recording compact --summary-bins 2000 --checkpoint-hours 3
```

Add `--history compare` for both field and original rolling arms. Use
`--history rolling` for the original float64 estimator,
`--history rolling --encoding both` for its encoding comparison, or
`--history rolling --backend python` for its Python reference. Incompatible
field options fail with a message explaining how to select the original mode.
Existing scripts that explicitly select float32, both encodings, Python or the
legacy hysteresis chart must now also select `--history rolling`.

All 66 targeted tests pass. Promotion adds checks for default selection,
bit-identical default/explicit-field output, and clear rejection of incompatible
options. Existing control tests now explicitly request their intended history
and encodings. The initial test failure was an old parity fixture looking for
the previous default arm's filename; its explicit-mode correction and both logs
are preserved in [receipt.json](receipt.json).

An additional four-hour default cell B / balanced-cycle / 35 Hz run completed
with all plots and 237 of 238 refreshes accepted; the one round-limit rejection
recovered on subsequent attempts. A matched comparison gives capacity error
−1.89% for field versus +1.67% for rolling, both outside the 0.5% target. SOC
errors are +0.0555 and −0.0595 percentage points. The single-arm and comparison
field messages are bit-identical. This limits any universal superiority claim
and keeps weak-stimulus capacity estimation on the roadmap.

The original owner-run environment at
`/home/easy/proj/mumble/.worktrees/rolling-joint-field` remains unchanged so its
compact checkpoints can still be replayed with the recorded sources. New
mainline runs retain snapshots, checkpoints and all existing plot families.

Only source, tests, documentation and small receipts are promoted. Generated
campaign streams, compiled libraries, checkpoint files and figures remain local.
