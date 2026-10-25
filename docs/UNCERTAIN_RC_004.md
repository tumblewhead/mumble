# One bounded uncertain RC mode

## Outcome and scope

This checkpoint extends the integer battery provider from known RC parameters
to one fixed but uncertain resistance/time-constant pair. The new C provider
encloses every real parameter pair in a supplied box, carries the resulting RC
state intervals, and preserves the existing capacity-bin and initial-SOC
constraints. It keeps outward current-SOC and capacity queries and the complete
observation transaction.

Six written arguments cover endpoint enclosures, interval forcing, a width
bound valid for every admitted finite prefix, complete-configuration retention,
composed availability and a conditional nominal-control nesting property.
The source and proofs have independent mathematical/source-operation review.
The frozen primary audit passed all sampled soundness checks and reproduced
three failed usefulness assertions in two parameter-corner cases. Overall
experimental acceptance remains **false**. The failures are retained with
their original box, stimulus and learning gates.

At the public midpoint, capacity narrows from 30-100 mAh to
61.718-67.187 mAh after charge, 62.812-67.187 mAh after quiet use, and
62.812-66.093 mAh after renewed charge. At two opposite corners, the last
phase does not narrow capacity further. This establishes a concrete precision
limit of this experiment and representation, not physical unidentifiability.

The resistance/time-constant box is supplied before the first observation and
does not contract. Those parameters remain unresolved inside that box. This
milestone propagates uncertainty; it does not claim to learn those parameters.
Known R0, the other two RC pairs, encoded OCV, exact represented current/time,
hard voltage-error intervals and absence of drift/hysteresis remain premises.

Branch: research/indefinite-numerical-stability-004.
Base: 4a990cf923e2e56935a1ffb346215faad05bff66.

Canonical source: `7c6f248f68638d632e297ff655da94652c09c0c2`. The original source and research
commits are preserved in a verified bundle. Published source/research trees
were compared against the original local trees using fetched Git objects; all
matched. See the [publication provenance](../provenance/indefinite_stability_004_publication.json).

| Artifact | Role |
| --- | --- |
| [Contract](../proofs/indefinite_stability_004/contract.json) | Continuous parameter box, units, input/domain assumptions and lifetime claims |
| [Lemma ledger](../proofs/indefinite_stability_004/lemmas.json) | U1-U6 and the reference coordinate identity |
| [C API](../include/scm_certificate_box.h) | Full configuration, state, workspace and status semantics |
| [C source](../src/scm_certificate_box.c) | Box attenuation, interval forcing and integrated provider |
| [Tests](../tests/test_certificate_box.c) | Range, sign, identity, transaction and degenerate-equivalence cases |
| [Audit plan](../experiments/indefinite_stability_004/plan.json) | Predeclared uncertainty, five phase traces, gates and independent comparison |
| [Primary receipt](../experiments/indefinite_stability_004/receipt.json) | Frozen audit outcomes and complete resource measurements |
| [Compact outcome summary](../experiments/indefinite_stability_004/summary.json) | Selective machine-readable results without loading the full receipt |
| [Independent review](../proofs/indefinite_stability_004/independent_review.json) | Mathematics, source correspondence, audit and reference review |
| [Build checks](../experiments/indefinite_stability_004/build_checks.json) | Frozen-source integration and targeted sanitizer results |
| [Verification](../experiments/indefinite_stability_004/verification.json) | Source/evidence integrity and explicit preserved failure status |
| [Development notes](../experiments/indefinite_stability_004/development_notes.json) | Original failed outcomes, exact source snapshot and disclosed audit hardening |
| [Earlier provider](BATTERY_CERTIFICATE_003.md) | Preserved known-RC provider and inherited SOC/capacity proofs |

## 1. What changes in the model

For the selected mode, the true constants satisfy

\[
R\in[R_l,R_u],\qquad \tau\in[\tau_l,\tau_u],\qquad \tau_l>0.
\]

They remain fixed over the certified episode. Their values can be real between
the encoded integer endpoints; they do not have to lie on a parameter grid.
The state equation is unchanged:

