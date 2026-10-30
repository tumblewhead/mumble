# SOC transport repair and a practical long-run gate

The user asks to analyze overall behavior before further optimization, with
diminishing value below approximately0.5% error. This step uses the established
preferred scales of0.5% relative Q and0.5SOC percentage points for comparisons.
They are application scales, not probability-coverage or universal history-error
certificates. We do not tune approximation order to reproduce tiny likelihood
differences once these query scales are met.

## Error mechanism

The old grid represents a translated point between two nodes separated by h
as weights(1-f,f). Its mean is correct, but its variance is h^2*f*(1-f).
Repeated transport injects variance that is unrelated to measurement noise,
capacity uncertainty or physical aging. A later nonlinear OCV likelihood then
uses a different SOC distribution, so both SOC and capacity learning can change.
Refining a fixed grid reduces this defect but increases memory and work.

The repair carries continuous SOC coordinates conditional on the same health,
temperature and nuisance hypotheses. For weights w_i entering a new health
state, the exact first two mixture moments are

    m = sum_i w_i*m_i,
    V = sum_i w_i*[V_i+(m_i-m)^2].

The known conditional charge decrement then changes m to m-d without changing
V. Initial-SOC mixture identities remain separate. Therefore real health-path
uncertainty creates variance, while deterministic translation does not. The
same temperature-path reciprocal-capacity integral and actual intervals are
used; no endpoint-only replacement of accumulated charge is made.

The resulting mixture is projected to one conditional Gaussian per retained
hypothesis. Voltage conditioning uses a first-order OCV approximation around
that conditional mean, with physical RC/hysteresis responses retained for each
nuisance candidate. This is an explicit nonlinear approximation. It is neither
exact posterior closure nor an original-model proof of Gaussian support.
Mean-domain checks do not certify the support of a Gaussian's entire tail.
Uncertainty and likelihood errors are reported separately from point-query
agreement. A short unmerged continuous-SOC path oracle checks the repair without
the grid and without the moment projection.

## Preserve useful history through longer operation

Two four-hour35Hz controlled streams are planned. One is stationary; the other
has a single15% reference-Q loss and15% reference-R0 rise after one hour. That
jump is an accelerated in-support model stress, not realistic aging calibration.
Both have90minutes of excitation,90minutes of weak zero-current use and60minutes
of renewed excitation. Their physical truth is generated using the original C
recurrence; the estimator sees observations and public inputs only.

The same public prior and assumed aging rate are used across cases. Initial
SOC has a public mixture with conditional0.03SD for these long streams, rather
than being set from truth. The old discrete prior is retained for the short
oracle comparison. These are separate declared experiments. The hypothesis
family remains a reduced finite support, so an in-support trajectory result
does not qualify general cells, arbitrary chemistry, continuous nuisance
parameters or calibrated coverage.

Compare uncompressed binary64 log weights, the previous fixed-range log16
encoding, and a binary32 log-weight diagnostic. Preserve log weights even when
their converted linear probabilities underflow in a readout. Fixed log16 must
report an exceeded dynamic range; it cannot clip weights, reset history or
silently widen its span. One failed encoding arm must not abort the other arms.
Each receives the same owned observations exactly once and retains chronology.

The existing log-ratio lemma applies to encoded weights with fixed conditional
shapes. When quantization changes later mixture moments, it does not by itself
bound the entire continuous posterior; the long experiment measures resulting
mean/variance/point differences explicitly. It supplies no ten-year guarantee.

## Scope and stopping rule

This is an end-to-end stream diagnostic for the repaired reduced history
model. It does not silently insert a posterior as independent evidence in the
original rolling optimizer or relabel this prototype as that C solver. A short
benchmark precedes long execution. Only measured execution problems justify
implementation optimization; no precision sweep is planned.

After short-prefix differences meet the practical query scales, move on to
long-run findings. Record point error, numerical status, uncertainty evolution,
history-versus-reference degradation, aging/re-excitation recovery, memory and
time. A small final error cannot hide intervening failures. Archive failed arms
and numerical adaptations separately. Complete SRAM, physical calibration,
rolling-provider integration and lifetime error control remain explicit limits.
