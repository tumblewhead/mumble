# Tangent development plan

Tangent is the leading development candidate; field64 remains the control.
The objective is dependable proposed-load voltage prediction with bounded cost,
while preserving useful SOC/Q estimates. This is a **planning-only** specification:
no estimator changes, benchmarks, forecast experiments or long campaigns have
been executed under it. The executable details are registered in [plan.json](plan.json)
and the selected source/checkpoint identities in [inputs.json](inputs.json).

The [72-hour review](../../provenance/field_tangent_72h_20261101/README.md) found
lower tangent SOC RMSE in all 16 cases, lower Q RMSE in 13, and much smaller
refresh-related Q/H/gamma movement. Final RC estimates remain nearly identical.
Weak-cycle Q/H ambiguity and embedded-load overconfidence remain shared limits.
Earlier host profiles put integrated tangent execution about 1.5 times slower than
field64; they do not measure target CPU time or complete peak SRAM.

The working application target for Q is now approximately 1% relative error,
as accepted by the user. Preserve the existing 0.5% reports for historical
comparison, keep SOC's 0.5 percentage-point target, and do not force every RC
parameter to a common percentage target. An unexcited Q estimate remains
explicitly unresolved. Voltage prediction and its uncertainty determine the
value of improving a nuisance parameter.

| Stage | Work | Decision/output |
|---|---|---|
| T0 | Bind original replay and validate complete state exports | Trustworthy common starting points; no lost or duplicated evidence |
| T1 | Profile matched intervals and memory lifetimes | Complete CPU/SRAM ledger, including full-refresh bursts |
| T2 | Forecast proposed loads before observing responses | Voltage minimum/recovery errors, uncertainty and decision tradeoffs |
| T3 | Make one profile-selected improvement at a time | Measured resource saving with retained prediction quality |
| T4 | Freeze and qualify the selected candidate | Promotion decision and explicit deployment/aging gaps |

T1 and T2 can proceed independently after T0. Optimization selection follows
both: a cheaper estimate that changes a useful load decision can be a poor trade.

## First study

Use four already-reviewed development witnesses from the owner's 72-hour run:

- case 0000: A, embedded, 2 mV, seed 1103; late narrow uncertainty.
- case 0011: B, embedded, 4 mV, seed 314159; residual fast-RC error.
- case 0006: A, repetitive cycle, 4 mV, seed 1103; large feedback excursions.
- case 0015: B, repetitive cycle, 4 mV, seed 314159; weak Q/H identification.

For each, select the first saved checkpoints at or after 3, 24 and 69 hours. Their
actual times are approximately 3.0037, 24.0299 and 69.0859 hours. All 12 checkpoint
hashes have been checked. These selected witnesses are diagnostic cases, not
an independent validation population.

For profiling, replay 16,384 new samples per prefix: 196,608 unique source samples
across 12 prefixes. Run five timing repetitions from freshly restored complete
states, alternating arm order. Separate response recurrence, field QR, local
update, full fit, state transport, covariance/readout and adapter cost. Measure
uninstrumented total time separately from instrumented component timings.
Report mean, quantiles, maxima and refresh bursts; repeated timing does not mean
repeated evidence is accumulated into an already-updated history.

For prediction, capture the paired banks immediately before the next refresh,
after that same refresh attempt, and halfway through the following interval.
This yields 36 anchor boundaries. Keep rejected refreshes visible rather than
selecting only successful fits. Each anchor gets 20 declared current programs:
16 single pulses spanning 0.015/0.03/0.06/0.12 A and 0.1/1/10/60 seconds, plus rest,
two burst trains and a mixed task, with recovery intervals. These are 720 paired
tasks, not 720 independent coverage trials. Commands use public absolute currents,
not the hidden cell capacity. Mark poorly excited or extrapolated tasks explicitly.

The first forks hold the measured anchor temperature constant. Both arms receive
the same declared task and temperature assumption. The current stream is 50 Hz;
nominal 35 Hz and rate controls follow in qualification. Preserve actual intervals
and label any requested-duration rounding at other rates.

## Forecast and uncertainty contract

The predictor receives a source/boundary identity, a read-only history/estimate
handle, a proposed load and an exogenous temperature assumption. It receives no
truth or future observed voltage. Freeze predictions before scoring against an
independent scalar plant fork. Preserve the inherited SOC, all three RC voltages
and hysteresis: do not reset polarization to zero or transplant true states.

