# Uncertainty and weak-stimulus experiments

Planning baseline: main `311218a`. Status: **specified, not executed**. This
work changes no estimator, default, physical prior or recorded result. The
promoted field remains the control. [plan.json](plan.json) registers cases,
stages and routing decisions; [inputs.json](inputs.json) locates the preserved
evidence. Numerical experiment tools and new stimuli still need implementation.

The goal is useful Q/SOC estimates and honest joint uncertainty over sustained
use. We retain the existing application targets: 0.5% relative Q error and
0.5 percentage points SOC error. Nuisance RC quantities need not all meet 0.5%.
Small physical error, solver convergence, local precision and validated coverage
are separate outcomes.

## Questions and competing explanations

1. The four low-noise 720-hour field cases have approximately 0.004–0.005% Q
   error but 13–14 local SD error. Is the dominant defect in the likelihood
   approximation gradient, the local uncertainty approximation, the sensor
   likelihood, numerical accumulation, or feedback/state transport?
2. The default cell B balanced-cycle case ends at −1.89% Q error with field and
   +1.67% with rolling after four hours. Is capacity weakly identified, or is
   useful information being lost by approximation or optimization?

Neither observation alone proves its proposed cause. In particular, field bias
measured against truth is not automatically compression error; an exact-data
estimate can also have finite-sample error or a misspecified likelihood.

## Mathematical controls

Let J be the retained-observation objective with the original prior once and
Jhat the compressed objective with that same prior. In prior-whitened coordinates,
at the field fit w_hat:

```
gradient(Jhat)(w_hat) approximately 0
g_defect = gradient(J)(w_hat) - gradient(Jhat)(w_hat)
predicted correction = -H_J^-1 gradient(J)(w_hat)
```

We evaluate both exact objective gradients and local GN curvature, then measure
the actual reference refit. GN is an approximation to H_J, not an exact Hessian.
Finite differences of the analytic gradient along selected joint directions
test the residual-Hessian contribution. These are local checks, not global
uniqueness certificates or exact marginal posterior calculations.
An indefinite observed curvature or a boundary-constrained fit is reported
explicitly; do not turn its inverse into an asserted Gaussian uncertainty.

For weighted residuals r and Jacobians B, write d=r_exact-r_field and
DeltaB=B_exact-B_field. If d=sum(d_j), DeltaB=sum(DeltaB_j), then

```
g_defect = B_exact^T d + DeltaB^T r_field
g_j      = B_exact^T d_j + DeltaB_j^T r_field
sum(g_j) = g_defect
```

This defines an explicit additive attribution convention for RC1, RC2, RC3 and
hysteresis. It retains all interactions with the other voltage components;
contributions can cancel and are not independent variances. OCV/charge and
ohmic response are algebraically exact in the present basis, so they serve as
numerical controls. Confirm that the component sum matches the full defect
within measured accumulation error before interpreting an attribution.

For linear OCV, z(t)=z0-q*A(t), q=1/Q, with
A(t)=integral(I/f_Q(T) dt)/3600. The OCV voltage sensitivity is -OCV_slope*A(t).
After allowing nuisance coordinates to adjust, the local data information is
the squared norm of that weighted sensitivity remaining after projection away
from nuisance sensitivities. Report this projection/SVD and the joint Schur
complement separately from prior precision. Use a rank-revealing calculation
with numerical backward-error diagnostics, not a new physical information cutoff.

Zero net charge does **not** mean zero capacity information. Repeated small
excursions can accumulate information; they can also be difficult to distinguish
from hysteresis and RC response. Conversely, if I is identically zero from the
initial sample, these equations are independent of Q and directional gamma.
With the current independent Q prior, the retained-data Q marginal must remain
that prior. Test likelihood invariance directly. Rest after earlier excitation
is different: relaxation and joint state correlations may legitimately update Q.

## Stage 0: reproduce and align the evidence

Use the preserved 720-hour run, load seed 7, noise seeds 1100 and 1103 at 2 and
20 mV (cases 0000, 0002, 0004, 0006), plus the four-hour cell B / 35 Hz / cycle /
4 mV / seed 314159 promotion control. These are diagnostic witnesses selected
from earlier evidence, not a fresh coverage sample.

The runs are compact and contain no retained raw sample arrays. Reconstruct
V/I/T using the archived sources, binary and recorded recipe in a separate
output directory. Validate regeneration against recorded checkpoint state,
controller/RNG state and original rolling outputs; hash each regenerated prefix.
Include checkpoint validation beyond the first training/holdout interval where
available. Never silently substitute a current harness version.

