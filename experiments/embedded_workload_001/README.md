# Semi-Markov embedded workload with independent seeds

`--loads embedded` is now available in the existing local campaign runner.
`--load-seeds` controls the activity schedule; the existing `--seeds` controls
measurement noise. The two RNG paths are independent. Selected load seeds and
noise seeds form a Cartesian product, with stable case ordering and labels.
Deterministic load profiles ignore load seeds and do not create duplicate cases.

```sh
python3 -B -m experiments.foster_campaign_001.run \
  --hours 24 --jobs 4 --sample-rate-hz 50 --cells A \
  --loads embedded --load-seeds 7 8 --seeds 1100 1103 --noise-v 0.002
```

This creates four cases, each with both coefficient encodings by default.
`--current-a` sets the embedded discharge envelope's peak, default0.03A.
It does not limit charger current, which continues to use the configured
nominal capacity and CC/CV charger capabilities. Voltage cutoffs and rest/taper
settings remain configurable. `--discharge-c` applies to the conventional
charge-discharge profile; embedded discharge instead uses the workload request.
Estimator/history code and production estimator defaults are unchanged.

## Workload model

A semi-Markov operation chain picks the next operation from explicit probabilities
and draws its dwell from a bounded uniform range in integer microseconds. A
separate LED chain overlaps those operations. Each chain has its own PCG64 stream
spawned from the load seed. Random draws happen at transitions, not every sample,
so workload scheduling is independent of noise draws, chunk size and sample rate.

At the default30mA peak:

|Operation|Battery-side envelope current|Episode duration|
|---|---:|---:|
|Sleep|0.25mA|0.5–8s|
|Sense|2.5mA|0.08–0.5s|
|Compute|6mA|0.1–2s|
|Radio transmit activity|10mA|0.04–0.32s|
|Radio receive activity|9mA|0.04–0.5s|
|Flash program batch|18mA|0.04–0.16s|
|Flash erase activity|25mA|0.06–0.6s|
|Overlapping LED on|+5mA|0.2–4s, alternating with0.5–6s off|

The operation chain follows sleep→sense, then compute/radio; radio often proceeds
to receive; computing or reception can produce a flash-program batch; occasional
flash maintenance returns to programming. The transition table is explicit in
[workload.py](../foster_campaign_001/workload.py) and copied into each run's
metadata. Currents/durations are declared generic synthetic assumptions, not a
specific MCU/radio/flash datasheet, power-converter model or realistic file-system
simulation. Flash-program episodes represent batches, not single page writes.
This first version uses LED on/off activity, not a fast PWM circuit simulation.

## Timing and acquisition contract

The logical event timeline is independent of Fs. Within each interval1/Fs,
the generator integrates the logical current envelope, quantizes its average to
the existing125uA current grid, then physically commands that constant current
for the whole interval. Both the plant and estimator receive the same held
current. This is a well-defined sampled load experiment, not an assertion that
unresolved RF pulses produce the same RC response as their mean current.
Subsample circuitry, anti-alias filtering and ADC aperture would require a
separate acquisition model before claiming board-waveform fidelity.

The embedded schedule continues during charging/rest. The measured-voltage
CC/CV controller selects when the workload is actually applied as discharge.
Consequently, identical load seeds yield identical logical event schedules, but
actual terminal-current sequences can differ across noise seeds because charger
phase decisions use measured voltage. The code does not hide that physical
feedback dependency or feed cell truth into the controller.

`workload_events.csv` records the operation/LED states and their exact scheduled
start/end times. `stimulus_events.csv` records charger phases and delivered-load
changes. Both seeds appear in scenario/results/summary CSV and individual/overlay
plot labels. The estimator receives only the usual chronological observation
rows; neither state labels nor load seed is an estimator feature.

## Validation and interpretation

The targeted suite covers52tests including seven workload-specific tests:
reproducibility, distinct seeds, legal transitions/dwells, bounds, interval-charge
conservation before current quantization across35/50/100Hz, exact event agreement
across those rates, independent noise/chunking, external-load accounting,
Cartesian seed sweeps, serial/parallel byte equality and summary labels. Existing
campaign, C-backend, bounded-hysteresis, charger and plot regressions pass.

[qualification.json](qualification.json) records the four-hour smoke campaign
and its limitations. Its four cases cross two load seeds with two noise seeds;
that verifies execution and provenance, not a causal repair of the RC bias.

The [720-hour review](../foster720h_rc_review_001/README.md) found that case0003's
individual RC values are wrong while total settled resistance is within0.0276%.
A richer workload is therefore worth testing against the original load with the
same cell/prior/noise configuration. It does not remove the need to distinguish
weak excitation from irreversible local-history approximation and overconfidence.
Bulk campaign outputs and plots stay local; only sources and small receipts are
retained in Git.
