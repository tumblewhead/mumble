# Individually reviewed deployment and optimization proofs

This package completes the mathematical statements for **D0–D7 and K0–K7** as
standalone conditional proofs. Each final packet has an accepting review from
its own fresh-context subagent. Six packets were strengthened or corrected after
initial review and sent to new reviewers. The 22 individual proof reports and
superseded texts are retained, including four initial `revise` verdicts.

Acceptance means that a reviewer found the mathematical derivation sound under
its explicit hypotheses. It does not mean H7 satisfies those hypotheses or that
the device is deployable. These are handwritten proofs with AI peer review and
supporting finite checks, not Lean/Coq verification, human expert certification,
or a proof of the complete C/Python program. Fresh contexts reduce shared history
bias but do not make reviewers immune to correlated model errors.

## Proof index

| ID | Completed statement |
|---|---|
| [D0](proofs/D0.md) | Limits on perfect trust classification under overlapping observation laws |
| [D1](proofs/D1.md) | Conservative reachability, measurement and compression containment |
| [D2](proofs/D2.md) | Query-specific lifetime authorization, relative Q and load trajectories |
| [D3](proofs/D3.md) | Sequential/epoch/restart risk and the supermartingale construction |
| [D4](proofs/D4.md) | Useful enclosure width, availability and complete publication deadlines |
| [D5](proofs/D5.md) | Aging propagation and the precise limits of monotonicity alone |
| [D6](proofs/D6.md) | Numerical accumulation and outward arithmetic for the bound engine |
| [D7](proofs/D7.md) | Transactional containment, persistent quarantine and recovery composition |
| [K0](proofs/K0.md) | Enabled, terminating observable refinement and qualified guard specialization |
| [K1](proofs/K1.md) | Propagated perturbations, decision margins and reference-gradient bounds |
| [K2](proofs/K2.md) | Cumulative likelihood, full joint precision and query error |
| [K3](proofs/K3.md) | Graph execution, cache equality/congruence and approximate-key error |
| [K4](proofs/K4.md) | Storage reuse across all live readers, including rollback |
| [K5](proofs/K5.md) | Counted costs, actual service guarantees, cache costs and memory layout |
| [K6](proofs/K6.md) | Fixed-row grouping and timed closed-loop equivalence |
| [K7](proofs/K7.md) | Feature/parameter coordinates, Gaussian elimination and omitted-mode error |

## Review method and outcomes

The author retained repository context. Every individual reviewer started with
`fork_turns="none"`, read its assigned complete proof plus required repository
instructions/current context, and did not receive the author's conversation or
other review reports. Review prompts asked for a comprehension summary, attempted
counterexamples, exact premise/conclusion checks and a verdict. Revised proofs
went to new reviewers without earlier critiques. This adapts the fresh-context
review principle of Google's [Elephant–Goldfish Model](https://github.com/google/elephant-goldfish-model);
no EGM plugin was installed or executed.

The reviews led to concrete changes:

- **K0:** require an enabled candidate step; a universal condition over no steps
  could otherwise pass while the machine deadlocks.
- **K3:** define cache equality as literal downstream value equality or a proved
  congruence. Display/numeric equality can hide observable distinctions.
- **K7:** require a diffeomorphism for the stated density Jacobian formula, and
  account for the penalty in constrained profiling.
- **D4:** include publication, scheduling and certificate validity within the
  deadline; finishing an enclosure by T was insufficient.
- **D5:** qualify the no-rate conclusion. Near a known terminal health bound,
  monotonicity alone can preserve a useful narrow interval.
- **D7:** preserve quarantine through no-change transitions until a verified
  complete valid state is established.

See [the review manifest](manifest.json), [dispositions](../../provenance/proof_review_001/dispositions.json),
and [receipt](../../provenance/proof_review_001/receipt.json). Earlier documents
remain preserved historical outlines; these reviewed packets supersede their
corresponding D/K statements where qualifications differ. Acceptance is not
retroactively assigned to other earlier proof collections.

## Continuing rule

`AGENTS.md` now requires independent peer review for **every proof and every
optimization**, iteration on findings, and re-review of substantive revisions.
A mathematical proof review and an optimization's implementation review are
different gates: an accepted lemma does not automatically accept a candidate.
Inherited unreviewed dependencies must be reviewed before relying on them for
acceptance, or their relevant statements must be supplied and reviewed in a
self-contained packet as here.

Run `python3 -B specifications/proof_review_001/verify.py` to check the complete
16-proof set, exact proof/review hashes and final accepting decisions. Its negative
checks reject missing entries, stale hashes and nonaccepting reports. This is an
artifact-consistency check, not a mathematical checker or repository-wide CI
enforcement of the policy. The coordinator also records the actual subagent tasks;
the JSON alone cannot authenticate who performed a review.

Run `python3 -B specifications/proof_review_001/check_examples.py` for the finite
counterexample checks, including noncommuting precision composition and the gaps
found during review. A passing example suite does not replace an unbounded proof.

## What remains before deployment or optimization acceptance

The next work is to instantiate the hypotheses against the actual implementation:
repair and review the field-flush transaction; implement a reviewed query/status
contract; establish physical/noise/aging and lifetime error bounds; demonstrate
useful reacquisition; and measure/prove target resource and deadline premises.
H7's 50,624-byte field factor and incomplete target port still prevent a 10 KiB
deployment claim. No code optimization, estimator behavior, original run or
production default changed in this proof review.
