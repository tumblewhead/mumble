# History discrepancy: diagnosis and repair plan

**The diagnosis supports accumulated approximation error during anchor movement.
The estimator has not been repaired or changed.** The next implementation is
specified in [repair_plan.json](repair_plan.json), following the requested
analysis-and-plan stage.

The completed [attribution review](result_review.json) checks the saved two-hour
prefix. Its [raw records](attempt002/records.json), [execution receipt](attempt002/receipt.json)
and [frozen diagnostic plan](localization_plan.json) preserve the evidence.

| Check | Result | Implication |
|---|---:|---|
| Direct sum of old residual polynomials versus saved QR factor, nine points | Maximum 4.60e-9 NLL gap | Storage/translation roundoff does not account for the 252.96 NLL witness |
| Same comparison after centering | 8.73e-11 NLL gap oscillation | Constant accumulation differences are also immaterial here |
| Direct versus stored analytic gradient, whitened norm | 5.63e-11 | The stored factor preserves the reconstructed row slopes |
| Error in the analytic likelihood gradient, whitened norm | 204.3534 | Confirms the earlier finite-difference slope discrepancy |
| Retrospective factor built at the final estimate, same 545 points | 0.00142448 NLL oscillation | The current 37-feature form is adequate locally around this estimate |
| Retrospective oracle's computed-arithmetic interval | [0.00128220, 0.00156676] NLL | Below the unchanged 0.1 NLL finite-point budget |

The last two rows are an external diagnostic, **not a causal repair**. Rebuilding
earlier observations at a later estimate uses information unavailable when those
observations arrived. The rebuilt factor is never installed in the estimator.
The original 545 reference results were reused; they were not rerun.

