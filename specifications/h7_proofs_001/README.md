# First H7 proof tranche

This package establishes a conditional mathematical foundation for optimizing
the continuous H7 likelihood/state-transport reference. It does not certify
H7's physical accuracy, global posterior coverage, arbitrary exception recovery
or ten-year numerical behavior.

- [Ownership proof](OWNERSHIP.md): exact feature-model compaction, single-prior
  tangent semantics, consumed versus published boundaries, and the precise
  failure contract. An injected field-QR failure refutes universal rollback.
- [Error-budget proofs](ERROR_BUDGET.md): centered likelihood error, posterior
  total-variation bound, state-query probability transfer, full joint precision
  and center bounds, plus identifiability and persistent-bias limits.
- [Numerical certificates](NUMERICS.md): exact rational certificates for five
  native QR witnesses and a reduced-precision counterexample.
- [Claim ledger](claims.json): proof status, evidence, assumptions and remaining
  obligations. [Evidence receipt](../../provenance/h7_proofs_001/receipt.json).

The central new result is a way to turn a declared uncertainty requirement into
a compression obligation. If the change in negative log density varies by at
most omega across the same supported parameter domain, the normalized
posteriors differ in total variation by at most tanh(omega/4). Parameter-independent
cost shifts cancel from that statement. Endpoint transport error and mass outside
the domain still need separate bounds. This improves on an arbitrary absolute
NLL threshold without asserting that H7 already meets the required bound.

The code checks eight polynomial identities exactly, explores 969 abstract
ownership states, and computes joint numerical certificates using exact rational
arithmetic on the recorded binary arrays. These are executable checks and
finite certificates, not a Lean/Coq/SMT proof of the C/Python implementation.
The universal mathematical statements are accompanied by explicit proofs;
source correspondence remains partial and openly records a failure witness.

The owner's capacity guidance is now recorded as +/-3sigma=2.6–3.6 mAh about a
nominal 60 mAh, hence sigma=0.8667–1.2000 mAh. That does not specify Gaussian
tails, hard support, the estimator's prior or an aging range.

No estimator source, original run, default or mainline was changed. The next
proof obligation is transactional field flushing/quarantine, followed by
uniform H7 feature/derivative/transport bounds on an admitted domain and horizon.
Those bounds are the missing premises needed to use the new probability-mass
result as an H7 certification. Numerical and Monte Carlo validation remain
complementary rather than interchangeable.
