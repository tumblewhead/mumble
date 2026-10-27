# Causal rolling anchor integration

This experiment integrates the selected live-anchor design and runs one public-start
four-hour stream. It produces traces of all sixteen original coordinates and the
five evolving states for the upcoming presentation update. A trace is evidence of the
observed trajectory, not a promise that every parameter is identified or converged.

## Ownership and input

The estimator owns one compact historical likelihood bank, sixteen retained raw
records, and an eight-record incoming FIFO. Its public input is a source identity,
an ordered sequence number, and a native sample containing three twelve-bit
channel codes and a sixty-four-bit actual-duration tick count. The host may play
an archive and save arbitrarily detailed traces. No archive handle, saved fitted
anchor, truth value, retrospective observation access, or heap allocator enters
the estimator interface.

Calibration is explicit and immutable for a source generation. `host_run_plan.json`
specifies a synthetic-study calibration selected from the declared physical model
support before inspecting archive outcomes. Those ranges and timing units are not
hardware specifications. The source archive has no temperature; the producer
supplies a declared constant 25 degrees C. The estimator preserves T but this
model does not compensate for temperature. The original decoded-point Gaussian
voltage likelihood with 1 mV standard deviation is retained as an approximation
after quantization. We do not infer a physical ADC noise law or add an invented
quantization-variance term.

Offer validates before mutation. A full queue, wrong source, wrong sequence,
invalid code, or invalid decoded sample leaves the context unchanged and ownership
with the caller. Admit transfers queue records into the current raw block without
counting them as likelihood evidence. Physical overrun requires an explicit
unavailable latch; silently skipping samples is outside the interface contract.
One external serialized caller is required. This implementation is not an ISR
driver or a checkpoint persistence implementation.

## Representation and query

All sixteen quantities retain the original entering-state chart. The five entering
states are initial SOC, three initial polarization voltages, and initial hysteresis.
They remain different from the corresponding states at the current sample.

Older observations are represented by a triangular square-root factor over twenty
selected quadratic features, sixteen linear features, and a constant. Its squared
norm is a quartic approximate likelihood. Constant residual energy is retained.
Moving the feature origin uses the qualified in-place polynomial translation;
it preserves that stored polynomial, not the missing exact historical likelihood.

The carried boundary contains second-order basis jets in the original logarithmic
rate coordinates. A query evaluates those boundary polynomials at its point and
then applies the nonlinear recurrence over the retained raw block. A 224-byte
query state holds the basis values and first derivatives. Jacobian entries are
generated individually; no full sixteen-vector model row is additionally owned.
The complete sixteen-dimensional gradient and Gauss-Newton metric include older
evidence and the current block. The common supported mixture prior is evaluated
once in the original chart. It is never merged as an observation or added again
as a posterior derived from the same samples.

Historical boundary transport is approximate. Products between transported basis
values and other parameters retain their nonlinear dependence during a block
query; a subsequently stored residual row contains only the selected second-order
terms. Neither translation nor a successful descent test certifies this historical
approximation away from its useful neighborhood.

## Supported finite refinement

Each canonical sixteen-record block gets one supported proposal and at most eight
fractions, from one through one hundred twenty-eighth. The proposal uses the
qualified full-joint support operation and all accumulated charge extrema. A
cost-only query leaves the packed metric and gradient bytewise unchanged. After
the metric has served its purpose, its first sixteen doubles retain the exact
full proposal endpoint across all trial queries. Acceptance installs the point
actually evaluated, including the full-fraction represented endpoint.

Acceptance compares the whole represented likelihood plus the original prior.
The inherited arithmetic allowances use 16,384 history/block cost operations,
256 prior operations, sixteen cost-combination operations and **thirty-two final
Armijo-combination operations**, with a quarter-Armijo factor. These bounds guard
specific computed arithmetic operands. They do not cover physical-model error,
historical approximation, libm error, or interval coverage. They are not voltage
noise cutoffs or arbitrary covariance inflation.

