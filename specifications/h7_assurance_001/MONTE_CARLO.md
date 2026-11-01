# H7 Monte Carlo assurance design

Status: proposed design, not a launched campaign or a certification. The current
reference is commit `92e4716`; the 720-hour evidence and selected late-SOC
witnesses are development data. Implementation of randomized scenario generation,
coverage telemetry and the final frozen population manifest remains to be done.
No broad simulation is authorized implicitly by this plan.

The default assumption is an engineering test envelope around the current models
until measured cell-family distributions are supplied. Results then describe
that declared synthetic population, not a prevalence estimate for real batteries.
See [conditional proofs](PROOFS.md) and [sample-size calculations](power.json).

## 1. Claims before counts

Separate four questions:

1. Does the implementation preserve its evidence, domain and numerical contracts?
2. Does it produce useful Q/SOC and proposed-load voltage estimates under declared
   informative stimulation, and remain explicit about weakly identified quantities?
3. Do reported intervals behave appropriately across independent trials?
4. Does an optimized implementation preserve the reference's useful behavior
   within a specified joint approximation budget, at lower measured target cost?

Passing one does not establish the others. In particular, a 3SD crossing is not
itself a defect: correctly calibrated marginal intervals have nonzero tail
probability. Zero crossings are not the acceptance objective. Many successive
crossings in one trajectory are correlated observations, not independent failures.

## 2. Three complementary experiment lanes

**Exploration and interactions.** A proposed first design is 20 distinct cell
parameter draws × 20 distinct load recipes × 3 independent noise realizations,
1,200 cases. Use a predeclared mixture of informative and weak-use recipes.
Start with a small generation/replay pilot before committing this matrix.
Seventy-two hours is useful for screening, but cannot qualify late behavior;
the known 473/712-hour witnesses make that limitation explicit. Preselect a
balanced long-duration subset independently of screening outcomes. Failure-driven
extensions are additional diagnostics, reported separately from that subset.

Use crossed cell/load identifiers and nested noise replicates for variance and
interaction analysis. Estimate uncertainty with a suitable crossed random-effects
model or multiway cluster procedure, including its diagnostics; ordinary iid
resampling of all rows is not valid. With only 20 cell draws, population-tail
claims about rare cell failures remain weak. Increasing to 20 noise realizations
per pair gives 8,000 runs but does not create 8,000 independent cell draws.

**Independent confirmation.** Freeze a scenario distribution and draw a fresh
cell, load recipe, temperature recipe and noise realization independently for
each complete scenario. Keep different latent quantities on separately derived
RNG streams. This lane supports binomial scenario-level risk statements. Pair
the reference and any candidate on identical exogenous random streams, using
scenario as the statistical unit. The initial candidate is frozen H7 itself.
A repeated cell or shared load introduces dependence and belongs in the first
lane unless the inferential target and conditional analysis explicitly account
for it.

**Challenge and model discrepancy.** Separately exercise boundaries, weak/rest
use, abrupt temperature changes, rate extremes, nearly overlapping poles, ADC
outliers, current offset, correlated noise, sensor drift and monotone aging.
These deliberately selected cases search for violations. They have no population
frequency interpretation unless an explicit mixture distribution is registered.
Keep matched-model calibration separate from model-discrepancy resilience.

## 3. Candidate engineering envelope

Updated owner guidance: nominal capacity is 60 mAh, with approximately
2.6–3.6 mAh variation. Whether that describes standard deviation, a plus/minus
bound or total spread is pending clarification. That is a much narrower primary
capacity population than the broad challenge envelope below. Keep these distinct;
do not infer a Gaussian distribution or convert a spread into variance without
specifying its meaning. If it denotes SD, 2.6/3.1/3.6 mAh can be three sensitivity
assumptions, rather than an unsupported mixture claimed to be measured reality.

Before execution, materialize and hash the exact distributions, bounds,
correlations, rejection rules and mixture weights. The following is a concrete
starting proposal to review against the harness, not an already implemented law:

- Cells: use the owner's capacity guidance for the primary Q population once
  clarified. For other quantities, an equal mixture around the existing A/B
  physical anchors with scale multipliers in [0.7,1.3] is an engineering proposal;
  a separate boundary challenge uses [0.5,1.5].
  Sample positive R and RC capacitances jointly, respecting tau=RC, ordered
  poles and approximate logarithmic spacing. Do not independently draw R, C and
  tau as though all three were free. A declared common health coordinate can
  correlate R increases with Q/C decreases. These bounds are engineering choices,
  not certified aging limits or empirical probability distributions.
