# RC5/H7 streaming integration and 72-hour comparison

The integration branch `implementation/h7-campaign-001` now runs RC5/H7 in the
native fused tangent estimator with compact recording, replay and plots.
All eight cases and all sixteen estimator arms completed 72 simulated hours.
The run used implementation commit `d300f742355a50876cede0f9ba4b921429b055fe`.
Defaults and mainline remain unchanged.

[Completion receipt](completion.json), [per-case review](run72_review.json),
[qualification](qualification.json), [registered plan](../../experiments/h7_campaign_001/plan.json),
and [integration guide and rerun command](../../experiments/h7_campaign_001/README.md).

## What changed in the results

Both arms processed the same 50 Hz observations from cells A/B, embedded and
CC/CV charge-discharge loads, noise seeds 1100/1103, 2 mV noise and embedded load
seed 7. H5 is `tangent64`; H7 is `tangent_h7`. The original prior, refresh cadence,
RC representation and physical model were held fixed. No covariance inflation,
truth correction or outgoing-posterior feedback was introduced.

| Measurement | H5 | H7 |
|---|---:|---:|
| Completed arms | 8/8 | 8/8 |
| Q 3SD misses / 6,480,000 outputs | 3,973,397 (61.3%) | 0 |
| SOC 3SD misses / 6,480,000 outputs | 3,502,106 (54.0%) | 34 (0.000525%) |
| Worst final absolute Q error | 0.00628% | 0.00179% |
| Worst final absolute SOC error | 0.00108 percentage points | 0.000449 percentage points |
| Worst final absolute Q error / local SD | 7.56 | 2.05 |
| Worst final absolute RC parameter error | 26.90% | 27.36% |
| Rejected scheduled refreshes / 34,464 attempts | 570 | 671 |

The Q and SOC uncertainty mismatch is substantially smaller. H7's final Q local
standard deviations are slightly smaller than H5's, so wider uncertainty is not
the explanation. These are correlated outputs from eight stationary scenarios,
not millions of independent coverage trials. Neither calibrated coverage nor
indefinite accumulation is established. The remaining SOC misses are all in cell
B, embedded load, seed 1103. RC point accuracy is largely unchanged and is not
the repair demonstrated here.

The cell-A charge-cycle cases still hit the refresh solver's `round_limit`:
117/109 rejections for H5/H7 with seed 1100, and 453/562 with seed 1103. Every
other case accepted all refreshes. Rejection preserves the current tangent and
accumulated evidence; no arm failed or required an emergency refresh. These
rejections need separate diagnosis before treating the refresh solver as robust.

The [24-hour checkpoint check](prefix24.json) also reproduces the frozen offline
H7 result on matching stimuli: streamed Q differs by at most 0.000000123%, and a
fresh full-field checkpoint refit differs by at most 0.00000136 local SD. This
checks integration fidelity; it is not an independent coverage study.

## Plots and storage

Local generated artifacts remain outside Git:

- [Q uncertainty comparison](../../experiments/h7_campaign_001/review002/Q_uncertainty.png)
- [SOC uncertainty comparison](../../experiments/h7_campaign_001/review002/SOC_uncertainty.png)
- [All-case error overlay](../../experiments/h7_campaign_001/run72_001/case_summary/errors.png)
- [Campaign summary](../../experiments/h7_campaign_001/run72_001/summary.json)

The uncertainty curves show ratios of bin-mean error to bin-mean local standard
deviation after three hours. Annotations count actual whole-run per-output
misses. The plots do not reconstruct individual samples from bin averages.
Individual V/I/T, state, parameter and error plots and parameter comparison pages
are also retained. Compact recording uses 2,000 bins and approximately three-hour
checkpoints. The completed campaign occupies about 257 MB (245 MiB), including
all PNG/PDF plots, checkpoints and source snapshots; it contains no raw stream CSV.

The H7 packed likelihood factor alone is 50,624 bytes (49.4 KiB). Add 1,336 bytes
of live collocation state, a 1,376-byte native tangent context and 10,088 bytes of
explicit native scratch. The desktop adapter additionally holds a dense field
root, raw batch buffer and other workspace. This is not a 10 KiB M23 implementation.

## Qualification and next work

The integration passed 59 targeted test executions, including frozen H5 bitwise
parity, independent H7 joint posterior/state transport, full/compact parity,
checkpoint replay, failed-refresh preservation and plotting. The initial review
made while summary plots were still rendering is preserved as
[run72_preplot_review.json](run72_preplot_review.json); the final review records
the finalized summary hash and artifact size. The original qualification receipt
retains its pre-run status as historical evidence.

H7 is now a useful streaming fidelity reference for reducing hysteresis storage
with a sparse or separable representation that preserves the joint likelihood
and state transport. Keep this run fixed when comparing a smaller representation.
Investigate the charge-cycle refresh failures separately. Aging, weak-use
coverage, retained-data accuracy across every new case, and target CPU/SRAM
qualification remain open; no additional long sweep or mainline promotion is
implied by this result.