\[
v_{n+1}=a_n v_n+(1-a_n)I_nR,
\qquad a_n=e^{-\Delta t_n/\tau}.
\]

The public API describes all three modes with endpoint pairs, and rejects a
configuration with more than one nondegenerate mode. A mode with both uncertain
R and uncertain tau counts once. All-degenerate configurations remain valid
for comparison with the frozen known-parameter provider.

Current uses microampere codes, resistance endpoints use integer milliohms,
and state/voltage endpoints use nanovolts. Their product gives an exact
nanovolt forcing endpoint. Time uses 35,000 ticks per second; nominal 35 Hz
corresponds to 1,000 ticks, but every actual interval is retained in order.

The bank still has up to 64 immutable capacity bins. Each original bin crosses
the common initial-SOC domain, entering-RC box and the selected R/tau box. Each
bin carries a contracting initial-SOC interval. There is no growing sample
history or lifetime counter.

## 2. U1-U2: a sound interval update

### Attenuation endpoints

For a fixed nonnegative interval, attenuation is nondecreasing in tau:

\[
\frac{\partial}{\partial\tau}e^{-\Delta t/\tau}
=\frac{\Delta t}{\tau^2}e^{-\Delta t/\tau}\ge0.
\]

The lower certificate from the existing integer kernel at tau_l and its upper
certificate at tau_u therefore enclose every attenuation in the continuous
box. This uses monotonicity of the exact exponential. It does not require
rounded output intervals from different kernel calls to be nested.

Write the resulting interval as [A_l,A_u]/D, with D=2^32. Equal tau endpoints
use the frozen kernel once. Zero elapsed time gives exactly [D,D].

### Signed forcing

The forcing interval is

\[
T=[\min(IR_l,IR_u),\max(IR_l,IR_u)].
\]

Negative current reverses the resistance endpoint order. Products are formed
in int64, checked against the state domain, then converted to int32. Config
validation requires the maximum allowed current times R_u to fit that domain,
so every admitted forcing remains inside [-B,B].

### Reusing the proved point-target kernel

For f(a,x,t)=a*x+(1-a)*t, the derivative with respect to t is 1-a>=0.
The minimum over forcing therefore occurs at T_l and the maximum at T_u.
The implementation runs the unchanged point-target enclosure on two copies of
the same entering state, then selects the lower endpoint from the first and
upper endpoint from the second.

Every exact image point is a convex combination of state and forcing inside
[-B,B]. Outward rounding at integer domain endpoints preserves that invariant.
Inherited corner magnitudes are at most D*B<=2^62. No new runtime multiplication
requires a wider integer type.

All inputs, including both forcing endpoints and their order, are validated
before the exact-unity no-write return. Negative statuses preserve the entire
destination. Both endpoint calculations begin with the original interval;
feeding the second calculation from the first would implement a different and
incorrect transition.

## 3. U3: the width theorem

Let W be the entering state width and F the forcing width. For any two points
in the image rectangle,

