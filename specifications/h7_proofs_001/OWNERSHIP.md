# O: evidence, transport and publication ownership

Status: exact-model induction with a finite abstract checker and targeted
implementation checks. Not a complete C/Python program verification. Reference:
`c9b68d1` source tree; the H7 implementation remains identical to its qualified
streaming revision. This strengthens P2 in the earlier assurance outline.

## O0. Object and domain

Let u_i=(dt_i,I_i,T_i,sigma_i) be the admitted measured input and y_i the voltage.
Let s_i be the response-generator state. The declared feature model defines

    (s_(i+1), a_i) = Generate(s_i,u_i,y_i),
    r_i(theta) = a_i phi(theta).

The a_i include the whitening and observed-voltage constant coefficient. They
are generated in the original sample order. This proof is about this declared
finite feature model; accuracy relative to the physical Foster model is a
separate obligation. The public prior is fixed, proper and introduced once.
Truth and test-rig settings are not part of Generate or the prior.

A semantically valid ready object has four boundaries:

- n: consumed evidence and live physical-response boundary;
- f: materialized history boundary;
- b=n-f: pending observations, not a second likelihood;
- p: last published estimate boundary, with p<=n.

The field root H represents [0,f), the pending FIFO represents [f,n), the live
state represents [0,n), and the native tangent represents [0,n) at one fixed
anchor. The root and pending FIFO jointly describe one likelihood. Native and
field roots are alternative views of that likelihood and are never multiplied
as independent evidence. A published estimate is a readout, not another factor.
At a ready public-call boundary p=n. After consuming a block but before a
successful readout, p<n is legitimate. A failed readout does not rewind n.

## O1. Exact QR compaction

For already generated rows A, orthogonal QR gives Q R=A, with Q'Q=I on the
column space (or an equivalent full orthogonal transformation with zero rows).
Consequently R'R=A'A. For every theta,

    ||R phi(theta)||^2 = phi(theta)' A'A phi(theta)
                        = sum_i r_i(theta)^2.

This includes linear terms through the constant feature. At a flush, replace
H by QR([H; A_pending]). Then

    H_new' H_new = H' H + A_pending' A_pending.

The same quadratic is retained; f advances to n and b becomes zero. The updated
field response state equals the already advanced live state in exact arithmetic.
Physical row generation remains chronological. Permuting inputs before generating
a_i generally changes the model; permuting already generated rows does not
change this exact quadratic. Neither statement asserts bitwise floating-point
commutativity.

All cross terms are essential. The exact algebra checker verifies a rationally
parameterized plane rotation preserves every pairwise column inner product,
which is the elementary identity behind this Gram invariant. The analytic QR
argument applies to arbitrary dimension; the polynomial checker is not a proof
of C's rounded rotation implementation.

## O2. Native tangent semantics

Write theta=m+Lw and let the last successful linearization anchor be a. For all
rows in the consumed prefix, define

    r_a = A phi(m+La),       B_a = A J_phi(m+La) L.

The native factor represents the augmented least-squares problem in delta:

    2 q_a(delta) = ||a+delta||^2 + ||r_a+B_a delta||^2.

