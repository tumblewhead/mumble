# Compact RC value-and-sensitivity comparison

Base f1500ba, branch experiment/conditional-architecture-001. The preceding H
completion study showed an RC-only fidelity benefit but a factor exceeding the
10 KiB target, with remaining joint-uncertainty defects. This experiment tests
whether explicit physical sensitivities improve the accuracy/storage tradeoff.
No production model, campaign default, public support or prior is changed.

## Candidates and controls

P1 derives exact first/second log-tau response recurrences and two projections:

- Taylor2_H2: three response coefficients, exact central value/first/second slope;
  factor 4760 B, same as existing R2_H2. It may extrapolate poorly within the box.
- Hermite3_H2: four coefficients from values/slopes at +/-1/sqrt(2); factor 6560 B.
- R3_H2: ordinary four-node cubic value interpolation, matched 6560 B factor.
- R2_H2, R5_H2 and R5_H7 are unchanged low/high-fidelity controls.

H2 remains unchanged to isolate RC representation. Two new study-only C builds
carry derivative states and preserve the existing H recurrence/measurement rows;
existing production C stays untouched. The joint field always uses one QR factor.
A lower numeric subtotal is 5168 B (Taylor2) or 7016 B (Hermite3/R3); full target
memory and timing remain open.

## Qualification sequence

1. Independently review P1. Check polynomial reproduction, anchor values/slopes,
   native recurrence and derivative identities, feature/transport finite differences,
   zero/irregular intervals, constant current, joint QR and failure atomicity.
2. Repeat the frozen rest/multiscale/embedded one-hour prefix (126000 samples),
   all 51 public queries plus the domain-exit witness. Use the same public profile,
   physical support, observation hashes, source chronology and public prior once.
   A pilot at 21008 records is allowed before this matched run.
3. Reuse the previous two public starts, 60-round local GN solver, and common
   log-shape box. Keep every stop/status, choose lowest-cost converged attempt,
   and leave unavailable direct comparisons unresolved. No hidden truth scoring.
4. Compare direct costs/gradients, precision and transport at public queries and
   fitted anchors; retain Q and endpoint SOC centre AND width readouts. Preserve
   all joint covariance in sampled rest60 and 120mA10s/rest30 voltage forecasts.
   Widths are local GN quantities, not physical coverage or identifiability.
5. Evaluate every regression and byte count. Hermite must be compared with equal-
   storage ordinary cubic, not just quadratic. No central identity, lower exp count
   or mean improvement automatically selects a winner. Independently review code,
   results and interpretation. Any adaptation gets a new recorded run and rationale.

Original results, derivatives, physical states and source hashes remain preserved.
Reference fitting can hold one bounded desktop prefix; raw observations need not
be stored on disk. This study supplies no lifetime error envelope, characterized
aging law, brownout authorization or production promotion. Candidate sensitivities
are response features, not extra observations or pseudomeasurements.
