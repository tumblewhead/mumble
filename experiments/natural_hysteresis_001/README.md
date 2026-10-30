# Natural parameters for bounded hysteresis conditionals

**All eight previously unfinished hysteresis fits now meet the constrained
numerical gradient tolerance.** Each reaches the exact bounded-exponential
limit in one or two Newton steps. The largest residual is **8.05e-9** against
the registered 1e-7 tolerance. This resolves a numerical representation issue;
it does not establish nonaccumulating history error or physical identification.

The [derivation](derivation.md) writes each conditional on its existing scaled
physical-rate support as `exp(eta*y - kappa*y²/2 - A)`. Positive precision kappa
is exactly the old bounded Gaussian. Zero precision is a finite supported
exponential, retaining uncertainty. It no longer requires diverging Gaussian
means and variances. The full sixteen-variable mixture, conditioning terms,
physical support, prior ownership, data split and other coefficients are
preserved. No new observations, truth, priors or forgetting factors enter.

The [frozen plan](plan.json) selects only the eight unfinished conditionals
from the [previous comparison](../partition_coordinate_fit_001/README.md).
The [new result](attempt001/result.json) preserves the original messages and
records each fit, all thirteen prediction probes and four independent sampling
batches of 16,384 draws per message. Baselines are exactly converted saved fits,
with fresh matched-size samples; they are not refitted. The saved baseline
heldout densities are reproduced within 2e-8. Original artifacts and hashes
are retained in the [reservation](attempt001/reservation.json).

All **48 controls** pass: the inherited 39 and nine new normalization,
derivative, sampling, constrained-fit and serialization controls. A separate
[512-node audit](independent_fit_audit.json) recomputes objectives and raw-feature
gradients without the optimizer's whitening or gradient routine. The
[verification receipt](verification.json) also checks source hashes, work caps,
ownership, payload size and unchanged non-rate parameters. This is a second
numerical calculation, not an independent implementation or reviewer.

At the optimum, precision gradients are positive, **0.00857–0.02969**. This is
the correct constrained optimum: increasing precision worsens the objective.
Zero precision does **not** mean zero uncertainty or an unidentifiable numeric
value. It describes the shape of the conditional distribution. Nor does a
boundary optimum prove that the source distribution is exactly exponential:
we have retained the Gaussian family's nonnegative precision restriction.
Negative precision would also be normalizable on finite support, but would
extend the model to log-convex conditionals and is outside this repair.

The main gain is numerical completion, not a large predictive improvement.
Heldout mean negative log density improves by **0.000403 and 0.000381** in the
two 32-record populations. At eight records it changes in opposite directions
(a 0.0000216 worsening and 0.0001166 improvement). These are diagnostic changes,
not a physical accuracy threshold.

At 32 records, pooled predictive voltage standard deviations are:

| Probe | Source reference | Converted baseline | Natural refit |
|---|---:|---:|---:|
| One-sample load | 0.600 mV | 0.576 mV | 0.575 mV |
| 0.1 s load | 0.680 mV | 0.737 mV | 0.735 mV |
| 1 s load | 3.070 mV | 3.081 mV | 3.078 mV |
| 10 s load | 16.373 mV | 16.040 mV | 16.060 mV |
| 10 s load + 10 s reversal | 23.117 mV | 24.585 mV | 24.679 mV |

Batch variation is recorded in the [summary](summary.json); these small
baseline/refit differences do not establish a predictive improvement. For
example, the one-second SD batch ranges are 3.062–3.092 mV and 3.063–3.103 mV.
The longer reversal discrepancy remains: refitted mean is **+1.470 mV** from
the finite source reference, and its SD is about **6.76% larger**. All generated
probes remain inside physical support. No coverage claim follows from this.

The uniform absolute log-density-change bounds are 0.06093 and 0.08133 for the
8/32-record messages; observed heldout changes stay below 0.02321 and 0.02844.
These conservative bounds describe the change from the old representation,
not error against the true posterior. Their exact-arithmetic derivation is
evaluated in binary64, without interval certification.

**Retained numeric storage remains 2,496 bytes for two components.** Each rate
still stores its linear coefficients and one shape scalar. Four components
would require 4,960 bytes by the same formula, but were not tested here.
Metadata, queue, physical state, solver scratch and stack are additional; the
complete ~10 KiB subsystem is not qualified. The desktop run's peak process
RSS was **100,503,552 bytes**. Construction samples alone occupy 1,048,576 bytes
and a pooled generated array 8,388,608 bytes. The eight refits took **0.073 CPU
seconds**, and the comparison took **1.87 CPU seconds** excluding controls and
the subsequent audit on this host. These are offline builder measurements,
not streaming or Cortex-M23 timings.

Next, diagnose the remaining distribution-shape and coupling residuals,
including whether the inherited nonnegative precision restriction explains
them. Then qualify posterior ownership and physical transport for a causal
rolling comparison. Source histories here are only **0.229/0.914 seconds**;
aging, four-hour trajectories, accumulated compression error and deployment
workspace remain unqualified. The rolling estimator is unchanged.

Reproduce into a new directory (the default saved attempt is exclusive):

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
python3 -B -m experiments.natural_hysteresis_001.compare \
  --output experiments/natural_hysteresis_001/reproduction001
```

Focused controls alone:

```sh
OPENBLAS_NUM_THREADS=1 python3 -B -m unittest experiments.natural_hysteresis_001.test_natural -v
```
