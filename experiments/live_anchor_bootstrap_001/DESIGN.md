# A live bootstrap and moving anchor with bounded history

## Decision and scope

Use **one quartic history bank and a rolling block of at most sixteen raw
samples**. Start from the public prior, with an empty bank and the original
initial-state law. Use each current block to refine the complete joint parameter
point; then append its evidence once and release its raw samples. Capacity is
allowed to become informative much later than startup.

This design follows the completed [fixed-origin comparison](../compact_nonlinear_history_001/decision.json).
That comparison found a useful local quartic representation, a large mismatch
when starting and remaining at the public origin, and a separate search failure
at the entering hysteresis bound. It did not establish a live bootstrap or
calibrated SOC/capacity intervals.

This change implements and qualifies three prerequisites: the ADC12 transport,
the support-aware joint proposal, and translation of an already represented
polynomial. It also supplies a concrete C layout for all simultaneous phases.
**The rolling estimator, boundary-jet recentering and current-block derivative
engine are the next integration; they are not implemented by these primitives.**
There is no new canonical battery-data run in this change.

## The input contract

The user permits a saved history and file playback for host studies, provided
the estimator does not depend on them. A file producer and a physical ADC must
deliver the same input contract. Neither a file handle nor an archive pointer
belongs to the estimator.

V, I and T each arrive as an integer code in `0..4095`, stored in three
`uint16_t` containers. An additional `uint64_t interval_ticks` preserves the
actual duration. A native sample is sixteen bytes on the qualified host ABI.
The optional five-byte codec packs only the 36 channel bits; it does not include
time, sequence or source identity. No timer width has been narrowed to obtain a
smaller packet.

The caller supplies voltage, current and temperature scale/offset pairs and a
positive seconds-per-tick value. All seven doubles are counted as 56 bytes of
RAM in the design. Twelve bits alone supplies none of these physical values.
Raw rail codes remain available. Their meaning as valid endpoints, saturation
or censored observations must be specified before a physical likelihood is
claimed. Converting a very large integer tick count to binary64 has the stated
C rounding; the original integer remains in the raw sample.

Calibration and the timing scale are immutable within one evidence generation.
The 32-byte source/config identity must bind the stream, calibration, model and
likelihood contract. Changing calibration after discarding raw codes would
change the meaning of the old factor and accumulated charge; the engine must
reject that silent change or use a separately designed migration. No migration
is implemented here.

The existing physical model is fixed at 25 degrees C. The interface preserves
and converts T, but the model has no temperature-dependent law. An initial
study using that model must explicitly retain its fixed-temperature scope.
There is no implicit temperature compensation.

The ADC12 component is externally serialized, not an interrupt-safe hardware
driver. Its separately qualified FIFO holds sixteen samples and occupies 304
bytes. The integrated design below uses a different organization of sixteen
retained plus eight incoming samples; it does **not** also own that FIFO.

## Evidence ownership and startup

At every observable, available state, ownership is disjoint:

| Owner | Records | Role |
|---|---|---|
| Committed factor | `[0,n)` | Joint quartic approximation of older likelihood |
| Retained raw block | `[n,n+m)`, `m <= 16` | Nonlinear current-block evaluation |
| Ingress queue | Later contiguous records | Delivered input awaiting admission |
| Common prior | Original supported sixteen-dimensional mixture | Included once per objective, never as another sample |

The objective is the old polynomial likelihood, plus the current-block
likelihood conditional on the carried boundary approximation, plus the original
common prior exactly once. A posterior obtained from earlier observations is
not added alongside their factor. The prior remains a density in the original
parameter chart.

For the first block, the committed factor is zero and the initial physical
state is represented symbolically. Initialization is `PUBLIC_MEAN`, not a saved
successful anchor, fitted archive point or truth. The first block provides a
causal bootstrap opportunity; its size is a memory and work choice. It does not
assert that sixteen samples identify capacity, hysteresis or every nuisance
parameter. A zero-current prefix must retain an uninformative capacity
likelihood even if the common prior prefers some capacity values.

All sixteen quantities remain joint. The entering SOC and RC/hysteresis states
refer to the original stream origin even after the approximation origin moves.
Recentring the parameter approximation must not replace entering SOC with
current SOC or reset the original prior on each block.

## What moving the anchor means

Order the normalized features as twenty quadratic monomials, sixteen linear
coordinates, then one constant. Keep the original public coordinate scales.
If old and new displacements satisfy `d_old = d_new + s`, then

