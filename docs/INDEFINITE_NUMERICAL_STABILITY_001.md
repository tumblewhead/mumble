# Indefinite-runtime numerical stability: proof gate 001

## Outcome and authority

The user requires numerical stability for indefinite runtime. This is now a
prerequisite for qualifying a repeatedly updating bounded estimator, rather
than a late endurance test or a target-porting detail.

The current B001/B002 implementation does **not** meet this requirement.
This review establishes mathematical obstructions to overly strong history
claims, proves conditional time-uniform lemmas for physical-state propagation
and quantized charge, and records seven small executable counterexamples.
It does not establish a full-estimator stability theorem or select a replacement
statistical model.

The reference is the published B002 tree at
e478d0eda07b16cdf9121e391d06e2fb9917128b. Its production numerical sources,
earlier results and failed receipts remain unchanged. New work is on
research/indefinite-numerical-stability-001.

| Artifact | Purpose |
| --- | --- |
| [Proof contract](../proofs/indefinite_stability_001/contract.json) | Quantifiers, obligations, nonvacuous acceptance gates and open choices |
| [Claim ledger](../proofs/indefinite_stability_001/claims.json) | Proved mathematical statements versus unproved executable obligations |
| [Counterexample plan](../experiments/indefinite_stability_001/plan.json) | Committed before the primary execution |
| [Counterexample receipt](../experiments/indefinite_stability_001/receipt.json) | Compiler/arithmetic properties, exact inputs, outcomes and hashes |
| [Witness source](../tools/stability_witness.c) | Small scalar and actual-API boundary transitions |
| [Witness runner](../tools/run_stability_witnesses.py) | Reproduction with new output paths and source integrity checks |
| [Previous nonlinear report](BOUNDED_EVENT_002.md) | Preserved 0.1 NLL trial policy, 18 numerical audit failures and memory limits |

The seven reproduced mechanisms are successful falsification evidence, **not
seven passing numerical-stability qualifications**. The API witnesses use
deliberately constructed boundary states. They do not claim that those complete
states arose from a valid physical battery history, or that an endurance run
was performed.

## 1. What “indefinite” must mean

The useful mathematical quantifier is **for every finite prefix length n**,
without a bound that deteriorates merely because the device has run longer.
It does not mean executing an infinite number of operations in a finite time.

There are separate requirements:

1. **Arithmetic safety:** accepted transitions keep representations in range
   and do not silently overflow, wrap, invalidate an enclosure or lose chronology.
2. **Numerical fidelity:** every numerical claim has a sound error bound
   relative to its explicitly defined real-arithmetic reference.
3. **Retention:** weak use does not erase earlier certified information through
   arithmetic loss, normalization or a global rank threshold.
4. **Usefulness:** on a stated class of informative, valid continuations, the
   estimator can still refine supported targets or make qualified updates.
   A construction that eventually returns unavailable forever does not close
   this gate.
5. **Lifecycle closure:** the same contract survives event merges, queries,
   model-chart changes and any supported restart/restore operation.

Indefinite numerical operation does not promise that all parameters become
identifiable, that a physical cell never ages, or that SOC remains known under
arbitrary sensor bias. Numerical error, measurement uncertainty, model error
and absent excitation remain separate.

The reference for an arithmetic proof should initially be the real-valued
calculation on the **same represented inputs and declared parameters**.
Relating those inputs to physical current, time and voltage is an additional
measurement/model proof. Synthetic truth is not an inference input.

### Input and machine assumptions are part of the theorem

Nominal 35 Hz is not a lower bound on every actual interval. The current API
allows zero and arbitrarily small positive intervals. A proof may explicitly
handle those cases, or declare a justified acquisition contract; it must not
silently replace actual intervals by 1/35 s.

Needed declarations include input magnitude and resolution, zero-interval
semantics, the behavior at out-of-domain observations, integer widths, rounding
mode, subnormal handling, arithmetic reassociation, fused operations, and bounds
for exp, expm1, log, tanh, hypot and sqrt as used by the implementation.

