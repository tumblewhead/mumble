# Uncertainty overconfidence: focused diagnosis and repair direction

The production estimator is unchanged. This study compares short controls on
seeds1000 and1006 from the completed196-hour bounded-hysteresis run. Every fit
uses the same first720,000observations (four hours at50Hz), public calibration
and declared prior. Truth enters only post-fit scoring, never objectives,
initial guesses, centering or state correction. The next90,000observations
(thirty minutes) are used solely for predictive checks.

## Results that constrain the repair

| Four-hour method | Seed1000 Q error (%) | Seed1006 Q error (%) |
|---|---:|---:|
|Current rolling,4rounds|+0.04574|+0.60089|
|Rolling,12rounds|+0.50630|+0.25234|
|Rolling,32rounds|+1.44424|+0.03240|
|Condition first, re-evaluate physical transport|+0.04477|+0.60349|
|Retained-observation nonlinear fit|−0.07366|+0.03231|

Increasing the iteration limit is not a reliable repair: it helps one seed and
harms the accurate control. Re-evaluating the outgoing physical state and its
joint Jacobian at the conditioned mean has negligible benefit here. That
candidate preserves all cross terms and counts each observation once, but is
not promoted. Its stage0 reproduces the saved C library's final messages exactly
on both binary64 controls; the context remains19416B in both stages.

The retained fit uses the public prior once, not the rolling posterior plus the
same data. For seed1006 its capacity error falls about18.6-fold, and SOC error
falls from0.17525points to0.00802points. Its three-SD Q width is0.18088%, versus
0.13303%for rolling. Thus the problem includes a displaced estimate, not just
a missing scalar multiplier on the covariance. Both retained-fit Q errors are
within1.1local standard deviations; this is not validated coverage.

Both retained fits stop with `no_descent`, not the configured gradient tolerance.
A separate local check finds predicted remaining GN cost improvements of
1.91e-10and3.05e-11, comparable to a cost ULP of5.82e-11. This supports near-local
stationarity at the attained solutions, not a global optimum or exact posterior.
See [retained/rounds comparison](attempt001/result.json) and
[local stationarity/future prediction](predictive001/result.json).

On the unused next30minutes, the retained fit improves the local joint Gaussian
predictive NLL by92.82and559.08relative to rolling4rounds for seeds1000and1006.
The calculation includes cross-time covariance through a low-rank Woodbury
calculation; it does not treat marginal predictive intervals as independent.
Mean forecast residuals change from+1.028mV to−0.052mV on seed1000, and from
−1.335mV to+0.030mV on seed1006. No truth is loaded for this predictive calculation.

Delayed retirement is also seed-dependent and nonmonotone. Windows of64,256,
1024and8192records all finish the four-hour controls; only8192places both tested
Q/SOC errors within their local three-SD bands. Its raw window alone costs
327680B (320KiB), before Jacobians, optimizer and history. This is a useful
comparison, not a firmware repair or a selected production window size.
See [window controls](windows001/result.json) and
[transport candidate](transport001/result.json).

## What the evidence suggests

The current message preserves the local quadratic it was given, but that
quadratic is anchored at earlier parameter estimates. Moving or transporting a
quadratic does not reconstruct the original nonlinear observation likelihood.
The controls implicate nonlinear/path-dependent approximation; they do not yet
isolate one unique defect or prove that every covariance error has this cause.

On common supported identifiable coordinates, write the exact and compressed
negative log likelihoods as

```
L(theta) = L_hat(theta) + E(theta)
E(theta) = accumulated likelihood and state-transport approximation error
```

At a compressed stationary point, the exact gradient includes grad(E). Where
local curvature is nonsingular, the first-order displacement is approximately
`-(H_hat + Hess(E))^-1 grad(E)`. Reporting only `H_hat^-1` omits both that
possible displacement and curvature error. This is a local error model, not a
certificate on the actual lifetime error. It motivates preserving a likelihood
that can be re-evaluated, rather than inflating independent parameter variances
or adding an unphysical decay rate.

## A concrete conditional packet prototype

This adapts the earlier
[partitioned closure derivation](../partitioned_battery_closure_001/README.md)
to the currently specified linear OCV and temperature-dependent Foster model.
It does not silently change the old tanh-OCV study.

Use five conditioning coordinates

```
phi = (tau1_ref, tau2_ref, tau3_ref,
       gamma_plus_ref / Q_ref, gamma_minus_ref / Q_ref)
```

and eleven amplitudes

```
a = (z0, v10, v20, v30, 1/Q_ref, R0_ref, R1_ref, R2_ref, R3_ref,
     H_ref, B0=H_ref*h0)
```

At fixed phi, the measured-current/temperature recurrence gives
`V_k = OCV_intercept + beta_k(phi)^T a` exactly for this stationary physical
model. SOC is affine in reciprocal capacity; each RC response is affine in its
initial voltage and resistance; hysteresis is affine in B0 and H at fixed
throughput rates. Known Arrhenius factors stay in beta. No truth or test-rig
logic enters the likelihood object.

QR of weighted rows `[beta_k, OCV_intercept - V_measured]` gives a12-by-12
upper-triangular factor with78entries. It preserves every amplitude cross term,
residual normalization and the prior-free likelihood. The outgoing amplitude
map has only nine nontrivial coefficients. Adjacent packets compose through the
entering-state map; source chronology, rate coordinates and calibration must
match. Signed-charge extrema preserve all-prefix SOC support. The H/B support
constraint remains coupled: `|B| <= H`.

[conditional_packet.py](conditional_packet.py) implements this fixed-rate
numeric prototype. Three targeted algebra tests compare repeated amplitude
queries and chronological compositions with the independent C-model evaluation,
including temperature changes, polarity reversals, rest and zero durations.
All tests pass. The full campaign/regression suite passes48tests.

This is a likelihood object, not a posterior or a repaired production history.
The original joint prior must be retained under the coordinate transformation,
including its measure and correlations; it cannot be replaced by independent
Gaussian amplitude/rate priors. Integrating uncertain rates can couple every
amplitude, even though the conditional likelihood is quadratic.

Estimated packed numeric storage, binary64:

- 78 factor entries: 624 B per rate point.
- Five conditioning values and nine transport coefficients:112B per point.
- Normalizer, two signed-charge extrema and count:32shared bytes.
- One point: 768 B; eight points: 5920 B; sixteen points: 11808 B.

These estimates exclude metadata, the prior, solver workspace and the rolling
window. The Python prototype allocates temporary rows and is not an SRAM-bounded
implementation. No number of rate points or codebook is selected. A single
point cannot represent uncertainty in phi or be regenerated at new rates after
raw samples are discarded. The earlier nonclosure result still applies to
arbitrary histories; useful bounded-error approximation remains necessary.

## Next repair gate

Build a re-evaluable likelihood/state-transport representation across the five
uncertain rate coordinates, using the measured field dependencies and the
existing residual-to-likelihood error framework. First compare its evaluations
and joint Q/SOC uncertainty with the retained-observation reference, then test it
alongside the continuous rolling estimator on all eight seeds. Keep source
ownership, original prior/support and compression-error accounting explicit.
Only promote after this comparison; do not tune an uncertainty multiplier,
iteration limit or window length against the two truth errors here.

The current estimator remains the stable owner-run baseline. The source data,
original results and frozen kernels are unchanged. [summary.json](summary.json)
contains compact outcomes, resource estimates and qualification limits. Large
inputs and generated shared libraries remain local.