- Pole coverage: vary the overall time-scale span and the approximately log-spaced
  positions, with 0.85–1.15 placement jitter as a candidate. Record any validity
  conditioning. Test pole overlap separately rather than accidentally excluding
  it through fit failures. Check ordering throughout the temperature envelope.
- Initial state: randomized SOC, polarization and hysteresis over a declared
  physically realizable preconditioning process. Prefer a public prehistory
  recipe to independent arbitrary initial RC voltages. The estimator's common
  public prior must not be recentered at the generated truth.
- Loads: stratify embedded activity, varied CC/CV cycles, multi-scale pulses,
  reversals, long weak-current episodes and long rests. Vary semi-Markov dwell
  distributions, activity intensities, duty cycle and peak current, not just RNG
  seeds of one fixed recipe. Express charger C-rates using a declared public
  nominal capacity; do not leak the generated true capacity to the estimator.
- Temperature: independent phase, mean, amplitude and period within the admitted
  known-thermal domain; additional thermal-model mismatch belongs to challenge
  testing. Temperature history and parameter temperature dependence are distinct.
- Noise: vary both realization and physical model/level. Candidate matched levels
  include 0, 0.5, 2 and 5 mV analog noise with the actual ADC quantizer. Zero analog
  noise is not zero measurement uncertainty. Bias, correlation, impulsive noise
  and current uncertainty form separate mismatch strata. Reusing a seed across
  cells is useful for paired analysis but is not an independent realization.
- Rate: hold 50 Hz for the first reference confirmation, then independent rate
  strata at 35 and 100 Hz. Preserve dt=1/Fs and actual intervals; do not change
  retirement cadence accidentally while calling it a pure sample-rate test.

Admissibility checks must run before fitting and log every rejected draw with its
reason. Distinguish generator-invalid draws from estimator failures on valid
inputs. Do not silently regenerate until an estimator survives. A draw inside
physical scope but outside H7's declared feature support is an unsupported case,
not permission to clamp truth or widen the prior after observing the result.

The current harness supports custom cells and load/noise seeds, but does not yet
provide all these distributions, independently randomized Arrhenius laws, aging,
current measurement error, or a complete uncertainty telemetry contract. These
are implementation work items. In particular, changing a cell file alone does
not create varied semi-Markov transition/dwell laws.

## 4. Primary outcomes and time semantics

Proposed practical targets reuse the application preference: 0.5% relative Q
error and 0.5 percentage-point SOC error. These are engineering requirements,
not mathematically derived thresholds. Register initial acquisition separately
from sustained performance. Before confirmation, specify an informative
acquisition protocol and fixed acquisition deadline using pilot evidence; do
not select a burn-in retrospectively for each successful trajectory.

Define one primary scenario-level failure indicator as the union of numerical
fatality, lost/duplicated evidence, unsupported physical state without the
required explicit response, or a sustained-phase Q/SOC target violation under
the registered informative-use contract. Keep the components separately visible.
A scenario with insufficient stimulus must not be credited with accurate Q
identification solely because its prior happens to be close. The weak-use lane
scores retention, uncertainty and explicit unresolved behavior. Requirements
for that unresolved classification are not yet fully implemented.

Report per-scenario maximum error, time-in-tolerance, acquisition time (including
right-censored failures), tail quantiles, error versus time and stimulus phase,
refresh acceptance, local precision, status and resources. A crash is a failed
scenario for the primary numerical reliability objective, not missing data.
For interval coverage after a failed run, report inability to return a valid
interval as a separate failure and use a predeclared conservative composite
where necessary; never analyze successful survivors alone.

Primary uncertainty queries should be at one prespecified horizon (proposed
720 h), separately for Q and SOC. Report 50%, 80%, 95%, 99% and 99.73% marginal
interval diagnostics, signed standardized errors and joint projections; use 95%
Q/SOC coverage for the first powered primary tests. Also preserve the fixed
72/144/360/720 h trajectories as secondary longitudinal diagnostics. Repeated
horizons do not multiply the number of independent scenarios.

Joint uncertainty needs independently prespecified physical/task projections,
including proposed-load voltage minima, and appropriate joint diagnostics. A
chi-square score is calibrated only under its distributional assumptions. Do
not diagonalize the joint covariance for scoring. Brownout safety requires a
separate declared horizon, voltage threshold/margin and tolerated false-admit
probability; these have not yet been specified and cannot be inferred from RC
parameter error alone.

