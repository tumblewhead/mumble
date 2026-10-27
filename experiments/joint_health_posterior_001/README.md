# Full joint desktop posterior reference

The aging model now has a working **full joint posterior sampler**. All nine
static parameters, five current physical states and two current health quantities
remain uncertain and correlated. Complete candidate health paths are retained
and integrated through particle samples. This is a desktop reference qualified
on short fabricated inputs, not a long-duration aging result or MCU estimator.

The stationary and dynamic posterior comparisons pass the registered finite
checks for means, covariance, percentiles and evidence. Four independent runs
at **2,048 particles** are compared with four at **4,096 particles** for each
query. All eight planned qualification areas are now covered through the
preserved second development run and an explicit completion. The development
failures remain failures in their original receipts.

## Solver and numerical contract

[model.py](model.py) evaluates the full retained-prefix density in an initial
public-scale chart and Gaussian health-innovation coordinates. It keeps the
original two-component capacity prior, support, every valid observation and
each health-transition normalizer. Deterministic health coordinates are removed
exactly. Original prior and observations appear once; no posterior is appended
as extra evidence.

[smc.py](smc.py) gradually introduces the likelihood, resamples particles, and
applies joint symmetric Metropolis moves. The proposal covariance is fixed
within each stage. This follows the general
[SMC sampler framework of Del Moral, Doucet and Jasra](https://www.stats.ox.ac.uk/~doucet/delmoral_doucet_jasra_sequentialmontecarlosamplersJRSSB.pdf).
The paper supports the method family, not this implementation's accuracy.
Initial particles come from the declared bounded prior; there is no truth or
optimized initialization.

[posterior.py](posterior.py) exposes `solve(records, profile, study)`. It computes
separate predictions with the last voltage masked and posteriors with that
voltage included. Reports contain current-state means, joint covariance,
5/50/95 percentiles, Monte Carlo errors, capacity-mixture mass, evidence
ownership and separate health prediction/correction/variance changes.
Covariance includes the original16 current coordinates and derived physical Q;
the extra Q column is not a seventeenth independent state.

Weight ESS and surviving ancestor counts are diagnostics, **not independent
posterior sample counts**. Adequacy uses independent populations and doubled
particle count. Failed gates produce `uncertainty_unresolved`; they do not
silently substitute a local Gaussian. The small end-to-end API test exercised
this unresolved result. These tests provide finite numerical evidence, not a
global convergence proof or calibrated uncertainty coverage.

## Results and preserved failures

| Evidence | Outcome |
| --- | --- |
| Vectorized density versus qualified scalar path kernel | Maximum difference 4.36e-11 NLL, including the coordinate Jacobian |
| Original bounded prior | 32,768 draws agree with independent one-dimensional quadrature controls |
| Analytic correlated Gaussian posterior | Means/covariance and numerical adequacy pass |
| Analytic two-component posterior | Relative integrated component masses and moments pass |
| Bounded scalar resistance posterior | Means/covariance agree with independent tensor quadrature |
| Full16 stationary posterior | Final refinement checks pass; maximum percentile shift 0.124 posterior SD |
| Full16 dynamic prediction | Checks pass; maximum mean MCSE 0.0221 posterior SD |
| Full16 dynamic conditioning | Checks pass; maximum mean MCSE 0.0284 posterior SD and percentile shift 0.107 posterior SD |
| Error paths | Source order, gaps, exhausted resources, sampling failure and inadequate particle counts remain explicit |

The dynamic fixture contains four intervals totaling **0.57 seconds** with
declared voltages and artificial diffusion rates. It is an implementation
control, not a simulated cell-aging study. All16 current-state variances remain
nonzero. The final capacity mean is about 60.78 mAh with posterior SD about
18.25 mAh: this tiny stimulus does not determine capacity. Its final-voltage
capacity correction is 0.253 mAh, smaller than its 0.366 mAh estimated Monte
Carlo error. Resistance correction is about 0.01346 ohm with Monte Carlo error
0.00163 ohm, conditional on the selected model. Neither identifies a physical
aging mechanism.

The [boundary report](qualification/completion001/boundary_report.json) contains
the full covariance and uncertainty/change fields. Predicted health increments
compare the last two boundaries under the predictive path posterior, conditional
on valid physical support. Very small increments and variance differences can
remain numerically unresolved even when the overall marginal checks pass.

Execution history is deliberately explicit:

1. [Development001](qualification/development001/receipt.json) failed its
   stationary polarization-tail refinement check: 0.478 SD versus the 0.3 limit.
   Late-stage proposal acceptance was about 3%. Seven other cases passed.
2. [The registered revision](development_review.json) reduced proposal size,
   doubled mutation steps and particle counts, and kept every adequacy threshold
   unchanged. [Development002](qualification/development002/receipt.json)
   passed the stationary case and the other six completed case reports. Its
   dynamic case stopped at the suite resource limit. Accounting occurred after
   a population, so actual work reached **201,106,285 steps against a 200M cap**.
   Forty-six refinement population artifacts were saved; one computed population
   was not captured and the final one had not run.
3. The separately [registered completion](completion_plan.json) preserved all
   saved populations, recomputed the one uncaptured population and ran the one
   missing population. It also exercised the public API on a small control.
   It reserved work before those launches: **31,759,360 conservative steps
   within a 50M cap**. [Completion passed](qualification/completion001/receipt.json).
   Its dynamic report combines14 bound saved populations with two new artifacts;
   no passing inference was silently repeated or selected out.

The three workers used about **115.0 CPU seconds in total**, with peak worker
RSS below65 MB. These include the failed work. They are qualification costs,
not a long-history throughput measurement. Final evidence comprises seven
passing development002 case reports (243 checks) plus seven completion checks;
the failed original assertions and receipts are not relabeled.

## Use and next work

The Python API accepts the same immutable `Record` and explicit eight-rate
`Profile` as the qualified kernels. For example, from the repository root:

```python
import sys
sys.path.insert(0, "experiments/joint_health_posterior_001")
from model import k
from posterior import solve

records = (k.Record("example", 0, 0.03, 0.02, 3.858),)
profile = k.Profile((0, 0, 0, 0, 0, 0, 0, 0))  # Explicit stationary control
result = solve(records, profile)
print(result["report"]["posterior_numerical_status"])
```

The caller must retain input/configuration identity and bound total runtime,
memory and output. `Study` bounds paths per population; the historical
qualification supervisor's suite-step cap was not a prospective total guard.
The completion demonstrates explicit conservative reservation. `run.py` and
the original plan remain historical reproducers, including that limit failure;
do not rerun the full study merely to resume. Use the saved-evidence verifier
for routine provenance and gate checks.

```sh
python3 -B experiments/joint_health_posterior_001/verify.py
```

This checks310 bound evidence files and recomputes all six final refinement
comparisons from saved populations, with no new sampling or model steps.

Next register a small progression of longer prefixes and measure mixing,
numerical adequacy, runtime and memory before extending duration. The full-path
dimension grows with every stochastic health interval; the current solver makes
no long-duration efficiency claim. Sample-moment checks do **not** establish
the compressor's 0.1 NLL message-contrast gate. That comparison, physical rate
calibration, varied cell/load/noise/duration robustness and Cortex-M23 execution
remain separate work. Deployment history stays SRAM-only within the complete
10,240-byte target. Original kernels and historical experiments are unchanged.
