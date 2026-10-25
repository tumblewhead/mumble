# M1 full-vector error and revised product thresholds

This is a post-inference supplement to the completed M1 experiment. It uses the
original fit records and observations without new optimization, inference
replay or replacement of any frozen M1 result.

## Product thresholds

The new capacity hard limit is 5% relative error and the new SOC hard limit is
10 percentage points. The preferred region is 0.5% capacity error and 0.5
percentage points SOC error, beyond which the user expects diminishing gains.
These are accuracy requirements assessed against synthetic truth, not certified
error bounds or validated coverage. The existing local-precision diagnostic
thresholds and the original M1 acceptance record remain unchanged.

Across the 16 declared arm/checkpoint comparisons, all 16 satisfy the SOC hard
limit. Fourteen satisfy the capacity hard limit. Cell B at 900 seconds in the
control and identical warm path still fails capacity at +26.6298%; its SOC
error of -3.96355 percentage points is within the new SOC hard limit. All 14
joint hard-limit passes also lie in the preferred region. The first sustained
joint accuracy time among saved queries remains 900 seconds for A and 1800
seconds for B. Cold paths remain unknown until their scheduled 1800-second fit,
then satisfy both preferred thresholds through the final saved query.

The relaxed SOC requirement therefore changes the interpretation of the B900s
failure, but capacity still prevents overall acceptance. Early unresolved
points are also retained: maximum available capacity errors are 41.67% for A
and 26.63% for B; maximum available SOC errors are 7.51 and 9.05 percentage
points. These are sparse-query maxima, not bounds on all intervening samples.

## What the full vector means

The sixteen physical quantities are eleven static parameters (R0, three RC
resistances, three RC time constants, hysteresis amplitude, two hysteresis
rates and capacity), plus the entering SOC, three entering RC voltages and
entering hysteresis state. Entering state refers to sample zero in control and
to the reset epoch at 900 seconds in the cold path. Current state is reported
separately below.

A raw norm mixing ohms, seconds, volts, Ah and SOC is not meaningful. For a
single declared aggregate, this supplement uses the estimator's existing
coordinate chart and scales:

`e_i = (estimate_i - truth_i) / coordinate_scale_i`

`scaled_RMS = sqrt(sum(e_i^2) / 16)`

Tau, hysteresis rates and capacity use log coordinates; SOC is linear; the
linear amplitudes include u0=H*h0. The scales are the existing engineering
scales, not uncertainties. The aggregate is dimensionless and scale-dependent;
it is not a percentage, a posterior distance or a coverage statistic.

| Cell/path | Nominal time, s | Scaled RMS | Maximum scaled component | Rank | Optimizer status | Provisional physical coordinates |
| --- | ---: | ---: | ---: | ---: | --- | ---: |
| A, control | 10 | 1.083001 | 2.512306 | 6/16 | converged | 0/16 |
| A, control | 900 | 0.030027 | 0.089672 | 16/16 | converged | 14/16 |
| A, control | 1800 | 0.024791 | 0.083910 | 16/16 | converged | 14/16 |
| A, control | 2100 | 0.023706 | 0.082061 | 16/16 | converged | 14/16 |
| A, cold | 1800 | 0.028350 | 0.073463 | 16/16 | converged | 12/16 |
| A, cold | 2100 | 0.021984 | 0.065009 | 16/16 | converged | 12/16 |
| B, control | 10 | 1.112179 | 3.374886 | 7/16 | converged | 3/16 |
| B, control | 900 | 1.087344 | 2.415329 | 16/16 | iteration limit | 0/16 |
| B, control | 1800 | 0.010897 | 0.031642 | 16/16 | converged | 16/16 |
| B, control | 2100 | 0.011203 | 0.032743 | 16/16 | converged | 16/16 |
| B, cold | 1800 | 0.033645 | 0.080733 | 16/16 | converged | 13/16 |
| B, cold | 2100 | 0.033326 | 0.082202 | 16/16 | converged | 13/16 |

The early rest gives only rank6/16 for A and rank7/16 for B. Cell B900s has
rank16 at its fitted point yet a poor, nonconverged vector; all sixteen physical
reports are unresolved. Full local rank does not establish reliable numerical
convergence or accuracy. At 2100 seconds A still has unresolved R0 and tau1
because their local ranges exceed the existing relative precision screen,
although their point errors are small. B's full-history result has all sixteen
physical coordinates provisional. Provisional is a local diagnostic, not a
coverage guarantee.