Forecast the complete voltage trajectory, its minimum and occurrence time, and
recovery. Include the instantaneous 0+ load edge, command boundaries and possible
intra-segment extrema; checking only sample endpoints can miss a voltage minimum.
Record numerical refinement error separately from model/prediction error.

Compare the full published joint endpoint messages of both arms first. Add a
separately labeled tangent geometry ablation using its original-coordinate factor
and nonlinear state transport. This tests whether readout loses useful geometry.
Retain state/parameter cross terms. Local linear covariance and deterministic
joint-direction probes are diagnostics, not calibrated probability guarantees;
unsupported directions remain reported rather than clipped or silently removed.
Pointwise voltage intervals cannot be treated as a simultaneous path-minimum bound.

Use cutoff sweeps to examine unsafe admissions, unnecessary rejections and
unresolved tasks. Operational acceptance requires a hardware-defined battery-side
limit, allowable transient duration, power-path model and risk budget. Those are
open requirements, not invented constants in this plan. Start with current loads;
constant-power/regulated tasks require voltage-dependent current and declared
regulator efficiency, including explicit low-voltage failure behavior.

If the saved anchors lack low-SOC states, add a separate declared discharge
continuation driven by public controls and measured-voltage stopping. Assimilate
its observations normally before the forecast fork. Never manufacture an EOD
initial estimate from truth. Initial prediction tests do not qualify brownout
risk or real-cell OCV behavior.

## Optimization order and the memory constraint

Select the first optimization from the measured cost breakdown. Candidate changes
are fused native operations, reused buffers, fewer language-boundary crossings,
and removal of duplicate recurrence at field-batch flushing. A streaming field
update must avoid replacing the raw buffer with an even larger lifted-row buffer.
Do not assume a smaller batch is computationally cheaper; measure it.

Separate mandatory mean/domain validation from application-requested full
covariance readout where the profile supports it. Every sample still contributes
to history. Domain failures and the warm start for the next refresh must remain
correct even when no expensive readout is requested. Cache only computations
whose prior/config/source, anchor, factor or transport generation is unchanged;
test invalidation across refreshes, actual time intervals and temperature changes.

The current shared 82-dimensional field factor has 3,403 triangular entries:
**27,224 bytes in float64, or 13,612 bytes even in float32.** Both exceed the
approximately 10 KiB target before states, prior, tables or workspace. These are
lower bounds for this numeric layout, not a proof that the information cannot
be compressed. A deployable design needs shared-history representation work;
optimizing only the 1,376-byte tangent context cannot solve the memory problem.
Keep full cross terms and test proposed compaction against voltage predictions
and uncertainty, not an arbitrary likelihood threshold.

Build a lifetime-based ledger for persistent storage and simultaneous peak
workspace. Distinguish the desktop raw batch/dense arrays/Python heap from a
proposed target layout. At 16 MHz and 35 Hz there are approximately 457,143 cycles per
sample on average, or 7.314 million per 16 records. These averages are not a latency
certificate: account for buffering, full-refresh scheduling and worst-case work.
Host timing cannot substitute for target compiler or Verilog measurements.

## Repairs and qualification gates

If both arms have the same consequential voltage bias, investigate the shared
physical partition, transport, sensor likelihood or joint approximation before
changing tangent. If only the field arm's decision changes with refresh phase,
retain the measured tangent stability benefit. If individual RC parameters are
inaccurate but voltage forecasts remain acceptable, avoid spending resources
forcing every nuisance parameter to its truth.

Preserve arithmetic-order parity where possible. For reordered arithmetic,
register numerical tolerances from dtype/conditioning before comparing results,
report differences and their application impact, and keep the existing nonfatal
investigation approach to small discrepancies. Do not hide deficiencies with
parameter smoothing, arbitrary covariance inflation or exponential forgetting.

After one candidate is frozen, use fresh noise and load seeds, both cells,
weak/wide traversals, near-EOD episodes and 35/50 Hz controls. Validate checkpoint
continuation and short forecasts before another long campaign. Count independent
trajectories appropriately for calibration; many correlated outputs do not prove
rare-event safety. Merge/promotion decisions should show prediction benefit,
failures and complete resources together, without a hidden weighted score.

Aging, real-cell/model mismatch and ten-year operation remain separate later
qualification. The immediate deliverable is the matched resource-and-forecast
scorecard from T0–T2, followed by one justified optimization or repair.
