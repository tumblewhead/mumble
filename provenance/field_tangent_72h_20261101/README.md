# 72-hour tangent comparison and oscillation review

All16cases and48arms completed72hours at50Hz. The16cases cross cellsA/B,
embedded/cycle loads,2/4mVnoise and seeds1103/314159, with embedded load seed7.
The [receipt](receipt.json) binds source identities, original evidence hashes,
metrics and three full-resolution diagnostic replays. No inference code or
original results were changed. `review.py` reproduces the analysis.

The candidate lowers SOC RMSE in16/16cases and Q RMSE in13/16against field64.
Pooled RMSE across equal-duration cases:

| Load | Arm | Q RMSE (%) | SOC RMSE (pp) |
|---|---|---:|---:|
| Embedded | field64 | 0.1881 | 0.0340 |
| Embedded | tangent64 | 0.1515 | 0.0202 |
| Repetitive cycle | field64 | 1.9386 | 0.0471 |
| Repetitive cycle | tangent64 | 1.6356 | 0.0241 |

There were1174rejected field refreshes and1298rejected tangent refreshes out of
68928attempts each. Tangent had no emergency recovery or failed arm; rejected
scheduled refreshes retain evidence and remain explicit. Most rejected fits are
in weak-cycle cases, and their last rejections precede the late replay intervals.

## Identified fast Q/H/gamma behavior

The strongest matching source is the **existing field64 arm**, especially the
4mVrepetitive-cycle cases0006,0007,0014and0015. Full-resolution replay confirms
large correlated excursions and jumps aligned with the60.16second field refresh.
The native tangent suppresses these excursions on the same samples.

Case0006 (cellA, cycle,4mV, seed1103),53.35–53.60hours:

| Reference parameter | field64 peak-to-peak / true value | tangent64 peak-to-peak / true value |
|---|---:|---:|
| Q | 9.1206% | 0.1023% |
| H | 108.1459% | 0.9192% |
| gamma+ | 42.2976% | 0.4390% |
| gamma− | 40.6927% | 0.4956% |

Median absolute Q jump at refresh is1.093percentage points forfield64,
versus0.00090for tangent. Log-Q and log-H increments are almost perfectly
anticorrelated. This supports the previously diagnosed weak joint direction
and Gaussian feedback-boundary problem: rolling estimates move away between
refreshes and are reset by full history. It does not establish a new battery
phenomenon or prove the remaining approximation unbiased.

[Separate-arm full-resolution plot](../../experiments/field_tangent_native_001/review72h001/case_0006_Q_H_gamma.png)
and [second cycle example](../../experiments/field_tangent_native_001/review72h001/case_0007_Q_H_gamma.png).
All complete replay bins have bitwise-identical minima and maxima to the stored
original summaries. Physical bin means agree to floating-point summation error.

These swings already occur early and diminish. Forcase0006, the95thpercentile
within-bin H span decreases from208% in0–4h to53.5% in48–72h forfield64; tangent
falls from12.0% to1.16%. The settling mean makes the remaining fast variation
prominent. Compact bins cover129.6seconds; they cannot identify its timing without
replay. These statistics describe the isolated cases, not every possible oscillation.

## What remains unresolved

Weak-cycle final Q error is still+1.265% to+3.142% for tangent, with local log-Q
SD0.86–1.74%. H is11–30%low. Final log-Q/log-H correlation is approximately−0.999.
This is consistent with weak joint identification under the short balanced
stimulus. Thus Q is not uniformly resolved even though SOC point error is small.

The embedded cases finish with absolute Q error below0.0046%, but still have
substantial local-uncertainty misses: pooled tangent SOC3SDmiss rate27.45%, and
some individual cases exceed50%. Weak-cycle tangent Q/SOC miss counts are zero,
versus4.50%/1.75% forfield64. These correlated time-series counts are diagnostics,
not independent coverage trials. Shared field approximation bias remains relevant.

Final RC estimates for the two field arms are nearly identical: their largest
RC relative-error difference is0.00511percentage points. Tangent final errors span:

| Parameter | Signed error range |
|---|---:|
| R0 | −3.26% to+1.13% |
| R1 | −5.45% to+6.65% |
| tau1 | −16.15% to+13.45% |
| R2 | −1.89% to+3.69% |
| tau2 | −5.61% to+2.49% |
| R3 | −1.17% to+1.56% |
| tau3 | −1.81% to+1.34% |

An isolated incremental Foster/ohmic120mAstep computed from final point estimates
has a maximum error below0.482mVover the sampled0–60sgrid at17/25/33°C. Correlated
parameter errors can compensate in voltage response. This diagnostic omits initial
polarization error, SOC/OCV/hysteresis changes, uncertainty and the power path.
It is not an EOD/brownout forecast qualification; sub-sample times are extrapolation.

There is sufficient value to retain the tangent implementation in mainline as an
opt-in comparison. Changing the default is a separate promotion decision. Next,
compare onlyfield64and tangent64 in readable parameter-error plots, then qualify
causal proposed-load forecasts from checkpoints with joint uncertainty. Keep Q/H
ambiguity and coverage failures visible while targeting RC/EOD performance.
