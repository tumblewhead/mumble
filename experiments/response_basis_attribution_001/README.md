# RC/hysteresis response attribution and paired basis study

Isolated desktop diagnostics. Read specifications/response_basis_attribution_001/
README.md and provenance/response_basis_attribution_001/README.md before interpreting
results. Production estimator/defaults and native C kernels remain unchanged.

Run from this worktree into new output directories:

```sh
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.response_basis_attribution_001.run_attribution \
  --out experiments/response_basis_attribution_001/local_attribution001
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.response_basis_attribution_001.run_basis \
  --out experiments/response_basis_attribution_001/local_basis001
```

These commands use local partitioned_coefficients_001/followup002 recipes and
reference results; pass --baseline to select an equivalent saved baseline. They
compare the same finite public queries through one hour, with no parameter fit.
The two scripts enforce no-overwrite output directories. Raw outputs stay ignored.

```sh
OPENBLAS_NUM_THREADS=1 python3 -B -m unittest \
  experiments.response_basis_attribution_001.test_basis -v
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.response_basis_attribution_001.analyze \
  --attribution experiments/response_basis_attribution_001/local_attribution001 \
  --basis experiments/response_basis_attribution_001/local_basis001 \
  --out experiments/response_basis_attribution_001/local_summary.json
```

BasisField's basis_query/evaluate derivatives are with respect to eleven physical
amplitudes followed by five log-shapes. Its chart-valued inherited helpers are
made coordinate-consistent, but the older external features_jacobian helper
assumes a log basis and is not a derivative API for the rate-coordinate arms.
Use basis_query's Jacobian with an explicit chart chain rule instead. No new
campaign adapter, fitted solver, full-memory budget or target implementation is
provided by this experiment.
