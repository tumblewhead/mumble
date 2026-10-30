# Prior-free chronological Gaussian operators

This implements the closed base family in L1–L5 of the
[foundation](../../proofs/ten_year_history_001/lemmas.md). It is an independently
testable reference for a future rolling-history interface. It does not replace
the nonlinear battery likelihood, its bounded health transitions or its prior.

For an interval, store the operator

    T(dx_out | x_in) = exp(-x_in' J x_in/2 + h' x_in - c)
                       N(dx_out; A x_in + b, Q).

Here J and Q are positive semidefinite, and a singular Q denotes a Gaussian
measure, including an exact deterministic map when Q=0. The first factor is
the observations' marginal likelihood given the entering state; the second
is the exit-state distribution conditional on those observations and the
entering state. There is no entering prior in this object. Keeping c preserves
evidence normalizers as well as means, uncertainty and cross terms.

For one step x'=F x+d+w, y=H x'+v, with w~N(0,W), v~N(0,R), independent,
define S=H W H'+R, r=y-Hd, K=W H' S^-1 and E=HF. Then

    J=E' S^-1 E; h=E' S^-1 r;
    c=(r' S^-1 r + log det S + dim(y) log(2 pi))/2;
    A=(I-KH)F; b=d+Kr;
    Q=(I-KH)W(I-KH)' + K R K'.

R is strictly positive definite; W can be zero or singular. This follows by
conditioning a joint Gaussian. No process precision W^-1 is needed.

## Composition proof, including deterministic transport

Let operator 1 precede operator 2 and eliminate their shared state z. Tilt
N(z;mu,Q1), mu=A1*x+b1, by exp(-z'J2*z/2+h2'z-c2). Put

    B=(I+Q1*J2)^-1; S=B*Q1;
    D=J2-J2*S*J2; g=h2-J2*S*h2;
    k=c2 + log det(I+Q1*J2)/2 - h2'S*h2/2.

The tilted z has mean B*mu+S*h2 and covariance S. Its integrated likelihood
has NLL mu'D*mu/2-g'mu+k. Thus the composed token has

    J=J1+A1'D*A1; h=h1+A1'(g-D*b1);
    c=c1+k+b1'D*b1/2-g'b1;
    A=A2*B*A1; b=A2*(B*b1+S*h2)+b2;
    Q=A2*S*A2'+Q2.

These formulas follow first on the support of Q1 using a factor Q1=L L'
and the positive definite matrix I+L'J2 L. The identities
S=L(I+L'J2 L)^-1 L' and det(I+Q1 J2)=det(I+L'J2 L) extend the formulas to
singular Q1. When Q1=0 they reduce to direct substitution through a
deterministic map. This is integration, not maximization over z.

Chronological associativity follows from integrating the same nonnegative
product over its intermediate states; disjoint adjacent source ownership is
required separately. Identity is J=h=c=0,A=I,b=Q=0. The implementation uses
linear solves, symmetrizes roundoff asymmetry and rejects material negative
eigenvalues/nonfinite output. It never injects process noise. Finite floating
point does not inherit exact associativity or a certified error bound.

Applying a token to a separately owned prior N(m,P) uses the same tilt with
J,h,c, then the conditional exit map A,b,Q. Keeping the token prior-free allows
queries with different priors without modifying it. A posterior returned from
a query is an estimate view and cannot be appended as an observation token.

## Ownership and rolling retirement

A stream contract binds source, model, noise, calibration, chart dimension and
integer tick frequency. Each token owns [first_sequence,next_sequence), plus
the entering/leaving elapsed ticks and actual signed charge/absolute throughput.
One accepted record advances the sequence even when elapsed ticks are equal.
Only adjacent tokens with matching boundaries compose. The fixed-capacity
reference queue holds new single-record operators. Retirement first constructs
the new aggregate, then atomically replaces the history and removes the owned
prefix. A query combines history and pending rows in temporary storage. It
does not move a watermark or alter history. Thus history and the pending suffix
cover each accepted observation once, even while successive queries overlap.

This is an in-process, trusted single-source interface. It is not an
authenticated transport, durable crash transaction, multistream merger or
adapter that converts arbitrary rolling posterior outputs into evidence.
The current C rolling engine follows a compatible offer/admit/commit ownership
pattern, but its polynomial history and optimizer are unchanged by this study.

## Error and aging semantics

Representation defect is zero **in real arithmetic within this declared
family**. Arithmetic defect and discrepancy from an actual battery are
unresolved, not zero. Roundoff PSD checks use 64 machine epsilons times matrix
scale; this is an arithmetic rejection rule, not an aging or physical threshold.
No error budget is reset by retirement. Query comparisons are finite controls.

Choosing F=I,H=0 makes a quiet health update P_next=P+W. Old information loses
current precision only through the supplied transition uncertainty. W is a
fixture assumption here, not a battery aging rate. Coupled transitions and
correlated priors can transfer information to an indirectly observed quantity;
an independent unobserved coordinate must retain its uncertainty. No universal
observability, coverage, monotonic aging or ten-year stability claim follows.

## Storage

A packed token has J,Q symmetric, A dense, h,b vectors and c scalar:
`8*(2*d*d+3*d+1)` bytes. This is 224 B for d=3 and **4488 B for d=16**.
A packed d=16 prior mean/covariance is 1216 B; their combined numeric payload
is 5704 B, excluding metadata, pending observations, query result, temporary
tokens, solves, eigensolvers, stack and the rolling optimizer. This prior-free
two-boundary token is a different object from the older 2544-B posterior fit.

The Python reference stores dense matrices: `8*(3*d*d+2*d+1)` bytes per token,
6408 B at d=16. A capacity-4 queue can retain five such tokens (32040 B),
before the prior and all workspace/Python overhead. Its time and retained
dimension do not grow with retired history length, but this is **not** a
complete 10240-B firmware layout. An embedded implementation must share fixed
model descriptors, store actual raw pending rows or another bounded encoding,
and audit peak live workspace. Finite-bit ten-year accuracy remains P4 work.
