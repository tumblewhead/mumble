# Shared uncertainty: matched 24/72-hour likelihood audit

The shared likelihood representation introduces a reproducible Q center shift
that grows from about **1.75 local SD at24hours to4.05 SD at72hours**. Hysteresis
accounts for more than99.9% of the signed gradient-predicted Q displacement.
This is separate from the between-refresh Gaussian-boundary defect already
addressed by tangent feedback.

[Receipt](../../provenance/shared_uncertainty_growth_001/receipt.json) and
[registration](registration.json). Branch: `experiment/shared-uncertainty-growth-001`,
base `b854600`. No estimator, campaign default or mainline change.

## Matched evidence

Both existing low-noise witnesses use cellA, embedded load seed7,2mV analog
noise and50Hz. Noise seeds are1100 and1103. The nearest saved checkpoints to
24/72hours are24.029867/72.089600hours, selected by sample count before fitting.
This adapts the older plan's scheduled-refresh endpoint to saved checkpoint
boundaries. Pending observations are flushed and the field is freshly refit;
an online between-refresh message is not compared with a different prefix.

| Noise seed | Hours | Field Q error (%) | Retained-data Q error (%) | Field/reference center separation (reference SD) |
|---|---:|---:|---:|---:|
|1100|24.03|−0.005729|−0.002602|1.741|
|1103|24.03|−0.004720|−0.001578|1.748|
|1100|72.09|−0.004323|−0.000218|4.043|
|1103|72.09|−0.003545|+0.000570|4.053|

Truth is opened only by the postfit scoring process. At72hours the retained-data
Q estimates are−0.215 and+0.562 local SD from truth, compared with−4.226 and−3.464
for the field. These are two selected, correlated witnesses, not a coverage
validation or a proof about other cells and aging.

The field/reference shift is approximately0.00313–0.00314%Q at24hours and
0.00410–0.00412% at72hours. Reference Q widths shrink from about0.00180% to
0.00102%. At common field anchors, field and retained-data widths differ by
only0.27–0.51%; at their respective optima they differ by less than0.8%.
Thus the problem exposed here is primarily a displaced center, despite a very
small application-level point error. Multiplying the covariance would conceal
that cause.

The discrepancy is joint: original-coordinate center separations are about6.7
and9.0 in the full reference local metric, with notable H/gamma contributions.
Those distances are descriptive, not calibrated chi-square tests. No joint
cross terms were removed during fitting, transport or attribution.

## Cause and controls

At the field optimum, evaluate the retained-data gradient g and joint GN
precision P. The predicted correction −P⁻¹g reproduces the measured Q refit
shift within0.14% relative error in all four comparisons. The existing additive
partition identity assigns99.942–99.984% of the signed predicted Q correction
to hysteresis. This percentage is an attribution convention with cancelling
cross terms, not a fraction of independent variance.

All four local field fits and both declared retained-data starts converge.
The two exact starts return identical Q values within recorded precision.
The starts are the field optimum and its computed GN correction; neither uses
truth. This checks the local correction, not global mode uniqueness.

All48 original stimulus/controller/RNG checkpoint checks match exactly.
The regenerated observations also match both earlier four-hour caches plus
holdout bitwise (808,912records each). The reference always uses observations
from sample zero, never a late compressed checkpoint as a surrogate prior.
The exported field is used only as the compared representation and an optimizer
start. The public prior is included once in each objective.

Instrumented partition voltage, Jacobian, endpoint and transport agree bitwise
with the archived model. Partition/QR gradient assembly differences project to
less than1.4e−8 local Q SD. Doubling exact derivative chunk size changes Q by
less than9e−12 local SD. These controls are negligible beside the measured shift.
Small-step Q-direction observed/GN curvature ratios lie between0.9983 and1.0013,
with some finite-difference scatter at the smallest step. This is a directional
check, not a full observed Hessian or a Gaussian posterior certificate.

Native versus exact endpoint transport is recorded separately. Static Q is
unchanged by that transport, so it cannot explain this Q displacement. The
hysteresis endpoint chart also shows approximation differences; this study does
not assign all forecast-voltage misses solely to the fitted center.

## Why long use exposes it

For a repeated operating distribution, a coherent response approximation can
produce a gradient defect proportional to observation count N. Information
also grows approximately as N. Consequently,

```
center displacement ≈ −(N F)⁻¹ (N b) = −F⁻¹ b
local standard deviation ≈ N⁻¹/²
standardized displacement ≈ √N × constant
```

Here F is per-observation joint information and b the mean gradient defect.
These are conditional asymptotic relations, not a fitted lifetime law. The
24/72hour results support the mechanism: a persistent small physical shift
becomes several local SD while widths shrink. They do not establish a permanent
bias limit or ten-year calibration. The year-long detour is not needed to
identify this repair target.

## Next repair experiment

Refine only the two-rate hysteresis response and its consistent state transport,
keeping OCV/charge, ohmic and RC representations fixed. Rebuild from the same
recorded prefixes for this diagnostic, retain the full joint likelihood and
compare the measured gradient defect, center, local width and proposed-load
forecasts with the retained-data reference. Begin with omitted mixed Chebyshev
modes and a degree6/7 hysteresis control; inspect mode contributions before
choosing a bounded implementation. The sensor-bin likelihood remains a later
control if a retained-data discrepancy persists.

Do not merely recenter the existing truncated polynomial: a change of coordinates
cannot restore coefficients already discarded. Do not promote a larger basis
without resource accounting, and do not add forgetting or scalar inflation.
The repair must eventually support chronological updates without retained data;
this offline audit does not solve adaptive-history migration.

## Resources and reproduction

Production storage added: **0B**. The two72-hour five-column observation caches
total1,038,090,496B (~0.97GiB), ignored by Git. No full truth/trace CSV is retained.
Derivative work is chunked. Regeneration takes about81host seconds/case; each
24/72hour audit takes about31–33/91seconds. These are diagnostic host timings,
not campaign or M23 timing estimates. Eleven targeted tests pass.

For a potential refinement with RC degree5 fixed, a dense packed joint factor
costs27,224B now (width82),37,248B with hysteresis degree6 (width96), or50,624B
with degree7 (width112). These are comparison sizes excluding live state, prior
and workspace, not accepted production requirements. Selective modes or a
better hysteresis basis must be evaluated before target deployment.

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -B -m unittest \
  experiments.uncertainty_weak_stimulus_001.test_diagnostics \
  experiments.shared_uncertainty_growth_001.test_audit -q

python3 -B -m experiments.shared_uncertainty_growth_001.execute \
  --out experiments/shared_uncertainty_growth_001/reproduction001

python3 -B -m experiments.shared_uncertainty_growth_001.summarize \
  --run experiments/shared_uncertainty_growth_001/reproduction001 \
  --out experiments/shared_uncertainty_growth_001/reproduction001/receipt.json
```

Use fresh output paths. The original source worktree and archived artifacts
must be present and pass binding validation. Generated outputs remain local;
source, tests and the compact receipt can be committed.
