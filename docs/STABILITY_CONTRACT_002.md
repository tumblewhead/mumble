# Stability contract and implemented lemmas 002

## Outcome

This checkpoint turns the previous lifetime proof outline into an explicit
research contract and four isolated C99 integer primitives:

- Exact bounded accumulation of represented current-code/time-tick products.
- Integer enclosures of exponential attenuation for encoded rational arguments.
- Outward interval propagation of a dissipative scalar state.
- Exact retention of certified exclusions over a finite static parameter cover.

The arithmetic lemmas are connected to the actual source operations. The
evidence lemma is conditional on a sound certificate provider. These are
written proofs, independently reviewed and checked against small exact-reference
experiments; they are not machine-checked compiler proofs.

This is not yet an integrated bounded battery estimator. The original
retained-history reference, B001/B002 numerical sources, results, 0.1 NLL
criterion and the original 18 B002 audit failures are preserved.

Work branch: research/indefinite-numerical-stability-002.
Base: a8f02b1402735a7f2f9be2dec54dedcc11ec2f8b.

| Artifact | Role |
| --- | --- |
| [Contract](../proofs/indefinite_stability_002/contract.json) | Encoded inputs, finite evidence semantics, assumptions and acceptance gates |
| [Lemma ledger](../proofs/indefinite_stability_002/lemmas.json) | Exact claims, proofs, implementation paths and remaining boundaries |
| [C API](../include/scm_stable.h) | Types, input conditions, return semantics and scope |
| [C implementation](../src/scm_stable.c) | Integer operations implementing the lemmas |
| [C tests](../tests/test_stable.c) | Boundary and failure-atomicity checks |
| [Audit plan](../experiments/indefinite_stability_002/plan.json) | Frozen small experiment specification |
| [Audit receipt](../experiments/indefinite_stability_002/receipt.json) | Independent rational oracles, outcomes, hashes and host memory evidence |
| [Prior obstruction report](INDEFINITE_NUMERICAL_STABILITY_001.md) | Why unrestricted finite-state all-history claims need a different contract |

## 1. The contract

### 1.1 Numerical reference and input meaning

All arithmetic claims concern the exact real or integer calculation on the
**same represented inputs**. They do not remove sensor quantization,
calibration error, current bias, clock error, uncertain parameters or model
mismatch.

Nominal acquisition remains 35 Hz. Each supplied tick count is the actual
represented interval; it is never replaced by a nominal constant. The caller
must preserve observation order, detect missing observations, and maintain
the meaning of the input units.

| Primitive | Admitted representation | Guaranteed output |
| --- | --- | --- |
| Charge | Signed 32-bit current code; unsigned 32-bit interval ticks; signed 64-bit bounded net accumulator | Exact updated integral, or atomic rejection |
| Attenuation | Exact ratio q=num/den with unsigned 32-bit numerator and positive denominator | Integers A_lo,A_hi enclosing exp(-q) after division by D=2^32 |
| Dissipative state | Integer interval endpoints and exact integer forcing target within [-B,B], B<=2^30 | Outward interval enclosing every admitted exact scalar transition |
| Evidence | Immutable mapping of up to 64 domain bits to static parameter cells; sound allowed-cell certificates | Exact accumulated intersection and explicit inconsistency if empty |

A successful return means the primitive completed its declared operation.
It does not mean parameter identification, useful precision, statistical
coverage, physical accuracy or successful estimator convergence.

Negative returns preserve the destination object. A rejected observation has
not been propagated. The surrounding system must not report the old state as
current. Combining several primitives into one atomic observation transaction
is a separate integration obligation.

### 1.2 Arithmetic environment

The code requires conforming C99 behavior and the exact-width integer types
int32_t, uint32_t, int64_t and uint64_t. It uses no floating-point arithmetic,
libm, heap allocation, variable-length arrays, mutable global state or lifetime
sample counter.

