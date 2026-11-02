# Symbolic hysteresis controls

See the [derivations](../../specifications/hysteresis_relationships_001/README.md)
and [reviewed evidence report](../../provenance/hysteresis_relationships_001/README.md).
These controls verify symbolic relationships at a public query. They do not change
the estimator, qualify a repair, or measure full-estimator accuracy or coverage.

Run from this worktree, using unused output paths:

```sh
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.hysteresis_relationships_001.check_relationships --out experiments/hysteresis_relationships_001/check003
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.hysteresis_relationships_001.check_mixed_term --out experiments/hysteresis_relationships_001/mixed002
python3 -B -m experiments.hysteresis_relationships_001.verify_receipts provenance/hysteresis_relationships_001/charge_moment_checks_v2.json
```

Both stream controls require the existing local baseline
`experiments/partitioned_coefficients_001/followup002` registration and case result
recipes. Override with `--baseline PATH`; prefix stream hashes must match. No raw
observations need storage. Build tools and the existing NumPy/native toolchain are
required. Raw run folders and binaries are intentionally untracked.

`check001` and its original compact receipt are preserved after independent review
found mutable-array prefix serialization. `check002` uses a per-prefix copy. The
serialization checker must reject `charge_moment_checks.json` (exit 1) and accept
`charge_moment_checks_v2.json` (exit 0). The original source/report are retained in
`provenance/hysteresis_relationships_001/versions/`; do not run the archived source
as a current control. `mixed001` was unaffected.

The checks use three synthetic measured-stream recipes, three prefixes each, and
the public prior centre. Rest is explicitly unresolved for joint SOC/capacity;
near-constant-charge designs beyond these fixtures require a numerical rank check.
The public centre has B=0; separate free-response coefficient checks supplement
the voltage witness. Memory numbers are hypothetical factor/numeric subtotals,
not complete device memory estimates.
