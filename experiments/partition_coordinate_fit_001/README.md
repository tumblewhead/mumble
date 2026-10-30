# Partition coordinates and normalized fitting: the matched comparison

All three proposed actions are implemented for an offline comparison:

1. Physical transport views and probability coordinates are defined separately,
   with exact inverses/Jacobians and tests of the linked physical operations.
2. All sixteen quantities remain in one joint conditional mixture. Component
   weights, source intervals and inherited prior ownership are preserved.
3. Current versus partition-specific coordinates are crossed with moment
   projection versus fitting the normalized bounded density, at both saved
   prefixes. The repaired run completes all **eight cases and39numerical tests**.

**Retained numeric storage is2,496B for every tested two-component message.**
The equivalent four-component formula is4,960B, not tested here. These are
about2.5/5.0kB, excluding metadata, solver state, queue, stack and working memory.
The implemented constructor still needs over2MiB of arrays and is not an
SRAM-only streaming update.

The specialized coordinates improve fast load predictions; normalized fitting
substantially reduces predictive mean shifts. The combined variant is the best
held-out joint-density score in this finite comparison, but its hysteresis-rate
fits remain iteration-limited. This is progress in representation, not a
deployment, coverage or long-duration qualification.

Evidence: [derivation](derivation.md), [frozen plan](plan.json),
[repaired results](attempt002/result.json), [controls](attempt002/controls.txt),
[original run](attempt001/result.json), and
[separately recorded arithmetic adaptation](numerical_adaptation.json).

## Separating transport from inference coordinates

Transport uses inverse capacity with carried SOC, the exact tanh/Möbius OCV
update for this illustrative curve, chronological affine RC operators, and
directional hysteresis log-distance/affine operators. The log-distance view
rejects hysteresis saturation; the affine operator remains valid there. The
derived H*h product is never given an independent prior or inverted by dividing
by H. These controls include changed capacity between intervals and reversals;
they test conditional physical identities, not an aging transition law.

The specialized probability chart uses Cayley-transformed positive RC rates,
physical hysteresis rates, inverse capacity, and physical R0/H/h coordinates.
The previously useful F/G RC response and boundary-voltage coordinates remain.
Each physical scalar is scaled on its declared public support; it is not sent
through another logit that would undo the proposed change.

The current chart remains as a control. Its original full9 Gaussian over base
coordinates is refactored into scalar conditionals without changing its joint
density. A saved-battery density parity check passes at both prefixes, in
addition to synthetic tests. All conditionals in both charts depend on all
preceding coordinates; physical partitioning does not imply independent fits
to separate copies of measured voltage.

The experiment fixes two capacity-partition components and the public mode-scale
RC response frame. Previous organization/count studies did not establish a
consistent benefit from more regions. Holding that organization fixed lets this
experiment distinguish coordinate effects from objective effects.

## The four-way result

At32records, noiseless predictive voltage standard deviations are:

| Coordinates / fitting | Load1/35s | Load0.1s | Load1s | Load10s | Reversal10+10s |
| --- | ---: | ---: | ---: | ---: | ---: |
| Saved reference | **0.600mV** | **0.680mV** | **3.070mV** | **16.373mV** | **23.117mV** |
| Current / moment projection | 1.014 | 1.271 | 3.220 | 16.138 | 24.274 |
| Current / bounded fit | 1.015 | 1.262 | 3.294 | 16.236 | 25.003 |
| Specialized / moment projection | **0.578** | **0.741** | 2.975 | 16.056 | 23.502 |
| Specialized / bounded fit† | **0.571** | **0.737** | **3.082** | 15.871 | 24.460 |

†The two hysteresis-rate conditionals in each component remain iteration-limited.
Their finite final parameters are used for evaluation with that status retained.
All other specialized bounded conditionals meet the registered first-order
tolerance. Values below the reference are not automatically better: a narrower
distribution can understate uncertainty.

Specialized coordinates repair much of the short-time spread that the previous
RC-response change alone did not repair. Bounded fitting mainly improves mean
shifts rather than every standard deviation. At32records, the one-second load
mean discrepancy relative to the reference changes from−0.414mV (current
projection) to−0.119mV (current bounded fit), −0.289mV (specialized projection),
and **−0.015mV** (specialized bounded fit). The last variant still has
**+0.772mV** mean discrepancy at ten seconds and **+1.873mV** after the long
reversal. Those remaining differences prevent a full fidelity claim.

At8records, specialized bounded fitting gives a one-sample load SD of2.664mV
against2.675mV, and a one-second load SD of16.713mV against16.728mV.
Long reversal SD remains37.173mV against34.018mV. The public stimulus and finite
reference do not establish that any transform is universally ideal.

Mean held-out log-density improvement over the current moment-projection
control, in nats per current-state sample:

| Variant | Eight records | 32records |
| --- | ---: | ---: |
| Current / bounded fit | 0.204 | 0.149 |
| Specialized / moment projection | 0.092 | 1.248 |
| Specialized / bounded fit† | **1.038** | **2.102** |