A finite ADC code range is compatible with a deterministic range proof.
The benchmark's ideal Gaussian noise distribution has no hard finite support.
Choosing a bounded-error measurement model for a new estimator would therefore
be a statistical-model decision, not an innocuous arithmetic optimization.

## 2. What the current code carries through time

| State or operation | Current behavior | Lifetime obligation |
| --- | --- | --- |
| RC and hysteresis states | Dissipative real recurrences, evaluated in ordinary double/libm | Prove local defects and their all-time composition; preserve exact freeze cases |
| State sensitivities and derivative envelopes | Coupled recurrences; some homogeneous entering-state effects decay | Prove the augmented recurrence, including cross-coupled derivatives and underflow effects |
| Net charge and SOC | Repeated floating-point integration; no contraction | Exact represented-input accumulation or another proved, non-growing error construction |
| Elapsed time | Positive floating-point sum from initialization | Remove unnecessary lifetime magnitude or give a proved bounded-time representation |
| Positive/negative throughput | Separate nondecreasing sums used by remainder bounds | Bound needed functions without losing enclosure when counters/sums lose resolution |
| Historical QR factor | Every event merges into one growing factor | Compose update errors and preserve weak directions after arbitrary repetition |
| Residual objective and normal matrix | Squared factor terms and sums/products | Bound query error, cancellation and range as well as ingestion error |
| Curvature RSS coefficients | Repeated hypot of positive per-observation bounds | Prove a true upper enclosure; nearest rounding can absorb positive additions |
| Rank/precision assessment | Eigenvalues screened relative to the largest eigenvalue | Distinguish numerically unresolved directions from truly absent historical information |
| Counts and source ordering | uint64 counters, explicit terminal-value rejection | A bounded rollover protocol and delivery assumptions if literal indefinite operation is required |
| Chart changes and restore | No such operation is currently qualified | Preserve physical state, evidence identity, uncertainty and the numerical error ledger |

Relevant implementation paths are
[model propagation](../src/scm_model.c),
[evidence ingestion/query](../src/scm_evidence.c),
[remainder propagation](../src/scm_remainder.c), and
[assessment](../src/scm_assess.c).

Checking isfinite is useful but insufficient: a finite value may stop changing
when a new increment is smaller than its representable spacing.

The current overflow checks are a legitimate fail-closed property. They prove
neither indefinite availability nor that all preceding finite arithmetic
remains accurate.

### A separate issue: relative rank screening

Consider the exact information matrix diag(1,N). The first direction retains
information 1 forever. With a global relative eigenvalue cutoff r*N and the
current strict greater-than test, that direction is classified below the
cutoff once N >= 1/r. For the default r=1e-10, this occurs at N >= 1e10.

This example needs no floating-point error. It is a qualification-policy
effect: increasingly repeated evidence in one direction can make earlier
evidence in another direction disappear from the reported retained subspace.
The factor itself has not necessarily lost that information. The status is
conservative, but it does not by itself satisfy the intended retention
requirement. A lifetime design needs error-aware, target-aware qualification.

### A separate issue: growth of the existing analytic bound

Even in exact arithmetic, the present remainder design adds the global
initial-SOC curvature bound 4 at every observation. With coordinate scale
s_z and voltage sigma, its coefficient after N samples is

\[
C_{zz}(N)=\frac{4s_z^2}{\sigma}\sqrt N.
\]

For a fixed nonzero scaled SOC displacement delta_z, the prediction bound
satisfies E >= C_zz(N)*delta_z^2/2, and the likelihood bound includes
E^2/2. That term grows proportionally to N even during quiet use.

This proves that the existing sufficient check cannot qualify a fixed
original-chart region containing a nonzero initial-SOC displacement forever.
It does not prove the actual nonlinear
error grows at that rate, or that every different local-query design fails.
This analytic growth must be handled separately from machine-rounding error.

## 3. Small executable falsification experiment

The source and plan were committed at
0eff2339eefdbed6d8ff373a3c5b53122e357048 before the primary run. The runner
checked that every executed source and the plan matched that commit, and that
production numerical sources matched the frozen B002 base.

