# Fixed-prefix joint likelihood-shape diagnostic

## Status

The C commit-only capture, original-recurrence reference backend and bounded
supervisor are implemented and qualified on fabricated inputs. The final suite
passed 704 C assertions, 80 Decimal checks, 11 negative/preservation checks and
four supervisor checks. The numerical geometry/analyzer retains its earlier
21 passing tests. The actual battery-data comparison has **not yet run**.

Both registered inputs have been restored from existing lossless repository
archives and match their exact byte counts and SHA256 values. The earlier
missing-input finding applied to the uncompressed path and missed the tracked
chunked archive. No source was regenerated. See [restoration](input_restoration001.json),
[backend contract](backend_contract.json), [source review](backend_review.json),
and [qualification](qualification/backend_development003/receipt.json).
The review was performed by the same assistant; it is not independent review.

The original failed development attempt is retained. It compared unused ADC
padding bytes; the checkpoint now serializes those bytes as zero, and equality
checks compare canonical input fields. Exact original source versions were
recovered against their recorded hashes in `qualification/recovered_sources001`.

## What repository inspection established

The current trace writer saves original entering parameters, current endpoints,
scalar costs and counters. It does not save the 703-entry factor, transported
boundary jet, or other complete bank state. Scalar traces cannot reconstruct
joint shape by themselves. The source's `re_refine` changes the estimate,
workspace, result and work counters; `re_commit` constructs the new represented
history from the preceding bank, chosen estimate and current sixteen records.
This supports a **commit-only reconstruction proposal**, not a claim that such a
reconstruction has already been qualified or executed.

The original observation file is referenced by a 16,128,000-byte identity and
SHA256 in the source manifest. It was absent as an uncompressed file at the inspected revision, but its exact
bytes are retained in the tracked `implementation/evidence/primary.tar.xz.part-*` archive. The first two-hour prefix occupies 8,064,000 bytes.
No substitute stream, source regeneration or reoptimization is authorized by
this design. The original trace is distributed through the existing verified
transport/restoration path. Its uncompressed identity is also fixed in the plan.

## Selected experiment

Use committed index 252,000, the first previously scheduled reference checkpoint,
not a prefix selected for favorable truth error. Restore the represented bank
from the public start using original decoded inputs and the saved, accepted
anchor at each block. Call `re_commit`, never `re_refine` or `re_process`. This is
an external forensic reconstruction, not a cold-start estimator demonstration.
Check all 15,751 original saved snapshots through this prefix. The backend must
first demonstrate bank equivalence on fabricated online/reconstruction cases.

Require exact binary64 parity for the recorded likelihood, original prior,
total cost, endpoint quantities and elapsed time. Counter values and search-stop
labels legitimately differ because no optimization is repeated. Do not invent
old optimization counts. Any parity failure stops the comparison; do not widen a
tolerance after seeing a mismatch. Save a pointer-free, hash-bound bank/input/
calibration checkpoint and explicit host ABI metadata. Never dump the live
auxiliary union, which can contain pointers. This is not a firmware checkpoint.

At the reconstructed anchor, use the existing full-dimensional Gauss-Newton plus
prior-kernel precision metric **only to choose test locations**. It is not the
exact mixture Hessian and is not certified posterior covariance. Scale with the
public coordinate standard deviations and whiten without jitter or eigenvalue
clipping. Preserve every nuisance coordinate.

The directions comprise 16 basis vectors and all 120 normalized pair sums. Test
both signs at two radii, plus the anchor: `1 + 2 * 2 * (16 + 120) = 545` nodes.
This identifies every entry of a symmetric second-difference matrix, rather than
only sixteen diagonal curvatures. The two radii expose finite-scale variation;
they do not prove differentiability, stationarity or asymptotic convergence.

Start with radii 1 and 1/2 in metric coordinates. A fixed, global support-only
halving schedule may use at most sixteen halvings, considering only the original
entering box and charge-extrema SOC constraints. This occurs before any reference
comparison. No per-node clipping or later adaptive shrinkage is allowed. An
anchor on a limiting boundary may have no supported symmetric stencil; that is
unresolved, not permission to erase the boundary. The approximate endpoint and
original recurrence support checks remain separate evaluation gates.

## What is compared

For represented and original-recurrence negative log likelihoods, compare

```
e(x) = [L_rep(x) - L_rep(anchor)] - [L_ref(x) - L_ref(anchor)].
```

The same original supported prior belongs to both objectives and cancels from
this discrepancy. No posterior is added as independent evidence, no coordinate
Jacobian is introduced just for choosing nodes, and no nuisance parameter is
fixed to truth. A large common scalar offset disappears, as it should.

The registered engineering budget is 0.1 NLL for the **oscillation** of `e` over
the tested set, including the anchor. This bounds computed pairwise likelihood-
ratio distortion on those nodes by `exp(0.1)`, after the declared arithmetic
allowances. It is not a voltage threshold, covariance inflation factor, posterior
normalization bound, or coverage criterion. It does not extend between nodes.

The analyzer reports odd directional contrasts and the complete mixed symmetric
second-difference matrices at both scales. These separate a displaced local
slope from curvature distortion. They are finite differences of the computed
likelihood, not certified exact Hessians. The supplied cost allowances and the
analyzer's rounding guard do not certify recurrence/libm or physical-model error.

A resolved witness above budget selects `repair_computed_shape_witness`. A
complete stencil with its allowance-inclusive oscillation below budget selects
`keep_on_tested_points_only`. Missing nodes, unresolved arithmetic, failed source
or state identity, and other inconclusive cases remain `unresolved`. A partial
stencil can expose a repair witness but can never earn a keep decision.

## Implemented commands

Requires Python and NumPy; the tested environment is in the qualification receipt.
Run from this directory:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -m unittest -v test_shape
```

The backend/supervisor supplies the capture; geometry can then be inspected with:

```sh
python shape.py design --capture capture.json --snapshot bank.bin --output nodes.json
```

After the separately closed reference evaluation supplies all 545 rows, including
explicit unavailable rows:

```sh
python shape.py analyze --design nodes.json --evaluations evaluations.json --output analysis.json
```

Both commands refuse to overwrite an existing output. `design` checks the bank
file identity and reconstruction receipt, not just a point vector. The backend
must supply the contracts in `plan.json`; these commands do not create a bank,
run the estimator, invoke an optimizer, or evaluate the battery model.

## Qualification and next action

Development attempt 001 failed five fabricated tests because the test fixture
scaled symmetric matrix entries in different operation orders. Its receipt and
stderr are retained. Using an outer-product scaling matrix fixed that fixture
and kept the whitening matrix exactly symmetric without covariance repair.
Development attempt 002 passed all 21 tests. These are software development test
iterations, not scientific-run retries. No canonical observations or truth were
read. No independent-agent review is claimed.

Next publish and verify the qualified backend source, then execute the one finite
plan using `runner.py --qualification qualification/backend_development003/receipt.json
--publication source_publication.json`. The runner reserves `attempt001` durably
and refuses any scientific retry. The original GCC13 producer and this GCC16
build must still pass every exact snapshot parity gate.
Do not rerun the four-hour estimator or its three closed audits. Do not propose
intervals or M3 promotion from this numerical-module qualification.

## Subsequent trajectory objective

After this development is stable, the requested next capability is a configurable
cell/load/noise/duration trajectory runner for longer-term behavior across those
variations. The current diagnostic remains a finite prerequisite. No longer
campaign has started, and this step will not establish coverage or M23 readiness.
