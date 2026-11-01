# H7 sustained streaming: 720-hour local run

All eight cases and sixteen arms completed 720 hours at 50 Hz. H7 retains the
large improvement in Q/SOC uncertainty seen at 72 hours, with no practical
divergence in these stationary-cell scenarios. Two cell-B cycle cases develop
late SOC 3SD misses. RC estimates improve with additional data in both arms.

Source revision: `92e47167119da07bfbeb9bdeadf90335c6f836a2`.
The user ran eight workers, cells A/B, embedded and CC/CV charge-discharge loads,
noise seeds 1100/1103 at 2 mV, embedded load seed 7, cyclic temperature, compact
recording, 2,000 plot bins and approximately three-hour checkpoints. Each arm
processed 129,600,000 samples per case. This review performs no refit or replay.

[Original summary](../../experiments/foster_campaign_001/run_20261101_071802_121297/summary.json),
[per-case review and hashes](review.json), [baseline comparison](comparison.json),
[72-hour report](../h7_campaign_001/README.md).

## Findings

| Measurement across eight cases | H5 tangent | H7 tangent |
|---|---:|---:|
| Completed arms | 8/8 | 8/8 |
| Q 3SD misses / 64,800,000 outputs | 62,106,003 (95.84%) | 0 |
| SOC 3SD misses / 64,800,000 outputs | 52,465,422 (80.97%) | 75,804 (0.1170%) |
| Worst final absolute Q error | 0.005574% | 0.000646% |
| Worst final absolute SOC error | 0.002706 pp | 0.000145 pp |
| Worst final absolute RC parameter error | 3.269% | 2.666% |
| Additional refresh rejections after 72 hours | 0 | 0 |

The H7 Q local standard deviations shrink to about 0.318–0.322 of their 72-hour
values, close to the square-root scaling expected from ten times the data. Its
final Q errors remain within 2.31 local SD in all cases. H5 retains a small
negative Q offset and ends 9.08–21.06 local SD from truth: small physical error
does not establish valid uncertainty.

Across H7 outputs in bins intersecting the interval after 72 hours, absolute Q
error stays below 0.001962%, and SOC error below 0.000786 percentage points.
These are stored extrema, not averages that could hide excursions. Bins are
0.36 hours wide and the boundary bin is included whole. Early initialization
errors are much larger; these bounds do not describe the entire run.

There are no new solver failures or refresh rejections. The original cell-A
charge-cycle `round_limit` rejections remain: H5 570 and H7 671 total. Their last
occurrence is approximately 51.90 hours. Accumulated evidence was retained;
the longer run does not erase the startup convergence limitation.

## Remaining SOC issue

H7's 75,804 SOC misses split as follows:

| Case | Scenario | Misses | First miss bounded by checkpoints |
|---|---|---:|---:|
| 0005 | B, embedded, seed 1103 | 34 | 24.03–27.03 h, already present at 72 h |
| 0006 | B, charge-discharge, seed 1100 | 6,765 | 711.88–714.89 h |
| 0007 | B, charge-discharge, seed 1103 | 69,005 | 471.59–474.59 h |

The two new sets of misses all occur at nonzero current. Their miss fractions
over approximately the final half of the run are 0.167% and 1.706%, respectively.
Case 0007 has no new refresh rejection associated with the onset. Its small
cyclic errors and narrowing uncertainty warrant a targeted diagnostic, not an
inference that the estimator has physically diverged. Residual likelihood
approximation, state transport and local covariance remain candidate causes;
this review does not isolate them. The whole-run miss fraction must not hide
this concentration in particular cases and intervals.

[Q uncertainty](../../experiments/h7_campaign_001/review720_001/Q_uncertainty.png),
[SOC uncertainty](../../experiments/h7_campaign_001/review720_001/SOC_uncertainty.png),
and [focused late SOC view](../../experiments/h7_campaign_001/review720_001/late_SOC.png).
The overview curves divide bin-mean error by bin-mean local SD. The focused
view displays actual bin error extrema and separate mean-SD curves; these are
not sample-aligned coverage bounds. Miss counters use the original outputs.

## RC estimates

Worst absolute final error among R0, R1/tau1, R2/tau2 and R3/tau3:

| Case | H7 at 72 h | H7 at 720 h | H5 at 720 h |
|---|---:|---:|---:|
| 0000 | 10.40% | 0.89% | 0.74% |
| 0001 | 2.11% | 0.98% | 1.10% |
| 0002 | 4.49% | 2.03% | 2.01% |
| 0003 | 27.36% | 2.67% | 3.27% |
| 0004 | 6.02% | 1.34% | 1.40% |
| 0005 | 2.71% | 0.77% | 0.86% |
| 0006 | 17.77% | 1.27% | 1.31% |
| 0007 | 4.19% | 0.32% | 0.31% |

The improvement with longer stimulation occurs in both representations. It
does not establish an H7-specific RC repair, and no new EOD/brownout forecast
qualification was performed. H7's largest remaining final RC error is tau1 in
case 0003.

## Integrity, resources and next step

Every checkpoint checksum was verified. At the last common scheduled checkpoint,
69.0859 hours, all estimator numeric state, plant/controller/RNG state and
cumulative statistics match the earlier run exactly. Native contexts have
different source identifiers because the recipe includes the requested duration;
all factor/anchor/count/magic fields match. The initial raw-byte comparison is
preserved in [comparison_raw_context.json](comparison_raw_context.json), and the
final comparison explicitly separates source identity from estimator state.
Neither run was modified.

The local campaign occupies 413,191,401 bytes (about 413 MB / 394 MiB), including
plots and checkpoints. Compact plot storage is bounded; checkpoints grow with
duration. H7 estimator storage is unchanged: the packed likelihood factor alone
is 50,624 bytes (49.4 KiB), plus live state and substantial workspace. It remains
a desktop reference above the 10 KiB M23 SRAM target.

Keep this run as the sustained reference for compression. Before another longer
sweep, inspect a short case-0007 interval near the first late SOC misses, comparing
state error and joint covariance around load transitions and refreshes. Reuse a
case-0006 late interval as a second control. Judge a smaller representation on
practical Q/SOC/RC errors, covariance fidelity and sustained behavior; do not
inflate uncertainty merely to remove misses. The very small remaining physical
errors do not justify postponing storage work indefinitely.

These correlated time samples from two noise seeds and stationary cell parameters
do not validate statistical coverage, aging or ten-year accumulation. Cyclic
temperature is exercised; irreversible cell aging is not. Defaults and mainline
remain unchanged. No implementation changes or new simulation were made for
this review.
