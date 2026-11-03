# Paper-contract finite witnesses

Run from this worktree root:

```sh
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.constrained_operator_contract_001.check --out /tmp/constrained_contract_checks.json
```

The checker supports [P1–P3](../../specifications/constrained_operator_contract_001/README.md)
with exact-rational local conditions, transfer identities, scalar QR replay vs
independent dense algebra, every post-write fault position in four small sizes,
full joint solves/covariance, and affine bounds with a retained nonstationary-fit
counterexample. It also recomputes named phase-memory totals. These are finite
witnesses, not a battery experiment, a fault-detecting runtime or compiled C memory
qualification. Source, old proof drafts and review findings are retained separately;
new runs refuse to overwrite results. Generated long-run data are not involved.