Finite exhaustion, no resolved direction, metric failure and rounding-limited
proposal results remain distinct from convergence. A valid block can be committed
after a finite unresolved refinement. If the current point becomes physically
inadmissible as new data arrive, this prototype fails explicitly; it has no
separate feasible-restoration solver. It must not interpret that local failure as
proof that the entire supported parameter set is infeasible.

## Commit transaction

Commit first evaluates the complete block at the chosen estimate and checks its
physical endpoint. It then prepares the transported boundary in disjoint scratch,
marks the context as committing, translates the old factor, and appends each raw
record once. Only after all appends succeed does it advance the committed cursor
and retire the raw block. A failure after mutation starts latches the context
unavailable and retains raw ownership; no query can use a partially changed bank.

Counters record attempts before recurrence calls. Counter reservation covers both
the read-only commit preflight and the merge pass. The host saves the search stop
and fraction before making its separately counted postcommit full-objective
query. The commit preflight itself excludes the prior and is not the trace cost.

## Bounded memory

| Owned object | Bytes on the qualified host ABI |
|---|---:|
| History bank, including factor and boundary | 6,368 |
| Shared query/proposal/merge workspace | 1,600 |
| Shared result | 120 |
| Sixteen raw records, eight incoming records, queue metadata | 408 |
| Explicit immutable calibration | 56 |
| Shared refinement/checkpoint auxiliary workspace | 128 |
| **Complete candidate context** | **8,680** |
| Project stack reservation | 768 |
| Runtime, IRQ and external-caller reservation | 768 |
| **Planning total** | **10,216** |

The auxiliary phase union holds either checkpoint scratch or a temporary
`ss_input` view and five acceptance scalars. These phases cannot overlap. Its live
pointers are never a serializable checkpoint image. Query, proposal, merge,
refinement and result unions are deliberately reused only after their previous
contents are dead. The independent qualification records compiled stack frames
and complete source-owned call paths. The reservations above remain assumptions
unless those paths fit; target libm, software floating point, interrupts, caller
stack, alignment and linker placement still need actual Cortex-M23 measurement.
The twenty-four-byte planning margin is not certified target headroom.

## Finite qualification and canonical run

`qualification/independent_plan.json` freezes sixteen fabricated integration
cases, an independent full-dimensional differentiation oracle, bounded
instrumentation, and one build/invocation. Instrumentation is host-only and is
not linked into the canonical candidate. The tests address derivatives, transport,
quadratic rows, prior/evidence ownership, cost-only workspace preservation,
evaluated-trial identity, support, queue ordering, atomic rejection, actual merge
failure, the pure ADC producer, and memory/call paths. They do not inspect archive
outcomes or truth.

After qualification and source review, publish and verify the source checkpoint.
The canonical invocation then reads exactly 504,000 chronological records and
allows 31,500 blocks, 346,501 queries, 315,001 prior evaluations, 6,048,000 attempted
model steps and 504,000 QR rows. `host_run_plan.json` owns the detailed resource,
capture, source-binding and failure contract. There is no automatic retry or
extension. Partial and failed results remain explicit and preserved.

Original trace bytes and an independently committed copy close before any
dependent analysis. If compressed for repository distribution, both original
roles retain their own raw identities and exact lossless reconstruction checks;
compression must not disguise or replace a missing original capture.

## External reporting and milestone limits

After whole-process closure, run only the three predetermined exact likelihood
audits at committed indices 252,000, 294,000 and 504,000, if those indices exist.
Each uses the saved point and the identical quantized/decoded inputs. The total
reference cap is 1,050,000 original recurrence steps. No optimization or reference
result feeds the candidate. A missing checkpoint stays missing.

Truth is read only after candidate closure for the all-parameter and evolving-state
plots. Report original quantities in physical units alongside their reference
values and report current SOC separately from initial SOC. Show the full run and
useful early behavior without selecting favorable windows. Capacity and SOC error
goals remain performance requirements, not confidence or coverage claims. The
presentation must distinguish numerical behavior, point accuracy, approximate
history fidelity and remaining uncertainty work.

Passing this experiment would establish a finite causal integration result. It
would not establish indefinite-runtime fidelity, calibrated SOC/capacity
intervals, varied-use robustness, complete Cortex-M23 SRAM/timing, or M3 promotion.
