# Joint refit diagnostic

Run from the h7-campaign worktree with the frozen local RC and H sensitivity study
artifacts present. Input identities are checked against committed provenance.

```sh
OPENBLAS_NUM_THREADS=1 python3 -B -m unittest experiments.hysteresis_joint_refit_001.test_refit -v
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.hysteresis_joint_refit_001.run --out experiments/hysteresis_joint_refit_001/run_new
python3 -B -m experiments.hysteresis_joint_refit_001.summarize --run experiments/hysteresis_joint_refit_001/run_new --out experiments/hysteresis_joint_refit_001/run_new/compact.json
```

The output directory and compact output must be new. This runs the six-case,
five-arm controlled joint refit, retaining original starts/prior/centres/support.
No production defaults or kernels change. Summaries distinguish fitted shifts,
same-anchor likelihood uncertainty and direct/compressed state transport. An
unresolved direct reference withholds fit-to-fit qualification.

See the [protocol](../../specifications/hysteresis_joint_refit_001/README.md) and
[completed report](../../provenance/hysteresis_joint_refit_001/README.md).
