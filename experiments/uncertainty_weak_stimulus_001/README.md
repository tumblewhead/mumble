# Uncertainty and weak-stimulus diagnosis

This implements Stage 0 and Stage 1 of the
[registered plan](../../specifications/uncertainty_weak_stimulus_001/README.md)
on branch `experiment/uncertainty-weak-stimulus-001`, from planning commit
`060a706`. The promoted estimator, physical prior, field degree and refresh
cadence are unchanged. No long sweep or uncertainty repair is enabled.

## Evidence and interpretation

The five initial comparisons completed. A short follow-up isolated weak-case
uncertainty loss between refreshes. The first execution uses `attempt001/` for
regenerated inputs, `diagnostic001/` for fits, and `scoring003/` for separate
postfit truth scoring and [plots](scoring003/diagnostics.png). Generated arrays,
binaries and figures stay local. [qualification.json](qualification.json)
records their identities and conclusions. Earlier attempts remain preserved.

## Findings

Capacity errors below are percentages of truth, scored only after fitting:

| Four-hour witness | Original rolling | Online field-assisted | Fresh field fit | Retained-data fit |
|---|---:|---:|---:|---:|
| 1100 / load7 / 2mV | +0.5026 | +0.0797 | +0.0797 | +0.0666 |
| 1103 / load7 / 2mV | +0.7879 | −0.0648 | −0.0648 | −0.0802 |
| 1100 / load7 / 20mV | +1.0817 | +0.4504 | +0.4504 | +0.4481 |
| 1103 / load7 / 20mV | +3.1796 | −0.5340 | −0.5340 | −0.5490 |
| B / balanced cycle / 4mV | +1.6650 | −1.8938 | +0.2760 | −0.1451 |

**The field approximation gradient is dominated by hysteresis in all five
witnesses.** In the four owner prefixes, fresh field/reference Q separation
is 0.0023–0.0154%, or 0.0034–0.169 reference local SD. Their same-anchor Q widths
agree within about 0.8%. At the weak prefix, separation is about 0.422%, still
only about 0.093 reference local SD. RC3 has a smaller contribution there.
The first-order correction accurately predicts the low-noise and weak-case Q
refit displacement. It is less exact for high-noise seed1100, so it is a local
diagnostic rather than an equality or global proof.

OCV/charge and ohmic contributions are numerically negligible. The instrumented
recurrence agrees exactly with the archived model in all audited blocks.
Gradient assembly differences project to less than 5e-9 local SD of Q.
Doubling the retained-data chunk size produces negligible shifts. This supports
response-approximation error rather than floating-point accumulation as the
observed field/reference displacement mechanism at these prefixes.

These four-hour results do **not** explain the 13–14 local-SD discrepancy in
the low-noise 720-hour run by themselves. Absolute center displacement and
shrinking widths must be measured at 24/72 hours before claiming a growth law
or choosing a lifetime discrepancy model. Sensor likelihood and non-Gaussian
uncertainty remain alternative causes if the retained reference also fails.

**Weak use exposes an additional online feedback problem.** The same four-hour
weak data give Q log-SD ×100 of 4.54% for the retained reference and 4.30% for
the fresh field. The original rolling arm reports 0.420%; the online field arm
reports 1.115%. Broad uncertainty persists even though a fresh point estimate
falls inside the application's preferred 0.5% error band. Q is not tightly
identified, and those point errors are not evidence of validated coverage.

The online field's last refresh was accepted at record502656, 38.4 seconds
before record504000. Its Q width was 4.278%. Replaying the following84 original
rolling windows from that joint message reproduces the saved mean/root exactly,
including narrowing to1.115% and the −1.894% endpoint error. Querying the full
history field after each of those same16-record windows instead ends at4.303%
and +0.276% error. This separates the between-refresh update behavior from a
missed refresh or absent full-history information. It also separates it from
the smaller fresh-field versus retained-data approximation error.

This conditional follow-up is registered in
[weak_boundary002/registration.json](weak_boundary002/registration.json), with
[results](weak_boundary002/result.json). A separate joint fit of the suffix
using the same boundary Gaussian did not satisfy the strict stopping criteria,
even after numerical continuation. Its unresolved starts are retained in both
`weak_boundary001` and `weak_boundary002`. Consequently this test does not yet
separate loss at the initial Gaussian boundary approximation from loss due to
repeated rolling relinearization. The every-window field is a diagnostic oracle,
not a proposed production cadence or M23 implementation.

The fresh field and retained reference both improve the withheld30-minute
Gaussian predictive score over original rolling in all five witnesses. This
is a small selected comparison, not a coverage calibration. Broad profile
failures and computational-domain limits remain explicit in the receipt.

