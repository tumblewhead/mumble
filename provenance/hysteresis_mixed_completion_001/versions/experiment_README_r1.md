# Mixed hysteresis completion and RC attribution controls

Run from this worktree with unused output directories:

```sh
OPENBLAS_NUM_THREADS=1 python3 -B -m unittest experiments.hysteresis_mixed_completion_001.test_completion experiments.hysteresis_mixed_completion_001.test_rc_control -v
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.hysteresis_mixed_completion_001.run --out experiments/hysteresis_mixed_completion_001/new_primary
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.hysteresis_mixed_completion_001.run --out experiments/hysteresis_mixed_completion_001/new_rc --rc-control --records 126000
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.hysteresis_mixed_completion_001.analyze --primary experiments/hysteresis_mixed_completion_001/new_primary --rc-control experiments/hysteresis_mixed_completion_001/new_rc --out /tmp/mumble-mixed-completion-summary.json
```

Requires the existing local frozen registration/recipes/results in
`experiments/partitioned_coefficients_001/followup002`; override with `--baseline`.
No large trajectory files are required or written. The native build/NumPy toolchain
is the existing repository toolchain. Each run binds sources, profile, public
queries, binaries and observation hashes. Outputs are refused if they already exist.

The inference objectives consume only public calibration/prior and observations;
the harness regenerates observations using its hidden plant definition and discards
truth outputs. Direct fitting holds one finite prefix in desktop memory. This is
not the production rolling estimator or a bounded-memory firmware implementation.

`pilot001`/`full001` use the preserved `versions/run_r1.py`; `rc001` uses the current
runner with the separately registered RC follow-up. No original data/results are
replaced. The current runner without `--rc-control` retains the primary algorithm.
Only scripts and compact provenance receipts are tracked; raw run folders,
shared libraries and factor snapshots remain ignored. See the
[report](../../provenance/hysteresis_mixed_completion_001/README.md) and
[protocol](../../specifications/hysteresis_mixed_completion_001/README.md).