The host used GCC 13.3.0, binary64, round-to-nearest, FLT_EVAL_METHOD=0, disabled
fast-math and disabled FP contraction. All seven expected mechanisms were
reproduced in approximately 0.010 seconds of witness execution.

| Witness | Exact expectation or intended increment | Observed behavior |
| --- | --- | --- |
| Sum from 2^53 | 4,096 additions of 1 add 4,096 | Stored double unchanged |
| Bounded zero-net scalar cycle | Starting at 1/2, add then subtract 2^-54; exact result is 1/2 | Result is 1/2 - 2^-54 |
| RSS norm from 2^27 | 4,096 unit rows add 4,096 to the squared norm | Repeated host hypot leaves the norm unchanged |
| Production QR merge | Constructed diagonal 2^27, then 4,096 unit event rows | Diagonal unchanged while sample count increases by 4,096 |
| Production curvature RSS | Constructed coefficient 2^36, then 4,096 positive bounds of about 40 | Coefficient unchanged |
| Production elapsed time | Constructed elapsed time 2^48 seconds plus actual dt=1/35 | Returns success with elapsed time unchanged |
| Production terminal counters | Push at UINT64_MAX | Both APIs return their overflow error and preserve the bank byte-for-byte |

The scalar zero-net cycle exhibits one rounding bias. Repetition of that exact
cycle stalls at the neighboring value; it is **not** evidence of linear
asymptotic drift.

The QR and curvature cases expose local transition mechanisms in unchanged
production functions. They are constructed boundary states, not reachable-history
proofs. The counter test confirms existing atomic rejection. None of these
tests estimates when a real cell or a particular deployment would encounter a
problem.

A finite stress test can falsify a proposed theorem or verify implementation
details. It cannot prove a statement quantified over all prefix lengths.

## 4. Two finite-state obstructions

These are mathematical results about a stated model of computation, not
empirical claims about this particular host.

### 4.1 Fixed absolute error in all-history likelihood contrast

Assume:

- A deterministic implementation has a finite complete state set S.
- It accepts arbitrarily many repetitions of an admissible observation w.
- It answers a fixed query comparing two fixed parameter candidates.
- The real likelihood contrast contributed by each observation is a nonzero
  constant c.
- There is no external unbounded counter, clock, exponent or archive.

Write q[n+1]=F(q[n],w). Finiteness implies q[i]=q[j] for some i<j.
With p=j-i, determinism implies q[i+kp]=q[i] for every nonnegative k.
A fixed query therefore receives the same answer at i and i+kp, while the
exact contrast changes by kp*c.

For any proposed fixed absolute tolerance epsilon, choose k with
kp*abs(c)>2*epsilon. One answer cannot be within epsilon of both exact values,
by the triangle inequality. This disproves the proposed uniform absolute
contrast guarantee.

The battery model contains this simple subproblem: zero current, zero entering
polarization/hysteresis voltage, constant SOC, positive actual sample intervals
and repeated constant voltage. Two SOC candidates can have distinct constant
OCV predictions and hence a nonzero likelihood contrast per sample.

Subtracting a parameter-independent residual constant does not evade the
argument: it concerns a **contrast**. Wider floating-point numbers, compensated
sums, finite exponent metadata and a larger finite counter do not remove the
finite-state premise. An externally supplied exact unbounded count would change
that premise and must be included in the system's resources.

This theorem does not say that useful indefinite estimation is impossible.
It says that this particular all-history numerical contract is impossible
under these assumptions. Returning unavailable avoids a false answer, but is
not by itself indefinite useful learning.

### 4.2 Normalization alone does not solve all-history retention

There is also a bounded-output obstruction. Suppose a deterministic finite-state
machine must approximate the empirical mean of every arbitrarily long binary
stream with a fixed absolute error epsilon<1/2, with no unbounded external
time/count.

Repeated ones eventually yield the same state after i>=1 ones and after
i+kp ones for arbitrarily large k. Choose a positive delta with
1-2*delta>2*epsilon. First choose m so that i/(i+m)<delta.
Then choose k so that (i+kp)/(i+kp+m)>1-delta.

