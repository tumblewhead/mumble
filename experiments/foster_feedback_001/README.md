# Continuous Foster rolling estimator with history feedback

The new model, rolling token producer and history feedback adapter are
implemented and runnable. The first four-hour control completed all **504,000
35 Hz observations** with both coefficient encodings. All eleven physical
parameters are continuous; no discrete population of battery capacities is used.

From the repository root, rerun the complete test with:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -B -m experiments.foster_feedback_001.run --hours 4
```

The command creates a unique `run_<timestamp>` directory and prints the result
path. It builds the C model, runs targeted qualification, generates the separate
plant observations, benchmarks a short stream, runs both encodings and writes
JSON results, complete block-output traces, PNG/PDF plots and source snapshots.
Requirements are Python with NumPy/Matplotlib and a C compiler. No SciPy, network
access or owner-specific path is required. Existing run directories are never
overwritten.

Optional arguments include `--cell A`, `--temperature constant`, `--noise-v 0.004`,
`--seed 314159`, `--encoding float32`, and `--out PATH`. Defaults are cell B,
cycling temperature, 4 mV noise, the displayed seed and both encodings. Cell and
noise settings belong to the harness; they never enter the history object.

## Architecture and model

The [user model contract](../../specifications/evidence_feedback_001/model.json)
is implemented by the pure C producer model [model.c](model.c): SOC, three RC
voltages, hysteresis, and eleven continuous reference-temperature parameters.
It preserves `+Hh`, separate dimensionless gamma+/gamma−, normalized throughput
`|I|dt/(3600 Q)`, and Q's effect on both SOC and hysteresis. Time constants use
continuous positive gaps to preserve ordering. R0 and H use a strictly positive
chart in this first reference; exact zero needs a different chart.

[plant.py](plant.py) independently generates physical truth and acquisition
samples with scalar recurrences. A programmable bidirectional current profile
and exogenous measured cell temperature feed the plant. The estimator sees
only indexed V/I/T observations, actual intervals, declared noise and the public
[calibration](calibration.json). Neither estimator nor compressor receives truth.

The initial OCV is the characterized linear law `3+1.15*z`. Its coefficients
and the eleven Arrhenius coefficients are **supplied public calibration**, not
learned values. Cell temperature is held per sample. The common time-constant
thermal coefficient preserves branch ordering. There is no imposed aging rate,
forgetting factor or process-noise injection. This first integrated test assumes
stationary reference parameters; observation-supported aging trajectories remain
later work.

[estimator.py](estimator.py) fits each active 16-record window against one joint
historical boundary message. It follows the bounded rolling refinement pattern
with at most four Gauss–Newton rounds and eight backtracking fractions. The
new current-boundary model/adapter is distinct from the preserved older C rolling
engine, whose original chart, prior and physical conventions remain unchanged.
All samples are ingested at 35 Hz; parameter outputs and retirement occur every
16 samples, approximately 0.457 seconds. A final partial window is also processed.

After fitting, the producer exports **only that window's likelihood and state
transport**, without its incoming prior or feedback density. Generic
[history.py](history.py) applies that token to the boundary message using the
[transaction protocol](../../specifications/evidence_feedback_001/protocol.py).
Commit acknowledgment advances the active-window boundary before raw samples
are released. There is no posterior-as-observation feedback or duplicated prior.

## What is compressed

The token contains a square-root quadratic likelihood, its continuous chart
center, and a deterministic first-order state-transport map. The feedback
message retains the full joint mean and covariance square root over all sixteen
state/parameter coordinates. Static-parameter and carried-state cross terms
remain present.

This is a **local Gaussian approximation**, not exact nonlinear posterior
closure. Each retired interval is linearized around its rolling fit. The
unbounded Gaussian's physical tails and accumulated nonlinear representation
error are unresolved even when its mean trajectory passes domain checks.

The two arms differ only in token coefficient storage: binary64 versus binary32
for the likelihood root and transport Jacobian. Centers, endpoint values and
normalization constants remain binary64. This is a fixed floating-point
coefficient encoding baseline, not a trained shape dictionary. It quantizes
the evidence object rather than restricting which batteries can exist.

## Completed four-hour result

[four_hour001/result.json](four_hour001/result.json) records the first execution.
It uses cell B with reference Q=56.7 mAh, temperature cycling between 17 and
33 °C, 90 minutes of balanced pulses, 90 minutes of rest and 60 minutes of
renewed pulses. Initial physical states and eleven parameters differ from the
public initial guess. Both arms commit exactly **31,500 disjoint tokens** and
finish with zero pending observations.

| Metric | Binary64 coefficients | Binary32 coefficients |
|---|---:|---:|
| Final capacity error | +0.4788% | +0.4793% |
| Final SOC error | −0.08431 points | −0.08429 points |
| Maximum Q error during rest | 2.4842% | 2.4853% |
| Maximum SOC error during rest | 0.08727 points | 0.08720 points |
| Maximum Q error after renewed loading | 2.6010% | 2.6019% |
| Whole-run Q RMS error, including learning | 2.4554% | 2.4558% |

The maximum binary32/binary64 difference is **0.001044% Q** and **0.000262 SOC
points**. Coefficient encoding is below the preferred application scales.
However, small final errors do not establish sustained 0.5% capacity accuracy:
capacity remains around +2.4% through rest, and both point targets hold for only
1.71% of binary32 block outputs over the whole run. Initial peaks reach 31.2% Q
and 0.797 SOC points; SOC stays within 0.5 points after about 22.9 seconds.

Uncertainty is also not qualified. Truth lies outside the reported three-SD Q
interval on 74.34% of binary32 outputs and outside the SOC interval on 92.16%.
These are descriptive single-trajectory diagnostics, not coverage estimates.
Most fits stop at their numerical gradient criterion, but 2,226 binary32 blocks
hit the round limit and 20 stop without further descent. Numerical stops and
useful physical accuracy are reported separately.

The two-arm run took **29.8 host wall seconds**; build, qualification, generation
and benchmark brought the recorded pre-plot total to **31.3 seconds**. This is
desktop performance, not M23 timing. See the [plots](four_hour001/errors.png)
([PDF](four_hour001/errors.pdf)). Every scored block output is plotted; shaded
regions mark ±0.5 error and the rest interval.

## Retained-data diagnosis

After recording the run, one separately registered
[retained-data audit](four_hour001/retained_audit001/result.json) fitted all
504,000 observations from the same public prior, without reading truth or
modifying streaming state. It obtained Q error +0.0652% and SOC error +0.0497
points when scored afterward, in 4.3 seconds. It stopped with `no_descent`, so
it is not claimed to have proven numerical/global convergence. Its GN covariance
is not an exact posterior.

This shows that a retained nonlinear fit can obtain a different, more accurate
final point from the same observations. It motivates investigation of rolling
linearization, joint-message approximation and refinement behavior. It does not
isolate their contributions or qualify the reference's coverage. There was no
truth-based retuning, automatic retry or change to the streaming result.

## Storage and verification

| Numeric object | Bytes |
|---|---:|
| Joint boundary mean, full square root and log evidence | 2,184 |
| Binary64 token | 3,537 |
| Binary32 token | 1,901 |
| Two boundary messages plus binary32 token | **6,269** |
| 16-record raw window | 640 |

These are implemented payload sizes. Protocol/Python objects, native Jacobians,
optimizer matrices, QR/solve scratch and stack/runtime are additional. There
is no complete 10 KiB memory claim. Square-root feedback avoids covariance
inversion or invented jitter/process noise; a singular physical transition is
permitted by the Gaussian conditioning algebra.

**55 targeted checks pass**, covering independent forward recurrences, all
sixteen observation/transport derivatives, continuous intermediate capacities,
the token update against retained linearized observations, full joint covariance,
normalization, source consumption and short two-cell streams. Short retained
nonlinear diagnostics are recorded without pretending they are exact marginal
posterior oracles. Both the [72-second development run](development001/result.json)
and the four-hour result are preserved.

[summary.json](summary.json) and [verification.json](verification.json) bind
the source, original evidence and findings. Each run's `manifest.json` covers
its original artifacts; the later retained audit is separately identified.

The next useful work is to diagnose the common rolling/message approximation
and uncertainty error before tuning coefficient precision or memory. This
implementation establishes the requested continuous-estimator/history pipeline
and rerunnable long test; it does not yet establish reliable aging, calibrated
coverage or approximately indefinite operation.
