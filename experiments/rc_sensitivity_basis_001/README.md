# RC sensitivity basis study

Run from this worktree with unused output names:

```sh
OPENBLAS_NUM_THREADS=1 python3 -B -m unittest experiments.rc_sensitivity_basis_001.test_basis -v
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.rc_sensitivity_basis_001.run --out experiments/rc_sensitivity_basis_001/new_pilot --records 21008
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.rc_sensitivity_basis_001.run --out experiments/rc_sensitivity_basis_001/new_full
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.rc_sensitivity_basis_001.analyze --pilot experiments/rc_sensitivity_basis_001/new_pilot --full experiments/rc_sensitivity_basis_001/new_full --out /tmp/mumble-rc-sensitivity-summary.json
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.rc_sensitivity_basis_001.response_probe --run experiments/rc_sensitivity_basis_001/new_full --out /tmp/mumble-rc-response-probe.json
```

The default full prefix is 126000 records at 35 Hz. The runner requires the frozen
public registration/recipes/results in `experiments/partitioned_coefficients_001/followup002`
(`--baseline` overrides it). The analyzer also verifies original one-hour controls
from `experiments/hysteresis_mixed_completion_001/rc001` (`--control` overrides it).
No stored raw trajectories are needed. Build and NumPy tools are the existing
repository dependencies. New derivative C builds are study-only; campaign C is
unchanged. Raw runs, binaries and factor snapshots remain local ignored artifacts.

Fits use the same shared-domain/prior-once helper as the preceding study. The new
runner includes full endpoint SOC covariance readouts without a separate refit.
It retains one finite prefix in desktop memory for direct reference evaluations;
that workspace is not a bounded-memory firmware proposal. Truth is confined to
the stimulus generator and is not passed to objectives, starts or forecasts.

The outcome-informed response probe uses public artificial inputs and boundary
states; it isolates value/slope mechanisms and is not independent confirmation.
Original rejected kernel-binding source/tests are retained in provenance versions.
See the [plan](../../specifications/rc_sensitivity_basis_001/README.md) and
[results](../../provenance/rc_sensitivity_basis_001/README.md).
