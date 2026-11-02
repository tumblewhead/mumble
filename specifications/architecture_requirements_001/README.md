# Architecture requirement decisions

This is a resolution layer over the reviewed A0–A8 contracts at e354203.
The original contracts and receipts remain unchanged. `resolution.json` maps
every original blocker to a decision, remaining evidence, and acceptance boundary.
This step selects semantics and feasibility tests, not individual code blocks.
No estimator, campaign default, kernel, or memory layout changes here.

The central decision is to carry **joint evidence and boundary-state transport**.
The rolling estimate is a view of that object. A centroid, covariance, or current
set of RC coefficients alone is not the history. Old evidence may stop tightly
constraining today's battery through a declared physical evolution relation;
there is no time-based discount, automatic covariance inflation, or information-rate
rule that silently deletes it.

## Decisions that are now specified

| Requirement | Architecture decision | Qualification still required |
|---|---|---|
| B_PHYSICAL | Versioned OCV + three Foster branches + directional hysteresis; five dynamic states and eleven continuous reference parameters; public thermal calibration separate from health. | Actual-cell OCV, discrepancy and support. |
| B_SENSOR | Acquisition supplies ordered I,V,T and interval, plus an explicit sensor-law identity. Input uncertainty and correlated drift are model variables or qualified joint bounds. | Hardware accuracy, correlations, drift, timing and ADC law. |
| B_AGING | Use an evolution relation on the joint boundary state. Reference R may increase and Q/C may decrease in the proposed family; tau need not be monotone. No stationary-history relabeling after health changes. | Quantitative family, state convention and evidence for real aging. |
| B_ERROR | Judge compression by query consequences and joint likelihood/transport defects. Consume remaining query margin; no universal NLL threshold and no assumed cancellation. | Uniform candidate bounds and useful error/resource tradeoff. |
| B_ACTION | Each authorization request must supply voltage floor, entire load horizon/envelope and fallback policy identity. No implicit floor or inherited permission for a changed load. | Device values, disturbances and fallback feasibility. |
| B_RISK | Separate diagnostic local precision, model-posterior fidelity and physical authorization. Default development results are diagnostic. Select a bounded-set or simultaneous-probability profile explicitly. | Physical premises, lifetime risk policy and validated construction. |
| B_AVAILABILITY | Measure useful service per registered scenario, including failures and refusals; lack of excitation is distinct from missed processing deadlines. | Achievable excitation, useful-query deadlines and outage objectives. |
| B_FAULT | Single writer, immutable published generations, bounded pending input; acquisition may interrupt but cannot mutate inference state. Fail closed on unknown continuity. | Platform interrupt/integrity/reset behavior and fault injection. |
| B_PLATFORM | SRAM-only history, all-in 10,240-byte design ceiling, 16 MHz nominal; one F_s controls fixed intervals. Finite ten-year counter envelope; timing acceptance needs actual useful service. | Maximum target F_s, CPU share, blackout/jitter, stack and linked image. |
| B_REPRESENTATION | Continuous-shape, partitioned joint likelihood/transport family is the first stationary candidate; coefficients may be encoded. Explicit boundary-message extension is required for aging. | Approximation closure, PSD, migration and complete resources. |

“Specified” does not mean measured or proved feasible. All ten architectural
responses are concrete; none of the ten original qualification blockers is
blanket-closed by this document. Missing device facts prevent device claims,
not the bounded desktop feasibility work listed below.

## Physical and acquisition profiles

Use positive I for discharge, Q in Ah, temperature in K internally, and seconds
for physical duration. Fixed-rate dt is exactly the configured expression 1/F_s;
the interval error model covers physical clock error. Nonces supply ordering,
not elapsed time. Rate changes establish a new acquisition generation without
resetting the battery state. A missing sample is a physical interval with an
unknown measurement/input, not a shorter experiment.

The reference-condition parameter vector is
`(Q,R0,R1,tau1,R2,tau2,R3,tau3,H,gamma_plus,gamma_minus)`.
The physical state is `(z,v1,v2,v3,h)`. Reference and effective-temperature Q must
be different query names; percent errors must use the same convention as truth
in an evaluation. No truth or load-generator seed is part of the inference API.

Two profiles avoid conflating architectural progress with physical qualification:

1. **Stationary exact-input reference.** Use the existing conditional architecture
   control, public calibration and original prior, constant reference temperature,
   continuous unknown shapes, and its declared fixed Gaussian observation weights.
   This is an algebra/representation reference. It is not an exact likelihood for
   rounded ADC measurements and does not inherit physical coverage. The original
   prior's untruncated tails remain explicit; a computational box does not truncate
   it by fiat. Comparisons on a box are restricted comparisons unless omitted mass
   is accounted for. Exact-linear OCV is this profile's assumption only.
