# N: exact finite-witness numerical certificates

Status: rigorous rational checks for supplied binary floating-point inputs and
outputs; not a proof of all executions of the native C kernel, its libm, or a
ten-year error bound. No external proof assistant is installed in this workspace.
The checker uses Python integer/Fraction arithmetic with no tolerance in its
acceptance decisions. The analytic inequalities below are handwritten proofs.

## N0. What was measured and what is exact

A diagnostic wrapper includes an unchanged copy of the native H7 `kernel.c` and
calls its actual `append` routine. It is compiled with the reference flags,
including `-fno-fast-math` and `-ffp-contract=off`, and linked to the unchanged H7
response source. Each witness appends 16 original-prior rows followed by 64
augmented likelihood rows. Rows have 16 coefficient columns plus one residual
column. They are synthetic numerical witnesses, not generated battery records.

The resulting binary64 factor R and every input double are converted exactly
to rational numbers using their stored binary values. Thus G=A'A and Gc=R'R are
computed in exact rational arithmetic for these supplied arrays. The measured
rounding error is not approximated by a floating-point residual calculation.
The compiler, source identities, arrays and binary are recorded in the receipt.

This certifies the QR operation on those arrays. Projection/feature-generation
roundoff occurred outside this artificial row interface and is not covered.
The production query's rounded triangular solve also needs its own bound.

## N1. A computable all-direction precision certificate

Take the leading 16×16 target precision P from G and the candidate Pc=U'U from
the leading block U of R. Choose any supplied square binary matrix Q, intended
as an approximate U inverse. Q need not be an exact inverse. Compute exactly:

    rho = ||I-UQ||_infinity,
    F = Q' P Q,
    Fc = Q' Pc Q,
    a = 1-||F-I||_infinity,
    d = ||Fc-F||_infinity.

If rho<1, the Neumann-series argument proves UQ nonsingular, hence U and Q are
nonsingular. Because F is symmetric, its spectral norm deviation from I is at
most the maximum absolute row sum, so F>=aI. If a>0, then for every vector w,

    |w'(Fc-F)w| <= d ||w||^2 <= (d/a) w' F w.

Set v=Qw; Q is nonsingular, so v ranges over the full parameter space. Therefore

    |v'(Pc-P)v| <= epsilon v' P v,    epsilon=d/a.

If epsilon<1, E4 gives the relative precision and covariance bounds. Every
comparison and the rational value of epsilon is exact. Decimal values in the
receipt are display approximations. If any premise fails, the checker reports
an unresolved certificate; it does not round into acceptance or clip an eigenvalue.

The infinity norm can be conservative. Failure to obtain a certificate is not
itself proof of instability. Conversely, the receipt also records explicit
Rayleigh ratios along supplied Q basis directions. A bad such ratio is a
constructive discrepancy witness rather than merely an inconclusive bound.

## N2. Results

| Numerical witness | Native binary64 epsilon bound | Same factor stored in binary32 |
|---|---:|---:|
| Ordinary rows | 1.69e-15 | 1.34e-7 |
| Repeated rank-one stimulus | 1.58e-14 | 2.38e-6 |
| Column scales 1e-4 through 1e4 | 2.75e-15 | 1.32e-7 |
| Strongly coupled large columns | 2.69e-5 | 0.435 |
| Strongly coupled, slightly tilted columns | 1.13e-5 | certificate unresolved |

The final binary32 case also exhibits a precision Rayleigh ratio of about
1.3868e-5 relative to the original rows in one direction. This is a large
constructive loss of joint precision, not just a conservative test failing.
The witness uses deliberately severe 1e10-scale correlated columns. It is not
evidence that a current battery run has this conditioning, and it does not rule
out a carefully scaled or certified reduced-precision representation.

The practical implication is narrow but useful: small entrywise storage error
is insufficient optimization authority. Measure or bound the error in the joint
information geometry, especially weak directions. The constants here certify
five finite local quadratics only; they cannot be extrapolated to all future
H7 rows, sample rates or stream lengths.

## N3. Failure-driven revisions

The first suite covered four numerical witnesses. A fifth, slightly tilted
strong-correlation witness showed a much larger effect of storing the factor in
binary32; both earlier artifacts and the new witness are retained.

A negative test then supplied a zero whitener Q. The checker correctly had no
usable SPD bound, but its optional Rayleigh-reporting code divided by a zero
quadratic. The revised checker reports no direction for that case and rejects
the certificate. The acceptance predicate was not relaxed. Corrupted factors
and noninvertible whiteners are tested explicitly. Original checker sources and
receipts remain in qr001/qr002/qr003; final evidence is in qr004.
The final checker also explicitly rejects malformed dimensions and nonfinite
inputs before applying matrix identities.

An independent fault-injection witness refuted universal rollback for the Python
field update; see O4. That is a source-contract limitation, not a native QR
roundoff result, and no production repair is included.

## N4. Open finite-precision and resource obligations

To turn the finite checks into a supported-horizon theorem, bound or track:

1. Each response recurrence and its derivative error, including exp/expm1,
   temperature factors, feature projection and small-decay cancellation.
2. Accumulated factor error relative to the declared real-arithmetic feature
   model, with admitted scaling and condition numbers. Fixed dimensions do not
   establish a bound independent of the number of updates.
3. Rounded triangular solves, nonlinear query evaluation and transported roots.
4. Solver stopping error, including changes to absolute-cost constants.
5. Failure/overflow/underflow policies and reachable states after every permitted
   error. Finite checks of normal paths do not discharge exception safety.
6. Input-domain bounds, index/tick widths, workspace aliasing and stack lifetimes.

For ten Julian years at up to 100 Hz, sample count is 31,557,600,000, which needs
at least 35 unsigned bits. Nominal 35 Hz already needs 34 bits. The selected C
cursor is uint64, but this fact alone does not prove every conversion or derived
product safe. The native block permits dt<=1 and hz<=INT32_MAX, so at most 16
rounded interval ticks fit well inside uint64 within one block. Cumulative ticks
must also have a declared horizon; at hz<=INT32_MAX for ten years the product
is below 2^60. Allocations, Python-to-C conversions, refresh rounding and sequence
arithmetic require separate range checks. A uint64 counter is not a timing bound.

The packed H7 field factor alone is 50,624 bytes. Its fixed size proves O(1)
history storage in sample count, not compliance with 10 KiB total SRAM. Target
flash, stack, native scratch, response tables, retained buffers and soft-float
support need a complete Cortex-M23 measurement class. Host measurements and
Python memory are separate evidence.
