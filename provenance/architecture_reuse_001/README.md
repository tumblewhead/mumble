# Dependency contracts and first exact-reuse candidate

The architecture branch now has nine explicit proof obligations, a machine-readable
dependency/lifetime plan, two individually reviewed conditional proofs, executable
counterexample checks, and a first measured reuse candidate. No production
estimator/default has changed. The graph is a design artifact, not a deployed
executive; continuous-rate compaction remains open.

## Proof-driven development result

A0 establishes the conditional raw likelihood coefficient dependency structure:
10shape-independent entries,33single-RC entries,12two-RC entries,11joint-hysteresis
entries,12RC/hysteresis entries. All78cross terms are retained. These are scalar
functions of shapes, not78stored numbers for an unknown-rate estimator. Stable
compression, joint support and approximation bounds remain separate obligations.

A1 proves the within-observation reuse under explicit binary64/deterministic-libm,
fixed ABI, immutable nonaliasing inputs and observable-value premises. Its first
review found that unwritten output suffixes required a tighter observable scope.
The original proof/critique are preserved; the revised proof received a fresh
independent review. No numerical kernel correction was needed for that revision.

The proof plan names future cache invalidation, rollback-safe storage reuse,
evidence ownership, query projection, continuous-shape error, aging and full target
resource gates. Passing a finite test is not presented as proof of a lifetime
property. The acceptance gate binds reviewed source/proof versions and recorded
test/evidence files; changing those bytes invalidates the old receipt. It is not
a theorem prover or authenticity mechanism.

## Implemented reuse and evidence

The H7 response kernel evaluates each active directional hysteresis exponential
pair once, then uses it for all matching grid entries. All64hysteresis state
updates remain in their original order; no observation is skipped or duplicated.
No cross-sample cache, quantized key, frozen battery parameter or new error budget
is introduced. Rest skips the same operations as before.

Instrumented call counts for one nonzero-current sample:

| Explicit response operation | Reference | Candidate |
|---|---:|---:|
|exp|93|37|
|expm1|82|26|
|Hysteresis state pairs updated|64|64|

At rest both remain29exp and18expm1 calls. Counter builds are excluded from timing.
The separate response comparison covers4096irregular observations. Complete
backends agree bitwise at2748boundaries over43,968samples, including native context,
field root/state, live state, publication, pending rows, normalizers and counts.
Rest at15C and multiscale at35C complete4224samples each. The embedded25C witness
matches the original failure at35,520samples with the same input digest and
quarantine. Exact reuse intentionally preserves that unresolved domain failure.

## Measured resources

Nine alternating response trials use identical initial state, restored outside
timing. Median host response CPU time falls from6.291ms to4.646ms per4096samples:
1.354x throughput, approximately26.1%less CPU time for this response workload.
Single paired complete-backend traces show1.057x/1.060x aggregate throughput for
multiscale/embedded and1.024x for rest. These exploratory whole-backend timings
are not repeated controlled speedup estimates; rest has no eliminated exponential
calls and its small timing difference illustrates measurement variability.

Persistent response state remains1336B and the packed H7 field root remains
50,624B. Added persistent storage is0B. The candidate declares128B of local
coefficient-table payload; this host compiler reports the same432B individual
response-function frame for both normal builds. This does not establish complete
call-chain stack usage or an ARM memory/timing result. The50KiB history problem
is unaffected by this optimization.

## Validation and next work

The suite has11kernel/graph tests and4review-binding gate tests. It covers exact
state/row/field/fused parity, signed-zero/rest/tiny-current/variable-dt/temperature
cases, invalid-prefix output semantics, primitive versus caller atomicity,
exp/expm1 counts, missing mixed dependencies, stale temperature keys, wrong
graph order and invalid review/source bindings. Independent reviews add their
own finite controls, recorded in immutable JSON receipts.

Next, select the continuous-shape coefficient representation using A0's dependency
map and an explicit application/error contract. Exact thermal/RC caches can follow
under A2, with complete keys and resource measurements. Exposure-based free-state
storage and scalar uncertainty queries require new numerical-error/implementation
proofs before replacing their current forms. The first candidate is isolated;
integration into local campaign defaults requires a separate promotion decision.