An exact full-prefix reference needs observations from the original start.
A late checkpoint plus its compressed history is not an exact retained-data
reference. A later checkpoint may regenerate a suffix for forecast testing,
but may not replace the discarded prefix in this comparison.

For owner-run uncertainty queries, use the scheduled refresh boundary at or
immediately before the requested hour, chosen by sample count, regardless of
whether that attempt succeeded. Record before/after distributions and rejected
attempts. For the four-hour weak case, retain the exact original endpoint and
label an offline full-prefix field refit separately from the hybrid endpoint
between scheduled refreshes. Never compare unequal observation prefixes.

## Stage 1: five short matched diagnostics first

Run four approximately four-hour owner prefixes and the four-hour weak prefix.
Compare, on exactly the same observations and public prior:

- Original rolling distribution and promoted field-assisted distribution.
- A fresh full-prefix degree-5 field fit and native state transport.
- A retained-observation local joint MAP/GN reference with exact state transport.
- Field fit with exact transport, to isolate transport from likelihood effects.

Declared fitting starts are the public prior, the signed slow-coordinate
offsets registered in the machine plan, and the saved field-origin warm start
when available. All starts optimize the same objective; choose by training
objective only. More iterations are a numerical control, not extra evidence.
Record rejected domains, round limits, gradient corrections and stop reasons.
An unconverged run is unresolved, not evidence of exclusion.

At common anchors, measure gradient defect, local joint widths/correlations,
GN versus directional observed curvature, predicted and actual correction in
Q/SOC, and component attribution. Repeat one selected anchor with a different
chunk size to bound numerical accumulation effects. Inspect before/after field
replacement separately from drift between replacements.

For Q, reoptimize nuisance coordinates on a fixed, registered log-Q grid covering
the declared prior neighborhood and a finer neighborhood around the fitted
reference. Plot continuous objective differences. Profiles are not marginal
posteriors; do not infer exclusion from an unfinished nuisance optimization or
use an invented 0.1-NLL acceptance threshold. Computational field-box boundaries
are not physical support boundaries for the retained-data reference.

Score 30 minutes of withheld observations without refitting, using local joint
predictive covariance and the same observation measure in each comparison.
Truth is read only afterward for separate error/coverage scoring. The weak
four-hour source has no saved future: its next segment must be explicitly
registered as a new continuation, not described as archived evidence.

## Stage 2U: uncertainty source and growth, only after Stage 1 works

Extend the two low-noise owner cases to approximately 24 and 72 hours. Reuse the
same prefixes across methods. Extend high-noise counterparts only when needed
to distinguish noise scaling. Record approximation-induced correction in both
physical units and local-SD units versus record count, exposure and excursion.
Test whether absolute error stabilizes while local widths shrink, rather than
assuming a divergence law from the standardized error alone.

If the reference remains too narrow or similarly displaced, examine the sensor
likelihood before adding a history uncertainty floor. The harness rounds an
analog noisy voltage to 1/1024 V codes; the current likelihood approximates this
with Gaussian variance sigma_analog^2 + delta^2/12. A diagnostic code likelihood is

```
P(code y | mu) = Phi((y+delta/2-mu)/sigma_analog)
              - Phi((y-delta/2-mu)/sigma_analog)
```

Sensor bin edges and analog noise calibration must be explicit public inputs,
not learned from hidden truth. Use stable log-probability evaluation. Compare
the sensor likelihood using exact physical responses first; do not change
compression and measurement models together. Compare proper predictive scores
on the same observed-code measure, not discrete probability against an
unnormalized continuous density. If an unquantized control is required, create
a separate harness run with matched analog innovations and frozen recorded I/T;
do not dequantize existing observations or let different voltage feedback
silently change the load in this measurement-model comparison.

Only if transport/between-refresh drift dominates should a short, separately
registered cadence comparison follow. Only if compression dominates should
partition-specific representation or correlated discrepancy storage follow.
An observed deterministic bias is not automatically a random variance: report
an error envelope or explicitly justified stochastic discrepancy, not an
unqualified scalar multiplier or ad hoc variance floor.

A 720-hour exact-data audit is conditional follow-up, not the first experiment.
Choose it only if the shorter-prefix attribution leaves a long-duration question
unresolved; regenerate the full prefix or label any late-window audit as local.

## Stage 2W: distinguish repetition from charge excursion

First inspect the weak case's exact-data Q profile and nuisance-residualized
information. As a separately labeled prior-sensitivity diagnostic, compare the
original Q log-SD 0.3 with 0.6, preserving the prior mean and scaling the Q row
of its root so correlations are retained. Start with the retained-data reference;
do not confuse the field's computational-domain restriction with prior support.
This is a sensitivity experiment, not proposed production covariance inflation,
and no prior is selected using truth error. Then fork the same four-hour
physical/estimator boundary into four
registered continuations, keeping the original prior/history and full state:

