# Evidence-token and feedback contract

The rolling estimator produces **two distinct outputs**: an estimate for the
application, and a prior-free evidence token for history. History returns a
joint boundary message that supports the next rolling fit. The compressor
contains no plant, stimulus generator, truth scorer or assumed aging rate.

The normative machine-readable specification is [contract.json](contract.json),
with the user's augmented Foster equations bound by [model.json](model.json).
[protocol.py](protocol.py) is an executable desktop reference for ownership and
transactions; its numerical backend is supplied separately. This is an interface
contract, not a new battery estimator or firmware implementation.

## Physical model and nearly linear OCV

Start with three Foster branches, ohmic resistance, charge integration and
directional hysteresis rates. Preserve the five physical states SOC, three RC
voltages and hysteresis. Estimate continuous reference-temperature parameters
Q, R0, three R values, three time constants, H and gamma+/gamma−. Derive branch
capacitances as C=tau/R. Enforce `0<tau1<tau2<tau3` over the admitted domain,
preserving each branch's R/tau/state pairing rather than sorting states.

The user's hysteresis law uses normalized throughput
`dξ=|I|dt/(3600 Q)` for Q in Ah and time in seconds. Its two gamma parameters
are dimensionless, and Q affects both charge and hysteresis transport. Terminal
voltage is `U+Hh−IR0−sum(vi)` as proposed. The older model used per-Ah gamma
and minusHh; these conventions cannot share a model identity or coefficients
silently. At zero current h holds while Foster voltages relax. The constant-
interval recurrences, positivity/domain constraints and temperature bindings
are explicit in the model contract.

Use `U(z,T)=a(T)+b(T) z+r(z,T)` with positive slope over the admitted SOC range.
The first reference may set r=0 explicitly. A nearly linear cell then requires
a stated residual model/bound; it does not justify silently treating systematic
curve error as independent measurement noise. This is the user's initial model
assumption, not a chemistry-wide empirical claim.

Linearity introduces an important ambiguity. For constant Q and temperature,
with transferred charge A in Ah,

    z = z0 − A/Q,
    U = (a+b*z0) − (b/Q)*A.

After accounting for RC/hysteresis response, observations constrain the
intercept a+b*z0 and the ratio b/Q. If a, b, z0 and Q are all unrestricted,
absolute Q and SOC cannot be uniquely recovered from this relation. Under the
proposed normalized hysteresis, simultaneously scaling gamma with Q also
preserves the hysteresis trajectory, so free gamma does not remove that ambiguity.
OCV slope
and intercept therefore need independent calibration/support or equivalent
anchors. Their shared uncertainty belongs in the joint inference once. A test
must not secretly supply the plant's OCV values as learned information.

Temperature is initially an exogenous cell temperature. Arrhenius reference
laws, coefficients, units and domains belong to the estimator's physical-model
binding. Thermal coefficients can be characterized or learned when excitation
supports them; those statuses must differ. OCV need not share the electrical
parameters' temperature law. Historical parameter changes are compared at a
common reference temperature to separate reversible thermal response from health.

There is no hidden calendar/cycle deterioration term. A stationary-reference
mode explicitly assumes fixed reference parameters. A later drift mode must
carry continuous parameter trajectories and their joint uncertainty, inferred
from rolling evidence under declared structural assumptions. Monotone physical
aging may constrain path direction without prescribing its speed. A compressor
must not invent transition rates, process noise or forgetting. Also, a revised
estimate of Q is not a physical instantaneous loss of charge: charge/availability
and RC-state continuity conventions belong to the producer model.

## Three objects and their ownership

| Object | Meaning | May history ingest it as new evidence? |
|---|---|---|
| EstimateView | Selected parameter/state values, uncertainty and numerical/excitation status | No |
| EvidenceToken | Likelihood and physical transport for one newly retired, contiguous observation interval | Yes, once |
| FeedbackMessage | Joint boundary posterior from the root prior and retired prefix | No; it is referenced by the next rolling query |

Let boundary k be immediately before observation k. Observation k contains
the actual interval duration, held current and temperature convention, then the
endpoint voltage. Its transition maps state k to k+1. A token [a,b) owns those
observations and transitions, entering at a and leaving at b. Equal time ticks
are permitted for a zero-duration observation; the sequence still advances.

The token represents the conditional kernel

    K_[a,b)(s_b, eta | s_a)
      = p(y_[a,b), s_b | s_a, eta, u_[a,b), declared_model).

Here s includes the required physical/path boundary state, eta denotes shared
parameters/calibration/nuisance, u denotes public inputs and y the observations.
The producer compiles these into the representation payload. The compressor
receives neither the raw test rig nor an independent synthetic observation
generator. All dimensions, coordinate charts, domains, noise/calibration and
evolution semantics are bound by immutable identities.

The token excludes the entering prior and previous feedback. Its payload must
retain the joint dependence, including cross terms, physical endpoint transport,
normalization and any deterministic constraints. A mean plus covariance or a
local Hessian is not automatically sufficient for a nonlinear likelihood.
The backend must state what representation it uses and its approximation limits.

