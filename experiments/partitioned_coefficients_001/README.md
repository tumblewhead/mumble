# Continuous coefficient feasibility experiment

This isolated study compares small dependency-partitioned likelihood encodings
with direct C and H7, then tests existing low-degree square-root response controls.
The candidates are not connected to the rolling estimator or campaign defaults.
See specifications/partitioned_coefficients_001/README.md for the registered domain,
probe selection, adaptation and interpretation limits; see
provenance/partitioned_coefficients_001/README.md for the reviewed result.

Run the current paired comparison into a new local directory:

```sh
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.partitioned_coefficients_001.run \
  --out experiments/partitioned_coefficients_001/local001 --response-control
```

This uses three short streams and three prefixes through one hour; it does not
fit parameters or establish long-duration accuracy. Remove --response-control
to execute only the original candidates and H7. Set --records and --loads for
an explicitly different diagnostic; do not pool changed scenarios as confirmation.
Raw outputs remain ignored. Never reuse an existing output directory.

Targeted checks:

```sh
OPENBLAS_NUM_THREADS=1 python3 -B -m unittest \
  experiments.partitioned_coefficients_001.test_representation \
  experiments.partitioned_coefficients_001.test_controls -v
```

Reduction/plot example (writes a new report):

```sh
MPLCONFIGDIR=/tmp/mumble-mpl OPENBLAS_NUM_THREADS=1 python3 -B \
  -m experiments.partitioned_coefficients_001.analyze \
  --out experiments/partitioned_coefficients_001/local_summary.json \
  --plot experiments/partitioned_coefficients_001/local_comparison.png \
  experiments/partitioned_coefficients_001/local001
```

The resource and outcome-selected curvature audits can be rerun with the
`resources` and `curvature_witness` modules, each taking --run and --out.
The audited byte subtotals exclude substantial state/workspace; this is a desktop
prototype, not a10KiB implementation. Original C/model/Field files are unchanged.
