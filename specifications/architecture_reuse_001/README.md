# Proof-driven architecture: dependency and reuse stage

Branch experiment/conditional-architecture-001, parent64fd124. A proof acts as a
contract, not a substitute for a unit test. Acceptance needs three separate links:
mathematical claim under named premises; evidence that the concrete implementation
satisfies those premises; measured resource effects on a named target/runtime.

## Architectural gates

| Contract | What it protects | Executable witness | Current scope |
|---|---|---|---|
|A0 dependency partition|All joint likelihood cross terms retained|Enumerate78entries and adversarially remove a mixed dependency|Proof plus static map; no compressed continuous-rate field|
|A1 exact local reuse|Identical state/row values, including sign/rest|Bitwise kernel/fused/backend parity, call counters, invalid-input paths|First candidate implemented; review and measurements required|
|A2 cache validity, using K3|No stale thermal/rate/anchor result|Change each dependency separately; signed-zero and version-wrap tests|Planned; no persistent cache implemented|
|A3 lifetime allocation, using K4|No overwrite of a rollback/query reader|Failure-path live ranges; inject a write before last recovery read|Planned; no shared arena implemented|
|A4 evidence transition, using D7/ownership|Each observation consumed once in order|Duplicate/gap/replay faults and transaction rollback|Existing contracts; must be instantiated for a new executive|
|A5 query projection|Full joint uncertainty retained by scalar solves|Compare j P^-1 j^T with full factor, weak/correlated directions|Planned; no query API changed|
|A6 continuous-shape approximation|Bound query/likelihood/transport error|Direct-history controls and uniform-domain bound checks|Open; finite probes alone cannot discharge it|
|A7 nonstationary physical transport|Aging does not make old evidence falsely current|Equal-final-health/different-path counterexamples; justified drift law|Open; no forgetting or aging substitution|
|A8 complete target resources, using K5|Bounded SRAM, stack and worst-path cycles|Link map, stack/call chain, miss/recovery workload on target|Open; host timing and subtotal bytes insufficient|

The individually reviewed D/K packets remain the generic foundation. A0/A1 are
small implementation-facing proof packets. Later changes must cite the exact
contracts they instantiate, preserve their premises or explicitly revise them,
and receive independent review. A test failure blocks acceptance; passing tests
alone does not close an unproved assumption. Counterexamples belong with receipts.

## Kernel dependency and lifetime plan

The machine-readable graph.json lists ordered dependencies, candidate exact
cache keys and storage lifetimes. It is a design artifact, not a deployed graph
executive. Use static kernel IDs and explicit generations before considering
dynamic graph allocation or dispatch. Exact keys require immutable input values
or full dependency generations whose wrap/reuse is prevented; hashes alone do
not prove equality. Sample count identifies chronology, not the duration dt.

Thermal factors live while T/config match; RC coefficients additionally depend
on dt and rates. Hysteresis coefficients additionally depend on current magnitude
and direction. Response state and evidence always advance for each observation,
even when transition coefficients are reused. Anchor calculations depend on
parameter/basis versions, while query results also depend on the evidence prefix.

Planned scratch reuse must include validation, rollback, checkpoint and diagnostic
readers. Old state/factor remains live until commit or rollback is complete.
The first candidate avoids these hazards by retaining current storage ownership
and sharing only two local arrays within one response observation.

## Registered experiment

Compare unmodified H7 with the experiment-only response candidate. Before timing,
require bitwise byte equality of rows/state on irregular intervals, signed current,
rest, variable T, tiny currents, zero intervals, and chunk boundaries; compare
joint field factors and fused native contexts/readouts at the same prefixes.
Replay the35520record failure witness in both backends, preserving errors and
quarantine. Count actual exp/expm1 calls using separately instrumented binaries;
exclude those counters from normal timing builds.

Benchmark matched response workloads with alternating order and repeated trials;
restore identical state outside timing. Report host compiler flags, individual
stack frames, call-count reduction, persistent bytes and complete-backend timing
separately. No minimum host speedup is assumed or used to change the mathematical
acceptance gate. If performance regresses, keep that result and revise the design.
No estimator default, mainline, uncertainty model or source data is modified.
