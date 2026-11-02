# Finite controls for symbolic estimator relationships

From this worktree, with an unused output directory:

```sh
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.symbolic_system_001.checks --out experiments/symbolic_system_001/check004
```

The runner uses the public t0_a0 query and configuration from the existing local
`experiments/partitioned_coefficients_001/followup002/registration.json`. Override
with `--baseline PATH` when needed. It does not need raw trajectories. The query
boundary RC voltages are explicitly replaced by the public diagnostic values
[0.004,-0.002,0.003] V; these are test inputs, not hidden-cell estimates. The RC
fixture has 600 samples, seven pole queries and five diagnostic forecast horizons.
The observed-voltage column is arbitrary and not fitted; this is a value/Jacobian
check. All other controls use labeled synthetic matrices, kernels and recurrences.

The existing native C recurrence and degree-2 study field are unchanged. Build
and NumPy dependencies are the repository's existing ones. The runner checks
registered source hashes before completing and refuses an existing output path.
`registration.json` binds the source; `result.json` binds the baseline public-profile
registration and test inputs, and records finite witnesses and negative controls. Original output must not be overwritten.
Only the runner, this guide and compact provenance receipts are tracked.

These controls do not estimate cells, measure coverage, prove uniform-domain
bounds or qualify the H7 campaign/firmware. See the
[plan and proofs](../../specifications/symbolic_system_001/README.md) and
[interpretation](../../provenance/symbolic_system_001/README.md).

Review iteration: `check001` binds the earlier repetition statement; `check002`
binds the narrowed statement; `check003` additionally exercises the two review
counterexamples and repeated fits with fresh observations. Original results,
registrations and runner are preserved. The final compact evidence is
`provenance/symbolic_system_001/check003_result.json`. Earlier results are not
silently relabeled as tests of revised source.
