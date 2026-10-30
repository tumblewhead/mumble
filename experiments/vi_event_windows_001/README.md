# VI event windows and explicit measurement faults

96 four-hour replay arms complete, each using720,000observations at50Hz followed
by a separate30-minute prediction interval. Event alignment helps the lower-noise
multiscale control, but does not reliably improve the original charge/discharge
streams. Keep the production fixed16/Gaussian defaults. The sparse scheduler and
measurement mixture remain separate experimental candidates.

[Plan](plan.json), [iteration rationale](iteration002.json),
[compact results](summary.json), and [validation](qualification.json) preserve
both the first attempt and the revised design. The original production solver,
physical model, calibration, history backend and saved owner results are unchanged.

## What was tested

The first comparison uses the same four-hour prefixes as the uncertainty audit:
cellA, CC/CV charge-discharge,20mV voltage noise, seeds1000 and1006. A separate
control uses cellB, balanced multiscale pulse/rest input,2mV noise,seed2000.
The latter input is generated with the existing independent scalar plant,
including the same Arrhenius parameter laws, varying exogenous temperature and
ADC quantization. All reference parameters are stationary. The comparison changes
cell, load and noise together, so it does not isolate which causes the different
outcome. It is not a coverage or aging qualification.

The detector uses measured I and V only, plus public prior RC time scales.
Each24-record candidate has9 possible splits,8..16. It removes an intercept and
linear trend for matching, then normalizes each waveform. Current is compared
with a step; voltage with the opposite-signed instantaneous or first-order
response at the three public prior tau values. Joint score is the product of
signed channel correlations, maximized over response shape. It is a routing
score, not a probability or an additional likelihood. Raw values, amplitudes,
temperature, intervals and all observations still enter estimation unchanged.
Temperature affects the physical estimator; it does not adapt this initial
matched-filter bank. Known sample intervals set template time, not a35Hz constant.

Attempt001 retires two blocks per24-record tile. Controls are fixed16, fixed12,
current-only boundaries and displaced VI splits with identical length histogram.
It increases fit count from45,000to60,000. It worsens original-noise capacity
endpoints on all three streams. The short execution pilot initially sees only
constant current and therefore cannot establish event-detection benefit.

Attempt002 preserves16-record blocks in steady regions. Around changing current,
a24-record lookahead selects an8..16record block and advances by that selected
length. Candidate windows overlap; committed likelihood windows never overlap.
No measurements are skipped, no match score is added as evidence, and the prior
appears once. A deterministic shuffled-length control preserves total records,
fit count and length histogram but removes deliberate event alignment. That
control is offline, not a deployable scheduler. Sparse VI uses45,169–45,761tokens
on the original streams, versus45,000baseline tokens.

Both designs are bounded-horizon step-response matchers. They do not cover full
slow relaxation, arbitrary token grammars, current-sensor faults or timing jitter.
Current is exact/quantized in these harness streams; voltage need not improve
current-edge localization. A floating-point zero-energy check is the only
fallback threshold; no correlation acceptance cutoff is tuned against truth.

## Results

Final signed errors on original-noise inputs, using the ordinary Gaussian model:

|Stream|Fixed16 Q (%)|Sparse I Q (%)|Sparse VI Q (%)|Fixed16 SOC (pp)|Sparse VI SOC (pp)|
|---|---:|---:|---:|---:|---:|
|A,CC/CV,20mV,1000|+0.04574|+0.13210|+0.23288|+0.02474|+0.08827|
|A,CC/CV,20mV,1006|+0.60089|+0.55185|+0.59459|+0.17525|+0.17126|
|B,multiscale,2mV,2000|+0.45529|+0.09138|+0.19594|−0.15591|+0.00532|

For the multiscale stream, sparse VI also reduces final-hour maximum absolute
errors: Q0.56705%→0.23581%, SOC0.16478pp→0.01797pp. Thus its benefit is sustained
within that last hour, not solely a favorable endpoint. The shuffled schedule
finishes near the baseline, atQ+0.45969%,SOC−0.15858pp. Current-only alignment is
competitive and produces better Q here, but its SOC endpoint is+0.03823pp.
We cannot claim a consistent advantage from adding the voltage channel.

On seed1000 sparse VI worsens both final and final-hour errors. Seed1006's final
Q error changes little and remains about13.5local standard deviations from truth.
The shuffled schedule can itself produce large gains or losses on those noisy
streams, confirming that path-dependent grouping remains a major concern.

The same future30minutes are predicted without assimilation. On original-noise
inputs, sparse VI's joint predictive NLL improves relative to fixed16 by30.32,
6.89and6.47for seeds1000,1006and2000, respectively. This includes full local
cross-time covariance via a low-rank calculation. Improved voltage prediction
can coexist with worse Q/SOC estimates; it is not a substitute for state accuracy.
The mixture arms' covariance is a local surrogate, so these are not exact
mixture predictive probabilities. The two original fixed16 endpoint messages
match the previous uncertainty audit byte-for-byte across all273values.

