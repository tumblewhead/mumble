# A same-size local RC representation helps, but has a limited useful region

The quadratic Taylor candidate preserves central RC values and sensitivities with
the same 4760-byte packed factor as R2_H2. It substantially improves the two active
one-hour fitted comparisons. Its agreement worsens away from the fixed public
centre, and the shared H2 uncertainty defect remains. Retain it as a research
candidate, not a production replacement. Cubic Hermite does not beat ordinary
cubic at equal storage in the multiscale example and has an unresolved rest fit.

See [P1 and the registered plan](../../specifications/rc_sensitivity_basis_001/README.md),
[complete compact results](summary.json), and the separate
[RC mechanism probe](response_probe.json). All Q/SOC/forecast differences below
are against direct local C fits, not plant truth or real-cell accuracy.

## What changed and what stayed fixed

Taylor2 streams each branch's free/forced value, first derivative and second
derivative at the original public log-tau centre. Those three states produce
three Chebyshev response coefficients. Hermite3 streams values/slopes at two
public anchors +/-1/sqrt(2), producing four coefficients. Ordinary R3 has four
value-only nodes as an equal-storage control. Every arm retains the same H2
representation except the explicitly labeled R5_H7 reference.

Two study-only native builds implement P1's derivative recurrences. The derivatives
are features of the same response, never additional measurements. One joint QR
factor retains all physical cross terms. Public prior, continuous shape box,
original-chart coordinates, observed inputs, likelihood and state chronology stay
fixed. Production C and campaign defaults remain unchanged.

The pilot uses 21008 records and the main study uses 126000 records for each of
rest, multiscale and embedded use. Each has all 51 frozen public queries plus the
preserved refused domain-exit witness. Two common public starts and the unchanged
60-round solver fit all 16 variables. Both direct and compressed transport carry
the full local covariance into sampled rest60 and 120mA10s/rest30 tasks. Endpoint
SOC centre and width comparisons are included in the primary runner this time.
These are fixed synthetic recipes and correlated diagnostic prefixes, not a new
population study or a continuous-time brownout guarantee.

All twelve direct/R2_H2/R5_H2/R5_H7 one-hour controls repeat the prior study's
selected origin charts exactly, including their convergence statuses. At one-hour
rest the direct fit and Hermite fit remain unresolved; fit-to-reference readouts
are unavailable there. In the pilot only Hermite rest is unresolved. These are
numerical stop outcomes, not physical exclusion or identification claims.

## One-hour fitted comparisons

Forecast is the larger sampled RMS voltage difference over the two future tasks,
using each field's compressed transport. Q differences are signed percentages of
direct fitted Q.

| Representation | Multiscale Q % | Embedded Q % | Multiscale forecast uV | Embedded forecast uV | Factor B |
|---|---:|---:|---:|---:|---:|
| R2_H2 | +3.281 | -0.278 | 62.68 | 78.30 | 4760 |
| Taylor2_H2 | +0.266 | -0.133 | 6.98 | 2.54 | 4760 |
| Hermite3_H2 | -3.641 | -0.082 | 84.99 | 20.35 | 6560 |
| Ordinary R3_H2 | -1.514 | -0.110 | 41.51 | 9.59 | 6560 |
| R5_H2 control | +0.322 | -0.137 | 7.66 | 2.66 | 11024 |
| R5_H7 reference | +0.0348 | +0.000313 | 2.96 | 0.55 | 50624 |

Taylor2 reduces the multiscale Q discrepancy about 12.3-fold and sampled forecast
RMS differences about 9.0-fold/30.8-fold across the two active cases, at unchanged
factor size. This is roughly the R5_H2 point-agreement level in these cases, with
less than half its factor storage. It does not establish general equivalence:
approximation cancellation can affect fitted outcomes, and these two fitted
reference RC log offsets lie close to the public centre (within about 0.133).
The fits and centres were not selected from hidden truth or re-centred afterwards.

