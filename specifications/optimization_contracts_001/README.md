# Proof contracts for future optimization

Status: conditional mathematical contracts and a review protocol. No estimator
optimization or performance claim is introduced here. This develops A11 of the
[unattended deployment case](../unattended_assurance_001/README.md).

An optimization must state what it saves, what observable behavior it preserves,
and what bounded changes it spends from an existing error/availability budget.
It must not obtain speed by silently weakening the physical domain, recovery
contract, uncertainty meaning, or source ownership. Explicitly restricted product
profiles are possible, but are separate contracts rather than universal savings.

## Three distinct acceptance classes

1. **Exact implementation refinement:** the same public trace for every admitted
   input/fault trace, allowing declared bounded internal scheduling differences.
   Examples may include elimination of duplicate work and scratch reuse. Bitwise
   equality requires the specified arithmetic/build behavior; an algebraic
   identity alone does not establish it.
2. **Bounded numerical refinement:** defined point, joint uncertainty, transport
   and decision differences remain inside cumulative budgets at every relevant
   prefix. Examples include quantization, approximate functions and sparse bases.
3. **Algorithm or policy change:** different evidence, refresh policy, physical
   model, trust decisions or acquisition requirements. This needs renewed
   behavioral qualification; it is not justified by a faster implementation alone.

An exact optimization of an unsafe reference preserves its defect. Correctness
repairs must be identified separately and evaluated against the deployment
contract. H7 remains a fidelity reference with unresolved deployment claims.
A candidate may be retained as a research improvement while explicitly carrying
those inherited gaps; that decision cannot authorize deployment or guard removal.

## Reusable proof collection

| Contract | Typical optimization | What must be established |
|---|---|---|
| K0: trace refinement | Kernel fusion, specialization, guard elimination | State relation, all observable outputs/statuses, evidence identity, fault behavior and bounded progress. |
| K1: numerical and decision bounds | Early solver termination, approximations | Propagated error, query/uncertainty bounds and explicit threshold margins; safe fallback near uncertain decisions. |
| K2: composition | A sequence of many small optimizations | Cumulative error relative to a frozen anchor; matrix errors compose multiplicatively, not automatically additively. |
| K3: graph and cache correctness | Executive, registry, memoization | Complete dependencies/keys, invalidation, side effects, faults and arithmetic environment; quantized keys need approximation bounds. |
| K4: storage reuse | Scratch sharing, in-place operations | Nonoverlapping lifetimes including retries/rollback, valid alignment/type/aliasing and concurrency. |
| K5: resources and deadlines | Smaller kernels, caches, scheduling | Target worst-case cycles and full memory bounds including cold cache, monitors and recovery. |
| K6: cadence and control | Less frequent solves/refreshes | Same evidence/time propagation, bounded output latency, fresh certificates and closed-loop behavior. |
| K7: representation equivalence | Basis changes, sparse/history compression | Full quadratic and state transport preserved exactly, or discarded modes and normalization explicitly bounded. |

The [lemmas](THEOREMS.md) provide the mathematical arguments. Existing E1–E6
supply likelihood, joint precision, center and transport error bounds. D0–D7
supply unattended-operation conditions. These dependencies prevent a local
optimization proof from being mistaken for a new physical accuracy proof.

## Fixed anchors and budgets

Keep an immutable numerical reference, physical model and qualification scenario
manifest. Compare each change both to its immediate parent and cumulatively to
that anchor. After a justified reference repair, start an explicitly versioned
anchor and record which earlier claims need rechecking. Do not repeatedly reset
the error allowance to zero as each candidate becomes the next parent.

Declare separate budgets for query point error, joint uncertainty distortion,
likelihood shape, endpoint transport, validity/availability, latency, memory and
lifetime risk. Not every optimization needs every numerical metric, but excluded
metrics need a proof explaining why they are unaffected. Small voltage residual
error does not automatically bound Q, SOC or weak RC directions. Bytes saved do
not compensate for unsafe load authorizations.

No numeric optimization allowances are invented here. The discussed 0.5% accuracy
scale is an application objective, not a fresh allowance for every optimization.
Only the remaining margin after reference/model/sensor error is available to an
implementation change. Use the earlier error proofs to translate requirements
into bounds once those requirements and physical premises are qualified.

## Per-change review record

The [template](change_template.json) records the following, with unknown values
left null and acceptance blocked until required evidence exists:

- Frozen reference, candidate revision, compiler/flags, ABI and scenario identities.
- Classification, exact changed kernels, dependency/lifetime contracts, and
  declared operating/input/fault domain.
- Claimed theorem and discharged premises; any inherited gaps remain visible.
- Per-change and cumulative error/resource bounds, including decision margins.
- Target flash, static SRAM, peak scratch/stack/interrupt memory, and worst-case
  cycles; host timing and finite observed maxima are labeled separately.
- Matched numerical/behavior tests, boundary and fault cases, assumption-violation
  tests, availability and reacquisition checks, and baseline/candidate results.
- Decision: accept, reject or unresolved, with no automatic promotion from a
  passing benchmark or small mean error.

The acceptance rule is componentwise: all required behavior/resource constraints
pass, and the claimed resource benefit is demonstrated under its stated metric.
If a larger table saves cycles but exceeds flash, or a cache saves average work
but violates worst-case latency, record the tradeoff rather than calling it an
unqualified improvement. Energy requires a qualified target power model or
measurement; CPU cycles alone are not an energy certificate.

## Useful first applications

Graph scheduling, exact memoization and lifetime-based scratch reuse are promising
early candidates because they can avoid changing the estimator mathematics.
Start with a small kernel dependency graph and explicit versioned inputs; prove
each cache hit and buffer reuse. The measured fused-update study is a precedent
for paired evidence, not proof that arbitrary future fusion is equivalent.
See [its receipt](../../provenance/tangent_fused_001/receipt.json).

Reduced precision, sparse bases and refresh changes follow only with the joint
error and decision contracts. A faster path that cannot establish its numerical
premises must take a bounded qualified fallback or report unresolved; availability
and deadline costs of that fallback remain part of acceptance.

The immediate implementation priority remains the field-flush and query/status
contract from the unattended case. This collection makes later optimization
reviewable without prematurely changing H7 or claiming M23 feasibility.
