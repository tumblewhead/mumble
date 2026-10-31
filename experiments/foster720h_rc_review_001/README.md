#720-hour owner run: RC offsets, oscillation and stimulus hypothesis

Read-only review of `run_20261030_221410_953809`, especially case0003(seed1103).
[Receipt](attempt001/review.json) records original small-file identities and saved
C-source verification. No fit was rerun and no original results were modified.

This run uses the **legacy hysteresis chart**, source revision c9571cf, not the
bounded-hysteresis mainline baseline. Six cases complete720h in both encodings;
cases0004/0007 stop around7minutes with model-domain failures. Their partial
endpoints are excluded from the completed-seed bias comparison.

Among the six completed seeds, tau1 is high in4/6; R2 is low in6/6; R1 is low
in3/6; R3 is high in4/6. Thus the proposed directional bias exists for some
coordinates, but is not a uniform resistance underestimate. Case0003 is unusual:
its two fastest poles collapse to much shorter time constants.

|Quantity at25C|Plant|Case0003 final|
|---|---:|---:|
|R0(ohm)|0.100|0.044472|
|R1(ohm)|0.040|0.022644|
|tau1(s)|0.050|0.010757|
|R2(ohm)|0.080|0.066143|
|tau2(s)|0.500|0.036691|
|R3(ohm)|0.120|0.206834|
|tau3(s)|5.000|2.875137|
|R0+R1+R2+R3(ohm)|0.340|0.340094|

Despite those individual errors, total settled resistance is within0.0276%.
All six completed seeds recover that sum within0.045%. Case0003's ohmic and
summed-RC voltage errors are almost perfectly anticorrelated(−0.99889) in the
sampled final24h: each is about1.79mV RMS, while the complete reconstructed
voltage error is0.143mV RMS. SOC and hysteresis voltage errors also compensate.
This directly demonstrates parameter compensation, not correct branch recovery.

Effective-parameter oscillation follows the declared hourly17–33C Arrhenius
cycle: dividing effective by reference parameters reproduces the known thermal
factors to1.1e-16. The25C reference parameters have much smaller late variation.
The roughly4.8h spectral peak in SOC error follows charge/discharge cycling;
SOC error correlates−0.999985with true SOC over the sampled final24h. Its amplitude
is consistent with accumulating a small capacity error across the SOC excursion,
not a rapidly growing RC instability. FFT period resolution is limited by the
24h inspection interval; it is not an exact cycle-length estimate.

Case0003 finishes atQ+0.1930%,SOC−0.02308pp. A regular10.24s sample of the final48h
hasQ errors0.1930–0.2010% andSOC errors−0.07357to+0.07189pp. Assimilated voltage RMS
against noiseless plant output is0.138mV, versus0.0080mV for case0002. These are
sampled summaries, not full-trace extrema or independent prediction scores.
Q truth misses the local3SDinterval at every sampled late output; SOC misses
at98.36%. Both encodings agree closely, so coefficient quantization is not a
credible explanation for these large offsets.

The aggregate match does not make the RC model interchangeable with the plant.
A diagnostic0.12Astep at25C produces about−4.43mV response error after1s with
case0003's final RC parameters, even though its long-time drop is nearly right.
Its tau1 is only0.54sample intervals at50Hz, approaching instantaneous-response
confounding with R0. No claim of structural nonidentifiability follows: stimulus,
measurement noise, nonlinear optimization and irreversible local-history
approximation can all contribute. The exact likelihood has not been profiled
here to distinguish them.

The user's proposed embedded-system workload is a useful matched comparison:
semi-Markov operating states with sensible dwell durations and transitions,
independent load/noise seeds, and the same cell/prior/estimator for each load
comparison. MCU,radio,LED and flash activity should be represented at the battery
input. Subsample circuitry needs explicit acquisition/averaging treatment;
initial tests should use resolved activity envelopes and state that limitation.
A richer stimulus is a hypothesis test, not a guaranteed fix for history bias.

Local figures: [oscillation](attempt001/oscillation.png),
[aggregate RC response](attempt001/RC_response.png). Generated plots stay local.

Reproduce into a NEW directory:

```sh
python3 -B -m experiments.foster720h_rc_review_001.review \
 --run /home/easy/proj/mumble/experiments/foster_campaign_001/run_20261030_221410_953809 \
 --out /tmp/foster720h_review001
```
