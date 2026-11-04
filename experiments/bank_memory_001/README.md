# Smaller bank history: experimental desktop comparison

Use branch `experiment/bank-memory-001` in the h7-campaign worktree. This extends
our original-origin bank tangent runner; it does not replace mainline or reintroduce
rolling Gaussian feedback. The complete desktop estimator still exceeds10KiB.

```sh
cd /home/easy/proj/mumble/.worktrees/h7-campaign
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -B -m experiments.foster_campaign_001.run \
  --history compare-small-bank --bank-rank 3 --bank-precision float64 \
  --hours 72 --sample-rate-hz 50 --jobs 2 \
  --cells B --loads embedded --load-seeds 7 --seeds 1100 1101 --noise-v .002 \
  --temperature constant --recording compact --summary-bins 2000 --checkpoint-hours 3
```

This produces individual plots and campaign overlays, including V/I/T, states,
parameters and parameter errors. It compares `bank_tangent` (full94-column bank)
with `small_bank`. Use rank4 for the less aggressive candidate; the opt-in mode's
CLI defaults are rank4/float64. Use `--history small-bank` to run only the reduced
arm. Parallel jobs, independent load/noise seeds and explicit debug-replay windows
remain available. Constant25C is required; aging is not implemented.

| Likelihood rank per free/forced RC block | Joint width | Packed float64 history |
|---|---:|---:|
| Full13 | 94 | 35,720B |
| 6 | 52 | 11,024B |
| 5 | 46 | 8,648B |
| 4 | 40 | 6,560B |
| 3 | 34 | 4,760B |

These are history factors, not total estimator sizes. The reduced implementation
also stores a1224B packed tangent factor and full936B physical response, regenerates
the tangent derivative matrix instead of caching it, and removes two unused roots.
The rank3 desktop reports17,176B resident numeric payload, excluding transient
solver/query arrays and language/runtime overhead. A dense34x34 query root alone
still costs9248B. The actual runner is a mixed Python/C development reference.

The fixed public basis is fitted once, independent of observations or truth, in
a combined free/impulse-response metric. Every sample contributes once to a joint
square-root likelihood, including cross terms. Its projection does not move or
repeatedly fold earlier history. Full N13e transport states remain continuous.
Projection is nevertheless an approximation: rank3 has about2% worst free-response
error on our public grid and negative tails; projected positivity/passivity and
uniform error bounds are not established. Full-bank response properties do not automatically
transfer to the truncated likelihood; the supplied map is itself not yet independently
certified in this integration. The reported Gaussian widths do
not include this model discrepancy. RC/EOD fidelity remains a qualification task.

Two paired24-hour runs at50Hz, cellB/load7 and noise seeds1100/1101 completed
for both float64 candidates. Rank3 ended within0.0018% capacity error and0.00046
SOC percentage points, but seed1101 had41 SOC3SD misses near3.66hours (rank4
and full bank had none). All1436scheduled refits per arm/case succeeded. The
ranks change individual RC estimates; these are two correlated synthetic traces,
not population coverage or proof of EOD accuracy. Preserve rank4 as the more
conservative comparison and rank3 as the memory-target tradeoff.

**Keep float64.** Uncentered float32 accumulated serious drift in four hours.
Fixed public-prior centering improves it but does not solve it: the24-hour trial
still produces Q/SOC3SD misses and hysteresis drift. `--bank-center` and float32
remain explicit diagnostic controls; they are not recommended settings. The
centering identity is exact algebra, not a lifetime floating-point certificate.

[MEMORY_PLAN.json](MEMORY_PLAN.json) gives a conditional9944B native layout,
including1024B reserved for helper/stack use. It depends on ROM tables, an original
diagonal prior, scalar query output, a one-row update schedule and a rowwise native
solver. Those integration and stack premises are not yet discharged. A generic
prior, full output covariance or extra response staging can break the budget.

`scratch_kernel.c` is an independently reviewed isolated prototype of rowwise
joint inference and scalar variance, with a1504B context (including a16B lease
registry). Fit and query use a264B union; no heap, dense history copy, full inverse
or cached feature Jacobian is needed inside this kernel. Derivative callbacks,
input arrays and stack are outside that context. This kernel is not yet the
campaign solver. Its registry assumes serial execution and does not synchronize
interrupts. Mid-rebuild failure invalidates the inference factor; it does not
roll back a previously overwritten factor.

Run targeted controls with:

```sh
OPENBLAS_NUM_THREADS=1 python3 -B -m unittest \
  experiments.bank_memory_001.test_memory \
  experiments.bank_memory_001.test_campaign \
  experiments.bank_memory_001.test_scratch -v
```

Results, original source-bound campaigns, failed precision attempts, component
profiling and independent reviews are indexed in
[the evidence receipt](../../provenance/bank_memory_001/receipt.json).
