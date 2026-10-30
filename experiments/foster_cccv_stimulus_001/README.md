# CC–CV and variable-load stimulus

The campaign now accepts `--loads charge-discharge`: constant current limited
by a scheduled charger capability, constant-voltage taper, rest, variable-load
discharge to a voltage cutoff, and rest. The user requested 2C charging,
0.2–0.7C discharging, taper near90%SOC, and changing charger/load capabilities.
See the [runner guide](../foster_campaign_001/README.md) for the full command.

Only the harness changes. C-rates use a declared60mAh nominal capacity, not
hidden trueQ. The controller consumes indexed measured terminal voltage; it
never reads true SOC, plant parameters or estimator feedback. Defaults are
2C/1C/1.5C capability in15min steps,0.2C/0.45C/0.7C discharge in10min steps,
4.06V CV,3.18V discharge cutoff,5min rests and0.05C taper endpoint held30s.
The integral CV controller has a declared0.5A/(V·s) gain and current saturation.
The same acquired noisy voltage supplied to the estimator drives the next
controller interval. There is no algebraic voltage clamp or state reset.

One [four-hour control](cycle001/case_0000/result.json) used cellA,4mV voltage
noise, cycling17–33°C temperature and both encodings. Both arms processed all
504,000 observations, retired31,500 tokens, and completed with no pending records.
The plant completed one discharge cycle and began a second, including two CC–CV
charges. The two tapers began at89.106% and89.207%SOC, scored afterward; charge
ended at93.351% and93.444%. The first discharge cutoff occurred at16.412%SOC.
The default therefore implements a roughly16–93% operating excursion for this
case, not an assumed0–100%cycle. Changes in capability and temperature can move
these points. No chemical-cell charging protocol or thermal-derating law is certified.

| Final quantity | Plant/reference | Float32 estimate/error |
|---|---:|---:|
| H | 15 mV | 15.115 mV |
| gamma+ | 6 | 5.886 |
| gamma− | 9 | 8.793 |
| Q relative error | — | −0.04035% |
| SOC error | — | −0.00742 percentage points |

These are final point diagnostics from one run. They do not establish coverage,
aging or sustained accuracy. Numerical stops and all uncertainty misses remain
in the result. Maximum float32/float64 differences were0.00845%Q and0.00301SOC
points. The one-case generation/estimation time before plots was38.0host seconds.
The physical model, prior, fitter and history backend were not retuned.

[V/I/T plot](cycle001/case_0000/signals.png) ·
[State/voltage errors](cycle001/case_0000/errors.png) ·
[Reference parameters](cycle001/case_0000/parameters_reference.png)

All22 controller/campaign/process tests pass, alongside the55 parent solver checks.
Targeted controller tests cover current signs/C-rate conversion, capability/load
steps, CV regulation using only measured voltage, taper dwell/reset, rests and
cutoff transitions, input/domain validation, chunk/seed invariance and aligned
event logging. A short serial/parallel comparison checks the new arguments and
byte-identical inputs, truth, events and both estimate traces. The original
campaign and parallel tests also run; no long campaign sweep is required.

[plan.json](plan.json) records the request, assumptions and archived pre-change
runner/stimulus/documentation. Original experiment results remain unchanged.
The history payload is still2,184B per message or6,269B for two messages plus a
float32 token, before active observations/solver workspace. Controller state is
harness-only. Recorded arrays/CSV continue growing with run duration as before.
