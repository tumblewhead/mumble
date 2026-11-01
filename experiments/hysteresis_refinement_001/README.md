# Hysteresis refinement with the remaining physical partitions fixed

The degree7 hysteresis candidate reduces compression-induced Q displacement by
**62× at24hours and71× at72hours** on the two registered low-noise witnesses.
Joint likelihood and voltage forecasts also move closer to the retained-data
reference. It is a useful diagnostic reference for a smaller implementation;
it is not promoted to the campaign or mainline.

[Receipt](../../provenance/hysteresis_refinement_001/receipt.json),
[comparison plot](report002/comparison.png), [registration](registration.json),
and [adaptations](adaptations.json). Branch: `experiment/hysteresis-refinement-001`,
base `4367e92`. The prior [shared uncertainty audit](../shared_uncertainty_growth_001/README.md)
identified the shared hysteresis gradient defect.

## What changed

The experimental C recurrence now has separate collocation orders for RC and
hysteresis. RC remains degree5 with the same rates, coefficients and operation
order. OCV/charge, ohmic response, the rate-domain box, public prior and sensor
likelihood are unchanged. Hysteresis uses total-degree6 or7 in its two log-rate
coordinates. The same basis drives both likelihood coefficients and endpoint
transport, with analytic derivatives. Physical parameters remain continuous.

Each candidate streams the complete saved prefix once into a prior-free joint
square-root likelihood. All amplitude/rate cross terms remain. Fits include the
original public prior once and start from the original field fit, without using
the retained-data optimum or truth as initialization. Reference fits and truth
are used only for comparison/scoring after candidate inference.

The cached observations are the previously validated seed1100/1103, cellA,
load7,2mV,50Hz prefixes at24.029867 and72.089600hours. No new long campaign was
run. Original data, fits, binaries and source worktrees remain untouched.

## Results

Absolute Q separation from the retained-data optimum, in reference local SD:

| Prefix | Original H5 | H6 | H7 |
|---|---:|---:|---:|
|24h, seed1100|1.741|0.571|0.0280|
|24h, seed1103|1.748|0.565|0.0284|
|72h, seed1100|4.043|0.894|0.0571|
|72h, seed1103|4.053|0.894|0.0572|

H7 Q widths agree with the reference within0.031% at the respective optima.
The correction is not covariance inflation. Full joint center distance falls
from6.70–6.71 to0.353–0.355 at24hours and8.98 to0.495–0.497 at72hours. These
local distances describe approximation agreement, not calibrated probability.
All eight candidate fits satisfy the existing solver stopping criteria.

Postfit Q errors for H7 are−0.00265%/−0.00163% at24hours and−0.000276%/+0.000512%
at72hours. The72hour values are−0.272/+0.504 local SD from truth. Application-level
Q error was already small; the useful change is removing an approximation bias
that otherwise becomes large relative to the accumulated precision.

## Forecast and transport checks

From every fitted prefix, forecast60seconds of rest and a120mA10second pulse
followed by30seconds of recovery, at the observed endpoint temperature. Forecasts
use the complete transported joint covariance. Truth scoring is a separate
process using the scalar plant recurrence; exact-data forecasts are also compared
on each candidate's evaluation times. Current-edge values and continuous-time
extrema are included by the existing forecast implementation.

Across the two tasks with equal task weights, H7 versus retained-data voltage
RMS is0.484–0.520µV at24hours, down from4.829–4.881µV. At72hours it is0.480–0.505µV,
down from2.550–2.578µV. Maximum path differences remain distinct from RMS:
H7's worst difference across these witnesses is4.84µV. All H7 forecast point
queries and512 exercised signed joint direction probes are supported.

In the selected seed1103/24hour rest witness, baseline voltage misses the local
three-SD band at70.0% of evaluated times; H7 has no misses. These are correlated
time samples, not independent coverage trials. A closer likelihood approximation
does not guarantee lower truth error on every noisy realization: for example,
seed1100 pulse truth errors become slightly larger while approaching the retained
reference. All point errors remain small for the application. No blanket accuracy
or coverage improvement is claimed.

Native versus exact transport of each candidate fit is recorded separately.
H7 physical h transport differences are approximately7–9e−8 at24hours and1.6e−5
at72hours. Remaining transport and fit errors are nonzero; they must remain
visible in subsequent lifetime/error-budget work.

