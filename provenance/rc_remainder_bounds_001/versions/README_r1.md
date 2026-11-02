# RC response error can be bounded independently of duration

We have closed the missing stationary RC derivative-envelope premise of P1.
For bounded supplied current and fixed branch parameters/initial-state coordinates,
the third and fourth log-tau response derivatives have explicit bounds independent
of elapsed time, sample count and minimum interval. This qualifies the mathematical
Taylor/Hermite remainder formulas for that family. It does not qualify accumulated
likelihood, finite-precision lifetime, aging or the complete estimator.

The [registered plan](../../specifications/rc_remainder_bounds_001/README.md),
[P2 response proof](../../specifications/rc_remainder_bounds_001/P2.md),
[P3 inference proof](../../specifications/rc_remainder_bounds_001/P3.md) and
[compact numerical result](result.json) keep these scopes separate.

## What the bound says

For a branch with incoming voltage b, resistance R, bounded current |I|<=Imax,
and fixed-centre offset t=log(tau/tau_c), define

    M3 = 0.42962 |b| + 1.78302 R Imax.

The Taylor2 branch voltage defect is at most M3 |t|^3/6, and its log-tau slope
defect is at most M3 t^2/2, at every elapsed duration in this stationary model.
The constants are conservative exact rationals. Their certificate isolates all
roots of two low-degree polynomials and encloses exponentials with rational series
bounds. It does not infer an envelope from sampled trajectories. A fourth-derivative
envelope also supplies the premise of the earlier Hermite value/slope formulas.

This explains why the previous Taylor improvement was local: its value defect
bound grows cubically with distance from the public centre and its slope defect
bound quadratically. The bound does not say that every particular response attains
these maxima, nor that error necessarily grows monotonically on a particular trace.

## Practical illustration, not an adopted threshold

Using the previous public probe's b=[4,-2,3] mV, R=[0.035,0.07,0.10] ohm and
Imax=30 mA gives branch M3=[3.591,4.604,6.638] mV. If one hypothetically asks for
at most 10 uV summed RC voltage approximation error and 100 uV per unit log-tau
error in each pole's slope, a sufficient common radius is |t|<=0.1593. That is
approximately 0.853 to 1.173 times the original tau centre. These budgets are
illustrative input values, not new battery-accuracy requirements or firmware gates.
The radius applies to these amplitudes; a joint amplitude region requires its
actual amplitude suprema. Rounding also needs qualification before runtime use.

At offset +0.35 the summed voltage bound is 106 uV; at +0.9 it is 1.802 mV.
The preserved finite probe's worst single-branch value defect at +0.9 is 334 uV.
These are deliberately different quantities: a sum of worst-case branch bounds
versus the largest observed individual branch error. The bound is conservative,
and the old regression remains visible. The independent analytic reconstruction
reproduces all seven prior native probe maxima within 2.0e-15 mV.

Being inside an admitted response-error region does not imply that the posterior
is contained there. Being outside does not exclude a physical battery. Neither
discarding mass nor re-centering stored evidence is justified.

## What this means for history and uncertainty

P3 maps the RC bounds to all RC amplitude/rate Jacobian columns and preserves
their coupling to the other physical quantities. At a common parameter anchor,
let eta be the spectral norm of the Jacobian defect expressed in the exact joint
precision metric. If epsilon=2 eta+eta^2<1, approximate precision lies between
(1-epsilon) and (1+epsilon) times exact precision as a matrix inequality. The
inverse bounds and a separate forecast-gradient defect bound then bound local
forecast variance. This is a conditional full joint test, not a diagonal precision
shortcut or a coverage theorem. We have not evaluated this certificate for all
campaign anchors; small voltage error does not ensure a useful epsilon.

For whitened residual r and response defect e, likelihood cost error is exactly
r^T e + e^T e/2. Even a duration-independent per-observation bound can accumulate
with the number of observations. In an abstract two-label Gaussian example, a
persistent defect of 0.001 noise standard deviations gives approximate odds
exp(-N*0.001^2/2) despite equal exact probabilities. At the number of 35 Hz samples
in ten 365-day years, its log odds are -5518.8. This is a counterexample to a general
implication, not a prediction of Taylor behavior or a measured Foster failure.

Thus we have a physical response bound, but not an indefinite-history proof.
Likelihood oscillation, shared hysteresis error and numerical accumulation remain
separate. In particular, the preceding H2 SOC-width ratio of about 0.525 is not
repaired by this work. No arbitrary forgetting, independent-evidence duplication
or support restriction is introduced.

## Validation, resources and next step

Six tests cover exact polynomial/root/exponential certificates, rejected invalid
certificates, chronological derivative recurrences against a separate suffix
expression, constant-current identities, public Taylor remainders, dense joint
precision/forecast inequalities and the likelihood counterexample. Independent
P2 and P3 reviews accepted their conditional statements without required changes.
The separate checker/result review and exact source bindings are recorded in the
final receipt. Numerical tests support implementation; the analytic arguments and
rational certificate establish the stated mathematical bounds.

No estimator, native implementation, runtime gate or campaign default changed.
The candidate still has a 4760 B factor and a 5168 B partial numeric subtotal.
This offline proof work adds zero runtime bytes; complete optimizer, scratch,
calibration, metadata and platform memory remain unqualified.

Next apply P3's common-anchor joint metric to the existing saved study, separating
RC-only and hysteresis-only Jacobian defects and their combination. Compare the
conservative certificate with actual joint precision/forecast discrepancies. This
will show whether the compact RC improvement survives shared uncertainty and
which representation defect should be repaired next. Use the saved finite study;
do not start a longer campaign or insert a runtime gate before that diagnosis.