## All sixteen errors at 2100 seconds

Warm results equal control. Positive parameters use signed relative percent;
entering-state errors use the explicit units below to avoid division by small
or zero entering states.

| Quantity | Error units | A control/warm | B control/warm | A cold | B cold |
| --- | --- | ---: | ---: | ---: | ---: |
| R0 | relative percent | -0.077142 | -0.423634 | +2.835127 | +10.275221 |
| R1 | relative percent | -1.008919 | +0.828607 | -3.009619 | -7.027920 |
| R2 | relative percent | +0.056281 | -0.436583 | +1.737080 | +0.103169 |
| R3 | relative percent | +0.641245 | -0.071203 | -0.589932 | -0.621546 |
| tau1 | relative percent | -1.501662 | -1.391695 | +3.395179 | +1.502401 |
| tau2 | relative percent | -2.126673 | -0.068255 | +2.560484 | +2.287113 |
| tau3 | relative percent | -0.614451 | -0.292188 | +0.740894 | -0.421308 |
| H | relative percent | +0.006801 | -0.111972 | -0.597974 | -2.058207 |
| gamma_plus | relative percent | -0.080707 | +0.353133 | -0.906236 | +1.166141 |
| gamma_minus | relative percent | +0.269263 | +0.170967 | +1.000762 | +3.052879 |
| Q_Ah | relative percent | +0.010786 | +0.000105 | +0.007027 | +0.126530 |
| z0 | percentage points | -0.004453 | +0.000234 | -0.016556 | -0.047644 |
| v10 | mV | +2.461828 | -0.982301 | -1.950262 | +1.373741 |
| v20 | mV | -1.083910 | +0.722274 | -0.016618 | -0.484059 |
| v30 | mV | +0.208793 | -0.055447 | -0.077824 | -0.093180 |
| h0 | absolute dimensionless | -0.002136 | +0.000567 | -0.003866 | -0.006283 |

For the final full-history fits, the largest positive-parameter error is tau2
at -2.12667% for A and tau1 at -1.39169% for B. The entering fast RC voltage still
has +2.46183mV error for A and -0.98230mV for B. Those initial-state errors are
not errors in the current RC voltage: the fitted dynamics transport and decay
the initial state.

In the cold B result, R0 is +10.2752% and R1 is -7.02792% while capacity is
+0.12653% and current SOC is -0.03137 percentage points. R0, R1 and tau1 remain
unresolved locally. This is a concrete case where useful SOC/capacity estimates
do not require every nuisance parameter to have subpercent error.

## Current hidden-state error at 2100 seconds

The scorer reconstructs both estimated and true current states through the
actual ordered inputs. These endpoint errors are distinct from the entering
states in the fitted vector.

| Cell/path | Current SOC error, pp | Current RC voltage errors, mV | Current hysteresis-state error |
| --- | ---: | --- | ---: |
| A, control | -0.002013 | -0.005448, +0.000371, +0.005386 | -0.000806 |
| B, control | +0.000256 | +0.005469, -0.003536, -0.000705 | +0.000923 |
| A, cold | -0.015580 | -0.016252, +0.011465, -0.004955 | -0.005172 |
| B, cold | -0.031367 | -0.046384, +0.000836, -0.006153 | +0.000113 |

## Evidence and reproduction

- [summary.json](summary.json): threshold semantics, aggregate definition,
  sampled first/sustained accuracy, validation and source hashes.
- [records.json](records.json): all twelve unique fit vectors, individual
  errors, local statuses/ranges, scaled components and current-state errors.
- [audit_m1_belief.py](../../tools/audit_m1_belief.py): reproducible scoring-only
  audit; refuses to overwrite an existing output directory.

The audit passed 117 consistency/preservation checks, including input/output
hashes, local rank and SOC/capacity status agreement with the saved C reports,
independent current-SOC agreement and unchanged source data. It made zero
optimizer calls and did not repeat primary inference. Its offline local
assessment uses the existing frozen Gram and existing diagnostic thresholds;
truth enters error scoring only.

```sh
python3 tools/audit_m1_belief.py --output-dir /tmp/mumble-m1-belief-reproduction
```