## Fault handling is a separate experiment

For every stream, a separate RNG injects additive voltage faults at probability
0.001. Their SD is sqrt(20²−1) times the reported ordinary measurement SD, giving
an approximately20-times broader total noise component. These are explicit
synthetic telemetry faults, not characterized ADC bit errors. They are added
post hoc: recorded current and charger feedback remain unchanged. Fault labels
are available only to scoring, never detector/estimator inputs. Future holdout
observations retain their original noise without these injected faults.

The alternative likelihood is

```
p(V|prediction) = (1-epsilon) N(prediction,sigma²)
                + epsilon N(prediction,(20 sigma)²), epsilon=.001.
```

These values are declared test assumptions, not parameters fitted using truth.
At standardized residual r, let p be the ordinary-component responsibility and
w=p+(1-p)/400. The exact NLL derivative is w*r. Fitting uses the exact mixture
cost and gradient with a positive frozen-responsibility GN/EM precision. The
history token matches the mixture value and gradient at its anchor, including
the normalization correction. That precision is not the observed mixture Hessian,
and the committed Gaussian token is not an exact mixture posterior. All samples
retain nonzero likelihood weight and their original physical transport.

Fixed16 final Q error under injected faults:

|Seed|Gaussian (%)|Mixture (%)|Injected faults|
|---|---:|---:|---:|
|1000|+1.27578|+0.03056|702|
|1006|+1.99042|+0.52853|796|
|2000|+0.42239|+0.51413|766|

This is useful protection on the two high-noise owner streams, but not a universal
endpoint improvement. On the multiscale stream the sparse VI+mixture arm improves
fault-contaminated Q from+0.58239%to+0.17790%, and SOC from−0.01751pp to+0.00368pp.
On original-noise fixed16 data, the mixture changes Q endpoints to+0.05884%,
+0.59453%,+0.44623%; it does not solve the existing history bias. Seed1006's
fault-contaminated fixed16 mixture result still misses truth by about12local
standard deviations. Do not promote this as calibrated uncertainty or a safe
rule for rejecting unfamiliar aging responses.

## Resources and validation

- Existing C context:19,416B. A separate24-record raw detector buffer adds960B,
  totaling20,376B before detector scratch, metadata and stack. Buffer sharing is
  only a potential optimization, not implemented or certified.
- The robust token adapter adds an explicit640B temporary row array on stack,
  plus scalar/compiler overhead. Total embedded stack has not been measured.
- At50Hz,24records span0.48s. Detection can require observations up to16records
  beyond an8-record selected block, adding up to0.32s after that block's endpoint.
- Ordinary C replay takes about1.0–1.3host seconds per4h stream; mixture replay
  about2.0–2.4s. These exclude input generation, Python scheduling, scoring and
  future prediction, and are single measurements rather than timing benchmarks.
- Vectorized tiled detector generation takes about0.25–0.29s for the owner
  streams. Python sparse I+VI scheduling together takes about4.8–5.6s there and
  1.6s on the multiscale stream. It is not a profiled C/M23 detector.
- All96four-hour arms complete.55targeted unit/integration tests pass, including
  original-Gaussian byte parity, variable-window ownership and interval checks,
  invalid-schedule rejection before mutation, exact mixture gradient, token
  value/gradient agreement, and step polarity/baseline invariance.

No production defaults change. The result supports testing sparse alignment and
sensor-grounded robust likelihoods independently, with boundary-phase/noise and
model-mismatch controls before promotion. It does not replace the need for
history that can be re-evaluated when uncertain parameters move.

## Reproduction and local plots

From the worktree root, choose a NEW output directory:

```sh
python3 -B -m experiments.vi_event_windows_001.run \
  --run /home/easy/proj/mumble/experiments/foster_campaign_001/run_bounded_20261030_185906_868310 \
  --out /tmp/mumble_vi_repeat001 --hours 4 --future-minutes 30 \
  --seeds 1000 1006 --schedules fixed16 sparse_current sparse_vi sparse_displaced
```

Both original/fault conditions and Gaussian/mixture likelihoods are default.
No existing output directory is overwritten. `generate_control` creates the
separate4.5h cellB/multiscale stream; see its source for the declared settings.

Local-only plots:
[seed1000](analysis001/errors_seed1000.png),
[seed1006](analysis001/errors_seed1006.png),
[seed2000](analysis001/errors_seed2000.png).
They preserve per-bin error extrema and use symmetric-log axes with a shaded
±0.5band. Compact receipts and sources are retained in Git; generated arrays,
compiled libraries and plots remain local. Original attempt sources are archived
under `attempt001/experiment_source_snapshot/` before the second iteration.
