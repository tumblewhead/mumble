# Original-origin tangent comparison with the new RC bank

Use `--history compare-bank-tangent` for `tangent64` versus `bank_tangent`.
Use `--history bank-tangent` for only the new bank tangent. Both maintain evidence
in the original prior coordinates; outgoing Gaussian readouts are never new
priors. The older `compare-bank` mode remains the field64/rolling-feedback control.
The new mode requires constant 25 C. Mainline default remains unchanged.

```sh
python3 -B -m experiments.foster_campaign_001.run \
  --history compare-bank-tangent --hours 24 --sample-rate-hz 50 --jobs 2 \
  --cells B --loads embedded --load-seeds 7 --seeds 1100 1101 --noise-v .002 \
  --temperature constant --recording compact --summary-bins 2000 --checkpoint-hours 1
```

Repeat with 35 or 100 Hz and fresh output directories. These are exploratory
rate runs, not physically matched-noise experiments: identical seeds at different
rates do not identify identical noise in physical time. D001 remains an older
feedback-control dataset. Do not overwrite it or pool it as an independent
replicate of the new estimator.

The bank tangent is a transparent Python/NumPy reference. Its fixed-anchor
17-column QR contains the original prior once and the joint linearization of
all observations. Scheduled full bank refits reset that linearization using the
same prior. Per-block response transport and the full 94-column history factor
are retained for future refits. No old rolling fitter is called. It deliberately
updates the dense history factor every block, so it is slower than the fused C
tangent and is not a CPU optimization. The bank still uses TaylorH2; tangent64
uses H5, so comparisons do not isolate RC representation alone.

Compact recording, plots, parallel cases and debug replay use the existing
runner. Checkpoints retain the bank factor, free/forced/H/path states, tangent
anchor and factor, and publication context. Unlike the native tangent, this reference does not attempt an emergency full
refit on readout-domain failure. Invalid accepted-step computations
quarantine the arm rather than publish a stale result. Statistical widths remain
provisional local Gaussian precision, without a certified deterministic bias floor.

The bank packed history factor remains 35,720 B plus 936 B response state.
The reference additionally stores a 2,312 B dense tangent factor, 12,032 B
feature-Jacobian cache, features/anchor, prior, output context and substantial
QR/solver workspace. This is not the 10 KiB target or a complete memory budget.
