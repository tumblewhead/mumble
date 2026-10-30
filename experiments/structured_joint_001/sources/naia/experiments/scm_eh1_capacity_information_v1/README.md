# SCM capacity-information probe v1

This new prospective experiment asks whether the unchanged joint V3 estimator
contracts capacity support when a larger charge traversal is supplied. It does
not demand final capacity accuracy, determine convergence time, or qualify
month-long operation. No experiment or implementation test was run while this
package was prepared.

Each original cell has two 1,170-second, 35 Hz arms: a 30-second rest, 1,080-second
10 mA discharge and 60-second rest, versus a matched zero-current control. The
3 mAh excursion separates the 48/84 mAh capacity extremes by 2.6786 SOC percentage
points for a common initial SOC, versus 0.3720 points in the historical test.
This signal comparison motivates the test; it is not an identifiability proof.
The original cell truths, broad priors, calibration, temperature-dependent laws,
unknown thermal states and heat/boundary supports are unchanged. A public
298.15 K chamber command replaces the old chamber steps prospectively in BOTH
arms. Core/surface/sensor temperatures remain dynamic and unknown; the actual
ambient and heat paths remain hidden from the estimator.

`PROTOCOL.json` freezes the gates before outcomes. Q width is measured against
its fresh estimator readout, not an assumed nominal width. Any reduction above
1e-12 Ah is reported as detectable arithmetic contraction; the separate 10%
contraction screen is a prospective research screen, not a product threshold.
Contraction is scored at 1,170 seconds; 1,110 seconds is diagnostic because the
final rest can reduce polarization ambiguity. Full raw contraction is retained,
including below-screen values. Valid no-signal and mixed-signal outcomes are
scientifically inconclusive, not execution failure or proof of unidentifiability.
Execution PASS requires completion, containment, domain, nonwidening, coherent
joint-witness and zero-current control gates. Invalid arms stop further work and
preserve evidence. Product accuracy and total convergence time are not tested.
No physical Q prior is shrunk, nuisance state fixed, or truth-centered estimate
injected. The zero-current model has no Q dependence for common initial SOC and
other coordinates; both arms use exactly the same broad estimator priors.

## Frozen dependency and source boundary

`DEPENDENCY_LOCK.json` binds the published source package
`experiments/scm_eh1_joint_constraints_source_v1` at source commit
`ef21ee216e65452bd0e743112604155608a74606`. The new harness imports its original
reference equations and estimator from a separately verified scratch copy. It
neither patches nor monkeypatches them. Historical 600-second failures and all
artifacts remain unchanged.

The current estimator admits at most 128 individual joint rows. This experiment
ends with 127 scheduled rows, before the 1,180-second final admission and
1,190-second first refusal. The zero-current rest-pair store may fill its own
128-pair budget; that saturation is recorded, not hidden or treated as capacity
information. This experiment deliberately does not test indefinite history.

## Owner execution interface

Use the reviewed owner instructions; all modes require `--dependency-root`.
`run_probe.py` supports `structural`, `reference`, `benchmark`, and `full` modes,
each writing to a new `--output` directory. Structural checks test schedule,
budget, support and zero-current model identities. Reference mode compares the
entire new workload at tighter DOP853 tolerance/step size. Benchmark runs only
100 frames per arm. Full requires the matching structural, reference and
benchmark receipts; no missing preliminary gate is silently accepted.

The full run is four independent arms, 40,950 frames each, 163,800 estimator
updates. Four 100-frame benchmark arms add 400, totaling **164,200 updates**.
The benchmark is only a 2.86-second zero-current prefix/native smoke check; its
cost is not a reliable extrapolation for late growing-history LP work.
Reference comparison uses eight full integration invocations, benchmark four
short invocations, and full replay four primary repetitions: 16 invocations,
40 piecewise solver calls, and 491,800 generated sample frames (not adaptive
solver RHS evaluations). No automatic retries, extensions or threshold search.

Each arm writes at most 1,400 rows per CSV.gz chunk, with source-index range,
row count and both stored and decompressed SHA-256 in `TRAJECTORY_INDEX.json`.
Full estimator snapshots and coherent witness audits occur at 30, 1,110 and
1,170 seconds, plus an initial witness audit: 16 full-arm witness checks and
four benchmark-initial checks. A witness must survive in one common active
candidate across all 12 joint coordinates, z0, eta/H and authoritative factors;
separate marginal truth containment is not substituted for this check. This is
not a full nonlinear trajectory compatibility proof. Failed rows/inputs and
final partial snapshots are preserved, with reference/source/native identity.

No reset branch or historical trace reuse is included. Source preparation and
static review do not establish runtime correctness. Dependency implementation
and numerical proof limits remain explicit even when measured gates pass.
