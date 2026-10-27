# Compact nonlinear history 001

A live ADC supplies new samples; this design avoids retaining them by carrying
a bounded likelihood approximation. Later samples can change the estimate, so
the retained information must support those changes. This finite experiment
tests one bounded approximation to that history.

## What the bank retains

For an immutable entering anchor `a`, represent each whitened residual by its
second-order Taylor polynomial:

`p_k(d) = r_k(a) + J_k(a)d + 0.5 d' H_k(a)d`.

The original 16-dimensional physical chart has 20 potentially nonzero Hessian
entries. Sixteen scaled linear monomials, those twenty quadratic monomials and
one constant make a 37-element feature vector. An incremental upper QR factor
stores the squared sum of these residual polynomials. Its packed 703 doubles
occupy 5,624 bytes, independent of stream duration. All cross-coordinate and
signed residual/curvature correlations of the represented polynomial survive.
The same factor yields the old affine approximation by zeroing its quadratic
features. It therefore supplies an inexpensive internal control without a second
historical factor.

This is a quartic likelihood approximation, not an exact sufficient statistic for
the nonlinear model. Higher-order historical information is irretrievably absent.
Changing the estimate does not move the approximation origin or renew that
information. The carried model jet stays at the fixed origin. SOC is transported
exactly using charge and capacity; RC/h endpoint values away from that origin
remain explicitly approximate.

## Two questions in one finite comparison

The public-origin arm starts from the compiled public mean and uses no saved fit
to initialize its estimate or accept its proposals. The autonomous-origin arm
starts from the preserved generation-7 entering anchor. It tests local maintenance
after a retrospective bootstrap. A success in that arm cannot establish public
cold start.

Both banks ingest the same ordered source once through 294,000 records, preserving
actual intervals. At records 252,000 and 294,000 each performs at most sixteen
pure-C refinement rounds using its sketch and exactly one common prior. The
search uses a full joint Gauss-Newton metric plus kernel precision, unmodified
Cholesky, an explicit one-public-SD step cap, and eight fixed fractions. Finite
work exhaustion remains unresolved; acceptance never consults an exact-history
evaluation.

## Independent reference and interpretation

Forty-two fixed joint diagnostic nodes are constructed before execution from the
public mean, saved anchor and saved full Gram matrix. The original model advances
those nodes alongside the live-stream emulation. At most two later audit children
evaluate the compactly chosen candidates. These model states and observation
reads belong solely to host qualification. They are never candidate memory,
candidate history or candidate feedback.

We compare likelihood differences and the oscillation of approximation error
over the available declared nodes, retain unavailable nodes explicitly, and show
the exact costs reached by compact refinement. The prior is identical on each
side, so it cancels from approximation-error contrasts. Finite-set fidelity is
useful evidence; it does not prove continuous-domain posterior accuracy or SOC/
capacity coverage. The diagnostic directions are not reported as intervals.

## Memory and failure ownership

One operational bank replaces the earlier learner. Its factor, origin, estimate,
source cursor, charge extrema, derivative state and serialized query/ingestion
workspace are all counted. The plan also reserves an ADC queue, a streaming
checkpoint codec, own stack and runtime/interrupt/caller space. Actual measured
layout and compiler stack evidence will determine whether the host planning
ledger fits 10,240 bytes. Cortex-M23 code, software floating point, worst-case
interrupt latency, runtime stack and checkpoint integration remain qualification
work; a small host `sizeof` is not an M3 pass.

Prevalidation failures preserve the bank. A numerical failure during an in-place
QR update invalidates the bank permanently, because maintaining an uncounted
second factor for rollback would violate the resource contract. No invalidated
partial bank can produce an estimate.

The supervisor preserves output using the independently qualified capture
transaction. Every child is reserved before launch; raw bytes, a distinct copy,
streaming hash and parent-pinned commit must agree. Loss of the original is still
a failed capture. No failure triggers a silent retry or expanded experiment.

The exact input identities, fixed work caps, qualification and decision boundaries
are in `plans/compact_nonlinear_history_001.json`. Existing failed experiments and
the seven accepted autonomous-anchor generations remain unchanged.