Append the same m zeros to both prefixes. Both machines finish in the same
state, but their exact means differ by more than 1-2*delta>2*epsilon.
One output cannot satisfy both error requirements.

Thus even a bounded empirical mean is not automatically an indefinitely
accurate all-history quantity in fixed finite state for arbitrary streams.
A precision floor, normalization or information saturation needs additional
semantics or assumptions; those words alone are not a proof.

This obstruction is about equivalence to arbitrary all-history objectives.
It does not forbid exact bounded physical-state recurrences, finite-horizon
objectives, conservative finite-resolution constraints under a declared
measurement model, or useful operation under an explicitly restricted
stream class.

### Consequence for the existing 0.1 NLL policy

B002's 0.1 NLL threshold remains its frozen finite-experiment analytic
trial criterion. It must not be silently relaxed or reinterpreted as a
lifetime numerical guarantee.

A fixed per-observation voltage error also does not imply a fixed total
likelihood error: residual cross terms and squared errors accumulate.
Normalizing L by n would change a total-error threshold epsilon into
epsilon/n, and confidence scaling still depends on the original weight.

A proposed future contract must specify which query is guaranteed, over what
candidate domain, and with what resolution. The impossibility theorem does
not automatically apply to every restricted local query; each proposed
restriction needs its own proof.

## 5. Constructive lemma: dissipative states can have uniform error bounds

Consider the exact scalar recurrence

\[
x_{k+1}=a_k x_k+(1-a_k)b_k,\qquad 0\leq a_k\leq1.
\]

For an RC state, a_k=exp(-dt_k/tau) and b_k is the forcing current or R*I.
For normalized hysteresis, a_k=exp(-gamma_sign*abs(I_k)*dt_k/3600) and
b_k is the current sign during an active update.

Assume the computed update, evaluated on the computed state, satisfies

\[
\widehat x_{k+1}
 =a_k\widehat x_k+(1-a_k)b_k+d_k,
\qquad |d_k|\leq \eta(1-a_k).
\]

All coefficient/input representation effects relevant to the chosen reference
must be included in d_k. In particular, an a_k=1 update must have zero defect.

Let \(e_k=\widehat{x}_k-x_k\) and \(P_n=\prod_{k=0}^{n-1}a_k\).
Unrolling gives

\[
|e_n|
\leq P_n|e_0|
+\eta\sum_{j=0}^{n-1}(1-a_j)
                  \prod_{\ell=j+1}^{n-1}a_\ell.
\]

The sum telescopes, because each summand equals the product starting at j+1
minus the product starting at j. Hence

\[
\boxed{|e_n|\leq P_n|e_0|+(1-P_n)\eta
                 \leq\max(|e_0|,\eta)\quad\text{for every finite }n.}
\]

No lower bound on contraction per observation and no requirement that P_n
tends to zero is needed. If |x_0|<=B and |b_k|<=B, the exact state remains
in [-B,B] by convexity, giving a corresponding computed-state range bound.

This is the kind of induction that establishes a genuine lifetime result.
It is **conditional**: the current C/libm expressions have not been shown to
satisfy the damping-scaled local-defect hypothesis. Ordinary roundoff can
contain a component independent of 1-a_k. That fact cannot be hidden inside
an asserted constant eta when a_k can approach 1 arbitrarily closely.

### Alternative with stronger acquisition assumptions

If instead |d_k|<=eta and a_k<=rho<1, then

\[
|e_n|
\leq \rho^n|e_0|+
       \eta\frac{1-\rho^n}{1-\rho}
\leq\max\left(|e_0|,\frac{\eta}{1-\rho}\right).
\]

A justified minimum positive interval and maximum tau could supply such a rho
for RC propagation. A finite-window contraction theorem is another option.
Nominal sampling rate alone does not establish either assumption, and a long
zero-current hysteresis interval supplies no active damping. Exact identity
updates must remain identities rather than accumulating an invented error
on every inactive observation.

The derivative/envelope system also needs proof. Scalar contraction of the
physical state does not automatically prove stability of all coupled
sensitivities or of historical evidence about initial states.

## 6. Constructive lemma: exact bounded charge accumulation

