# Hysteresis dominates the active-use joint uncertainty defect

The saved-anchor decomposition identifies the next repair: preserve hysteresis
values and sensitivities more faithfully at compact storage. Taylor RC largely
repairs the active-use RC contribution, but leaves the H2 defect exposed. Rest
remains an RC counterexample. These are comparisons with direct local inference,
not battery truth or calibrated coverage.

See the [registered plan](../../specifications/joint_precision_attribution_001/README.md),
[independently reviewed M1 identities](../../specifications/joint_precision_attribution_001/M1.md)
and [complete compact result](result.json).

## The decisive same-anchor comparison

The one-hour embedded case at its saved Taylor anchor gives these ratios of local
standard deviation to direct inference, using direct state transport to isolate
precision:

| Approximation included | Q width ratio | Endpoint SOC width ratio |
|---|---:|---:|
| Taylor RC only, exact H | 0.9960 | 0.9982 |
| H2 only, exact RC | 0.6599 | 0.5247 |
| Taylor RC and H2 | 0.6572 | 0.5246 |
| R5_H7 reference | 0.9987 | 0.9995 |

This reproduces the earlier approximately 0.525 SOC-width result and attributes
it to hysteresis in this case. These counterfactual components are not independent
variances or separate evidence packets. Their precision cross term is retained.
At the same multiscale one-hour anchor, H2 relative joint precision eigenvalues span
about 0.00387 to 221.6. It both loses and invents local precision in different joint
directions; a scalar covariance inflation is not established as a repair.

## How broad is this diagnostic?

Both saved prefixes (21008 and 126000 records), all three recipes and the selected
direct and Taylor anchors give 12 anchors, three representations and three
counterfactual partitions: 108 local matrix/forecast comparisons. No fits changed.
The full rest direct fit remains unresolved; diagnostics at that admitted anchor
do not convert it into a converged result. The two anchors per recipe and two
prefixes are correlated observations, not independent population trials.

P3's sufficient test is epsilon=2 eta+eta^2<1, using Jacobian error in the direct
joint precision metric. The actual matrix spectra are also retained, so an
inconclusive sufficient test is not confused with failure of positive definiteness.

| Representation/partition | Active-use anchors passing | Rest anchors passing |
|---|---:|---:|
| Taylor2, RC only | 8/8 | 0/4 |
| R2, RC only | 0/8 | 0/4 |
| Shared H2, H only | 0/8 | 4/4 |
| Taylor2_H2, combined | 0/8 | 0/4 |
| R5_H7, combined | 8/8 | 4/4 |

At the saved Taylor one-hour anchors, RC-only epsilon is 0.0621 for multiscale
and 0.1081 for embedded use; H-only epsilon is 249.6 and 11.53 respectively.
The largest H column contributions in these two cases involve log(gamma+/Q) and
log(gamma-/Q). These column norms are descriptive and not additive error fractions.
The ten-minute embedded case also has substantial H/Hh0 amplitude contributions;
the next repair must preserve amplitude values as well as rate derivatives.

## Forecast utility, bounds and the rest regression

Forecasts include full incoming-state derivatives and compare sampled rest60 and
120 mA for 10 s followed by rest30, at the same origin anchor. With Taylor RC only,
one-hour embedded forecast widths span approximately 0.982 to 1.002 times direct.
With both RC and H2 approximation they span approximately 0.898 to 1.001.
In multiscale use, combined widths fall as low as 0.827 of direct, while RC-only
widths stay approximately 0.986 to 1.003. Full results distinguish precision-only
and hybrid-state transport, plus voltage differences. This is not continuous-time
brownout authorization, fit-to-fit agreement or nonlinear coverage.

At the saved Taylor rest anchors, RC epsilon is approximately 8.6 and 8.5, and
some joint precision directions differ materially. Q and SOC widths remain nearly
unchanged there because those particular query directions do not expose the RC
defect. The rest forecast width differences are small, but that does not erase
the preceding study's point-forecast regression. Taylor is still a local research
candidate, not a global replacement.

P2's universal RC envelope is conservative. At the one-hour Taylor multiscale
anchor it gives eta<=0.557 versus measured 0.0306; at embedded it gives eta<=3.17
versus 0.0527. The resulting sufficient envelope test is inconclusive in both
cases despite the measured RC tests passing. This is useful evidence about bound
tightness, not a reason to weaken the theorem or adopt an empirical threshold.
The envelope is duration-independent at the response level; its accumulated
inference consequence still depends on evidence and the joint precision metric.

## Numerical lessons and integrity checks

The first attempt formed normal matrices for covariance and failed an internal
query-bound consistency check in pilot rest. Replacing that calculation with
QR square roots resolved the check without relaxing its numerical allowance.
A second attempt compared the new root-based width to historical normal-matrix
readouts too strictly. At one-hour rest the reference precision condition number
is about 2.0e10, and the historical ratio 1.0000020302 differs from the root-based
1.0000000000 by about 2 ppm. The final result retains both rather than rewriting
the historical evidence. The actual saved-factor QR readout independently checks
the new calculation. Neither numerical issue explains the active 0.525 result.

All generated response endpoint states match saved snapshots bitwise. Saved-factor
relative precision eigenvalues agree to a maximum scaled discrepancy of 3.65e-11.
Observation, binary, source, case and factor identities are checked. Physical
partitioning is performed before mapping into the solver chart, preserving Q/gamma
coupling. Six targeted tests pass. Independent M1 and implementation/result reviews
and exact source bindings are recorded in the final receipt. Preserved failed
attempts and source versions document the numerical adaptation.

## Resources and next repair

No estimator or production code changed. Taylor remains at a 4760 B factor and
5168 B partial numeric subtotal. R5_H7 remains a 50624 B factor reference, not an
M23 candidate. This read-only analysis adds zero runtime bytes. Its desktop
51-column augmented QR root is 20808 B and its 1024-row augmented chunk is 417792 B,
in addition to other diagnostic arrays; these are not proposed device allocations.
Full firmware memory and timing remain unqualified.

Next derive and compare a compact, sensitivity-preserving hysteresis representation
using the chronological recurrence and both rate coordinates. A six-term quadratic
Taylor representation including the mixed derivative is a same-factor-size candidate,
not an accepted repair. It must retain amplitude values, mixed/rate derivatives,
the full joint factor and the original public centre/support. Compare against H2,
the previous mixed-term completion and direct/H7 at these saved anchors before
refitting or running a long campaign. Check off-centre failure and seek an explicit
remainder argument; central matching alone did not make Taylor RC globally reliable.
