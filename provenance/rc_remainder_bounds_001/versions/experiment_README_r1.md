# RC remainder certificate and diagnostics

From this worktree:

```sh
OPENBLAS_NUM_THREADS=1 python3 -B -m unittest experiments.rc_remainder_bounds_001.test_bounds -v
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.rc_remainder_bounds_001.run --out /tmp/mumble-rc-remainder-result.json
```

Use an unused output path. Python standard-library rational arithmetic certifies
the constants; existing NumPy supports finite diagnostics. No new package or
native build is needed. The runner compares against the compact committed prior
mechanism probe; it needs no ignored raw run, binary or fitted trajectory.

The six tests distinguish exact rational inequalities from floating sanity checks.
Rational certification uses no floating root solving or exponential evaluation.
The response probe independently reconstructs the prior public Taylor values/slopes
with analytic derivative recurrences and retains its off-centre regressions.
The Gaussian counterexample is abstract, not a simulated Foster battery.

The reported example budgets (10 uV voltage and 100 uV per unit log-tau slope)
are illustrative inputs to the derived inequalities, not product requirements or
adopted thresholds. No runtime gate, support restriction, centre change, estimator
change or optimization is implemented. See the
[plan and proofs](../../specifications/rc_remainder_bounds_001/README.md) and
[result interpretation](../../provenance/rc_remainder_bounds_001/README.md).
