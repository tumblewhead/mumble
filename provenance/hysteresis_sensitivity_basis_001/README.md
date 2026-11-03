# Six hysteresis sensitivities repair the saved local uncertainty comparison

The Taylor hysteresis candidate substantially improves the saved-anchor joint
uncertainty comparison without increasing factor storage. It preserves the value,
both first rate derivatives and all second derivatives at the original public
centre, including the mixed term. Its H-only precision test passes all twelve
saved anchors; old H2 and both mixed-completion controls pass only the four rest
anchors. This is a promising local representation, not a promoted estimator.
Off-centre regressions and the existing Taylor RC rest failure remain.

See the [plan](../../specifications/hysteresis_sensitivity_basis_001/README.md),
[H5 recurrence proof](../../specifications/hysteresis_sensitivity_basis_001/H5.md),
[H6 remainder proof](../../specifications/hysteresis_sensitivity_basis_001/H6.md),
[saved-anchor results](result.json) and [public locality probe](probe.json).
All reported errors/widths are relative to direct inference at the same parameter
anchor, not battery truth, refitted estimates or calibrated physical coverage.

## Saved-anchor improvement at unchanged factor size

The table uses the previously saved Taylor-RC/H2 fitted anchors and direct state
transport to isolate covariance. All listed principal arms have identical Taylor
RC; only the H representation changes.

| H representation | One-hour multiscale Q/SOC width ratios | One-hour embedded Q/SOC width ratios | Factor B |
|---|---:|---:|---:|
| H2 | 0.9559 / 1.0479 | 0.6572 / 0.5246 | 4760 |
| H2 plus c22 | 0.9312 / 1.0699 | 0.6571 / 0.5204 | 5328 |
| Full quadratic H tensor | 0.9428 / 0.8469 | 0.6574 / 0.5332 | 6560 |
| Taylor H2 | 0.9954 / 0.9920 | 1.0066 / 1.0028 | 4760 |
| H7 | 0.9939 / 0.9970 | 0.9947 / 0.9977 | 35720 |

The embedded SOC width moves from about half the direct width to within 0.3%.
That percentage describes width agreement, not SOC estimation error. The mixed
completion controls do not achieve the same repair even though they can correct
centre values. Rate sensitivities and their joint coupling matter.

Across both prefixes, three loads and two saved anchors, Taylor-H H-only epsilon
passes 12/12; H2, c22 and tensor pass 4/12 (rest only); H7 passes 12/12. For the
combined RC/H test, Taylor-H and matched H7 both pass the eight active-use anchors
and fail the four rest anchors because Taylor RC remains problematic there.
The separate R5_H7 reference passes all twelve combined tests at a 50624 B factor.
Passing epsilon<1 is a sufficient finite-anchor perturbation result, not uniform
posterior fidelity. The twelve anchors are correlated diagnostics, not trials in
a population study. The full rest direct fit remains explicitly unresolved.

At the one-hour multiscale Taylor anchor, combined epsilon falls from 249.6 to
0.559, and relative precision eigenvalues change from 0.00387–221.6 to 0.800–1.278.
At embedded, epsilon falls from 11.53 to 0.124 and eigenvalues become 0.943–1.096.
The gradient defect also falls, but is not eliminated: its direct precision-metric
norm is about 5.08 for multiscale and 0.648 for embedded. No new joint refit has
yet established where the candidate's optimum will move.

## Likelihood and transport improve together

We retained direct and hybrid state transport separately. At the one-hour
multiscale Taylor anchor, old H2 pulse forecast widths range from 1.109 to 11.162
times direct when direct transport is held fixed, but look much closer after
approximate transport masks the precision defect. Taylor H changes those ranges
to 0.992–1.028 with direct transport and 0.988–1.007 with hybrid transport.
For rest60 they are 1.036–1.055 and 1.009–1.020 respectively. The large compensation
seen with H2 is substantially reduced in these readouts.

At embedded, Taylor-H pulse widths are 0.982–1.002 under either transport; rest
widths are approximately 0.989–1.004 across the two views. Hybrid-transport forecast
voltage RMS discrepancies fall from roughly 32–33 uV to 1.37–1.43 uV in multiscale
and from 41–42 uV to 0.018–0.022 uV in embedded use. These are same-anchor sampled
comparisons. Small numbers may include cancellation; they do not prove improved
truth accuracy, nonlinear coverage or continuous-time brownout safety.

## Why it works locally, and where it fails

H5 differentiates the chronological affine recurrence, preserving actual reversals.
The six states per free/forced response are value, plus/minus first derivatives,
two pure second derivatives and the mixed derivative. Their coefficient map fits
the existing six-term joint H feature layout. H and B=H*h0 remain continuous
amplitudes; rates remain continuous gamma/Q coordinates. Derivatives do not become
extra observations. Supplied observations/calibration drive the recurrence; hidden
plant truth is confined to fixture generation and does not enter inference readouts.

H6 proves conservative stationary third-derivative bounds independent of duration.
Pure log-rate third derivatives have bounds 13 for the free response and 26 for
the forced response; mixed third derivatives have bounds 3 and 6. Taylor remainder
bounds follow, including amplitude and rate derivatives. They do not qualify
finite-precision accumulation, changing Q/gamma/H, aging or indefinite likelihood.
They are also loose: at the one-hour multiscale Taylor anchor the H metric bound
gives eta<=153.3 versus measured 0.249, so it does not supply a useful runtime gate.

The saved anchors are near the centre: their largest absolute H log-rate offset
is about 0.154. The separate 512-sample public probe tests fifteen two-rate queries.
At the centre, Taylor H value/first/mixed derivatives match direct within numerical
rounding; H2 has up to about 126 uV per unit log-rate slope defect. At offsets
(-0.9,+0.9), Taylor H voltage discrepancy reaches 201 uV versus 13.3 uV for H2;
at (+0.9,+0.9), it reaches 95.2 uV versus 21.0 uV. H7 stays much closer in these
finite probes. Central matching does not authorize replacing the whole support,
re-centering old evidence, dropping posterior mass or declaring the history fixed.

## Validation, resources and next step

Six targeted tests pass. Individual independent reviews accepted H5 and H6;
kernel review independently checked high-precision derivatives, remainders, mixed
completion/H7 legacy H-row parity, mode rejection, transport and failure atomicity.
Both unchanged control arms reproduce all 24 prior anchor metric records exactly,
and their endpoint states match saved snapshots bitwise. New joint factors agree
with the common augmented QR precision comparison to at most 3.65e-11 scaled
eigenvalue discrepancy. Source, binary, observation and snapshot identities remain
bound. Separate runner/result review is recorded in the final receipt.

The candidate factor is 4760 B; live response is 312 B and domain/scalars 96 B,
for a 5168 B partial subtotal, unchanged from Taylor-RC/H2. Six derivative slots
are padded to nine per H response for the shared transport API. Removing that
padding could save 48 B later, but no such saving is credited. All totals exclude
prior, tables, optimizer, metadata, scratch, stacks and platform overhead. New C
is study-only; production/defaults and runtime allocations are unchanged.

Next perform the full joint refit with Taylor RC plus Taylor H, alongside unchanged
H2 and matched H7 controls, using the same public starts/prior, original centre
and full declared support. Check convergence, fitted shifts, Q/SOC widths and both
forecast-transport views. Preserve unsupported/off-centre outcomes rather than
narrowing the box to obtain a pass. This is the next finite desktop qualification;
a long campaign or firmware promotion would be premature.