\[
\begin{aligned}
f(a,x,t)-f(a',x',t')
={}&a(x-x')+(1-a)(t-t')\\
 &+(a-a')(x'-t').
\end{aligned}
\]

Since |x'-t'|<=2B, the image diameter and two outward endpoint roundings obey

\[
W_{n+1}\le
\frac{A_uW_n+(D-A_l)F_n+2B(A_u-A_l)}{D}+2.
\]

The three terms have distinct meanings: carried state uncertainty, uncertain
forcing, and uncertain attenuation. The final two-grid-unit allowance bounds
rounding. When tau is uncertain, the attenuation span includes model ambiguity
as well as numerical enclosure error.

Suppose a declared future input domain certifies

\[
A_u\le D-g,\quad g>0,\qquad
D-A_l\le b,\qquad A_u-A_l\le h,\qquad F_n\le F_{\max}.
\]

Set rho=1-g/D. Geometric induction gives

\[
W_n\le
\min\left(2B,\;
\max\left(W_0,\frac{bF_{\max}+2Bh+2D}{g}\right)\right)
\]

for every finite prefix. Arbitrarily many exact [D,D] identity updates can
intervene because they add no width or rounding. The index in this proof is
mathematical; the runtime stores no corresponding lifetime count.

This theorem bounds the larger rectangle used by the implementation. It does
not assume that the true state, R and tau become independent. Their lost
correlations make the bound conservative. If no positive future contraction
margin is certified, the refined bound is unavailable; the convex-domain
2B bound and containment still hold.

The audit computes the width certificate with arbitrary-precision integers and
rational arithmetic. Its generic numerator can exceed fixed-width ranges even
though every runtime state update remains safe. The C provider does not
evaluate or accumulate that numerator.

## 4. U4-U5: evidence and availability still compose

The compatible set now contains complete static configurations

\[
(R,\tau,z_0,Q,\text{initial RC}).
\]

For any such configuration consistent with the whole prefix, U1-U2 enclose its
RC trajectory. Corrected-voltage addition and the unchanged PWL inverse enclose
its current SOC. The exact charge-ratio bound gives its depletion. Thus its
initial SOC lies both in the previous retained interval and in the new implied
interval for every original capacity cell containing its Q. Intersecting
those intervals cannot exclude it.

This is an every-containing-cell statement, including overlaps and shared
capacity boundaries. The stored outer support may still contain false
positives. In particular, propagating a shared interval can admit trajectories
that effectively choose different nuisance values at different times, even
though the true R and tau are fixed. This is a precision cost; it does not
invalidate containment of every fixed admitted pair.

The outward queries and historical-retention arguments then transfer from
certificate003. Excluded cells stay excluded, active SOC0 intervals contract,
and equal-net-charge queries cannot widen. Changing physical charge can grow
current-SOC width because capacity remains uncertain. A prefix with P=0 at every observation
still supplies no capacity discrimination; returning to zero after informative
history retains earlier exclusions.

The staged bank still makes one complete observation a transaction. A negative
status leaves the bank unchanged and does not propagate that sample. A valid
contradiction commits the physical update and empty support. Neither case
silently resets the evidence.

The charge-domain argument is unchanged:

\[
|P_n|=126000000\,Q\,|z_0-z_n|
\le12600000000000<2^{44}
\]

when Q<=100000 microAh and the true SOC trajectory remains in[0,1]. Validated
forcing and convex RC domains supply the remaining arithmetic invariants.
Every admitted update therefore returns OK at every finite prefix under the
complete contract. Age alone causes neither range failure nor loss of true
support. The proof is conditional on the model/error/storage/delivery premises;
it is not a claim about an aging physical cell or the full original estimator.

The parameter box must be immutable. Widening it after historical exclusions
can make formerly rejected configurations compatible with the old observations.
Checking that the new endpoints are well formed would not justify retaining
those exclusions. That operation needs a separate history/transport proof.

## 5. U6: adding uncertainty must not create spurious precision

The experiment includes a public nominal singleton control and the uncertain
box on the same observations. For this comparison, it explicitly certifies
that the nominal computed attenuation interval lies inside the box interval
for every tick in the declared future alphabet, including zero-time identity.
Physical parameter containment alone is insufficient to assert that property
for rounded numerical enclosures.

Given that extra certificate and common priors, scales, R0/OCV, initial states
and admitted inputs, monotonic interval propagation preserves nested RC states.
Voltage inversion, initial-SOC intersection and target projection preserve
the same inclusion. Every active nominal cell and its meaningful SOC0 support
remain inside the uncertain bank's support. Frozen fields of excluded nominal
cells have no support meaning and need not remain nested.

This gives an all-prefix comparison theorem on the certified alphabet and a
useful implementation canary. It requires no positive contraction margin.
The uncertain provider's soundness for the full continuous parameter box is
already established by U1-U5 and does not depend on the nominal comparison.

## 6. Frozen experiment and reference comparison

The public stress box is R=[54,66] milliohm and tau=[27,33] seconds for the slow
mode, an explicit +/-10 percent interval around the previously declared public
60 milliohm/30 second model. It is not a measured calibration result. The box,
trace, cases and usefulness gates are selected before numerical development.

The same 3,675-sample phase shape as003 is used: 5 seconds of unexcited rest,
35 seconds of charging, 30 seconds of quiet rest and 35 seconds of renewed
charging. The actual tick pattern is retained. Five complete cases exercise
the public midpoint and all four R/tau corners. A separate fractional-parameter
case checks continuous interior values, and other small canaries cover signed
charge, shared capacity boundaries, entering-state uncertainty and errors.

Truth remains in generation/scoring. Every full case uses the same public
uncertain configuration. The generator supplies observations, and an independent
positive-series rational exponential oracle checks the exact modeled state.
The voltage admission interval remains a declared hard +/-1 mV assumption.

Each full case must retain truth and prior evidence, leave capacity unresolved
at zero charge, and preserve quiet-use queries. Strict capacity/evidence
narrowing after each informative phase is the same usefulness gate used in003.
A failure remains recorded; it does not authorize changing the uncertainty box
or a gate to obtain a pass. Useful precision and soundness are separate outcomes.

### Keeping the original C reference

The frozen three-mode solver's slow-tau support ends at 30 seconds, which would
exclude part of the chosen box in its original coordinates. The new harness
uses a public exact unit transformation while retaining the old solver source:

\[
\Delta t'=\Delta t/2,\quad I'=2I,\quad
R'=R/2,\quad \tau'=\tau/2.
\]

Capacity, SOC, voltage and initial RC voltages are unchanged. The identities
I'*dt'=I*dt, dt'/tau'=dt/tau and I'*R'=I*R preserve the exact trajectory and
objective. Known fast time constants map to 0.025 and 0.25 seconds, inside the
frozen solver bounds. The free slow-tau support maps back to physical [3,60]
seconds and the free resistance support to [0,2] ohm. These cover the complete
certificate box but remain broader supports, so this is not an equal-domain
likelihood comparison.

The selected R/tau, SOC0 and capacity are free in this comparison. No synthetic
unknown parameter is supplied as a fixed value or start. The three public
solver-coordinate starts are unchanged; their physical tau values change with
the unit map. Reported tau, R and physical time are converted back by two;
charge, SOC, capacity, objective and CPU time are not scaled.

The raw four-coordinate Gram uses the solver's stated scales. In particular,
R'/.2 corresponds to physicalR/.4. It is a local diagnostic at the returned fit,
not a coverage claim or marginal SOC/capacity precision while nuisance values
are free. Exact model invariance also does not imply bitwise floating-point
identity between different evaluation paths.

### Primary results and preserved failures

The primary source revision is
`beaf30e6da0445c5220701d239b336c6805dacab`. The receipt SHA-256 is
`d996c70d60a2c1f996d1c4e9924925bbe3c01edce86a1fc0bd509093aab88928`.
All 25 source/proof/plan files matched the committed source and stayed unchanged.
All 164 preserved pre004 files matched the base before and after the run.
The primary executed once in about 6.61 seconds and returned status 1 because
the predeclared usefulness conditions did not all pass. It completed as planned.

| Public midpoint checkpoint | Time (s) | Active capacity bins | Capacity hull (mAh) | Current-SOC grid hull | SOC width (percentage points) |
| --- | ---: | ---: | --- | --- | ---: |
| Unexcited rest | 5 | 64 | [30,100] | [34730,34739]/65536 | 0.01373 |
| Informative charge | 40 | 5 | [61.718,67.187] | [35867,35972]/65536 | 0.16022 |
| Quiet rest | 70 | 4 | [62.812,67.187] | [35870,35957]/65536 | 0.13275 |
| Renewed charge | 105 | 3 | [62.812,66.093] | [37043,37174]/65536 | 0.19989 |

Quiet use can refine capacity after earlier nonzero-charge history: the relaxing
RC state helps constrain current SOC, which combines with retained initial-SOC
constraints and charge history. This does not contradict the all-zero-charge
inability to distinguish capacity. In this midpoint case both target hulls
narrow during the quiet phase; the later current-SOC width increase reflects
propagation of remaining capacity uncertainty while the historical strips
continue to contract.

| Fixed generator/scorer R, tau | Capacity at 70 s (mAh) | Capacity at 105 s (mAh) | All seven usefulness gates |
| --- | --- | --- | --- |
| 60 milliohm, 30 s | [62.812,67.187] | [62.812,66.093] | Pass |
| 54 milliohm, 27 s | [62.812,67.187] | [63.906,67.187] | Pass |
| 54 milliohm, 33 s | [63.906,67.187] | [63.906,67.187] | **Fail: renewed capacity and SOC0-evidence narrowing** |
| 66 milliohm, 27 s | [62.812,66.093] | [62.812,66.093] | **Fail: renewed capacity narrowing** |
| 66 milliohm, 33 s | [61.718,66.093] | [62.812,66.093] | Pass |

Every row uses the same full uncertain inference box. The row labels are fixed
parameters used only to generate and score that case, not fitted inputs.
All cases preserve truth containment and earlier evidence. The two capacity
failures retain a 3,281 microAh hull width. For 54 milliohm/33 s the sum of
active SOC0 interval widths stays 27 grid units; for 66 milliohm/27 s that sum
does decrease from 23 to 22, despite unchanged capacity-bin endpoints.

These are exact failures of strict narrowing. They are not arithmetic or
containment failures and do not establish that no more information is present
in the observations. Finite capacity bins and discarded nuisance correlations
can leave conservative support. Determining which cost dominates needs a
separate comparison; this checkpoint does not assign the cause by assumption.

The receipt records 11,501 top-level assertions with two failed usefulness
summary gates. Its 234,658 nested assertions contain three failed usefulness
leaf gates. Those summary and leaf failures overlap. All 226,635 full-trace
soundness checks, 7,615 nested boundary checks, 373 fractional-parameter checks
and remaining soundness controls pass. There are 35 nested usefulness checks,
of which 32 pass. Neither the counts nor their sum supplies the lifetime proof.

The all-degenerate new provider agrees with frozen certificate003 numerical
fields at every midpoint sample. The uncertain bank contains the nominal
bank's active support and target hulls at every prefix. Every coefficient in
the declared future alphabet also passes the extra U6 nesting certificate.

### All-prefix width and uncertainty contributions

The slow mode's certified constants are g=3,709,543, h=827,214,
b=4,551,618 and Fmax=2,400,000 nV. With B=16,777,216 nV, the bound is
10,429,632.180309... nV, below the full 2B domain width. The future premise
covers all represented currents between +/-200,000 microA and active ticks
998..1002 at 35,000 Hz, with arbitrary exact zero-time identities.

| Slow-mode width contribution | Value, approximately |
| --- | ---: |
| Resistance-forcing term bFmax/g | 2.944806 mV |
| Combined coefficient-span term 2Bh/g | 7.482511 mV |
| Integer endpoint-rounding allowance 2D/g | 0.002316 mV |
| **Total all-prefix bound** | **10.429633 mV, rounded upward** |
| Maximum observed width in any complete case | 1.669448 mV |
| Maximum observed width in the degenerate midpoint control | 0.001027 mV |

The independent coefficient analysis bounds the physical-tau contribution by
about 7.482453 mV and the endpoint-kernel overenclosure contribution by
about 0.0000615 mV. These separate maxima conservatively cover the combined
coefficient term; they need not occur at the same tick. This is a model and
representation uncertainty bound, not 10.43 mV of floating-point drift. The
underlying provider uses integer arithmetic and no libm.

The other two modes retain their prior all-time numerical bounds of
5.32055 nV and 37.06620 nV, with observed maxima 3 and 18 nV. Exact rational
certificates are in the primary receipt. A bounded width remains distinct
from a guarantee of arbitrarily useful SOC/capacity precision.

### Retained-history point fits

All four broader-support SCM_FULL fits converge numerically. Their physical
capacity points are 60.000000, 65.729027, 65.057318 and 64.703064 mAh. At the first
informative checkpoint, the fitted R/tau are about 69.0181 milliohm and 33.0014 s,
outside the declared certificate box. This is permitted by the explicitly
broader comparison support and is not a counterexample to hard-set containment.

The final physical point is R=60.2107599 milliohm, tau=30.0581752 s,
Q=64.7030638 mAh and currentSOC=0.5660573039. Synthetic scoring gives capacity
error 0.004735 percent and current-SOC error -0.0006581 percentage points.
These describe this matched synthetic midpoint case; they do not establish
physical accuracy or coverage.

At zero charge, the four-coordinate Gram has rank 1: it carries initial-SOC
information while R/tau/Q remain unexcited. The later local raw-Gram condition
numbers are about 6.81e7, 1.91e6 and 1.87e5 under the reported scales and threshold.
These are local floating-point diagnostics, separate from convergence, hard
support, global identification and validated coverage.

### Complete owned objects and scoped host resources

| Simultaneous provider object | Host bytes |
| --- | ---: |
| Full backing configuration, including boxes, capacity bins and OCV | 896 |
| Persistent bank | 600 |
| Staged observation workspace | 600 |
| Input sample | 24 |
| Query result | 32 |
| **Owned objects** | **2152** |
| Loose sum of all reported nonrecursive core stack frames | 1320 |
| **Objects plus own-source stack subtotal** | **3472** |

The owned-object increase from 003 is 24 bytes; the scoped object/stack subtotal
increases by 224 bytes. The largest individual reported frame is 640 bytes.
The sum includes initialization and mutually exclusive calls, so it is a loose
own-source bound, not a measured high-water mark. No heap or libm imports appear.
Host text is 4,797 bytes and read-only constants 80 bytes; these are not target
flash measurements. Caller/interrupt/runtime stack and any compiler helper
routines remain additional target costs.

The reference reports 2,471,672 internal retained bytes at the last prefix. Its
comparison harness additionally owns 91,296 bytes of complete input and model/
options/result objects, for a 2,562,968-byte owned subtotal before its stack,
allocator overhead, runtime and OS. Earlier prefixes still retain the full
input buffer in this offline harness. These scopes are explicit and do not
imply equal inference semantics or a complete firmware memory comparison.

The integration suite and targeted strict-C99 ASAN/UBSAN checks pass at the
frozen source. Leak detection is disabled. Development source and results are
archived separately, including the three original failed usefulness gates.
After development, only failure-count reporting, fail-closed resource
inspection and EOF formatting changed in the active auditor. No physical box,
stimulus, provider arithmetic, tolerance or learning gate changed. The original
auditor bytes were recovered and accepted only after matching the recorded
pre-run SHA-256. The primary reproduced all trace, usefulness, degeneration and
width-analysis fields exactly.

Complete Cortex-M23 resources, physical validation and statistical coverage
remain unqualified.

## 7. Remaining gates

The next concrete experiment should partition the same declared R/tau box
into a small fixed number of subboxes, with carried RC state and SOC0/capacity
evidence conditioned on each subbox. Start from a complete cover before the
first observation, preserve every true-containing subbox/capacity cell, and
form outward target unions. The full parameter domain and all 004 failure gates
must remain unchanged. This can test whether retaining more of the static
parameter relationship improves the plateau at an acceptable memory cost.

That is a proposed follow-on, not an implemented fix or proof that partitioning
will resolve the failures. Complete shared backing storage, staging and stack
must be counted. No existing bank may be silently repartitioned or have its
historical constraints reset. Finite resolution and physical ambiguity may
still limit precision after improving the representation.

Measured bounds, uncertain current/time and OCV, other unknown dynamics,
hysteresis, temperature/aging, box transport, delivery, persistence/recovery
and target resources still need separate arguments and evidence. A small
successful trace cannot substitute for either physical validation or the
all-prefix proof.