2. **Evolution-enabled reference.** A versioned transition describes physical state,
   health and any noise/calibration memory. For a first *synthetic* aging fixture,
   retain the user's phenomenological equations: z,v_i,h are continuous as reference
   parameters change, and integrate their ODEs using current effective parameters.
   For constant parameters this reduces to the stationary recurrence. Do not also
   impose charge-preserving C*v or absolute-charge conservation at parameter changes:
   those are different models. A charge-conserving/loss model requires a different
   explicit transition and comparison fixture. No physical aging deployment profile
   is enabled by choosing this synthetic convention.

Within the synthetic aging fixture, branches retain physical identity. Reject a
crossing trajectory as outside that fixture's ordered-pole assumption; do not
sort R,tau independently of branch states. A future crossing-capable profile must
permute states, parameters, correlations and all history dependencies consistently,
or use persistent unsorted physical branch identities. Thermal effects are
reversible calibration, not monotone health. H/gamma aging is unspecified rather
than silently assumed monotone. A profile must declare whether those parameters
are stationary or evolve. Actual schedules, bounds and uncertainty remain inputs
to a preregistered fixture, not hidden constants in the compressor.

The supplied +/-3sigma capacity guidance gives sigma approximately 0.867–1.2mAh
around nominal60mAh, but does not select a distribution, hard support or aging rate.
The proposed [0.5,1.5] health envelope is likewise not a qualified physical bound.
Neither is converted into a Gaussian prior or drift rate without an explicit study.

## History, solver, and controller responsibilities

The prior-free `EvidenceObject` remains unchanged. Add two distinct semantic
objects (specified in S1): a prior-free `TransitionEvidence` for a disjoint
interval, and a `BoundaryMessage` derived from the original prior and owned
evidence. The latter is **not prior-free** and must never be passed as an
independent new likelihood alongside its ancestors. It carries joint endpoint
state/health uncertainty, conditional sensor memory and approximation provenance.
This makes the aging interface explicit without pretending that a fixed-shape
624-byte factor can represent changing unknown parameters.

The rolling solver proposes continuous parameters and evaluates the retained
object; it does not define the physical support or rewrite prior evidence. A
local Gaussian is a derived diagnostic view. The controller asks queries with
tolerance, horizon and semantics; it does not infer trust from a solver success
flag. Historical output remains inspectable, with its original prefix, after
current authority is revoked.

An aging state is sufficient only if the declared evolution/sensor law has the
conditional-independence property in S1. Hidden path dependence requires an
augmented separator, possibly latent spline coefficients, accumulated exposure,
or sensor drift state. A four-knot spline is a candidate trajectory restriction,
not an established sufficient statistic. There is no fixed-size closure claim
for arbitrary monotone aging or arbitrary correlated sensor error.

## Representation selection and migration

For the first stationary feasibility comparison, select **dependency-partitioned
coefficient functions** of continuous log(tau_i) and log(gamma_dir/Q), over an
explicit public computational domain. Preserve all78 augmented Gram entries and
the endpoint response/transport functions. A log chart is a coordinate change,
not a battery quantizer. Priors keep their original measure/Jacobian semantics.
A0's partition is proven only for its stationary restricted family; it must be
re-derived before time-varying/uncertain thermal laws or aging use it.

S2 gives the storage frontier before choosing a basis, degree, quantizer or
kernel. A one-table cubic tensor-product family already exhausts the SRAM target
on raw likelihood coefficients alone. The first comparison therefore considers
lower-order/sparse partitioned encodings against H7 and direct retained-data
evaluation, with every unsupported query and failure visible. This selects a
candidate family for feasibility, not a degree or numerical acceptance threshold.
Encoded Gram entries must have a justified PSD/precision/error treatment; silently
projecting negative eigenvalues away or converting normal equations into a trusted
square-root factor is not justified by storage savings.

Choose the following migration policy now: changing coordinates is permitted only
with a bound relative to the same original object. Domain enlargement/refinement
needs a retained global enclosure, sufficient richer coefficients, or owned replay
data covering the affected evidence. A small recent window cannot reconstruct
discarded old shape dependence. No such fallback is assumed to fit until counted.
If it does not fit, preserve diagnostics but withdraw affected authority and record
loss of useful availability. Do not clip a physical estimate or reset the error
ledger. The known kplus box-exit at35520samples is a mandatory boundary witness.

For target feasibility, the candidate must preserve useful service over its
declared full physical support, or explicitly account for omitted support/mass.
Passing only a narrow box about a successful fitted trajectory cannot satisfy this
requirement. Field/H7 remains the desktop control; neither is silently promoted
into this new representation.

## Error, risk, and useful service

The application objectives remain SOC0.005fraction and Q1% relative for development.
Do not split those into invented per-module percentages. For an interval
`[l,u]` with valid *physical* containment semantics, point q and separately bounded
query distortion e, the conservative interval is `[l-e,u+e]`. SOC authorization
requires the largest endpoint distance from q to be <=0.005. Q uses the A5
relative criterion on that expanded **positive** interval with t=0.01. Numerical,
representation, transport and physical-model errors enter by their justified
composition rules; e cannot absorb unknown error or duplicate error already in
the interval. Until containment is qualified, these remain model diagnostics.