\[
d_{old,i}d_{old,j}=d_{new,i}d_{new,j}
 +s_jd_{new,i}+s_id_{new,j}+s_is_j.
\]

The feature transform `T` is upper triangular in this order. Thus an upper
factor can be translated in place as `R_new = R_old T`. For each row, update its
constant using the old linear and quadratic coefficients, then update its
linear coefficients. Quadratic coefficients remain unchanged. No second factor
or full transform matrix is necessary.

`history_translation.c` performs a complete read-only preflight of prospective
coefficients before mutation. Prevalidation failure leaves the factor unchanged.
An unexpected mutation-pass numerical failure requires the owner to latch
unavailable; a rollback factor is not hidden in the memory budget. The old
experiment's **linear-first** QR cannot be reinterpreted as this new ordering.
The new bank must create its rows and queries consistently in quadratic-first
order.

Translation preserves the already represented polynomial, including its joint
dependence. It does not recover discarded higher derivatives or renew the
historical validity of the approximation. Its algebraic qualification checks
cost, all sixteen gradient entries and the full symmetric Hessian. It does not
test fidelity to the battery likelihood.

The future integration will also recenter the carried second-order RC and
hysteresis boundary functions. For a scalar RC function, for example,

\[
 f_{new}=f+f's+\tfrac12 f''s^2,\qquad
 f'_{new}=f'+f''s,\qquad f''_{new}=f''.
\]

The two-rate hysteresis functions use the corresponding two-dimensional
quadratic translation. Subsequent recurrence uses the candidate parameters and
those transported boundary functions. Current-block evaluation is nonlinear
conditional on this boundary approximation; it is not an exact reconstruction
of the earlier physical path. Original cumulative charge and the exact
conditional relation `SOC = z0 - charge/Q` remain carried explicitly.

The integration must check transported state admissibility without clipping,
retain an explicit historical-fidelity-unverified status, and count all
preflight/query/merge model work. No calibrated interval may be inferred from
the represented curvature while historical error remains unbounded.

## A proposal that respects support

The old search could repeatedly halve an outward direction at an active
hysteresis bound while another feasible direction existed. The new primitive
constructs a direction inside support instead.

Its input is the full joint gradient and the full symmetric local
Gauss-Newton-plus-prior optimization metric. The proposal uses reciprocal
capacity `q = exp(-x5)` locally, with

\[
t_5=\frac{q-q_0}{q_0 S_5},\qquad
t_i=\frac{x_i-x_{0,i}}{S_i}\quad(i\ne5).
\]

At the anchor, the Jacobian back to original coordinates has diagonal `S`,
with a negative sign in coordinate 5. This is an optimization parameterization;
the objective and prior are still evaluated in original coordinates. There is
no density-Jacobian addition to the prior.

For the scaled full metric `A`, form `m_i = sum_j |A_ij|`. The diagonal matrix
with entries `m` majorizes `A`: its difference from `A` is symmetric diagonally
dominant with nonnegative diagonal and is positive semidefinite. This gives a
conservative, separable quadratic proposal without inventing a damping ridge.
The original metric must pass the declared positive-definiteness checks.
The diagonal matrix is an optimization aid, not a posterior precision or an
uncertainty estimate.

Fourteen coordinates have direct bounded quadratic minimizers. The remaining
capacity/SOC pair is solved together. With charge extrema including zero,

\[
z_0-C_{max}q\ge0,\qquad 1-z_0+C_{min}q\ge0.
\]

These are affine constraints in `(q,z0)`. Alongside the support and local step
box they define a polygon with at most six edges. Enumerating its feasible edge
segments and the unconstrained minimizer gives a finite two-dimensional
weighted quadratic solution, including cases that require simultaneous
capacity and SOC movement. The one-public-SD step box is a declared work and
local-proposal policy, not a confidence boundary.

The primitive rechecks the represented candidate in the original support and
checks resolved descent using the original gradient. A rounding rejection or
unresolved direction is explicit; the code does not clip a rejected candidate
back into support. The integration must still evaluate the complete represented
old-factor/current-block/prior objective and use its declared finite
cost-decrease and Armijo checks. A direction-generator result alone is not an
accepted estimator update or proof of stationarity.

## Commit and failure semantics

Before a commit, validate configuration/source/sequence, every retained input,
candidate support and the planned boundary transport. Keep all raw block slots
occupied while conversion is in progress. No large raw prefix may be aliased
with the factor: unread records and the growing factor would overlap.

