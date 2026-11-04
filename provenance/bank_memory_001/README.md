# Memory reduction: runnable candidates and a native scratch prototype

The full bank's 35,720-byte history factor can be reduced to **4,760 bytes**
(rank3) or **6,560 bytes** (rank4), retaining a joint likelihood and all physical
transport states. These are opt-in, stationary desktop experiments. The complete
rank3 desktop numeric payload is still **17,176 bytes**, plus temporary workspace.
The [runner guide](../../experiments/bank_memory_001/README.md) contains a72-hour
comparison command with compact recording, plots, seeds and parallel jobs.

We completed eight paired four-hour cases and six paired24-hour cases:352 simulated
arm-hours in total. Each comparison used the same observations for its two arms.
The24-hour tests used cellB, embedded load7,50Hz and noise seeds1100/1101 at2mV.
They are repeated synthetic scenarios, not a population qualification.

| 24-hour candidate | History bytes | Worst final absolute Q error | Q3SD misses | SOC3SD misses |
|---|---:|---:|---:|---:|
| Full bank | 35,720 | 0.00130% | 0 / 0 | 0 / 0 |
| Rank4, float64 | 6,560 | 0.00143% | 0 / 0 | 0 / 0 |
| Rank3, float64 | 4,760 | 0.00177% | 0 / 0 | 0 / 41 |
| Rank5, centered float32 | 4,324 | 0.20611% | 202,877 / 203,057 | 195,343 / 194,841 |

Counts refer to correlated output windows, not independent trials. All scheduled
refits succeeded. Earlier uncentered float32 runs were worse, reaching about1.2%
capacity error at four hours. Fixed public-prior centering greatly reduced that
problem but did not eliminate recurrent rounding drift. Float64 is recommended.

Rank3's41 SOC misses were reproduced through a nonzero checkpoint replay. They
occurred from3.65662 to3.66196 hours, with peak absolute error0.02090 percentage
points and maximum standardized error3.0701SD. The full bank peaked at2.8430SD
in the same window. Final SOC error remained below0.00046 percentage points.
This small transient regression is retained explicitly; no uncertainty fix or
coverage claim was inferred from the otherwise good point estimates.

RC results change with projection. For seed1100, final R0 error changes from
-1.48% to-2.50% at rank3; tau1 changes from+5.33% to-3.05%. Neither vector alone
establishes better admissible-load prediction. Public-grid response checks also
find approximately2% worst rank3 free-response error and negative projected tails.
These are likelihood approximations with full-bank transport, not newly certified
physical Foster networks. Projection and full-bank model bias are not yet included
in the Gaussian widths.

Memory changes implemented in the runner are packed native QR storage, a packed
1224-byte tangent factor, removal of the persistent derivative cache, and removal
of unused roots. Fixed projection avoids repeatedly changing or folding old
history. It does not prove lifetime floating-point accuracy. In a short host
component profile, rank3 response/history updates took223 microseconds per16
records versus367 for the full dense bank. This excludes readout/refits and is
neither a complete solver speedup nor Cortex-M23 timing.

The separately tested C scratch prototype keeps the joint inference factor and a
shared fit/query workspace in1504 bytes, including a16-byte owner/generation
registry. Steps and scalar variances agree with dense controls. Derivatives are
emitted rowwise, trading recomputation for storage; no full inverse or cached
Jacobian is required inside the kernel. A general graph executive was unnecessary
for these serial phases. Caller buffers, callback workspace and stack remain
additional, and the kernel is not yet the campaign's solver.

The [native memory plan](../../experiments/bank_memory_001/MEMORY_PLAN.json) now
names a9944-byte layout including a1024-byte helper/stack reservation. Review
required adding a dedicated streaming row and clarifying ROM placement and
staging lifetimes. This is a conditional allocation proposal, not measured total
SRAM: it requires a native feature emitter, rowwise solver, scalar-query interface,
verified in-place streaming schedule and bounded stack. Full response staging,
a general prior or platform needs can exceed it. The remaining296 bytes are not
proven free RAM.

All16 targeted tests passed, including full/compact parity, replay, ownership,
malformed native inputs and scratch failures. Independent reviews are preserved
in [review.json](review.json), [review_r2.json](review_r2.json),
[review_r3.json](review_r3.json) and [scratch_review.json](scratch_review.json).
[results.json](results.json) records original campaign hashes and all attempted
variants; [receipt.json](receipt.json) binds source, tests and remaining limits.
Generated campaigns and images remain local and ignored by Git.