| Branch | First hour after the shared prefix | Following three hours |
|---|---|---|
| Repeat | Existing cycle schedule at its original absolute phase | Same schedule |
| Rest | I=0 | I=0 |
| Short excursions | 24 repeats: +30 mA 50 s, rest 25 s, −30 mA 50 s, rest 25 s | Existing cycle schedule |
| Wide excursion | +30 mA 1,200 s, rest 600 s, −30 mA 1,200 s, rest 600 s | Existing cycle schedule |

For this causal fork, hold measured temperature at 25 C after hour 4 for all
branches, starting at the cycle's 25 C boundary. The last two branches have the
same one-hour duration, peak current, positive/negative active time and total
absolute throughput (0.020 Ah), but charge excursions of 0.0004167 and 0.010 Ah.
The 24-fold difference in excursion is the controlled change. It also changes
RC/hysteresis timing, so attribute improved Q information after marginalizing
those nuisance sensitivities; do not assume an exclusively capacity effect.

Use measured-voltage/domain guards and label a truncated stimulus explicitly;
no truth-based SOC cutoff or state reset. Each branch gets its own source
lineage with the identical parent-prefix identity. The same recorded/scheduled
observations feed all estimator arms within that branch. Compare first-hour
forecasts made at hour 4 separately from assimilation results at hours 5 and 8.
The primary diagnostic seed is the recorded seed 314159; reserve 2100–2131 for
later validation. Register noise continuation state/counter mapping before
generation; do not resample a preferred realization.

Also include a standalone four-hour rest-from-start control at 35 Hz, cell B,
4 mV, constant 25 C to test the Q-null-information identity. It is distinct from
the rest-after-prefix branch. Do not impose a rule that Q must never move at rest.

## Decisions, validation and resources

If the exact-data profile is broad and remains sensitive to reasonable declared
priors, improve unresolved/precision reporting and stimulus design. Do not force
Q toward truth. If exact data identify a much tighter estimate but field does
not, repair the measured representation/optimization defect. If both miss with
narrow widths, investigate measurement/model assumptions and local-Gaussian
adequacy. A constrained computational domain is always reported as a limitation.

Once a repair is chosen, evaluate fresh seeds at fixed endpoints. The proposed
pilot has 32 noise seeds in each of four registered strata (128 trajectories),
with paired control/candidate arms. Report 50/80/95% marginal interval coverage
with binomial uncertainty, joint diagnostics, point error, forecast score and
refresh failures. These are fixed-cell frequentist diagnostics, not a proof of
posterior calibration across all batteries. Do not count millions of correlated
time samples as independent trials. Thirty-two seeds per stratum cannot validate
three-sigma tail coverage; larger validation requires a separate precision plan.
The validation matrix is conditional, not an authorized automatic long sweep.

Implementation acceptance requires exact source chronology and ownership, no
truth leakage, correct rest-null and covariance controls, and preserved compact
replay behavior. Scientific decisions use the measured decomposition, physical
application errors and uncertainty evidence, not arbitrary likelihood cutoffs.
Changing a representation must also report RAM, operations and latency; a point
improvement alone is insufficient for promotion.

Cache only one case at a time when exact repeated passes need samples. Five
float64 observation columns cost 28.8 MB for 4 h at 50 Hz, 172.8 MB for 24 h,
518.4 MB for 72 h, and 5.184 GB for 720 h. A 30-minute holdout adds 3.6 MB.
The four-hour 35 Hz weak prefix costs 20.16 MB. Do not write full truth/trace CSVs;
keep compact summaries, source hashes and small diagnostic receipts. Use
blockwise derivatives, not a full N-by-16 Jacobian allocation.

Current field payload plus live collocation remains 28,864 B, excluding prior,
workspace and the desktop pending buffer. A diagnostic 16-vector gradient is
128 B; a packed symmetric 16-by-16 curvature is 1,088 B. An illustrative k-mode
discrepancy basis with 16-by-k directions, k means and a k-by-k triangular root
would require 296 B for k=2 or 624 B for k=4, before metadata or online statistics.
These are sizing examples, not a selected repair or proof of sufficient rank.
SRAM-only M23 deployment and aging remain separate open requirements.

Execution order: implement and qualify regeneration/diagnostic controls, run the
five Stage-1 prefixes, interpret them, then select the appropriate uncertainty
or stimulus follow-up. No new 720-hour campaign is needed to start.