Charge integration has coefficient one:

\[
q_{k+1}=q_k+\Delta q_k.
\]

With ordinary additive defects, its general bound is

\[
|e_n|\leq |e_0|+\sum_{k<n}|d_k|.
\]

There is no dissipative term to remove old errors. A bounded true SOC path
does not by itself establish a small time-uniform numerical error.

One possible exact arithmetic construction starts from the acquisition codes:

\[
I_k=c_I m_k,\qquad dt_k=c_t t_k,\qquad
P_n=\sum_{k<n}m_k t_k,
\]

where m_k and t_k are integers.

Assume each product fits a proved exact product width, every accepted prefix
P_n lies in a declared representable interval [L,U], and range checks avoid
performing an overflowing signed operation. Starting from exact P_0, integer
multiplication and addition preserve exact P_n by induction for every accepted
prefix, independently of n.

Charge is obtained at query time as

\[
q_n=\frac{c_I c_t}{3600}P_n.
\]

Because P_n is bounded, conversion error can be bounded independently of
runtime. SOC evaluation also has a bounded arithmetic error if Q is bounded
away from zero and its parameter/reference semantics are fixed.

This is a proof opportunity, not an implemented conversion of the current
arbitrary-double API. ADC and clock quantization, calibration error, current
bias, changes to capacity and state/chart transitions remain distinct issues.
The prefix-range assumption must follow from the physical/model contract or
be checked with an honest out-of-domain state. It cannot be assumed merely
because the output is called SOC.

The result also does not apply to positive-only throughput or total elapsed
time; those quantities have no bounded-prefix premise.

## 7. Composing transitions without restarting the error budget

Suppose a model-chart change transports an already uncertain representation.
A general error recurrence has the form

\[
E_{m+1}\leq L_m E_m+\delta_m.
\]

If L_m=1 and each change introduces a fixed positive delta, the resulting
bound grows with the number of changes. Calling each transition individually
accurate, or assigning it a fresh budget, does not prove lifetime stability.

A satisfactory construction needs an exact transformation, a closed
contraction/error invariant, a genuinely summable total defect, or another
proved mechanism. Merely re-centering the old polynomial does not reconstruct
historical nonlinear Jacobians or the physical state associated with changed
parameters.

A useful enclosure formulation is:

\[
F(\Gamma(\widehat s),u)
   \subseteq \Gamma(\widehat F(\widehat s,u)),
\]

where Gamma decodes the machine state into a sound set of exact reference
states. Proving this inclusion for every permitted transition, together with
initial containment, proves containment for all finite execution lengths by
induction.

Containment alone is insufficient if the set expands to the entire domain and
stays there. The proof must also establish the declared useful resolution on
an explicit informative stream class. Neither arbitrary parameter learning
nor recovery within one fixed number of samples after every possible history
can be assumed.

Every event merge, query, chart transport and supported restore must preserve
the same invariant. Earlier observations remain source-disjoint and counted
once. Uncertainty cannot be reset as if the compressed evidence had become a
new independent prior.

## 8. What common numerical fixes do and do not establish

| Technique | Useful role | Remaining proof obligation |
| --- | --- | --- |
| Compensated summation | Reduces some finite-run accumulation errors | Range, higher-order error, cancellation, counters and all-history semantics |
| Wider floating point | Extends dynamic range and resolution | Still finite state; does not establish an all-n bound |
| Fixed point | Can make a specifically bounded integer accumulator exact | Product/range proof, quantization, recurrence errors and limit cycles |
| Square-root/QR factors | Avoid some weaknesses of direct normal-matrix updates | Composition of infinitely many finite update errors and preservation of weak directions |
| Power-of-two rescaling | Controls representable magnitude | Significand information, exponent metadata and correct confidence scaling |
| Normalization | Keeps some displayed quantities bounded | Correct objective weighting; arbitrary all-history mean obstruction still applies |
| Rebasing/checkpointing | Can simplify coordinates or recovery | Exact or bounded transport of state, evidence and accumulated numerical error |
| Endurance tests | Find defects and check code against the contract | They cannot replace an induction proof |