Each multiplication, addition, division and shift has a range argument below.
Signed negative shifts are avoided. Signed division uses C99 truncation toward
zero, with explicit remainder corrections for floor and ceiling.
See the WG14 [C99 consolidated draft N1256](https://www.open-std.org/jtc1/sc22/wg14/www/docs/n1256.pdf),
sections 6.5.5, 6.5.7 and 7.18.1.1.

This source-level argument trusts the compiler and the declared C execution
model. No target compiler correctness theorem or Cortex-M23 timing result is
claimed.

### 1.3 Historical evidence semantics: a declared research candidate

The selected candidate stores **certified cell exclusions** at a finite spatial
resolution. It does not store an all-history likelihood, measurement
multiplicity or a continually increasing confidence weight.

This is an explicit alternative representation under investigation, not an
equivalence claim about the existing Gaussian reference. No old likelihood
factor or local precision report is converted into a hard exclusion.

The finite cover and certificate meaning must remain fixed for a certified
episode. Parameter drift, changing covers, chart transitions and recovery
require a separate transport contract. The current implementation offers no
automatic reset, forgetting or reintroduction of excluded cells.

The spatial resolution is explicit. It is not a hidden cap on a Gaussian
information matrix. At most K bits can be removed from a K-cell cover; further
learning below that cover's resolution is unavailable until a separately
proved refinement/transport operation exists.

## 2. L1: exact bounded charge for every accepted prefix

Let the represented current and duration be

\[
I_k=c_I m_k,\qquad \Delta t_k=c_t t_k,
\]

where m_k is int32 and t_k is uint32. Define

\[
P_n=P_0+\sum_{k<n}m_kt_k.
\]

The initial value and every admitted exact prefix lie in the declared
signed-64-bit interval [L,U].

### Product range

The complete product range is

\[
-2^{63}+2^{31}
\leq m_kt_k
\leq 2^{63}-2^{32}-2^{31}+1.
\]

Both endpoints are representable in int64. The implementation casts both
operands to int64 before multiplication.

For a positive product p, the check P<=INT64_MAX-p establishes safe addition.
For a negative p, the check P>=INT64_MIN-p does the same. The guard expressions
are themselves representable. Only then is P+p evaluated and tested against
the application interval [L,U].

### Induction

Assume the stored P equals the exact represented-input sum through a prefix.
The next product and guarded addition are exact. If the application range
accepts the result, the committed value equals the extended exact sum.
Induction establishes exactness for every admitted finite prefix.

There is no accumulated rounding term and no age counter. A cycling stream
whose exact prefixes stay in [L,U] cannot be rejected solely because it has
run longer.

Physical charge is

\[
q_n=\frac{c_Ic_t}{3600}P_n.
\]

That conversion and any subsequent SOC calculation need their own numerical
enclosure. The kernel retains the exact integer sufficient quantity and does
not silently convert through floating point.

This lemma does not apply to a positive-only lifetime throughput sum, which
does not have a bounded-prefix premise. Nor does it establish physical
accuracy when the represented current contains a bias.

Implementation: scm_stable_charge_init and scm_stable_charge_push.

## 3. L2: a libm-free exponential enclosure

Define D=2^32. The API returns integers satisfying

\[
0\leq A_{\rm lo}\leq A_{\rm hi}\leq D,\qquad
\frac{A_{\rm lo}}{D}
\leq e^{-q}\leq
\frac{A_{\rm hi}}{D},
\quad q=\frac{\mathrm{num}}{\mathrm{den}}\geq0.
\]

The exact value one needs 33 unsigned bits in this representation, which is
why the endpoints use uint64.

### Special cases

For q=0, return [D,D] exactly.

For q>=32, e>2 gives

\[
e^{-q}\leq e^{-32}<2^{-32}.
\]

The returned interval is [0,1]/D. This retains a positive upper bound; it does
not assert that a small nonzero decay is exactly zero.

### Range reduction and polynomial bounds

For q<32, the product D*num fits uint64 because num<=2^32-1. Integer floor
and ceiling division enclose D*q. At most eight outward halvings produce an
interval for x=q/2^s contained in [0,1/8].

Let

\[
P_r(x)=\sum_{j=0}^{r}\frac{(-x)^j}{j!}.
\]

Taylor's integral remainder gives

\[
e^{-x}-P_r(x)
=
\frac{(-1)^{r+1}}{r!}
\int_0^x e^{-t}(x-t)^r\,dt.
\]

The integrand is nonnegative. Therefore

\[
P_7(x)\leq e^{-x}\leq P_6(x).
\]

The code computes interval powers with outward integer multiplication.
Positive polynomial terms use their lower endpoint for the lower bound and
their upper endpoint for the upper bound; negative terms use the opposite
endpoints. Division by each factorial is rounded in the corresponding
direction.

The polynomial enclosure is intersected with the known range [0,1].
Then s outward interval squarings reconstruct e^(-q). Squaring is monotone
on this nonnegative interval, so every step preserves containment.

### Machine range argument

When multiplying Q32 values a,b in [0,D], an endpoint equal to D is handled
as exact multiplication by one. Otherwise a*b<2^64. The high 32 bits give
the downward result; a nonzero low part adds one for the upward result.

Ceiling division uses quotient plus a nonzero-remainder indicator, avoiding
an overflowing numerator of the form n+d-1. Taylor terms are each bounded
by D; even a loose eight-term magnitude bound is far below int64 limits.

All loop counts are bounded independently of runtime: seven power/term
iterations and no more than eight reduction/squaring steps.

The theorem covers the encoded ratio. Converting a continuous estimated tau
or hysteresis parameter into this ratio, or a sound interval of ratios,
remains part of the surrounding model contract.

Implementation: scm_stable_attenuation_ratio.

## 4. L3: bounded outward state propagation

Consider

\[
x_{k+1}=a_kx_k+(1-a_k)b_k.
\]

The exact state may lie between integer grid points. Stored endpoints and
the exact target b_k use the same declared unit.

Suppose

\[
-B\leq l_k\leq x_k\leq u_k\leq B,
\qquad |b_k|\leq B,\qquad B\leq2^{30},
\]

and a_k belongs to [A_lo/D,A_hi/D].

### Four exact corners

The map is bilinear in a and x. Its extrema over the rectangle occur at
the four combinations of state and attenuation endpoints. Each corner is

\[
\frac{N}{D},\qquad
N=A x+(D-A)b.
\]

The weights are nonnegative and sum to D, so

\[
|N|\leq DB\leq2^{62}.
\]

Each individual product is also representable in int64. The code computes
the four numerators exactly, then stores

\[
l_{k+1}=\left\lfloor\frac{\min N}{D}\right\rfloor,\qquad
u_{k+1}=\left\lceil\frac{\max N}{D}\right\rceil.
\]

C99 quotient/remainder operations are corrected for the desired direction;
negative signed shifts are not used.

### Closed range and enclosure invariant

Every corner is a convex combination of values in [-B,B]. Because -B and B
are integer endpoints, outward rounding cannot cross that domain. Thus the
new interval still lies within [-B,B] and contains every admitted exact update.

Combining this one-step property with initial containment proves soundness
and fixed range for every finite execution length.

If A_lo=A_hi=D, the numerators are exactly D*x and division is exact.
The entire interval is unchanged. Arbitrarily many such identity updates
introduce no additional width.
After validating all inputs, the implementation returns before any write in
this case. Thus the complete object, including any ABI padding, is preserved.

For RC propagation, attenuation comes from actual interval/tau ratios.
For hysteresis, it comes from a throughput ratio. Mapping the model inputs
and uncertain parameters to those ratios is not supplied by this scalar
kernel.

Implementation: scm_stable_interval_init and scm_stable_interval_step.

## 5. L4: a useful width bound independent of runtime

Containment in the physical domain alone can be too coarse. Let w_k=u_k-l_k
in grid units. For two rectangle points,

\[
|F(a,x)-F(a',x')|
\leq a_{\rm hi}|x-x'|+
       |a-a'|\,|x'-b|.
\]

Because |x'-b|<=2B, the exact image width is at most

\[
a_{\rm hi}w_k+2B(a_{\rm hi}-a_{\rm lo}).
\]

Outward integer endpoints add less than two units. If each active update
satisfies

\[
A_{\rm hi}\leq D-g,\qquad
A_{\rm hi}-A_{\rm lo}\leq h,\qquad g>0,
\]

then

\[
w_{k+1}\leq
\left(1-\frac{g}{D}\right)w_k+
\frac{2Bh}{D}+2.
\]

Geometric-series induction yields

\[
\boxed{
w_n\leq
\max\left(w_0,\frac{2Bh+2D}{g}\right)
}
\]

and the domain invariant also gives w_n<=2B. Multiplying by the declared
physical state quantum converts this into a width in physical units.

The number n here may count active updates. Exact identity updates inserted
between them add no width. Actual positive-time zero-current RC relaxation is
still an active update; zero-throughput hysteresis can be an identity.

This theorem needs a certified g>0 and a useful resulting width. Very small
positive q can produce A_hi=D; the theorem's contraction premise then does
not hold. The enclosure remains sound, but useful precision must be withheld.
Nominal 35 Hz alone supplies no global contraction assumption.

A chosen application tolerance must exceed the derived numerical width.
No new arbitrary SOC/capacity tolerance or revision of B002's 0.1 NLL policy
is introduced here.

The scalar theorem does not automatically cover coupled sensitivities,
higher derivative envelopes or parameter-chart transport.

## 6. L5: finite historical certificates and exact retention

Let fixed cells B_j cover a declared static parameter domain. Cells may overlap.
Let F_n be the exact compatible parameter set under the provider's stated
model after prefix n, with

\[
F_n\subseteq F_{n-1}.
\]

Define the cell-index set

\[
J(F)=\{j:B_j\cap F\ne\varnothing\}.
\]

A supplied certificate C_n must satisfy

\[
J(F_n)\subseteq C_n.
\]

The mask starts with all domain cells and updates by

\[
A_n=A_{n-1}\cap C_n.
\]

### Soundness proof

Nesting implies

\[
J(F_n)\subseteq J(F_{n-1})\subseteq A_{n-1}.
\]

Certificate soundness also gives J(F_n) subset C_n. Hence J(F_n) is
contained in their intersection A_n. Induction proves this for every
finite prefix.

The C update is a bitwise AND. It is exact and requires no growing weight,
normalization factor or observation count.

Consequently:

- Earlier certified cell exclusions remain excluded.
- An all-domain certificate is an exact identity.
- A repeated certificate is exactly idempotent.
- There are at most K strict bit removals for a K-cell cover.
- An empty mask is retained and reported as inconsistent; it is not reset
  to all cells.

If the domain covers all admitted parameters and certificates are sound,
empty A_n implies empty F_n. A nonempty mask does **not** prove that F_n is
nonempty: different points in the same cell can survive different observations,
so the representation can retain false positives.

### Why the “every intersecting cell” premise matters

Suppose two overlapping cells both contain a compatible parameter.
A first certificate retains only cell 1, and a second retains only cell 2.
Each certificate's union covers that parameter, but their mask intersection
is empty.

Therefore merely requiring the union of each certificate to cover F_n is
insufficient for this update. The stronger J(F_n) subset C_n condition is
required. A genuinely disjoint partition with an immutable boundary convention
can use its equivalent unique-cell formulation.

### Statistical boundary

The kernel consumes certificates; it does not manufacture them. A provider
must prove the relation between measurements, physical-state enclosures,
model assumptions and its allowed cells.

The existing Gaussian voltage model has unbounded residual support. Its
1 mV standard deviation is not a deterministic hard residual bound. A
bounded-error feasibility provider would be a separately declared model;
probabilistic certificates would require a separately proved simultaneous
coverage contract. Neither is supplied here.

Logical idempotence also does not prove that a provider used raw observations
correctly or preserved physical chronology. It does not authorize treating
replayed likelihood observations as independent evidence.

Implementation: scm_stable_mask_init and scm_stable_mask_apply.

## 7. L6: conditional eventual refinement

Let T be the cells acceptable at a declared target resolution. Assume every
unwanted cell j in A_0 outside T receives a sound excluding certificate at
some finite event index k_j.

If there are no unwanted cells, take N=0. Otherwise, because there are
finitely many unwanted cells, N=max_j k_j is finite.
Monotone intersection has removed every unwanted cell by N and retains
those exclusions thereafter. Thus

\[
A_n\subseteq T\qquad \text{for all }n\geq N.
\]

This connects the representation to the project's conditional-learning goal:
when enough distinct informative events supply the necessary exclusions,
they accumulate; repetitive uninformative events do not undo them.

The theorem supplies no universal convergence time. It does not prove the
excluding events exist for the real battery stimulus, nor that the chosen
cover is fine enough. Excluding individual points at different times is not
the same as certifying exclusion of an entire cell.

A useful target estimate additionally needs a sound bound on that target
over the union of surviving cells. Nuisance parameters may remain broad while
SOC or capacity becomes useful. Those target queries remain provider work.

## 8. Proof composition and remaining boundaries

These kernels remove lifetime-growing arithmetic from their own state.
The product of their state spaces is finite and bounded, but this is not
a proof that the complete existing estimator inherits their properties.

The surrounding estimator still needs:

1. An actual finite battery parameter cover and sound observation-to-certificate
   provider under an explicit error/statistical model.
2. Model-state enclosures for all relevant unknown parameters, including
   sensitivities or a justified method that does not require them.
3. Sound OCV, voltage and SOC/capacity target queries.
4. Joint transaction and chronology handling across the primitive updates.
5. Transport when parameter meanings, covers or physical assumptions change.
6. Persistence, reset and input-delivery semantics.
7. Target memory, stack, division cost, latency and power measurements.

No history-dependent chart change is implemented. No prior error ledger is
reset. No Gaussian likelihood factor is deleted, capped or reclassified by
these kernels. They are a separate research component.

## 9. Validation and memory scope

The source and plan are committed before the primary audit. Development
checks preceded this freeze; no claim of an unseen statistical validation set
is made. The primary audit compiles the exact integer core and compares it with
independent references:

- Exact Python integers/Fractions for charge and interval transitions.
- A positive Taylor series for exp(q), a geometric bound on its positive
  remainder, and inversion to enclose exp(-q). This differs from the C
  alternating-polynomial/range-reduction construction.
- Exhaustive small-domain mask checks and chronological informative/quiet/new
  certificate examples.
- An overlapping-cell negative control that refutes the insufficient
  union-cover premise.
- Variable actual tick intervals at a nominal 35 Hz rate, with all arithmetic
  grid and timing assumptions declared.

The audit tests correspondence to the proof and detects implementation defects.
The induction arguments, not a finite replay duration, establish the
all-prefix claims.

Host sizeof, static storage and compiler stack reports describe only these
isolated primitives and the listed call paths. They exclude the parameter
cover, certificate provider, full battery state, acquisition, application,
interrupt and target-runtime costs. They do not establish that the complete
estimator fits the approximately 10 KiB target.
Any external delivery or chronology state must be counted in that full-system
accounting; the proof does not assume a hidden unbounded counter.

Detailed outcomes are appended after the frozen primary audit.

## 10. Next milestone

Build one concrete battery-relevant certificate provider and target query
whose assumptions are explicit and whose state propagation uses these
enclosures. Test its ability to retain useful earlier constraints through
weak use and refine them after new excitation.

The frozen Gaussian retained-history estimator remains the comparison
reference. The next provider must disclose any difference in inference
semantics and compare practical usefulness separately from numerical proof.