During the serialized commit phase, translate the old factor, install the
transported boundary state and new origin, generate and append each retained
record once, then publish the advanced committed cursor and retire the block.
No query is permitted to observe a partly merged block. If an internal fault
occurs after mutation starts, latch unavailable; neither a partial factor nor
partially advanced state is an admissible continuing estimate. A preflight can
reevaluate records, but only the committed append contributes evidence.

Queue-full rejection must not silently advance chronology. If a real input is
lost and cannot be redelivered, expose overrun/recovery required. Eight incoming
slots are approximately 0.229 seconds of arrivals at nominal 35 Hz, not a
measured execution deadline. Preserve the actual intervals and order throughout.

## Complete phase-liveness budget

`live_layout.h` makes the proposed object sizes concrete. The qualification
compiles this schema; it does not execute a complete rolling engine.

| Simultaneously reserved item | Bytes |
|---|---:|
| One bank, including 5,624-byte factor, boundary jet, origin, estimate, identity and counters | 6,368 |
| Shared query/proposal/merge workspace | 1,600 |
| Shared result | 120 |
| Sixteen retained and eight incoming native samples | 384 |
| Ingress cursor and four 32-bit metadata fields | 24 |
| Immutable calibration, conservatively counted in RAM | 56 |
| Checkpoint codec reservation | 128 |
| Project stack reservation | 768 |
| Runtime, IRQ and caller reservation | 768 |
| **Planned complete total** | **10,216** |
| **Remaining to 10,240** | **24** |

The source identity and committed cursor are already in the bank. They are not
duplicated in the input store. The former persistent 24-byte decoded sample is
removed; decoding uses the phase workspace. Caller delivery objects, driver
state and call chains must fit their explicit reservations, not appear outside
this total.

The 1,600-byte phase workspace has three mutually exclusive views:

| Phase | Live contents | Bytes |
|---|---|---:|
| Current-block query | Packed full metric 1,088 + gradient 128 + point 128 + sparse first-order state 224 + decoded V/I/T/time 32 | 1,600 |
| Proposal | Packed full metric 1,088 + four sixteen-double vectors | 1,600 |
| Merge | Prospective second-order jet 376 + feature row 296 + decoded input 32 + model sample 24 | 728 |

The query state stores RC `f,a,df,da`, hysteresis `hb,ha,dhb,dha`, charge,
inverse capacity, five rates, and three prediction scalars. Generate Jacobian
entries on demand. A second 376-byte jet or the existing 512-byte model row
cannot coexist in this query phase.

These are host ABI sizes plus explicit planning reservations. Integrated stack,
interrupt latency, software floating-point timing and actual Cortex-M23 SRAM
are unmeasured. The 24-byte margin is too small to absorb uncounted state. Any
temperature law, calibration-uncertainty state, recovery implementation or
additional error envelope must receive a new complete account.

## Calibration and uncertainty obligations

Twelve-bit input does not justify twelve-bit accumulators or a noise variance.
The retained polynomial and joint metric currently use binary64. Quantization
and saturation require an explicit observation law. Even the familiar uniform
quantization variance requires a statistical assumption beyond code width.

Current gain has a direct capacity identifiability consequence in the present
model. If `I_actual = k I_code`, then changing `k` to `c k`, `Q` to `c Q`,
`R0,Ri` to `R0/c,Ri/c`, and both hysteresis rates to their values divided by `c`
leaves the model voltage trajectory unchanged within support. Thus voltage data
alone cannot distinguish capacity from an unknown current gain. Timer scale
has related ambiguities. A future capacity interval must be conditional on
declared calibration or carry its uncertainty jointly. This follows from the
charge, RC and hysteresis recurrences in [scm_model.c](../../src/scm_model.c).

## Next finite integration

Implement one new rolling engine using this layout and the qualified
primitives. Before any new canonical stream, qualify current-block predictions
and joint derivatives, boundary transport, support-aware objective acceptance,
prior-once and record-once ownership, queue/fault transitions, and actual phase
and project call-chain liveness. Include a fabricated zero-current prefix with
later excitation; do not manufacture early capacity information.

Then freeze one public-start chronological stream and a finite predetermined
proposal schedule. File playback is allowed to supply that interface. Saved
archive calculations may assess candidate results after closure; they must not
initialize, steer or repair the candidate. That study decides whether causal
anchor transitions improve progress without unacceptable historical error.
It does not automatically establish calibrated intervals or M3 readiness.
