# Joint refits: compact hysteresis improvement survives optimization

The six-term Taylor hysteresis representation remains a useful compact candidate
after full joint refitting. In four active-load cases its Q differs from the direct
fit by at most 0.058%, end SOC by 0.00160 percentage points, and Q/SOC local SDs by
at most 2.08%/1.16%. These are agreement with the direct numerical reference,
not physical accuracy or validated coverage. Rest and full-support limitations
prevent promotion.

## Controlled experiment

[Protocol](../../specifications/hysteresis_joint_refit_001/README.md),
[compact evidence](result.json), and
[runner](../../experiments/hysteresis_joint_refit_001/run.py).
Base revision 0f02271 on experiment/conditional-architecture-001. Replay the two
frozen 35 Hz prefixes (21008 and 126000 records, about ten minutes and one hour)
for rest, multiscale and embedded stimuli. Every arm keeps the original centres,
prior once, full rate/path support, two public starts and 60-round joint solver.
The native kernels and numerical optimizer are unchanged.

Five arms per case: direct, TaylorRC/H2, TaylorRC/TaylorH2, matched TaylorRC/H7,
and the distinct R5/H7 reference. All 24 compressed fits converge by the existing
criterion. Direct converges in five cases; both one-hour rest starts remain
unresolved with no_descent. There are 60 attempts, with four unresolved direct
attempts retained. All 18 unchanged direct/H2/R5 selected fits, including statuses,
roots and diagnostics, reproduce exactly. No support narrowing or recentering.

Readouts retain the historical solver results and independently compute joint QR
covariance roots. Same-anchor widths isolate likelihood distortion; comparisons
to the direct fitted reference also include movement of the fit. The original
chart, Q/gamma coupling and complete covariance are retained. Physical parameter
values and qualified differences are in result.json. Full one-hour rest fit-to-fit
and forecast comparisons are withheld because its reference is unresolved.

## Candidate results relative to direct fitted reference

| Input | Q difference (%) | SOC difference (pp) | Q SD ratio | SOC SD ratio |
|---|---:|---:|---:|---:|
| Short multiscale | -0.027250 | +0.001598 | 0.993875 | 1.007143 |
| Short embedded | +0.006284 | -0.000854 | 1.020770 | 0.999365 |
| One-hour multiscale | -0.057991 | +0.000936 | 0.995096 | 0.994771 |
| One-hour embedded | +0.007314 | -0.000654 | 1.011321 | 1.011568 |

SOC here uses direct physical transport. Compressed SOC transport agrees within
2.4e-10 pp on these cases. Their largest absolute H log-rate offset from the
original centre is 0.12976; these fits remain local even though the original
declared support is unchanged.

The one-hour embedded H2 control has Q/SOC width ratios 0.682762/0.583149 and
Q/SOC shifts -0.133259%/+0.039820 pp. Taylor H restores widths to approximately
1.01 and reduces both shifts. The one-hour multiscale Q shift improves from
+0.265960% to -0.057991%, though the short multiscale Q shift alone grows from
-0.003272% to -0.027250%. This is not universal dominance on every scalar.

For the four active cases, joint displacement in the direct local covariance
metric is 0.143–0.617, versus 6.80–27.57 with H2. This is a 16-dimensional local
distance, not a one-dimensional significance test. Direct objective excess at
the candidate fit is 0.011–0.178 NLL; these values are diagnostics with no invented
accept/reject threshold. Numerical convergence of a compressed objective does
not imply stationarity of the direct objective.

## Likelihood and transport uncertainty

At the candidate's own active fits, measured H-only and combined sufficient
precision tests pass in all four cases (combined epsilon 0.213–0.496). Q/SOC
same-anchor width ratios are 0.994718–1.023398 / 0.993487–1.013556. These are
sampled local checks, not a certificate over all support or future time.

The 60 s rest and 120 mA for 10 s followed by 30 s rest forecast tasks are evaluated
under both direct and compressed state transport. Across active cases and both
paths, voltage RMS difference from the direct fit is at most 3.543 microvolts;
local forecast SD ratios span 0.982168–1.050560. The largest width inflation is
the one-hour multiscale direct-transport rest forecast. Compressed transport alone
would make this look smaller, so both paths remain visible.

For comparison, that case's H2 direct-transport rest width ratios are
6.58–8.14, while compressed transport gives 0.827–0.910: compensation can conceal
an inference defect. The matched H7 control remains useful and is somewhat
closer in several diagnostics; it is not a guaranteed exact reference. R5/H7
is also imperfect, including a larger active multiscale joint displacement.

## Failures and scope retained

At rest, the hysteresis variants coincide and the Taylor RC defect remains:
combined epsilon about 8.6, direct-gradient defect about 2.1. The short rest
fit's pulse forecast differs by 0.462 mV RMS from direct despite nearly identical
Q/SOC widths. R5/H7 reduces this to 0.00394 mV. The one-hour direct rest fit stays
unresolved. Good Q/SOC agreement alone would miss this RC/forecast issue.

The earlier [off-centre failures](../hysteresis_sensitivity_basis_001/README.md)
are unchanged and were not rerun here: Taylor H is worse than H2 at some public
large offsets. H6's uniform derivative envelope is valid but yields epsilon
upper bounds approximately 1.39e3–6.66e4 at the active fitted anchors, far too
loose for a useful guarantee. Measured local success cannot replace that missing
bound. No full-support replacement, population coverage, aging, indefinite
history or production promotion follows from these six correlated cases.

The next focused experiment should address the remaining RC rest/large-offset
representation defect, retaining Taylor H as a provisional candidate and H7 as
a control. It should preserve the original support and test forecast uncertainty
as well as Q/SOC. A usable locality/remainder contract is still needed before
retiring raw evidence without a reference.

## Storage and validation

Candidate packed factor: **4760 B**. Factor, live response and domain scalars:
**5168 B** partial subtotal, unchanged from H2. Matched TaylorRC/H7 factor:
35720 B; R5/H7: 50624 B. The candidate's actual retained NumPy arrays occupy
10408 B, with separate chunk/QR workspace and up to 5,040,000 B of observations.
These subtotals exclude a complete MCU prior/solver/workspace/stack accounting;
this desktop replay reference is not firmware-ready.

Five focused tests cover key routing, public starts/domain/budget, QR covariance,
control mismatch detection and native uncertainty/gating. Independent reviews:
[implementation](implementation_review_r1.json) and
[results/reproduction](results_review_r1.json). See [validation](validation.json)
and [receipt](receipt.json) for commands, bindings and final dispositions. Generated
fit files, native binaries, input arrays and factor snapshots remain ignored locally.
