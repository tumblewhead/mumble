# Architecture contract set, before kernel design

This set completes the specification of A0–A8 on branch
experiment/conditional-architecture-001, parent b9c898f. Kernel, registry-layout,
compression-basis and scheduling implementations are paused until these contracts
are reviewed. No new estimator or optimization code belongs to this step.

Contract completeness means interfaces, premises, obligations, failure outcomes
and acceptance evidence are specified. It does not mean all physical premises,
numerical constants, resource bounds or deployment guarantees are established.
The immutable review/requirement manifest distinguishes these states.

## Common object and model contract

The physical model is OCV(SOC)+three-branch Foster+hysteresis with dynamic
z,v1,v2,v3,h and continuous Q,R0,Ri,taui,H,gamma_plus,gamma_minus. At the reference
temperature R and tau are positive, H>=0, gamma directions positive, |h|<=1;
SOC support and ordered-pole convention belong to the declared model domain.
With Q in Ah, z advances by -I*dt/(3600Q) in the stationary exact-input case.
Positive current denotes discharge. Known reversible thermal factors and their
uncertainty are distinct from irreversible reference-condition aging. Exact linear
OCV is a qualified subfamily, not a requirement to fit a real nonlinear curve badly.

Every object binds model/calibration/noise/support/coordinate versions, source
identity, reset epoch and actual observation prefix. These are semantic identities,
not merely pointer addresses or unchecked short digests. Coordinate or physical
law changes require a qualified migration, independent reinitialization, or refusal.
The generator/rig's hidden truth never enters estimation or authorization inputs.

Abstract interfaces (not memory layouts) are specified in interfaces.json:

- Observation: source/epoch/nonce, I,V,T with declared measurement semantics,
  actual interval or interval uncertainty, acquisition/configuration identity.
- Evidence object: prior-free joint likelihood or declared evidence-set semantics,
  chronological ownership, continuous support, carried state/transport relation,
  representation and approximation accounting. A fit/readout is a derived view.
- Prior: explicit public initialization support/law and measure, included once.
- Candidate transaction: borrowed immutable committed generation and prepared
  successor; no authority until a consistent commit.
- Query: quantity/units, prefix and validity horizon, future load/input envelope
  when relevant, tolerance and requested guarantee class.
- Result: point or range, provenance, approximation/solver status, guarantee kind,
  authorization decision and expiry/revocation boundary. Unresolved is not a claim
  that the point is wrong or the battery is physically impossible.
- Recovery/reset: consumed versus published prefixes, replay/gap disposition,
  qualified initialization and risk-accounting continuity.

One configured F_s determines dt=1/F_s in fixed-rate acquisition. Nonces establish
order; they do not replace physical duration. Irregular intervals, dropped samples
or rate changes require the recorded actual interval or a qualified interval set.
No numerical kernel infers time from host processing speed. Cadence changes are
observable architecture changes if they alter query timing or linearization.

## Contract index

| ID | Contract document | Mathematical foundation | Acceptance boundary |
|---|---|---|---|
|A0|Existing architecture_reuse_001/A0.md|Reviewed affine-response dependency lemma|Restricted-family raw coefficient map; not independent posteriors|
|A1|Existing architecture_reuse_001/A1.md|Reviewed exact local reuse lemma|Its fixed ABI/runtime/observable premises only|
|A2|A2.md|K3 exact graph/cache refinement|Complete dependencies and error/effect semantics|
|A3|A3.md|K4 lifetime refinement|All readers, failures, interrupts and restore paths|
|A4|A4.md|D7, ownership, K6|Ordered once-only evidence, atomic authority, bounded recovery classes|
|A5|A5.md|Joint linear algebra, D0–D4, K7|Query accuracy/uncertainty/availability separately|
|A6|A6.md|K1/K2/K7, D1|Continuous support, accumulated approximation and numerical budgets|
|A7|A7.md|D1/D5 and physical path relations|Aging/temperature/path consistency; no invented rate law|
|A8|A8.md|K5/K6|Complete memory, service/backlog, deadlines and controller effects|

A0/A1 and their accepted reviews remain byte-for-byte unchanged. This set specifies
their place in the whole architecture without extending their proven domains.
All new A2–A8 proof packets require individual independent review; substantive
revisions require renewed independent review. Tests listed in each packet are
acceptance obligations, not newly executed implementation tests in this step.

## Composition contract

Start with a valid bound initial object, or quarantine. A4 serializes evidence and
authority transitions. A2 may replace a pure computation only within its exact
or explicitly bounded semantics; A3 may alias storage only after every reader is
finished. A6 accounts for every approximation and solver/transport error on a
declared support. A7 supplies the physical path relation needed by A6/A5 as the
cell changes. A5 authorizes only the requested query under the qualified guarantee
law/set. A8 supplies processing and publication service before the result expires.
Each successor must reestablish the common identity, support and authority
invariants. Those premises compose by induction over committed transitions;
no claim of system validity follows when one required premise is still open.

Likelihood fidelity, local curvature, solver convergence, physical coverage,
useful availability and target feasibility are separate acceptance axes. There is
no rule that a small residual, successful optimization or a fixed-size object
automatically satisfies another axis. Permanent refusal is not an availability
solution; forced acceptance is not an uncertainty solution.

## Quantitative requirement closure

requirements.json separates known design targets from unqualified assumptions.
Known targets include roughly10KiB SRAM,16MHz baseline M23,35Hz nominal configurable
acquisition, and approximately ten years. SOC0.5percentage-point and Q1% relative
are development objectives; they are not yet device safety requirements.

Before deployment, bind physical population/thermal/aging/input-error envelopes,
load voltage margin/horizon, risk semantics and lifetime risk allocation, useful
availability scenarios/deadlines, tolerated gaps/resets, and target service/stack
bounds. Before an approximate kernel is accepted, also allocate its share of
query/likelihood/numerical error against a frozen reference. These remain explicit
parameters/blockers rather than arbitrary thresholds selected to pass a fixture.

The next step after contract review is resolving the design blockers needed for
the first continuous-shape representation, then selecting kernels against this
contract set. This specification alone does not authorize mainline promotion.
