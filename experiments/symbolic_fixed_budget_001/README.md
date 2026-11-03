# Symbolic joint-error and shared-kernel controls

No estimator edits or refits. Requires the preceding local sensitivity/partition
native binaries; their recorded identities are checked.

```sh
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.symbolic_fixed_budget_001.check --out experiments/symbolic_fixed_budget_001/check_new.json
```

Output must be new. The checker verifies small joint algebra examples and a public
constant-current RC equilibrium witness against the existing three representations.
Read [proofs/plan](../../specifications/symbolic_fixed_budget_001/README.md) and
[interpretation](../../provenance/symbolic_fixed_budget_001/README.md). No finite
control proves lifetime coverage or complete target feasibility.