Classic summation error analyses explicitly depend on problem length and
conditioning; they are not an indefinite-runtime result. See
[Higham, The Accuracy of Floating Point Summation (1993)](https://nhigham.com/wp-content/uploads/2023/10/high93s.pdf).
Floating-point behavior also depends on rounding, subnormal treatment and
compiler evaluation semantics; see
[Goldberg's floating-point arithmetic tutorial](https://docs.oracle.com/cd/E19957-01/806-3568/ncg_goldberg.html).

## 9. Revised proof-first roadmap

### S0 — State the lifetime contract

Declare represented-input ranges/resolution, reference semantics, arithmetic
environment, permitted lifecycle operations, numerical metrics and useful
per-target resolution. Resolve the meaning of historical evidence at finite
precision without silently introducing forgetting, capping or a different
noise model.

**Current status:** the requirement and obstructions are recorded; the final
evidence semantics and numerical budgets are open.

### S1 — Close physical-state and charge invariants

Select concrete arithmetic for propagation and charge, prove local defects
and range bounds, and compose them into invariants independent of runtime.
Handle zero/weak input explicitly. Include derivative/envelope state and
functions of elapsed time/throughput actually needed by the estimator.

**Current status:** conditional lemmas are proved on paper; executable
constants and a selected implementation are open.

### S2 — Close evidence, query and transition invariants

Specify what the bounded evidence represents indefinitely. Prove composition,
query margins, old weak-direction retention, counter rollover and any
chart/state transport under the same contract. A proposed signed-curvature
summary belongs here and must include these lifetime obligations from its
design, not after an implementation campaign.

**Current status:** open. The signed-curvature idea remains a candidate; it is
not abandoned or promoted without this proof work.

### S3 — Connect proof to C and target arithmetic

Bind statements to exact source, compiler options, integer behavior, floating
format, libm enclosures and lifecycle implementation. A tool such as
[Gappa](https://gappa.gitlabpages.inria.fr/gappa/index.html) can help prove local
floating/fixed-point range and error properties; loop induction and evidence
semantics still require the corresponding mathematical argument. No such
machine-checked certificate is claimed in this checkpoint.

### S4 — Falsify and demonstrate useful operation

Run small adversarial cases at range/precision boundaries and chronological
informative/quiet/renewed-excitation cases. These verify correspondence and
usefulness after the invariant is stated. Retain failures and original
tolerances. Longer testing is corroboration, never the lifetime proof.

### S5 — Finish resource and physical validation

Measure complete Cortex-M23 memory, stack, arithmetic, cycles, flash and power
for the selected design. Measured OCV, sensing imperfections, correlated noise,
mismatch, drift and coverage remain separate scientific validation.
The existing approximately 10 KiB target is not met by the host implementation.

## 10. What is established and what remains unresolved

Established at this checkpoint:

- The finite-state fixed-absolute likelihood-contrast obstruction.
- The finite-state arbitrary-stream empirical-mean obstruction.
- The conditional damping-scaled defect theorem.
- The conditional exact bounded quantized-charge theorem.
- Seven reproduced finite-precision/counter mechanisms in a small frozen-source
  experiment.
- A proof gate that distinguishes safety, fidelity, retention and usefulness.

Still unresolved:

- A selected indefinite evidence semantics compatible with the project goal.
- Concrete useful numerical budgets and acquisition bounds.
- Verified arithmetic defects for the executed model/derivative/library paths.
- Indefinite evidence/query/chart-transition stability.
- Indefinite source-order/restore protocol.
- A full-estimator, machine-checked proof and Cortex-M23 qualification.

Earlier evidence remains authoritative: B001's corrected 72/72 checks,
B002's original 654/672 checks with 18 retained failures, the 0.1 NLL analytic
trial budget, and the existing memory accounting are unchanged.

Reproduce only the new small witnesses with a new output path:

    python3 tools/run_stability_witnesses.py \
      --output experiments/indefinite_stability_001/NEW_RECEIPT.json

An all-reproduced result confirms the listed failure mechanisms. It does
not certify indefinite stability.

