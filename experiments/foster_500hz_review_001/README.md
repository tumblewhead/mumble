# Review of the eight-seed500Hz campaign

The saved run completes all sixteen arms with useful final Q/SOC estimates,
but it exposes severe RC-spectrum drift in seed5 and unreliable uncertainty
across all seeds. This is a review of existing evidence, not a solver rerun or
a repair. The exact source is
`experiments/foster_campaign_001/run_20261030_102748_571075`.

Settings:48 simulated hours,500Hz, cellA,20mV independent voltage-noise SD,
seeds5/6/7/500/600/700/54/321, both encodings. Charging capabilities are2/1/1.5C;
discharge alternates0.2/0.01/0.45/0.08C. Noise affects both observations and
measured-voltage charger decisions, so seeds also slightly change the stimulus
trajectory. Each case retires86,400,000 samples in5,400,000 tokens per arm.
No pending observations or failed arms are reported.

[review.png](review.png) separates the Q/SOC result from the RC failure using
logarithmic time-constant axes and distinct seed colors. It samples every minute
plus the final endpoint; it is not a min/max envelope. Full-run metrics below
come from the original complete summaries. [review.json](review.json) records
the calculations, selected source hashes and event chronology.

## State estimates and physical parameter estimates separate

All binary64 final Q errors are between−0.0723% and+0.1493%; final SOC errors
are between−0.1269 and+0.01413 percentage points. Over the entire run, including
startup, both application bands are met for92.21–96.39% of reported boundaries.
These fractions do not establish uninterrupted long-term accuracy or aging.

Seed5 (`case_0000`) ends with:

| Reference-temperature quantity | Plant truth | Estimate |
|---|---:|---:|
| R0,ohm |0.100|0.297082|
| tau1,s |0.050|0.000797|
| tau2,s |0.500|2268.307|
| tau3,s |5.000|2268.424|
| H,V |0.015|0.017636|

The two slow poles nearly coincide: their time constants differ by only0.1174s,
about0.0052%. The original decade spacing is lost. The fast time constant falls
below the2ms sample interval. Ordering remains legal because the estimator uses
positive cumulative gaps; ordering does not guarantee separation or correctness.
The plant still uses the declared0.05/0.5/5s reference constants. Temperature
scales them together, so these reference-parameter excursions are estimator error.

Other seeds also leave significant RC errors. Seed500 ends at tau1≈0.687s and
R0≈0.162ohm. Some seeds recover the slower modes fairly closely. The ensemble
therefore shows seed-dependent RC inference, despite stable final Q/SOC.

## Seed5 chronology

At4h, its estimated tau2 is already1.476s and R0≈0.154ohm. During the second
charge, charger capability changes at4.5h and CV begins at4.57529h. The rapid
growth then passes these diagnostic markers:

| Marker | Simulated hour | Stimulus context |
|---|---:|---|
| tau2 crosses10s |4.62813|CV taper, I≈−38mA|
| tau2 crosses100s |4.67360|CV taper, I≈−4mA|
| tau2 crosses1000s |4.88797|Following discharge, I≈+0.625mA|

CV ends at4.69377h; discharge resumes at4.7771h after rest. Each marker is the
first minute-grid detection refined within the preceding minute; earlier brief
unsampled excursions are not excluded. These thresholds only locate the event,
and are not acceptance gates. Timing association does not establish that CV
caused the failure. By48h both slow modes remain around37.8minutes.

## Compression and uncertainty

Seed5's maximum binary32-versus-binary64 differences over the complete run are
only0.00258%Q and0.000225SOC percentage points. Both show the RC failure. Across
all seeds, the largest encoding difference is0.2171%Q and0.05854SOC points in
seed6. Compact coefficient quantization is therefore not necessary for this
failure; the shared nonlinear fitting/history approximation still needs review.

Truth misses the nominal three-SD intervals at89.08–99.77% of binary64 Q outputs
and77.64–99.59% of SOC outputs. These are temporal miss fractions, not independent
coverage trials, but the reported local precision plainly fails to describe the
observed errors. For seed5 at48h:

- Q error is−0.07226%, versus an approximate three-SD width of0.01377%.
- SOC error is−0.12691percentage points, versus a three-SD width of0.002427points.

The assimilated voltage can still fit reasonably closely: minute-sampled RMS
against noiseless plant voltage is1.337mV for seed5, and0.092–0.320mV for the
other seeds. These are in-sample, sparse diagnostics. They do not qualify
predictions under a new load or prove that the learned physical model is correct.

## Interpretation and next diagnostic

At500Hz, the fixed16-record fit spans32ms, shorter than even the true50ms fast
time constant. History carries state across windows, so this alone does not
prove unobservability. It does change the local fitting and approximation cadence.
Earlier identical-observation controls already demonstrated partition and stopping
sensitivity. This campaign additionally changes load schedules and seeds, so it
cannot isolate sampling rate as the cause.

The result is consistent with a weakly constrained nonlinear decomposition
moving into an incorrect solution while its local Gaussian confidence contracts.
That is a hypothesis; raw-data physical exclusion or a causal diagnosis has not
been established. R0, RC states, SOC and hysteresis can compensate in terminal
voltage, and low voltage residuals cannot settle the physical decomposition.

The next bounded experiment should replay the saved seed5 prefix through the
4.5–4.9h transition, preserving full joint messages before CV. Compare retirement
grouping and iteration limits on the same evidence, monitor joint covariance and
fresh-observation prediction, and compare a seed without runaway. This targets
the first divergence without repeating the48h campaign. A log-spacing prior
should be justified separately as physical knowledge; clamping the recovered
poles would not diagnose lost evidence or miscalibrated uncertainty.

Original results were left untouched.44 small artifacts were verified against
the run manifest, including summaries, configuration, joint messages and stimulus
events. Large arrays were read via memory maps at selected rows; their full
multi-gigabyte hashes were not recomputed. [verification.json](verification.json)
records the review artifacts and command. No production code changed.
