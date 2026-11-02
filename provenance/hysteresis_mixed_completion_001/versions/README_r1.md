# Mixed-term completion is insufficient; RC fidelity matters to the joint fit

The targeted H4 repair works at its intended centre point but does not reliably
improve fitted estimates. No candidate is promoted. A separately registered RC
control shows that low RC fidelity accounts for a substantial part of the fitted
capacity and proposed-load discrepancy in these finite examples. Raising RC
degree is an attribution control, not a memory-feasible solution.

See the [primary protocol](../../specifications/hysteresis_mixed_completion_001/README.md),
[outcome-informed follow-up](../../specifications/hysteresis_mixed_completion_001/RC_FOLLOWUP.md),
and [complete compact summary](summary.json). All differences below are relative
to the same-prior direct C fit, not hidden cell truth or real-battery accuracy.

## What was run

The primary experiment uses the same rest, multiscale and embedded recipes at
21008, 35520 and 126000 records (about 10, 17 and 60 minutes at 35 Hz). It retains
51 public queries plus the known domain-exit witness per prefix. Compare existing
R2_H2, c22-only, full quadratic H tensor, R2_H3 and R5_H7 fields. All preserve a
single joint square-root factor and continuous physical parameter support.

At each prefix, fit all 16 variables jointly using the public prior once, two
common public starts and unchanged GN stopping rules. Direct fits enforce the
same computational box as the compressed fields. Full joint local covariance is
propagated through both direct and compressed state transport into sampled future
rest60 and +120mA10s/rest30 tasks. No observations from those future tasks are fitted.

Of 54 primary arm/prefix fits, 51 satisfy the registered numerical stop rule.
The direct reference remains unresolved at one-hour rest and 35520-record embedded;
H7 is also unresolved at the latter prefix. Those comparisons remain unavailable.
No tolerance/support change was made to obtain convergence. Numerical stopping
is not a global-optimum proof, physical identifiability or coverage guarantee.
In particular, capacity under rest remains prior-supported rather than identified.

## The central identity does not select the best fitted representation

Independent targeted checks verify the H4 projection identity, analytic feature
and transport derivatives, joint cross terms, domain refusal, ownership, failure
atomicity and storage counts. The c22 addition and full tensor exactly restore
the ideal central value. They do not remove off-centre interpolation or all true
physical derivative errors.

Across 306 active-load public probes, relative gradient defects improve/worsen/tie
against H2 as follows (ties use absolute metric difference <=1e-12 solely for
reporting, not a physical acceptance threshold):

| H representation, RC degree 2 | Improved | Worsened | Tied |
|---|---:|---:|---:|
| c22-only | 161 | 94 | 51 |
| full quadratic tensor | 206 | 49 | 51 |
| total degree 3 | 191 | 115 | 0 |

The full tensor improves more probes but its worst relative gradient defect is
0.868, versus 0.576 for H2. There is no uniform improvement. The 51 ties for the
mixed-completion arms occur in the early one-direction embedded prefix, consistent
with the symbolic interaction being absent there.

## Matched one-hour joint-fit and application comparisons

Q columns are signed relative differences (%) versus direct fitted Q. Forecast
columns are the larger RMS voltage difference across the two sampled future tasks,
using each field's compressed state/covariance transport (microvolts). The R5_H2
variants are from the follow-up; original arms repeated with matching status and
Q-comparison changes below 9.4e-8 percentage points after chunk regrouping.

| Representation | Multiscale Q % | Embedded Q % | Multiscale forecast uV | Embedded forecast uV | Packed factor B |
|---|---:|---:|---:|---:|---:|
| R2_H2 | +3.281 | -0.278 | 62.68 | 78.30 | 4760 |
| R2_H2 + c22 | +4.681 | -0.278 | 66.34 | 78.33 | 5328 |
| R2 full H tensor | +4.253 | -0.277 | 64.56 | 77.98 | 6560 |
| R2_H3 | +3.771 | -0.266 | 73.63 | 81.21 | 7224 |
| R5_H2 | +0.322 | -0.137 | 7.66 | 2.66 | 11024 |
| R5_H2 + c22 | +1.147 | -0.137 | 8.50 | 2.78 | 11880 |
| R5 full H tensor | +0.552 | -0.136 | 13.96 | 2.53 | 13688 |
| R5_H7 reference field | +0.0348 | +0.000313 | 2.96 | 0.55 | 50624 |

Changing only RC fidelity from R2_H2 to R5_H2 reduces the multiscale Q discrepancy
by about 10.2 times. The forecast RMS differences decrease by about 8.2 times
(multiscale) and 29.4 times (embedded). These outcomes support prioritizing a
more efficient RC response/sensitivity representation. They do not establish the
same factors across cells, noise, stimulus families or longer durations.

The c22/full-tensor additions still do not consistently improve Q when RC is held
at degree 5. The remaining hysteresis interpolation/derivative issue therefore
cannot be dismissed as merely hidden by an RC error. Likewise improved point
agreement is not sufficient to accept uncertainty: R5_H2 one-hour relative joint
GN-precision eigenvalues span about 0.0039 to 219 for multiscale. In embedded use,
its Q width at the same anchor is about 0.66 of the direct width and its fitted Q
is about -2.73 reference local SD away. R5_H7's corresponding precision spectra
are much closer to one, but that is still local model-based curvature, not
validated physical coverage. Keep the full correlated diagnostics visible.

## Storage and implementation scope

The four R2 factors/lower numeric subtotals are 4760/5168, 5328/5736, 6560/6968 and
7224/7744 B. The RC5 follow-up subtotals are 11576, 12432 and 14240 B. Even their
factors exceed the 10240 B device goal. H7's factor alone is 50624 B; its response
state adds 1336 B and host projection tables add 18720 B. None of these totals
includes all prior, calibration, metadata, optimizer, scratch, stack or platform
storage. No M23 timing or complete SRAM qualification follows.

Direct fitting retains a finite prefix in desktop memory: the one-hour raw
observation array occupies 5,040,000 B. It is reference workspace, never mixed with
its field as extra independent evidence. Native C, the campaign default and
production estimator are unchanged. Raw runs/factor snapshots stay local and
ignored; only source and compact receipts are tracked.

## Decision and next step

Do not promote c22-only, the full quadratic tensor or RC5 controls. Preserve the
H4 identity as a correct local diagnostic and the failed joint-fit intervention
as evidence. Prioritize a compact RC response basis that controls values and
sensitivities together, while retaining hysteresis and full-joint uncertainty
checks against H7/direct references. A candidate such as derivative-constrained
interpolation needs a new explicit error/resource contract and matched tests;
no untested representation is selected by this report.

Candidate classes and RC controls receive separate independent review; the
runner, fit/forecast semantics and this interpretation receive an integration
review. Exact bindings, test commands and review dispositions are in the final
receipt. This is an exploratory result, not independent statistical confirmation,
a repaired production estimator or ten-year history qualification.
