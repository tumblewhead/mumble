# Saved-anchor joint precision attribution

From the worktree, using existing frozen local pilot/full assets:

```sh
OPENBLAS_NUM_THREADS=1 python3 -B -m unittest experiments.joint_precision_attribution_001.test_metrics -v
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.joint_precision_attribution_001.run --out /tmp/mumble-joint-precision.json
```

Choose an unused output path. `--runs` and `--loads` select smaller diagnostic
subsets, but acceptance uses both registered runs and all three loads. The runner
verifies committed registration/manifest copies and their local source, binary,
case, recipe, observation and factor identities. It regenerates the same finite
observations and computes derivatives; it does not refit or use truth in readouts.
Local `experiments/rc_sensitivity_basis_001/{pilot001,full001}` assets and saved
baseline recipes are required; raw observation logs are not needed.

`metrics.py` implements M1's physical-chart split and common 51-column QR reduction.
It keeps one prior, cross-partition interactions, dense covariance and state-chain
derivatives. Reference and variant covariance calculations use QR roots. The first
attempt exposed a normal-matrix roundoff problem in weak rest; its source is
preserved. A second attempt exposed a 2 ppm difference from historical stored
normal-matrix covariance. The final runner records that comparison separately and
verifies new covariance against the saved factor via QR, without changing old data.

Six tests cover physical coordinates and Q/gamma coupling, shared QR/chunking,
cross terms, conditional forecast bounds, weak-direction square-root arithmetic,
hybrid state-row selection and a short native response split. Precision epsilon
tests are finite floating diagnostics, not global certificates or physical coverage.
No runtime or campaign change. See the
[plan](../../specifications/joint_precision_attribution_001/README.md) and
[report](../../provenance/joint_precision_attribution_001/README.md).
