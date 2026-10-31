# Owner 720-hour joint-field campaign review

The conspicuous struggle in seed 1103 / load seed 7 is principally the original
`float64` rolling arm at 20 mV noise (`case_0006`). The field-assisted `field64`
arm substantially improves capacity, SOC and the RC parameters. Load seed 8
with the same noise seed also struggles in the baseline, so this is not unique
to load seed 7.

Source: `experiments/foster_campaign_001/run_20261031_182600_810547`, revision
`7d8b6ae09e76951722b092071e2d81cf9dd44959`. All eight cases and sixteen arms
completed 720 hours at 50 Hz. [review.json](review.json) records the calculations
and input hashes; [review.py](review.py) reproduces them from compact summaries
and final joint messages. No simulations, refits, source changes to estimation,
or modifications to original evidence were performed.

## The highlighted case

Final signed errors, 20 mV / noise seed 1103 / load seed 7:

| Quantity | Rolling | Field feedback |
|---|---:|---:|
| Q | +0.16536% | −0.00343% |
| SOC | −0.03756 percentage points | +0.00138 percentage points |
| R0 | −49.67% | −2.70% |
| R1 | −71.61% | +3.47% |
| tau1 | −92.38% | −8.20% |
| R2 | +57.46% | +1.47% |
| tau2 | −78.05% | −0.37% |
| R3 | +28.81% | +0.12% |
| tau3 | −25.79% | +0.30% |

The true pole times are 0.05, 0.5 and 5 seconds. Rolling ends at 0.003809,
0.10973 and 3.71049 seconds; field feedback ends at 0.045900, 0.49813 and
5.01505 seconds. The remaining high-noise field RC errors are all within
0.73 of their respective local log-parameter SDs. This does not establish
coverage, but the residual fast-pole error is consistent with considerable
local uncertainty: its log-SD is about 15.5%.

The last bin containing a Q/SOC application-band violation ends at 74.16 hours
for rolling and 5.04 hours for field feedback. Bins are 0.36 hours wide; these
are conservative bin endpoints, not exact settling times. Whole-run capacity
RMSE is 0.44787% versus 0.08658%. Every one of this case's 43,085 field refreshes
was accepted.

Local plots:
[errors](../../experiments/foster_campaign_001/run_20261031_182600_810547/case_0006/errors.png),
[reference parameters](../../experiments/foster_campaign_001/run_20261031_182600_810547/case_0006/parameters_reference.png).

## Timing and interpretation

The baseline RC representations separate strongly during approximately hours
6–12. At a bin ending 12.24 hours, load seed 7 has mean tau1 about 5.1 ms;
load seed 8 has about 2.0 s. Both have the same true 50 ms pole. These paths
eventually settle to very different wrong RC decompositions. This is evidence
of sensitivity to observations and historical approximation, rather than a
common fixed physical pole offset; it is not a controlled proof of one solver
failure mechanism.

In case 0006, the final baseline tau1 is below the 20 ms sampling period.
That fitted mode decays almost completely within a sample and can trade with
instantaneous resistance. More broadly, wrong branch resistances compensate:
the baseline R0+R1+R2+R3 is 0.34222 ohm, only 0.65% from the true 0.34000 ohm.
The field value is 0.340007 ohm. Similar total resistance does not imply the
correct frequency response, nor does a small voltage residual certify each
hidden RC parameter. The periodic SOC error is consistent with the remaining
capacity and hysteresis compensation over charge/discharge cycles; no new
mechanistic attribution is proven here.

The original baseline at 20 mV / seed 1103 / load 8 is also an outlier: final Q
error +0.18183%, compared with −0.00132% for field feedback. At 2 mV / seed 1103 /
load 7, Q errors are +0.00239% and −0.00421% respectively; baseline RC errors
remain appreciable even when Q is very accurate.

## Whole-campaign outcome and remaining obstacle

There were nine rejected refreshes out of 344,680 attempts, all in two other
cases during the first 3.48 hours, with the recorded reason `round_limit`.
The affected arms recovered. They do not explain the highlighted trajectory.
All field arms' final 72-hour extrema stay below 0.0059% Q error and 0.0035
percentage points SOC error. This is sustained stationary-cell evidence over
720 hours, not an aging or indefinite-stability qualification.

There is still a systematic precision issue at low noise. The four 2 mV field
cases finish with Q errors −0.00421% to −0.00471%, while local log-Q SDs are
approximately 0.000330%. Their final errors are 12.76–14.28 local SDs from
truth. Their recorded three-SD bands miss truth on about 94–98% of the updates.
Those updates are strongly dependent; the proportions are descriptive and
must not be treated as independent coverage trials. In contrast, the four
20 mV field endpoint Q errors are 0.33–1.39 local SDs from truth.

The practical point errors are far below the 0.5% application target. The
remaining issue is whether the history carries an honest uncertainty floor
as data accumulate. The common low-noise offset is consistent with the
previously measured compressed-likelihood gradient defect, but no retained-data
reference was fitted at 720 hours here, so that cause is not established for
this run.

The next focused experiment should measure derivative/approximation error on
selected low-noise prefixes and propagate its effect into joint uncertainty,
while keeping this successful integration as the control. The high-noise fast
RC widths should remain explicit instead of forcing every nuisance parameter
to meet the capacity/SOC accuracy target. No threshold tuning, scalar inflation
or production change is warranted solely by this review.