## 5. Sample sizes with an explicit interpretation

For n iid scenarios and zero failures, the one-sided 95% upper bound on scenario
failure probability is

    p_upper = 1 - 0.05^(1/n).

It follows by inverting Pr(K=0)=(1-p)^n. To place the upper bound below 1%, 0.1%,
or 0.01% requires respectively 299, 2,995 or 29,956 zero-failure scenarios.
With 20 independent units the bound is still 13.91%. This is a risk bound over
the registered scenario distribution and horizon, not a lifetime failure rate.
With failures, use the exact binomial interval rather than a zero-event formula.
See [NIST's exact interval construction](https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm).

A reasonable *proposed first confirmation* is 500 iid 720-hour scenarios. It
supports a practical 1% risk objective: at most one primary failure rejects
risk >=1% at one-sided 5% size (P(K<=1 | p=.01)=0.03975). Complete all 500;
do not stop early after a favorable prefix. This is one composite primary
endpoint; separate simultaneous component claims require a multiplicity plan.
Population/generator fixes after inspecting results create a new confirmation
set rather than reusing these outcomes as fresh validation.

500 scenarios are not enough for a tight coverage certificate. As an explicit
planning example, test the null that nominal-95% coverage is <=94%, separately
for Q and SOC, with Bonferroni per-test alpha=.025. Exact binomial calculations
in [power.json](power.json) give approximately:

| Independent scenarios | Power if actual coverage is 95% |
|---|---:|
| 500 | 12.7% |
| 2,000 | 48.6% |
| 3,000 | 65.1% |
| 4,000 | 77.8% |
| 5,000 | 87.1% |
| 8,000 | 97.5% |

Thus 5,000 fresh iid complete scenarios is a defensible candidate if the desired
claim is ruling out a one-percentage-point undercoverage at useful power. It is
not a default request to run them now. The 94% floor is an explicit proposed
engineering tolerance and must be agreed/frozen; the theorem does not select it.
This test alone permits overly wide intervals, so report sharpness and add a
separately powered overcoverage/equivalence requirement if full calibration is
claimed. More parameters, horizons or subgroup claims consume additional error
budget and require recalculation. Rare 3SD tails need more evidence than central
95% coverage; observing zero H7 misses is not proof of correct calibration.

Freeze primary decision rules before results. Use a fixed budget or a valid
sequential design with its own error-spending/confidence-sequence argument.
Adaptive exploration may inform a later independent confirmation, not rewrite
its rules midway. Keep independently generated holdout cells and load recipes
out of basis selection, quantizer training and threshold tuning.

## 6. Bayesian calibration lane

For a true posterior claim, add a separate prior-predictive calibration lane.
Draw initial parameters/states from exactly the inference prior and support,
generate with the matching likelihood and sensor/feedback model, and evaluate
marginal ranks/intervals and joint projections over independent datasets.
[Simulation-based calibration](https://arxiv.org/abs/1804.06788) provides the
relevant framework; it validates inference relative to the chosen generative
model, not the physical adequacy of that model.

This lane is not ready merely because the current engineering simulator runs.
H7 uses a local Gaussian readout and a finite feature domain; its effective
support must be specified. The present rounded analog measurement model and
Gaussian variance-matched likelihood are not identical. Confirm prior/support,
policy conditioning and likelihood equivalence before labeling a result SBC.
Engineering-population coverage and matched-prior calibration must stay distinct.

## 7. Execution and evidence budget

First implement a reproducible generator/manifest, explicit outcome reducer,
per-horizon full joint snapshots and scenario-level confidence analysis. Run a
small smoke pilot, then exploration, then freeze the confirmation manifest and
source. Optimize recording before a huge campaign: online counters and compact
bins, selected joint snapshots and deterministic replay recipes; avoid full
trajectories. For large campaigns, generate detailed plots only for prespecified
sentinels and diagnostics rather than thousands of dense PDFs. Preserve failure
metadata for every case. Original data remain local and ignored by Git.

A full 20×20×20 matrix at 720 h is 5.76 million simulated cell-hours and
1,036,800,000,000 samples at 50 Hz per estimator arm. Estimate wall time and
storage from a pilot on the user's hardware, including failing/slow cases;
do not extrapolate only fast successful scenarios. Maintain independent load,
noise, temperature and cell streams with stable scenario IDs so changing jobs
or ordering cannot change a trial. Gate replay equality on selected snapshots.

Only the diagnostic windows have been executed in this step. No Monte Carlo
campaign or production optimization has been launched.