Initial directional-curvature checks at0.1/0.03 local SD were not step-stable,
especially in the weak case. The separately registered
[refinement](curvature001/result.json) reduces the step down to0.0001 SD.
The retained-fit Q-direction curvature then approaches about1.040 times GN
for the weak case, versus1.000/1.012/1.113/0.996 in the owner cases. The initial
large weak-case values therefore cannot be interpreted as an enormous local
Hessian. They expose strong finite-displacement nonlinearity along that tangent
direction. These are directional checks, not a full covariance correction.

## Next step

Prioritize preserving joint likelihood information during the rolling updates
between field refreshes. Use the short weak-case replay and every-window field
as controls; distinguish Gaussian boundary-shape loss from repeated projection
before selecting a cheaper update. Do not repair this by scalar covariance
inflation or by declaring capacity resolved from its point error.

Separately, extend the two low-noise gradient-attribution prefixes to24/72hours
before changing hysteresis degree or discrepancy storage. The matched short/
wide charge-excursion and prior-sensitivity forks remain planned, not executed.
No new720-hour campaign is needed to start either diagnostic.

Four owner-run prefixes use noise seeds 1100/1103, load seed 7 and noise
2/20 mV at 50 Hz. Training ends at the scheduled field boundary at or before
four hours. The fifth prefix is the original four-hour cell B balanced-cycle
control at 35 Hz. Its next 30 minutes are explicitly a new continuation; the
other heldout segments reconstruct previously simulated evidence.

`regenerate.py` runs with imports from each preserved source worktree and
uses its archived binary. It reconstructs from sample zero. At saved checkpoints
it compares complete joint messages, field state/root/pending observations,
physical state, load controller and RNG state. After the training prefix it
continues plant/controller validation without advancing an estimator.
No late compressed checkpoint substitutes for exact full-prefix observations.

`run.py` never opens plant or truth files. It uses the original public prior
once and selects only converged training fits from four declared starts. It
compares fresh degree-5 field and retained-data local MAP/GN fits, transports
the same field fit both ways, and retains saved online pre/post-refresh messages.
This is a continuous deterministic local fit, not particles or an exact posterior.

The partition diagnostic instruments the unchanged C recurrence to emit OCV,
ohmic, RC1/2/3 and hysteresis contributions and analytic derivatives. Every
audit block compares its total voltage, Jacobian and state transport against
the archived model. Attribution uses the registered additive gradient identity,
with cross terms retained. Component terms may cancel; they are not independent
variance estimates. Summation/QR differences and their projected effect on Q
are reported separately.

Profiles reoptimize all 15 nuisance coordinates at each fixed Q. Failed starts,
computational field-box limits and physical-path failures remain unresolved.
They are not physical exclusions. Directional observed-curvature checks use
two finite-difference steps and do not certify the full Hessian or posterior.
Forecasts retain joint cross-time covariance and condition on the recorded I/T.

## Reproduction

From this worktree, with the source runs and their preserved worktrees present:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -B -m unittest \
  experiments.uncertainty_weak_stimulus_001.test_diagnostics -v

python3 -B -m experiments.uncertainty_weak_stimulus_001.execute \
  --out experiments/uncertainty_weak_stimulus_001/reproduction002
```

Use a fresh output directory; `--labels weak_B_cycle` selects one registered
case. The runner launches only the five short diagnostics, never conditional
24/72-hour extensions or a fresh coverage sweep. It binds source identities,
stores exact input hashes and keeps truth scoring in a separate process.

The current regeneration exporter also saves the last refresh message. To
repeat the short adaptive test after a new Stage-1 execution:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -B -m \
  experiments.uncertainty_weak_stimulus_001.boundary \
  --inputs experiments/uncertainty_weak_stimulus_001/reproduction002/inputs/weak_B_cycle \
  --original-inputs experiments/uncertainty_weak_stimulus_001/attempt001/weak_B_cycle \
  --stage1 experiments/uncertainty_weak_stimulus_001/reproduction002/diagnostics/weak_B_cycle \
  --out experiments/uncertainty_weak_stimulus_001/boundary_reproduction003
```

For already regenerated observations, the fitting and postfit commands can be
run separately using `run --inputs ... --out ...` and
`postfit --inputs ... --diagnostics ... --out ...`.

## Resources and limits

The diagnostic processes one case at a time with blockwise derivatives. The
five small regenerated input caches are retained locally for reproducibility;
there are no full truth or rolling trace CSVs. This retains more disk caches
than the plan's one-case cache preference, without retaining full trajectories
for the original 720-hour runs. Per-case fit workspace remains bounded by the
chosen derivative chunk, except the small 30-minute prediction Jacobian.
All six observation caches, including the repeated weak boundary export, total
about175 MB. The five matched fit/profile diagnostics took about886 host seconds;
the adaptive boundary replay took about3.2 seconds, excluding regeneration.
These include costly diagnostic profiles and are not production timing results.

Production field payload plus live collocation remains **28,864 B**, excluding
the prior, pending buffer and solver workspace. These diagnostics add no
production storage or CPU work. They do not qualify aging, long-run uncertainty,
coverage, or deployment within the M23 SRAM budget.