This defines a remaining-margin budget at each query. Modules must jointly fit
that budget with conservative bound arithmetic. No useful margin means unresolved,
not permission to relax the objective. A future fixed allocation is accepted only
after measuring its usefulness and proving its bound against the reference.
NLL oscillation and TV bounds compare model distributions; they are not units of
SOC or guaranteed point displacement. Gaussianized uncertainty is not upgraded
to physical containment by adding a representation bound.

For load admission the request supplies `(V_floor, margin, horizon, I/T envelope,
transition profile, fallback policy)`. Authorize only if a qualified lower bound
on the minimum voltage over the *entire* horizon exceeds V_floor+margin. Missing
inputs yield a diagnostic forecast at most. The estimator refuses permission;
the system owns a feasible fallback. A changed request needs reevaluation.

Choose deterministic set containment as the first conditional physical-assurance
profile when hard input/model/transition bounds exist. It has no statistical alpha,
but its scope is conditional on those bounds and admitted faults; it does not
cover unbounded Gaussian sensor noise. A probabilistic profile must supply one
simultaneous event over the claimed lifetime and reset policy, or a justified
finite-query allocation. Alpha/beta remain device-policy inputs. Per-boot or
per-sample95% intervals cannot supply this profile. Unknown risk continuity after
SRAM loss disables the lifetime-probability claim; no hidden nonvolatile history
is added. Neither profile is presently physically qualified.

Availability is a separate requirement, not satisfied by permanent refusal. Record
time to useful SOC/Q/task queries, duration/frequency of unavailable periods,
recovery cost, failures and false authorizations, under a frozen scenario law.
Include weak/rest/repeated/embedded/charge-cycle stimulus, aging, thermal variation,
sensor drift and resets. The existing ~18–33minute convergence experience motivates
test horizons; it is not a deadline proof or a promise for unexcited batteries.
Prespecify useful-service deadlines before confirmation, not after observing runs.

## Fault and resource boundary

The architecture has one inference writer. An acquisition interrupt may enqueue
an immutable observation within a bounded buffer, and readers see complete
published generations. Concurrent direct mutation, unchecked stale pointers and
unbounded asynchronous work are outside this profile. Queue overflow, invalid
interval, failed validation, domain exhaustion and iteration limit have explicit
A4 outcomes. Loss of input continuity needs a qualified reach relation or current
authority is revoked. Solver retries never reacquire ownership of the same evidence.

Power loss destroys SRAM history. Restart from public support valid for an aged
cell, not a narrow fresh-cell posterior; current authority is initially absent.
Choose a new session identity through the platform, or prohibit cross-reset handle
reuse when no durable identity exists. External telemetry must then label sessions
separately. Unbounded silent memory corruption cannot be detected by a software
invariant alone. Detected corruption quarantines; physical deployment must supply
an admitted corruption/fault model and protection. No arbitrary-fault guarantee.

All state, pending inputs, rollback, cached values/keys, temporary factors, query
scratch, stacks and feasible ISR nesting share the10240-byte ceiling. Flash/code
size is reported separately. No extra persistent medium is assumed for history.
Use a ten-year upper envelope of10*366days and nonwrapping64-bit logical counters;
S2 checks sample counts. Transaction/cache generations need their own bounded
operation counts, not just the sample count. Before counter exhaustion revoke
affected handles and refuse or use a qualified rollover; never wrap silently.

35Hz is nominal, configurable desktop rates remain useful stress tests. Target
maximum rate and CPU share await platform requirements. S2 reports necessary
cycle ceilings, not WCET. Require service/blackout/backlog/latency qualification
and complete stack/layout evidence before target acceptance. Desktop wall time
and a fast average cache path do not discharge these obligations.

## Next decision and acceptance sequence

1. Freeze one stationary public domain/reference profile and representative
   common queries, including the preserved domain-failure witness. Compare the
   low-order/sparse coefficient candidates for joint likelihood, derivatives,
   transport, PSD, query error and complete byte/work cost. No large sweep yet.
2. Reject candidates without a credible full-domain/migration error bound and
   sufficient remaining SRAM. Only then select individual blocks and allocations.
   A small typical error does not close a ten-year accumulation requirement.
3. Derive the evolution-enabled closure against S1, first with declared synthetic
   transitions and then characterized physical aging. Keep a direct short-history
   reference and equal-final-health/different-path counterexamples.
4. Qualify useful service and physical trust separately with frozen scenarios,
   independent confirmation, and target measurements. Any proof or optimization
   receives independent review, including substantive revisions.

The immediate unresolved algorithm question is whether a continuous-shape family
can meet useful error and full-resource budgets without replay. This is smaller
and more testable than requiring every hardware or cell specification before
architectural development, but it remains a real feasibility question.
