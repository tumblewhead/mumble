# Fixed-budget shared-query feasibility runner

Requires the existing frozen RC/H/partition-study artifacts in this worktree.
No native build or production estimator changes. Original source/input identities
and unchanged controls are checked before accepting results.

```sh
OPENBLAS_NUM_THREADS=1 python3 -B -m unittest experiments.shared_operator_budget_001.test_shared -v
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.shared_operator_budget_001.run --out experiments/shared_operator_budget_001/run_new
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.shared_operator_budget_001.probe --out experiments/shared_operator_budget_001/probe_new.json
python3 -B -m experiments.shared_operator_budget_001.summarize --run experiments/shared_operator_budget_001/run_new --out experiments/shared_operator_budget_001/run_new/compact.json
```

Use new output paths. Read [C1/plan](../../specifications/shared_operator_budget_001/README.md)
and [results](../../provenance/shared_operator_budget_001/README.md). The negative
free-response witness and unresolved rest precision are retained failures. This
candidate is not promoted and does not prove complete10KiB feasibility.
