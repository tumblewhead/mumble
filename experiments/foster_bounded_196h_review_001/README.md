# Completed 196-hour bounded-hysteresis review

The owner run `run_bounded_20261030_185906_868310` completes all eight seeds in
both coefficient encodings at50Hz. Each arm retires35,280,000observations into
2,205,000tokens with no pending samples or fatality. The recorded observation
and truth identities match the earlier failing run for every seed. This is a
matched-input comparison; original files and estimator implementation are unchanged.

All reported boundaries in both encodings remain within0.5%Q and0.5SOC percentage
points after17.76836hours. Seven seeds reach that final uninterrupted interval
within3.291hours; seed1006 is the slower learner. These times are last observed
violations, not a guarantee about future operation or unreported sample times.
The full-run scores include substantial initial learning error.

|Seed|Final Q error (%)|Final SOC error (pp)|Last target violation, either encoding (h)|Last48h max Q error (%), binary64|
|---|---:|---:|---:|---:|
|1000|+0.002996|+0.000731|1.9300|0.004232|
|1001|+0.011136|-0.004153|2.4088|0.014320|
|1002|+0.000172|+0.000046|1.1996|0.005408|
|1003|+0.022920|-0.008565|3.1665|0.028727|
|1004|+0.021038|-0.008938|3.2909|0.026840|
|1005|-0.005288|+0.002319|1.5710|0.006310|
|1006|+0.132638|-0.051584|17.7684|0.164818|
|1007|-0.000526|-0.000399|2.9584|0.005761|

Final errors across both encodings are at most0.13264%Q and0.05159SOC points.
Over all of the final48hours, maxima are0.16482%Q and0.06397SOC points. The
full-trace scan confirms this is sustained late accuracy, not a favorable endpoint
alone. [system_review.png](system_review.png) shows hourly maxima, uncertainty
miss fractions and assimilated voltage error. The plot uses binary64; the
machine receipt scans both encodings without decimating estimate boundaries.

## Remaining uncertainty and identification limitations

Seed1006 finishes with+0.13264%Q error but a reported upper three-SD relative
width of only0.01643%. Its Q interval misses truth at every output during the
last48hours, and its SOC interval misses at95.97% of those outputs. Seed1003 also
misses Q truth throughout the final48hours despite its small point bias; seed1004
misses about79.9%. These are correlated temporal miss fractions, not independent
coverage trials. The uncertainty is substantially overconfident on these paths.

RC identification remains incomplete. For example seed1001's final R1 error is
+119.08%; seed1006 has tau1/tau2 errors of−54.03%/−62.59%. Good Q/SOC and voltage
fits do not identify every nuisance parameter. Seed1006's H and gamma+/gamma−
errors are−3.10%,+4.81%,+5.18%, respectively. It has0.08570mV assimilated-voltage
RMS error against noiseless truth over the last48hours; this is not an independent
prediction error. The residual bias and optimistic uncertainty warrant diagnosis,
not a requirement that every nuisance parameter meet the Q/SOC target.

The largest full-run encoding differences remain within application scales:
0.17691%Q and0.33091SOC points, both from seed1001. Seven seeds have much smaller
differences. Thus support repair succeeds in both encodings, but does not establish
coordinate-invariant or exactly equivalent approximate posteriors.

## Evidence and next step

[summary.json](summary.json) gives compact conclusions and limits;
[attempt001/review.json](attempt001/review.json) contains per-seed results,
source hashes, time-window statistics, final parameters and uncertainty widths.
92small source/configuration/evidence artifacts were verified against the run
manifest. The scan checks chronology, finite telemetry, physical h support and
final-message/trace agreement. Independently accumulated extrema, RMSE, target
fractions and three-SD miss counts agree with the original summaries for all16arms.
Large arrays were memory-mapped in bounded chunks; their entire hashes were not
recomputed. Recorded input identities, rather than fresh bulk hashes, establish
the comparison with the original run.

Keep this version as the stable baseline. The next focused investigation is the
joint uncertainty and residual bias on seed1006, with an accurate seed as a
control: compare retained likelihood information against the compressed Gaussian
message and check fresh-observation predictions. Do not add empirical inflation
or decay merely to match these observed errors. Broader cell/load/noise and aging
qualification remains separate; this run uses one stationary cell definition and
eight noise realizations of the same program.

Reproduce the read-only review into a new output directory:

```sh
python3 -B -m experiments.foster_bounded_196h_review_001.review \
  --run /home/easy/proj/mumble/experiments/foster_campaign_001/run_bounded_20261030_185906_868310 \
  --original /home/easy/proj/mumble/experiments/foster_campaign_001/run_20261030_175523_166400 \
  --out experiments/foster_bounded_196h_review_001/attempt002
```

Bulk traces and generated hourly/plot files remain local. No simulations were rerun.
