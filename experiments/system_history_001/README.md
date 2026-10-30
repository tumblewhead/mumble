# Overall system testing before optimization

Four four-hour, 35 Hz trials completed: **2,016,000 distinct observations**, each
processed independently by binary32 history, binary64 history, and the unchanged
legacy C rolling estimator. The harness passes **45 targeted checks**.

The history encoding remains useful at the application's preferred accuracy
scale. The broader tests nevertheless expose **capacity bias and overly narrow
uncertainty when the true cell lies between the model's health nodes or ages
gradually**. Further codec precision or storage tuning is not the next priority.

## Results

| Case | Final history Q error | Final history SOC error | Final legacy Q error | Final legacy SOC error |
|---|---:|---:|---:|---:|
| Matched stationary control | −0.000029% | +0.000104 points | +1.611% | +0.515 points |
| Stationary cell between nodes | **−10.053%** | +0.004316 points | +1.700% | +0.507 points |
| Gradual Q/R0 aging | **−5.761%** | +0.031717 points | +5.698% | +0.484 points |
| Combined cell/thermal/RC/load/noise variation | **−2.702%** | −0.011367 points | +8.987% | +0.313 points |

History values in this report use binary32 log weights. Binary64 produces the
same system findings. The maximum encoding-induced query differences across
all samples and cases are **0.02813% Q** and **0.0000745 SOC points**, both below
the preferred 0.5% Q / 0.5 SOC-point scales. The latter are practical scales,
not universal probability-distribution error bounds.

Every history SOC point estimate remains within 0.5 points, including initial
learning. Capacity does not satisfy the corresponding generalization gate:

| Case | Maximum Q error in 90-minute rest | Maximum Q error after renewed loading | Q truth outside reported mean ±3 SD, whole run |
|---|---:|---:|---:|
| Matched | 0.00936% | 0.784% | 0% |
| Between nodes | 10.056% | 24.818% | 91.34% |
| Gradual | 6.135% | 24.233% | 42.35% |
| Combined | 10.579% | 19.569% | 79.02% |

The matched control has four Q-scale breaches among 126,000 renewed-loading
samples. These remain explicit; small final errors do not erase them. The
three-standard-deviation misses are descriptive single-trajectory diagnostics,
not calibrated coverage estimates. They reveal severe false precision in the
mismatched cases despite useful SOC and reasonable voltage residuals.

See the [full review](review001/result.json),
[error plots](review001/system_errors.png) ([PDF](review001/system_errors.pdf)),
and [analysis](analysis.md). Plot traces use saved/decimated points, while history
metrics score every observation and legacy metrics score every 16-record output.
The review additionally compares 60 exactly shared saved checkpoints per case.

## What changed in this study

Only the experiment harness and analysis are new. Both estimators remain
unchanged. Each receives the same decoded 12-bit V/I/T observations and actual
intervals, without truth-based initialization or corrections. All arms finish
504,000 observations per case, with no retries, clipping, tail pruning, resets
or precision tuning.

The [registered plan](plan.json) specifies 90 minutes of cycling, 90 minutes of
rest and 60 minutes of renewed cycling. The first three cases share nominal
1 mV noise and 25 °C. The between-nodes cell changes only Q/R0 from the matched
control. Smooth aging begins at one hour and reaches a 10% Q loss / 12% R0 rise
by four hours. This is accelerated stress, not calibrated real aging.

The combined case adds a different cell, smooth Q/R/RC-capacitance aging,
17–33 °C variation with off-support thermal slopes, varied balanced pulse
amplitudes, and 12 mV noise. It tests combined behavior rather than isolating
each cause. Each case uses one deterministic noise realization; no ensemble
coverage or general-cell qualification is claimed.

The legacy baseline keeps its public prior, 16-record blocks, one refinement
round, fixed 1 mV likelihood noise, and original approximate history. It does
not compensate temperature or model aging. The new history uses its unchanged
finite prior, conditional SOC SD 0.03, assumed aging scale 0.01 and declared
noise plus ADC variance. Thus the legacy comparison is a system baseline, not
a controlled isolation of history compression. The binary32/binary64 pair
provides that controlled encoding comparison.

## Interpretation and next step

At 25 °C the history has only three Q levels: 0.060, 0.051 and 0.042 Ah. A true
0.0567 Ah cell lies inside the envelope but outside the latent state support.
Its estimated capacity switches among supported states and ultimately settles
near 0.051 Ah with unjustifiably small uncertainty. Gradual aging similarly
traverses missing intermediate states. The [analysis](analysis.md) separates
this evidence from what remains unidentified about projection, nuisance
coupling and the assumed aging kernel.

The next focused comparison should permit continuous Q/R health variation while
preserving joint SOC/nuisance uncertainty, first on the frozen matched and
between-nodes controls, then on gradual aging. This builds on the earlier
centroid/trajectory idea without treating a moving point estimate as sufficient
history. Require honest uncertainty or unresolved status during weak excitation;
do not add arbitrary forgetting to force tracking.

The new history is **not yet fed into the original rolling solver**. Its current
boundary posterior cannot simply be appended to a likelihood that already owns
those observations. The [boundary contract](boundary.md) specifies replacement
of retired evidence, disjoint ownership and the distinction between marginal
and profile inference. Feedback integration remains open.

## Resources and provenance

The history retains 729 hypotheses. Binary32 log weights plus binary64 SOC
moments require a **14,580 B partial packed payload**, before operator state,
descriptors and workspace. Live decoded primary arrays use 17,496 B plus the
encoded packet and temporary storage. The legacy context is 8,680 B; these
independent desktop arms are not a combined firmware layout. No complete near-
10 KiB fit, M23 timing or ten-year stability claim is made.

The four cases ran concurrently, each taking approximately 184–189 host wall
seconds including both history arms, scoring and its legacy run. Each native
legacy run took approximately 3.7–3.8 seconds. This exposes a substantial
prototype execution cost, but does not measure the standalone history arm or
target hardware. No runtime optimization was undertaken in this step.

[Reservation and source snapshots](campaign001/reservation.json),
[native build](campaign001/build.json),
[qualification](campaign001/qualification/result.json),
[input identities](campaign001/inputs/manifest.json),
[summary](summary.json) and [verification](verification.json) preserve the
commands, revision, outcomes and earlier evidence. The qualification checks
causality, acquisition equivalence, repeat generation, monotone truth trajectories,
source consumption and an independent physical recurrence. Scientific gate
failures above are reported rather than treated as failed harness arithmetic.

From the repository root, use a new directory for any intentional rerun:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -B -m experiments.system_history_001.campaign prepare experiments/system_history_001/campaign002
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -B -m experiments.system_history_001.campaign qualify experiments/system_history_001/campaign002
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -B -m experiments.system_history_001.campaign run experiments/system_history_001/campaign002 matched
```

The final command accepts `matched`, `between_nodes`, `gradual` or `combined`.
Independent cases may run concurrently with one BLAS thread each. Existing
attempt directories are never overwritten. The saved review targets
`campaign001`; verification does not rerun inference.
