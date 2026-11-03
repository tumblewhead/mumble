# Problem statement: the next mathematical direction for battery history

Find a physically consistent, fixed-memory representation of battery history that
preserves useful joint inference over sustained operation.

We have a continuous rolling estimator for an augmented Foster battery model.
We need to compress its historical likelihood and state transport without gradually
introducing bias, overstating certainty, or growing storage.

The next mathematical direction should change the representation's available
response shapes, rather than keep tuning a family whose approximation limit is
already known.

## Reference problem

For each stationary RC branch,

\[
\dot v=-\frac{v}{\tau}+\frac{R}{\tau}I,
\qquad
v(t)=bF_\tau(t)+R(k_\tau*I)(t),
\]

where

\[
F_\tau(t)=e^{-t/\tau},\qquad k_\tau(t)=-F_\tau'(t).
\]

Resistance and time constant remain continuous unknown physical parameters.
Initially, study the original range \(\log(\tau/\tau_c)\in[-1,1]\) at fixed
temperature. Temperature dependence and physical aging must subsequently have
explicit extensions.

## Required properties

1. **Shared physical response.** One representation must generate both free
   relaxation and forced response. It must preserve chronology, constant-current
   equilibrium, and carried state across load changes and rest. Establish
   nonnegative monotone free relaxation and the appropriate driven-response
   energy property.

2. **Continuous parameter queries and sensitivities.** Support arbitrary parameter
   queries throughout the original physical domain, including derivatives needed
   for joint estimation. Do not replace continuous batteries with a discrete set
   of allowable batteries. Exact matching at the computational centre may be
   reconsidered explicitly if it conflicts with better accuracy across the domain.

3. **Joint likelihood and uncertainty.** Preserve coupling between RC parameters,
   SOC, capacity, hysteresis and incoming states. Evaluate approximation through
   joint score error, relative precision distortion, state-transport error and
   application-query error. Improving one parameter must not conceal
   deterioration elsewhere.

4. **Fixed resources.** Compare candidates within the existing **34-feature,
   4,760-byte likelihood-factor ceiling**, with a **312-byte response-state
   ceiling** for this comparison. Count coefficient tables, prior, workspace and
   transaction machinery separately. The eventual complete subsystem target
   remains approximately **10 KiB SRAM**; factor size alone does not establish
   feasibility.

5. **Sustained, honest inference.** Derive how response and sensitivity errors
   accumulate into likelihood and query errors. Explain how deterministic
   approximation uncertainty remains represented as statistical precision
   increases. Do not invent forgetting, independent noise, or health decay to
   conceal persistent approximation bias.

## Known obstruction

The current experimental repeated-pole family,

\[
\widehat F(d)=e^{-d}(1+\alpha d+\beta d^2),
\]

cannot approximate the full original domain arbitrarily accurately while
remaining monotone. At one admitted parameter/time pair, its absolute
free-response error is at least **0.07453**, regardless of coefficient tuning.
This excludes further query-map tuning as a route below that floor; it does not
exclude other fixed-rank realizations.

## Required outcome

Produce a candidate family — or a justified limitation — with:

- A closed streaming recurrence and shared free/forced construction.
- Proven physical properties and response/sensitivity error bounds.
- Joint inference and transported-query comparisons against retained-data references.
- Explicit storage, computation and cumulative-error accounting.

**Central question:** What finite set of response shapes preserves the physically
relevant information across the parameter range most effectively, while keeping
approximation error visible and bounded rather than allowing it to become false
confidence?

## Checkpoint and resumption context

This captures the problem statement requested in conversation. It is a design
brief, not a new proof, candidate selection, or qualification claim. The
[reviewed contracts](../constrained_operator_contract_001/README.md) and
[study report](../../provenance/constrained_operator_contract_001/README.md)
remain the technical baseline.

- [P1](../constrained_operator_contract_001/P1.md): shared physical constraints
  and the positive-bank centre-sensitivity obstruction.
- [P2](../constrained_operator_contract_001/P2.md): joint error and query objectives.
- [P3](../constrained_operator_contract_001/P3.md): conditional memory schedule.
- [P4](../constrained_operator_contract_001/P4.md): the three-jet error floor.

The floor concerns a dimensionless isolated free kernel, not a bound on fitted
terminal voltage, Q or SOC. It does not establish that every fixed-memory
representation is exhausted. The current family remains a reference; a change
of response shapes, such as distinct poles, is a hypothesis requiring new proof.

The previously agreed immediate implementation step is the isolated P3 memory
feasibility kernel: compare validation/replay QR and rowwise joint inference
against copied-factor/dense references; measure actual scratch, stack and CPU;
check prevalidation rejection and mid-write quarantine/ownership. No new physical
approximation is required for that experiment. A later response search needs
its own shared-closure proof, fixed budget and registered joint comparisons.

The named paper memory peak is 8,568 B (9,528 B with a general prior), excluding
unqualified helpers, stack, queues and recovery. It is not a measured M23 fit.
Aging, cumulative error, H approximation and calibrated coverage remain open.
Every new proof and optimization requires independent peer review and revision
where needed. Production defaults are unchanged.

Use [handoff/CONTINUE.json](../../handoff/CONTINUE.json) to resume in the correct
worktree and branch. The checkpoint receipt is
[handoff/next_history_checkpoint.json](../../handoff/next_history_checkpoint.json).