## Why adding degree helps

A fixed-grid control separates additional collocation samples from extra modes.
Starting with the H7/grid8 joint factor, QR-restrict its columns to total-degree5
or6, while retaining exactly the same grid8 live response state. These refits
reuse the original likelihood only; no evidence is duplicated.

Degree5/grid8 still has Q shifts of2.02SD at24hours and4.51–4.52SD at72hours.
Degree6/grid8 gives0.56SD and0.94SD. Therefore more collocation points alone do
not remove the bias. The missing modes matter.

The largest negative Q-gradient contributions include pure mode(6,0), mixed
mode(4,2), and pure mode(7,0), with positive contributions from other modes that
partly cancel them. Indices refer to Chebyshev degrees in the positive/negative
hysteresis log-rate coordinates. Mixed terms cannot be replaced by independent
one-dimensional fits. The mode attribution uses a full-joint gradient identity,
not independent variances or a license to drop all small coefficients. Its Q
projection assembly residual is below4e−14percentage points; first-order shifts
remain local approximations, not exact refit displacements.

## Storage, cost and next step

| Representation | Lifted width | Packed joint factor | Live collocation state |
|---|---:|---:|---:|
|RC5/H5|82|27,224B (26.6KiB)|888B|
|RC5/H6|96|37,248B (36.4KiB)|1,096B|
|RC5/H7|112|50,624B (49.4KiB)|1,336B|

These exclude prior, rates/projection tables, tangent carrier, metadata and
workspace. The literal Python H7 implementation also has a100,352B dense root
and18,720B projection tables. It is not an approximately50KiB complete estimator,
and it does not meet the10KiB M23 target. Production storage added by this
experiment is0B because campaign backends are unchanged.

Per seed, rebuilding the72hour H6/H7 factors takes approximately60/80host seconds.
These offline bulk builds do not measure online16-record latency or M23 cycles.
The same1.038GB observation caches are reused; this experiment adds no new raw
observation trajectories. Generated factors, forecasts, reports and plots stay
ignored by Git. Only source, tests and a compact receipt are committed.

Carry H7 forward as the fidelity reference. Next, evaluate a sparse or separable
representation that preserves the important pure and mixed terms, judged by the
full joint likelihood/transport error and proposed-load forecasts. Avoid selecting
modes only for Q or only from these two similar seeds. Validate on weak/reversing
stimulus and other cells before campaign integration. An online migration cannot
recover omitted coefficients from an existing H5 factor; the implementation must
start with the new representation or have an explicit reconstruction strategy.

Finite-degree refinement reduces the measured bias but does not prove indefinite
calibration. A persistent residual can still become significant as precision
grows. Aging and an explicit accumulated approximation-error budget remain open.
No variance floor, forgetting or truth-dependent correction is introduced.

## Qualification and reproduction

Twenty targeted tests pass: nine mixed-field/ablation tests plus eleven existing
likelihood and input-binding controls. Degree5 exactly matches original rows,
features, analytic derivatives, endpoint transport and QR factors. Non-hysteresis
rows are bitwise unchanged at higher degrees. Finite-difference derivatives,
chronology rejection, rest-null information, chunked joint likelihood and
column-restriction cross terms are checked.

The first run stopped after writing its first24hour result because console JSON
logging received NumPy arrays. Scalar-only progress logging fixed that issue;
both seeds were rerun into fresh `attempt002` directories. Original attempts
are preserved. A later amplitude-readout API override is separately documented
and tested; it is not used by the qualified fit/forecast paths. Each completed
run retains the exact source snapshots it executed.

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -B -m unittest \
  experiments.hysteresis_refinement_001.test_field \
  experiments.hysteresis_refinement_001.test_ablation \
  experiments.shared_uncertainty_growth_001.test_audit \
  experiments.uncertainty_weak_stimulus_001.test_diagnostics -q

python3 -B -m experiments.hysteresis_refinement_001.execute \
  --out experiments/hysteresis_refinement_001/reproduction001
```

The reproduction runner requires the previous validated observation caches and
archived model binaries. It builds both candidates, performs fixed-grid controls
and scores frozen outputs. Use a fresh output directory.