The prior rows are [I,a], not [I,0]. The likelihood rows are [B_a,r_a]. The
minimizer and local precision are

    P_a = I+B_a'B_a,
    delta* = -P_a^-1 (a+B_a'r_a),
    w_query = a+delta*.

A new observation is appended after evaluating its residual and Jacobian at
this same anchor a. Thus the native factor continues to represent the entire
prefix at one anchor; it does not accumulate independently marginalized window
posteriors. At refresh, choose a new anchor using the full prior-free field and
original prior, then REPLACE the old tangent with the newly linearized prefix.
Refreshing is not a new observation and does not increment n.

Proof: expand the augmented row norm. QR preserves that norm by O1. The normal
equations give the displayed minimizer, and P_a is SPD because of the single I.
At a successful refresh the same construction applies at the new a. The root
prior does not become repeated merely because the representation is rebuilt.

The endpoint readout uses the nonlinear transport at w_query but the local
precision at a. It is a local tangent approximation, not an exact nonlinear
posterior. This distinction is retained in all later uncertainty statements.

## O3. Induction over admitted operations

Base: n=f=b=p=0, empty likelihood, initial response state, and one prior in the
native tangent. Suppose the invariants hold before an operation.

1. Reject invalid input or wrong source/order before commitment: logical evidence
   and boundaries are unchanged. Scratch memory is not part of this claim.
2. Consume a valid block [n,n+k): append only those new rows to the native
   tangent, advance the live response in order, and append the raw rows to the
   pending FIFO. Set n:=n+k; f and p are unchanged. The consumed prefix is still
   contiguous and no observation has two owners.
3. Flush: apply O1 to the pending suffix. Set f:=n,b:=0. This changes materialized
   representation, not evidence, prior count or p.
4. Successful refresh: flush if needed, then REPLACE the tangent using O2 at a
   supported new anchor. n and the field evidence do not change. A successful
   query can publish at n.
5. Rejected refresh after a successful flush: preserve the old native tangent
   and the already accumulated field. Do not append the rejected fit or undo
   newly consumed observations. A query of the retained tangent can still
   publish at n; otherwise enter unresolved/terminal handling.
6. Successful query: publish p:=n. It changes no likelihood or prior ownership.
7. Failed query after consume: retain evidence at n and keep the previous
   published p. Recovery operates on that same prefix. If recovery fails,
   quarantine the arm; a caller must not interpret the stale estimate as one
   based on [0,n), or resubmit [p,n) as fresh evidence.

Each operation preserves the stated prefix partition and exactly one prior,
provided its elementary kernels complete or obey the specified failure contract.
Induction therefore proves the invariant for every finite admitted trace, not
merely for the bounded traces explored by the executable checker.

The finite checker enumerates 969 states and 4,381 transitions through prefixes
of length eight, including rejected refreshes and post-consume query failures.
Mutations for repeated prior, duplicated/skipped evidence and publication ahead
of evidence are rejected. That is finite model evidence; the unbounded claim is
the induction above, and the code-to-model connection remains conditional.

## O4. Source correspondence and a refuted stronger claim

- `ft_init`: appends [I,a] and rows projected from the prior-free field, then
  commits the new native factor. It does not read the published Gaussian.
- `ft_step`: builds trial factor and response state in scratch; validation,
  response or update errors return before their commit. A query error is
  reported separately after commit. Thus not every non-successful readout means
  the observation was rejected.
- `ft_update`: builds a trial factor before committing it and incrementing count.
- `_flush_field`: materializes pending history and checks live/batch state parity.
- `_refresh`: snapshots the native factor, attempts relinearization, and restores
  that factor on the handled solve/query failures after a successful flush.
- `advance`: uses consumed/published state and a terminal flag for failed
  readout recovery. The compact campaign also removes unresolved arms from
  further updates and the active checkpoint set.

A blanket claim that *every* field/backend exception leaves all bytes unchanged
is FALSE. In `MixedField.update`, row generation changes `state`, `count` and
noise before `np.linalg.qr` returns. The injected QR failure witness advances
count 0->16 while leaving the old root intact. At backend flush level, pending
rows have not yet been cleared. This partial field cannot be treated as a valid
retry/checkpoint state. The normal-path induction does not cover it.

The current compact campaign catches LinAlgError and marks the arm unresolved;
that caller containment is not a transactional rollback theorem for the backend.
Allocation failure, arbitrary corruption, asynchronous exceptions and all other
uncaught failure paths are also not discharged. Before firmware specialization,
prove a compute-then-commit flush or an explicit terminal/quarantine policy at
the backend boundary. No such repair is silently included in this proof branch.

## O5. Optimization authority

O1/O2 permit exact basis changes and alternative QR schedules only when they
preserve the declared quadratic, chronological response and single-prior
semantics. O3 permits lifetime-based storage reuse only after the last reader of
the old object, including rollback/recovery, has finished. It does not permit
aliasing trial buffers with live state merely because ordinary successful
traces never trigger recovery. Finite-precision changes require the separate
joint error certificate; a Monte Carlo pass does not discharge that obligation.
