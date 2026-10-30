# Hysteresis diagnosis from the owner's 12-hour campaign

The [read-only result](attempt001/result.json) snapshots the seven completed cases
available during inspection of `foster_campaign_001/run_20261030_064220_507192`.
The eighth case was not part of this diagnosis. No estimator, stimulus, original
result or running campaign was modified; no new fit was performed.

For cell A, repeated-cycle loading and 8 mV added voltage noise, the float64
history arm ends with the following reference-temperature parameters:

| Parameter | Plant | Estimate after 12 h |
|---|---:|---:|
| H | 15 mV | 15.318 mV |
| gamma+ | 6 | 1.279 |
| gamma− | 9 | 10.969 |

During its final hour, hysteresis-voltage error averages −9.093 mV while OCV/SOC
error averages +9.069 mV. The complete assimilated voltage fit differs from the
noiseless plant by only 0.123 mV RMS. It is therefore possible to match voltage
closely with incorrect internal hysteresis and SOC. The
[component plot](attempt001/hysteresis_cancellation.png) shows this compensation.
The sum of independently extracted OCV, hysteresis, ohmic and RC errors agrees
with total voltage error within 1e−12 V for every inspected arm.

Weak stimulus separation is a plausible contributor. At cell A's 25 °C reference,
the model gives hysteresis time constants `3600Q/(gamma*abs(I))`: 20 minutes for
positive current and 13.3 minutes for negative current at 30 mA. The cycle load
reverses after 50 seconds, moving only 4.1% or 6.1% of the remaining distance to
the directional asymptote. Even the longest multiscale pulse has an exponent of
only 0.075 or 0.1125. In the final hour of the cycle case, true h spans only about
−0.226 to −0.174, with hysteresis voltage spanning less than 0.86 mV.

At fixed temperature define `u=Hh`. Its exact equation is
`du/dxi=gamma_dir*(H*sign(I)-u)`. A short pulse primarily constrains
`gamma_dir*(H*sign(I)-u)/Q`, rather than separately determining H, gamma and Q.
For fast balanced cycles the approximate center is
`h_bar=(gamma_plus-gamma_minus)/(gamma_plus+gamma_minus)`.
Near that center, neglecting relaxed RC terms, terminal slope is approximately
`I/(3600Q)*[-b+2H*gamma_plus*gamma_minus/(gamma_plus+gamma_minus)]`.
This explains coupling to apparent capacity and the OCV/SOC offset. These are
small-pulse approximations, not proof that the full nonlinear data cannot identify
the parameters. Repeated observations, startup transients and temperature changes
may provide additional information.

Uncertainty is also misleading: gamma+ in the example has reported log SD 0.0371,
while its log error is approximately 41.6 times that SD. These local Gaussian
SDs are already unvalidated; this mismatch is a diagnostic of false precision,
not a calibrated statistical significance statement. It occurs with float64
history, so float32 encoding is not required for the failure.

The next controlled comparison should fit one existing trace with its retained
nonlinear likelihood and public prior, comparing hysteresis/SOC/Q estimates and
joint likelihood shape with the streaming result. That separates what the data
support from effects of optimization and irreversible local history projection.
Then add longer, unequal-duration charge/discharge excursions, chosen using the
public prior and physical SOC domain, to probe hysteresis curvature and both
directions. More cycles alone should not be assumed to repair the bias, and
changing the uncertainty width by an arbitrary factor would not establish a fix.

This diagnosis adds no history storage or algorithm change. Existing payload
estimates remain 2,184 bytes per message, or 6,269 bytes for two messages plus a
float32 token before raw samples and solver workspace.