A rolling fit may use history to choose a linearization center. That does not
authorize exporting history's density or information matrix again. Construct
the token from factors belonging to [a,b); do not subtract approximate posterior
and prior Hessians and assume the remainder is valid evidence. Chart-context
provenance and approximation domains accompany the payload. A representation
must not restrict physical support merely because a point fit is confident.

## Feedback and chronology

History starts with one public root prior. Retirement updates its boundary
message by integrating the old boundary state:

    M_b(s_b,eta) proportional to
      integral K_[a,b)(s_b,eta | s_a) M_a(s_a,eta) ds_a.

Shared eta remains shared. When nuisance variables are eliminated, retain their
necessary joint effect instead of replacing it with independent marginals.
Deterministic transport is a singular measure, not a reason to add fictitious
process noise. Likelihood normalization and parameter-dependent Jacobians must
be preserved under any coordinate change. Marginalization and profiling are
different operations; this message contract uses marginal semantics.

The next rolling query combines **M_b and observations [b,n), once each**. It
does not add the root prior again. The original C solver's current approximate
history cannot remain in the objective for that same retired prefix. Its
original-entering-state chart also needs an explicit adapter to this current
boundary chart; the contract does not claim that adapter is already present.

Rest observations may update correlated health parameters through SOC and RC
information. In an unexcited independent direction, stationary transport must
retain uncertainty without forced drift. Neither a narrow local curvature nor
a normal-looking voltage residual is evidence that capacity is identified.

## Atomic retirement and feedback reuse

1. The estimator holds active observations [k,n) and reads immutable message
   generation v, owning the root prior plus [0,k).
2. It constructs a token for the oldest prefix [k,m), with m<=n and a reference
   to that base message. Fits on overlapping windows are allowed; overlapping
   evidence exports are not.
3. `prepare` validates identities, epochs, ownership, observed-end watermark,
   representation and byte capacity. It constructs a candidate message without
   publishing it. A failed prepare leaves the old message and raw data intact.
4. `commit` atomically publishes generation v+1 and returns a receipt. Repeating
   that same most recent commit returns the same receipt without another update.
5. The estimator acknowledges the receipt, advances its active start to m and
   only then releases the retired raw prefix. A new message cannot be queried
   alongside the old prefix while acknowledgment is pending.

The reference stores one pending candidate and the last receipt. Older repeated
tokens are rejected by their interval/generation; no growing deduplication log
is needed. Abort discards only the candidate. Queries are read-only, and changing
the display cadence cannot change retained evidence. Resource exhaustion must
cause explicit backpressure or unavailable status, never silent evidence loss.

This is an externally serialized in-process contract. Idempotent retry is not
a promise of power-loss durability. SRAM-only operation loses state on power
loss unless a separate persistence mechanism is deliberately introduced. Soft
restore requires consistent message, prior and window ownership; resetting an
estimator must not reset the simulated plant or supply truth.

## Approximation, status and storage

Keep numerical stop, excitation, representation quality and coverage status
separate. Tokens/messages declare their representation/domain and preserve a
cumulative error certificate when available, otherwise explicit unresolved
status. A provenance hash does not replace an error bound. Retiring a window
does not reset accumulated error. The preferred 0.5% Q and 0.5 SOC-point scales
guide system assessment; they are not arbitrary per-token likelihood thresholds.

For perspective, a float64 Gaussian boundary mean and packed covariance over
16 coordinates needs **1,216 B**; the earlier prior-free two-boundary Gaussian
operator needs **4,488 B** of numeric coefficients. Two boundary messages plus
one such operator require **6,920 B** before metadata, normalizers, uncertainty
in thermal/OCV/path coefficients, solver, raw window and composition workspace.
This illustrative count is not a selected nonlinear representation or complete
10 KiB fit. `protocol.py` has a configurable message-payload cap, not a complete
SRAM allocator. The next implementation must account for the transaction peak
as well as the final compact object.

## Verification and next implementation

[qualification.py](qualification.py) exercises the protocol with a separate
linear-Gaussian fixture backend. It checks duplicate/prior/feedback rejection,
source and epoch mismatches, stale versions, lost acknowledgments, atomic failure,
finite storage caps and one-prior/one-observation algebra. It also checks the
linear-OCV identifiability symmetry and the distinction between independent
unexcited and correlated indirectly observed directions. The Gaussian fixture
is test code; no battery model or harness is imported by the protocol.

See [qualification001/result.json](qualification001/result.json),
[summary.json](summary.json) and [verification.json](verification.json).
These establish finite interface behavior, not nonlinear battery closure or
coverage. Existing estimator results and sources remain preserved.

Next implement a small **stationary, continuous-parameter Foster token producer
and feedback adapter**, using the declared linear OCV calibration. Compare
rolling+history against independent retained-data inference, including rest and
re-excitation. Only after the source-once and joint-uncertainty checks pass should
we add observation-supported parameter trajectories and optimize storage.