These are comparable physical-coordinate densities with full Jacobians. They
are not observation NLL residuals, absolute KL bounds or a new acceptance
threshold. Scores are retained separately for both held-out populations.
SOC/Q/R0 means, covariance and quantiles are also retained; for example,
specialized bounded R0 SD at32records is0.02268ohm versus0.02249ohm in the
reference, compared with0.03354ohm for the current projection. This factorial
changes several coordinates together, so it does not uniquely attribute that
improvement to one scalar transform.

## Fitting and the numerical repair

Moment projection fits unbounded regression and then normalizes on physical
support. Bounded fitting includes that support normalizer in every coefficient
and scale derivative. QR whitening and residual scaling use construction
samples only and are inverted before storing coefficients. No regularizer,
covariance repair, truth-based centering, extra prior or held-out optimization
was introduced. Component memberships/weights stay fixed: this is not EM or
a claim of globally optimizing the overlapping mixture likelihood.

The first frozen run uncovered an arithmetic gap in the inherited erfc branch.
At a standardized Gaussian interval[38.4,38.5], nonzero but subnormal tail
values had too few relative bits; log-mass error reached about0.06822 before
underflow finally triggered the existing accurate scaled fallback. This caused
line-search failures in physical hysteresis-rate fits. Earlier40-sigma controls
already took the fallback and therefore missed the transition region.

The repair selects the existing scaled integration whenever the direct erfc
mass is subnormal, as well as retaining the previous cancellation guard. It
changes arithmetic, not the distribution or fit settings. New controls cover
both tail signs near that transition and the complete objective derivative
there. The recorded repaired log-mass discrepancies are at most2.28e-13 on
those witnesses. [Tail-control receipt](attempt002/tail_control.json)

The original source and attempt001 remain unchanged. A documented process-local
normalizer substitution in [compare_repaired.py](compare_repaired.py) runs the
same plan into attempt002, binds the new source identities and preserves the
first result's hash. Optimizer caps, data, initialization, region count and
physical probes are unchanged.

After repair, **120 of128 bounded conditional fits reach first-order stationarity**:
all64 current-chart fits and56of64 specialized fits. The remaining eight are
exactly the two directional hysteresis rates in each specialized component at
each prefix. They hit the frozen128-iteration limit. Thus the arithmetic defect
and the remaining parameterization/convergence issue are separate findings.

## What the unresolved hysteresis fits suggest

For a normalized physical-rate coordinate `y in (-1,1)`, the same bounded
Gaussian can be written in natural parameters:

```
p(y | preceding coordinates) proportional to exp(eta*y - k*y*y/2),
eta = mu/sigma^2,   k = 1/sigma^2.
```

The unresolved fits have large unbounded means/scales while their natural linear
coefficients remain moderate. Their quadratic coefficient magnitudes are only
about0.00049–0.00108. For these fixed coefficients and fixed conditioning values,
removing the quadratic term changes normalized log density by at most that
magnitude on `(-1,1)`, since `0 <= y² <= 1`. This demonstrates proximity to a
bounded-exponential shape; it does not prove that the fitted limit is optimal.

The next focused repair is to fit these bounded conditionals in natural
parameters and represent the `k=0` exponential limit explicitly, with constrained
stationarity checks. This avoids needing divergent Gaussian means/variances to
describe a finite supported density. It requires the same number of retained
coefficients. Keep the current frozen comparison and all prediction horizons;
do not enlarge region memory or treat nonconverged nuisance fits as known.

## Storage, work and scope

The tested core is136conditional mean coefficients+16log scales+1log weight per
component, all binary64. Two components, three interval edges and three response
timescales total **2,496B**; four would total **4,960B**. Fixed chart constants
can be compiled into ROM. These leave7,744B or5,280B of a10,240B total budget
before all metadata and subsystem/workspace needs. The counts do not establish
a complete firmware fit.

The desktop builder retains over2MiB of construction/coordinate arrays. A single
largest BFGS matrix alone is17×17doubles,2,312B, before its other simultaneous
arrays; this is additional construction workspace, not retained history.
The repaired process peaked at **95,703,040B RSS** and used **49.11CPU seconds**
for eight cases, excluding controls. It evaluated8,791,379 construction-objective
sample rows,65,536held-out density points,256serialization checks and6,815,744
predictive sample-steps. Scaled tail integrations make the specialized limiting
fits relatively expensive. No streaming or Cortex-M23 speed claim follows.

The saved references still cover0.229/0.914seconds and have finite moment checks,
not validated density/coverage. Reusing their held-out populations tests this
predeclared hypothesis; it is not a new independent campaign. No observation
history was compacted online, no aging law was changed, and the four-hour causal
gate remains open. The deterministic transport identities qualify the linked
views only; they do not supply a full bounded-memory history update.

Reproduce the repaired comparison into a new directory:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  python3 -B -m experiments.partition_coordinate_fit_001.compare_repaired \
  --output experiments/partition_coordinate_fit_001/reproduction001
```