The causal mechanism is visible in the source. Each commit translates the old
factor, transports a second-order boundary jet and adds new second-order residual
rows at the accepted estimate. Translation preserves the old polynomial exactly
in real arithmetic. It cannot supply the higher-order dependence omitted when
the earlier rows were formed. As the estimate moves, those omissions become
errors in the current historical likelihood and its slope. Boundary-jet transport
introduces an additional approximation. See
[commit](../live_anchor_integration_001/rolling_engine.c#L422),
[row construction](../live_anchor_integration_001/rolling_model.c#L261) and
[boundary transport](../live_anchor_integration_001/rolling_model.c#L132).

The large slope discrepancy is concentrated in early learning:

| Sample interval | Nominal minutes | Signed contribution along the total slope-error direction |
|---|---:|---:|
| 0–4,096 | 0–1.95 | 0.76% |
| 4,096–16,384 | 1.95–7.80 | 57.79% |
| 16,384–65,536 | 7.80–31.21 | 39.96% |
| 65,536–252,000 | 31.21–120 | 1.50% |

These are projections of signed gradient vectors, not percentages of physical
error or independent error magnitudes. The two middle intervals contribute
97.74% along the total discrepancy direction. The recorded sample chronology
and actual intervals, rather than nominal minute labels, drive the calculation.

Eight selected 16-sample blocks separate the two approximation mechanisms. At
sample 16,384 the boundary contribution has gradient norm 0.007587 and the
residual-approximation contribution 0.072922 in the same whitened coordinates.
At sample 65,536 these are 0.002302 and 0.000275. At the final block, where its
anchor equals the query point, residual truncation is effectively zero but the
boundary contribution remains 0.000971. Both mechanisms exist. These sparse
controls do not apportion every historical row or prove a unique global cause.

## Selected repair design

Change what the factor approximates before considering more memory or a larger
polynomial. The model is exactly linear in R0, the three RC resistances, the
three entering RC voltages, H and the product H·h0 when the nonlinear rates and
SOC/capacity coordinates are fixed. The present joint Taylor expansion discards
some of that useful structure.

Use a 37-feature residual representation that keeps those amplitude dependences
exact and approximates only the nonlinear basis functions. Keep the public
16-coordinate query, support and original prior unchanged; compute H·h0 inside
the features, with no division by H. Use reciprocal capacity internally for
the OCV features, so SOC = initial SOC − charge/capacity is affine in those
two internal coordinates.

| Residual component | Features |
|---|---:|
| Three RC modes: resistance and entering voltage, each times a quadratic basis in its log rate | 18 |
| Hysteresis: H and H·h0, each times the six-term quadratic basis in the two log rates | 12 |
| Ohmic current × R0 | 1 |
| OCV: six-term quadratic basis in initial SOC and reciprocal capacity, including the residual constant | 6 |
| **Total** | **37** |

This retains interactions such as resistance × squared log-rate displacement
that the current joint second-order residual drops. It also retains the H·h0
product exactly. This is an algebraically motivated candidate, not a demonstrated
fix for all 252.96 NLL of error. Nonlinear-rate and OCV truncation remain possible.

The feature family is closed under changes of its seven nonlinear origins:
15 quadratic features, 12 linear features and 10 features constant with respect
to those origin shifts. Use that ordering for an upper-triangular translation,
preserving all 703 square-root-factor entries. The factor storage remains
5,624 bytes. Derivatives must include the reciprocal-capacity and H·h0 chain
rules in the original public coordinates. The new factor must have a distinct
bank schema: identical byte counts do not make old coefficients compatible.

For boundary transport, evaluate the initial-state attenuation functions from
their exact algebraic forms:

```
a_i(t) = exp(-elapsed / tau_i)
ha(t)  = exp(-gamma_plus * positive_charge - gamma_minus * negative_charge)
```

The two unsigned charge integrals use the actual ordered decoded samples.
Their accumulation and floating-point error remain explicit. Replace redundant
stored attenuation jets with those integrals, rather than adding an uncounted
buffer. RC forced-response f and hysteresis forced-response hb still require
approximation; this change alone does not make the entire boundary exact.

## Implementation and acceptance sequence

1. Create a separate `structured_history_repair_001` candidate. Implement feature
   construction, original-coordinate derivatives and in-place origin translation.
   Qualify exact amplitude dependence, zero H/R cases, translation identities,
   support, evidence ownership and error rejection with fabricated inputs.
2. Implement analytic attenuation transport and qualify it independently across
   sign changes, variable intervals, zero current and moving query points. Measure
   the actual context, phase workspace and compiled call-chain stack. The complete
   planning ledger must remain within 10,240 bytes; the present 24-byte margin
   cannot absorb hidden scratch objects.
3. Run two bounded diagnostic arms using the saved accepted-anchor schedule:
   structured features with the old boundary, then the full selected candidate.
   Start from the original public state. Query the existing 545 frozen points and
   reuse their original-reference results. Compare every point with the unchanged
   0.1 NLL criterion, retain unavailable points and record both arms' results.
   This is a controlled representation test, not new autonomous inference.
4. If the full candidate passes, qualify and run one separately registered causal
   two-hour public-start probe. Its anchors must be generated by the candidate,
   without the saved schedule, final estimate, oracle or truth. Freeze its own
   postclosure node design before reference evaluation. Only this stage can show
   that the repaired representation works in the live learning loop.

If the selected candidate fails, preserve the failure and use the measured
residual to decide whether forced-response boundary transport or nonlinear-rate/
OCV truncation requires redesign. Do not tune a slope correction to the saved
oracle, raise the tolerance or shrink the tested region after inspecting results.
No wider trajectory campaign or M3 promotion follows from the retrospective
oracle's pass. Useful uncertainty and longer varied trajectories remain later gates.

## Execution record and limits

The final diagnostic qualification passed 54 checks. The canonical worker ran
once: 717,280 merge steps, 252,000 original-reference steps and 252,000 QR rows,
in 1.318669 CPU seconds. There were no optimizer calls, truth reads or candidate
updates. Source was published before execution. Input/source hashes and separate
capture copies pass the saved-result verification. Review was not independent.

Development and launcher failures remain preserved. The first compile stopped
on indentation warnings; the first canonical supervisor stopped on a path bug
before launching a worker. The separately registered
[continuation](continuation_plan.json) performed the first and only canonical
model work. A reporting-only list/dictionary loader error is also preserved;
its correction used saved outputs and made no model calls.

Computed-cost allowances do not certify coefficient construction, recurrence or
libm forward error. There is no claim of calibrated coverage, all-parameter
convergence, indefinite fidelity or measured Cortex-M23 readiness. The damaged
historical coefficients cannot be retroactively repaired from the compact bank
alone; any controlled rebuild remains external diagnostic machinery.