There is a preserved regression: at the ten-minute rest pilot, Taylor2's larger
forecast RMS difference is about 462 uV versus 48 uV for R2_H2. Capacity stays at
the public prior under rest and does not make that a successful capacity test.
Hermite rest fails to meet the registered numerical stopping rule at both prefixes.

## Why the locality matters

P1 proves central value/first/second derivative matching for Taylor2 and value/
first-derivative matching at the two Hermite anchors. It gives conditional remainder
bounds requiring third/fourth derivative envelopes. No trajectory-family envelope
is established by these finite controls; an exact point identity is not a uniform
support guarantee.

The separate public mechanism probe uses 600 irregular signed-current/rest samples,
explicit public nonzero boundary RC voltages and seven common log-tau offsets.
It isolates RC response and log-tau derivatives from the unchanged H terms, without
fitting or plant truth. Taylor central values/slopes and Hermite anchor values/slopes
match direct C within arithmetic tolerances. At the centre, R2's largest slope
error is about 0.305 mV per unit log-tau; Taylor removes it to rounding. Hermite's
central slope error is about 0.0217 mV and its value error about 0.0566 mV, versus
0.0109/0.0284 mV for ordinary cubic.

At offset +0.9, Taylor's maximum branch voltage defect grows to about 0.334 mV
versus 0.0214 mV for R2; its largest slope defect is about 1.063 mV per log-tau
versus 0.662 mV for R2. These are individual sampled maxima, not certified bounds.
They rule out calling the local Taylor improvement a whole-box replacement.
Across the 102 active one-hour public probes, Taylor improves 62 relative gradient
metrics and worsens 40; Hermite and ordinary cubic each improve 48 and worsen 54.
The shared H2 error also contributes to those full-gradient metrics.

## Joint uncertainty still prevents promotion

In one-hour embedded use, Taylor's endpoint SOC width is about 0.525 of the direct
width evaluated at the same anchor, and 0.583 of the direct fitted reference width.
H7 is about 0.9994 under either comparison. The close Taylor/R5_H2 point agreement
therefore does not repair the shared H2 uncertainty distortion. These are full
joint local GN widths including the prior, not validated physical coverage.
The complete summary retains Q widths, joint precision spectra, fit shifts,
transport support, SOC widths and future-voltage width ratios rather than selecting
only the favorable point metrics.

## Storage, review and next decision

Taylor2's factor/response/domain-scalar subtotal is 4760+312+96=5168 B, unchanged
from R2. Hermite3 and ordinary R3 both use 6560+360+96=7016 B. The R5_H2 control is
11024+456+96=11576 B and already exceeds the 10240 B goal. These are lower numeric
subtotals; calibration, tables, prior, optimizer, metadata, rollback/scratch, stacks
and platform overhead are excluded. One versus two/four RC anchors is an operation
count distinction, not a measured CPU or WCET result. No deployment qualification.

P1 received individual independent review. Implementation review found a kernel
binding hole: ordinary cubic could load the Hermite binary. The original class/
tests and finding are preserved; the fix rejects all six mismatched pairings and
was freshly reviewed. Seven targeted tests cover reproduction, native sensitivity
recurrences, feature/transport derivatives, unchanged H rows, joint QR/chunking,
atomic rejection and memory. Runner, readouts and interpretation receive separate
integration review, with exact source and result bindings in the final receipt.

Next retain Taylor2 as a compact local research baseline and derive how to bound
its value/sensitivity remainder over an explicitly admitted region. Any later
chart change or region transition must preserve old evidence/transport or refuse;
no silent re-centering or forgetting is justified. Keep H2 uncertainty repair as
an independent blocker, using direct/H7 joint comparisons. Do not promote Taylor,
Hermite or the ordinary cubic from these two active fitted examples, and do not
launch a long campaign before the locality and uncertainty questions are resolved.
