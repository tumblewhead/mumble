# Free/forced RC partition repairs the observed rest discrepancy

Giving only the free RC response a degree-five basis reduces the short-rest pulse
forecast discrepancy from **461.994 to 3.936 microvolts RMS**, approximately
117-fold. The forced RC response keeps its compact degree-two Taylor basis;
hysteresis keeps the six-term Taylor basis. The measured local combined-precision
test now passes at all six selected candidate anchors, including both rests.
This is a targeted representation repair, not a whole-support or lifetime guarantee.

The [P4 derivation](../../specifications/rc_partition_repair_001/P4.md) explains why:
for an entirely zero-current history from the retained origin, forced RC response
and its derivatives vanish. Only the free decay can explain the RC approximation
defect. Later rest after active use is different: forced state must persist.
The candidate always runs both families, with no rest detector, reset or rig input.

## Design and evidence

[Registered plan](../../specifications/rc_partition_repair_001/README.md),
[compact refits](result.json), [public response probe](probe.json), and
[runner](../../experiments/rc_partition_repair_001/README.md).
Base 8ebf9b4, branch experiment/rc-free-forced-repair-001. Six frozen cases at
21008/126000 records, original public centres/prior/support and two starts,
unchanged 60-round solver. Every observation contributes once to one joint factor.
The partition changes response features, not the battery parameterization.

Seven arms: direct, previous TaylorRC/TaylorH2, free3/forced2/TaylorH2,
free5/forced2/TaylorH2, full RC5/TaylorH2, TaylorRC/H7 and R5/H7. All 36 compressed
fits converge by the existing numerical criterion. Direct converges in five cases;
the one-hour rest direct reference remains unresolved. All 24 unchanged selected
controls reproduce exactly. All 84 attempts are retained: 80 converge and four
direct attempts remain unresolved. The latter are not physical exclusions.

QR-based uncertainty readouts retain full cross terms, the Q/gamma coordinate
chain and direct versus compressed transport separately. No Taylor free-response
remainder bound is applied to the new collocation free response. Measured M1/P3
local checks remain distinct from uniform analytic bounds or validated coverage.

## Rest repair and active-case tradeoffs

| Representation | Short-rest pulse RMS difference (uV) | Short/full rest combined epsilon | Packed factor (B) |
|---|---:|---:|---:|
| Previous Taylor RC | 461.994 | 8.618 / 8.545 | 4760 |
| Free3 / forced Taylor2 | 53.941 | 5.063 / 4.844 | 5624 |
| Free5 / forced Taylor2 | 3.936 | 0.191 / 0.177 | 7568 |
| Full RC5 / Taylor H | 3.936 | 0.191 / 0.177 | 11024 |

The smaller cubic candidate improves rest point agreement but leaves the sufficient
precision test inconclusive. The degree-five free partition matches the full-RC5
Taylor-H selected fits exactly in both rest cases; the R5/H7 reference agrees to
floating precision. In the short rest case, fitted slow tau changes from 3.0054 s
with Taylor RC to 2.35359 s, versus direct 2.34783 s. Joint displacement in the
direct local covariance metric drops from 2.585 to 0.01823. Q remains at its prior
under rest, so its agreement supplies no new capacity identification evidence.

The one-hour rest local test compares precision at the candidate anchor; its
direct fitted reference is still unresolved. Accordingly no one-hour rest
fit-to-fit or forecast qualification is reported.

For the free5/forced2 candidate, differences below are against the direct fitted
reference, not hidden plant truth:

| Active input | Q difference (%) | SOC difference (pp) | Q SD ratio | SOC SD ratio | Largest forecast RMS difference (uV) |
|---|---:|---:|---:|---:|---:|
| Short multiscale | -0.025610 | +0.001614 | 0.993892 | 1.007176 | 0.423 |
| Short embedded | +0.005877 | -0.000809 | 1.020830 | 0.999403 | 7.573 |
| One-hour multiscale | -0.057689 | +0.000955 | 0.995098 | 0.994795 | 1.528 |
| One-hour embedded | +0.007044 | -0.000636 | 1.011425 | 1.011633 | 2.010 |

Forecast maxima include both tasks and both direct/compressed transport paths.
Local forecast SD ratios across active cases span 0.981902–1.050562. Candidate
same-anchor Q/SOC width ratios span 0.994716–1.023185 / 0.993468–1.013554. These
local uncertainty differences do not establish calibrated coverage.

There are regressions: short embedded forecast RMS grows from 3.542 to 7.573 uV,
and short multiscale from 0.377 to 0.423 uV. Cubic free response is worse in those
tasks (23.254 and 1.157 uV). Enlarging both RC families also does not universally
improve fitted forecasts. Keep all arms visible; no scalar or whole-system
dominance claim is supported.

## Off-centre obstruction is now isolated more clearly

The public 600-record irregular signed-current probe checks nine common RC
log-offsets, with nonzero public incoming RC voltages and no fit or truth input.
Free5 reduces the sampled free-response value defect at log offset -1 from
0.0660 to 0.000268, and at +1 from 0.0669 to 0.000263. It sacrifices exact central
matching: at zero offset, free-response defect is about 0.000294 versus rounding
for Taylor; the resulting combined RC voltage discrepancy is about 0.9715 uV.

Forced Taylor error is unchanged. At offset -1 the total RC voltage discrepancy
is 1.405 mV for free5/forced2, versus 1.360 mV for the old Taylor representation;
at +1 it is 1.087 versus 1.146 mV. Removing a free error can remove cancellation
with the forced error. Full RC5 reduces these sampled discrepancies to about
5.58/6.23 uV, but costs an 11024 B factor before other memory. Sampled maxima are
not uniform bounds. Earlier off-centre H regressions and loose H6 envelopes also
remain; this study neither repairs nor requalifies them.

The conclusion is specific: independent free/forced representation earns its
storage for the demonstrated rest problem. It does not solve the forced response
over the original full rate box. The next experiment should target that forced
response and its sensitivity while retaining central matching, with an explicit
memory budget and the same uncertainty/transport controls. Do not silently narrow
support, recenter retained evidence, or launch a lifetime qualification from this
finite stationary study.

## Resources and review

The candidate factor is 7568 B; padded live response is 456 B, and the existing
domain/scalar allowance is 96 B: **8120 B partial subtotal**. This is 2952 B above
the previous 5168 B partial subtotal and 3456 B below full-RC5/Taylor-H's 11576 B.
The actual Python arrays occupy 17680 B, including the dense 14792 B factor and
projection/index tables. The current diagnostic allocates full native rows then
selected rows (425984 and 352256 B per 1024 records), plus QR workspace and up to
5040000 B of observation replay. These allocations are not firmware memory claims.
Complete prior/solver/stack/platform SRAM and Cortex-M23 timing remain unqualified.

P4 has an [individual independent review](p4_review_r1.json); native implementation
and fit plumbing have a separate [review](implementation_review_r1.json). Five
targeted tests cover original row controls, zero-origin/later-rest distinction,
derivative/covariance chains, chunking and atomic refusal. A third reviewer covers
[results and reproduction](results_review_r1.json), including the mechanism probe.
The [validation](validation.json) and [receipt](receipt.json) bind final artifacts.
No production kernel, campaign default or mainline change; generated runs remain
local and ignored.
