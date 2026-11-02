# Architecture contracts completed before further kernel design

This step specifies the full A0–A8 architecture contract set, eight abstract data
interfaces and ten explicit requirement-closure items. It changes no estimator,
kernel, cache, executive, compression representation or optimization implementation.
The existing55-file exact-reuse acceptance gate still passes.

The [contract index](../../specifications/architecture_contracts_001/README.md)
defines assumptions, invariants, terminal failure behavior, conditional proofs
and required implementation/qualification witnesses. [Interfaces](../../specifications/architecture_contracts_001/interfaces.json)
describe semantic objects rather than C structs or memory layouts.
[Requirements](../../specifications/architecture_contracts_001/requirements.json)
separate known targets from hypotheses and unbound acceptance parameters.

## Review result

A0/A1 retain their previously accepted proof versions and reviews unchanged.
Each new A2–A8 packet received an individual fresh-context review. A2 and A7
were revised after critiques and received new independent reviews. A final
composition review checks the assembled common interfaces, requirements and
cross-contract assumptions. Exact versions and dispositions are in manifest.json.

| Contract | Architectural obligation |
|---|---|
|A0|Preserve joint coefficient dependencies and cross terms|
|A1|Reuse identical local calculations within its qualified ABI/runtime|
|A2|Complete cache keys, generation validity and bounded approximate reuse|
|A3|Ownership, all-path lifetimes and rollback-safe storage|
|A4|Ordered once-only evidence, publication authority and qualified recovery|
|A5|Full-joint query projection, honest trust semantics and useful availability|
|A6|Continuous support and accumulated numerical/representation error|
|A7|Explicit aging/thermal/state-transition laws and historical path uncertainty|
|A8|Complete memory, service/backlog, deadlines and closed-loop behavior|

Three substantive clarifications came from individual review:

1. Approximate cache reuse needs both query and representative inside the same
   certified Lipschitz region; proximity alone is insufficient. Exact transition
   coefficients may survive a new prefix when all their own dependencies match.
2. Monotonicity without an aging rate permits the entire remaining support, but
   that support can itself be narrow near an endpoint. The contract must not
   claim useful narrowness is categorically impossible.
3. The variable-capacity SOC sum assumes a particular integrator/state convention.
   SOC continuity and preservation of absolute charge under changing capacity
   are different physical models; the evolution relation must specify which is
   qualified instead of quietly selecting one.

Original A2/A7 drafts and critiques are preserved alongside the revised reviews.
The accepted mathematics is conditional: a review does not validate a real cell
family, a concrete concurrent runtime, coverage, useful recovery or M23 feasibility.

## Open requirement closure

The specified architecture needs explicit closure of: physical model/population,
sensor/ADC/clock behavior, aging and state maps, approximation allocation, proposed
load voltage/horizon, lifetime risk semantics, useful availability, admitted faults,
platform scheduling/resources, and the continuous-shape representation strategy.

Known engineering targets remain approximately10KiB SRAM,16MHz,35Hz nominal
configurable acquisition and ten years. SOC0.5percentage point and Q1% are
development objectives, not silently adopted safety specifications. The proposed
aging range and manufacturing3sigma guidance do not determine a process law.
No numerical risk, drift, covariance-floor, forgetting or recovery threshold was
invented to close these requirements.

Specification completeness and deployment qualification are separate states.
Kernel design remains paused as requested. The next work is resolving the relevant
requirement parameters and architectural representation/error choices against
these contracts. A passing paper review does not establish implementation
qualification.

## Verification scope

This step performs document/JSON/reference/hash consistency checks and preserves
the prior implementation acceptance binding. It introduces no new unit-test code
and does not rerun long simulations. Reviewer algebra/counterexample checks are
recorded in their individual receipts; proposed runtime witnesses remain future
acceptance obligations. The contract set is neither a mechanically verified
whole program nor a completed safety case.
