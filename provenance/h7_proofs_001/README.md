# H7 proof tranche 1 receipt

The [proof package](../../specifications/h7_proofs_001/README.md) turns several
optimization goals into explicit mathematical obligations. Production source,
defaults and original campaign evidence are unchanged on `proof/h7-contracts-001`.
The source parent is `c9b68d1`; the [receipt](receipt.json) records exact identities.

The principal results are:

- Exact feature-model QR compaction and single-prior tangent semantics, with
  an ownership induction that distinguishes consumed samples from published
  estimates. Eight exact polynomial identities and 969 abstract protocol states
  support the manuscript; they are not complete program verification.
- A normalized-posterior bound: log-density error oscillation omega implies
  total variation at most tanh(omega/4). Transport error, outside-domain mass,
  local Gaussian approximation and physical model error remain separate.
- Full joint precision, query-width and center bounds that retain cross terms.
  Exact rational checks certify five finite native QR witnesses in all sixteen
  local parameter directions. No horizon-wide numerical bound is claimed.

Two stronger claims failed and were retained as evidence. Injecting a Python
field-QR failure advances the response/count but leaves the old root, refuting
universal rollback. The campaign contains that exception by marking the arm
unresolved; backend-level atomic recovery remains open. Storing a deliberately
ill-conditioned synthetic factor in binary32 loses most precision in one joint
direction. This rules out assuming that small coefficient errors guarantee
uncertainty preservation; it does not establish that H7 battery runs have that
conditioning or rule out certified mixed precision.

One checker negative test initially failed because optional Rayleigh reporting
divided by zero for a zero whitener. The checker was repaired without weakening
acceptance; malformed inputs and noninvertible whiteners are now rejected.
The final **11 targeted tests pass**. Earlier numerical artifacts and checker
versions remain local in `experiments/h7_proofs_001/qr001` through `qr003`;
`qr004` is final. Only source, specifications and small receipts are tracked.
The copied [QR receipt](qr_certificate.json) preserves rational certificates and
hashes; bulk binary arrays and the diagnostic shared library stay local.

The capacity clarification is recorded as +/-3sigma=2.6–3.6 mAh, so
sigma=0.8667–1.2000 mAh for nominal 60 mAh. It supplies neither hard support nor
a measured Gaussian law. Monte Carlo implementation remains deferred while this
proof tranche is reviewed.

Next: make field flush failure semantics explicit and verifiable, then bound
H7 feature/derivative/endpoint errors uniformly on an admitted physical domain
and horizon. The posterior theorem becomes an H7 certificate only after those
premises are discharged. Persistent model bias can eventually overwhelm a
shrinking uncertainty interval even when compaction is exact. No ten-year
accuracy, coverage, aging or M23 qualification follows from these results.
