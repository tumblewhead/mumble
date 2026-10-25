# Battery certificate provider 003

## Outcome and scope

This checkpoint connects the integer kernels from stability002 to a concrete
battery certificate provider. The provider maintains a finite outer enclosure
of initial SOC and capacity, propagates physical RC state, and returns outward
current-SOC and capacity ranges. It retains evidence through quiet use without
a growing sample count, likelihood sum or stored trace.

The model is deliberately conditional: R0 and three Foster R/tau pairs and the
encoded OCV curve are known and fixed; capacity and initial SOC are unknown;
entering RC voltages belong to a supplied box; hysteresis and parameter drift
are absent. Each supplied voltage interval must contain the exact terminal
voltage under that model. This bounded-error contract is a separate research
candidate from the preserved Gaussian estimator. It does not identify all
16 quantities in the original study or establish statistical coverage.

The source-level guarantees quantify over every finite prefix satisfying these
assumptions. Physical validity of the assumptions, compiler correctness,
recovery and target qualification remain separate obligations.

The primary experiment passed its declared soundness and usefulness gates.
Capacity narrowed from 30-100 mAh to 63.906-66.093 mAh, retained that range through
quiet use, and narrowed to 63.906-65.000 mAh after renewed excitation. A composed
availability argument now proves that age alone cannot exhaust this provider's
arithmetic or eliminate true support on an admitted stream. This conclusion
uses the model and observation premises, rather than the duration of the test.

Branch: research/indefinite-numerical-stability-003.
Base: d84db851955b3c3c686d0738939059dbcde3ea9b.

| Artifact | Role |
| --- | --- |
| [Contract](../proofs/indefinite_stability_003/contract.json) | Model, units, admissible ranges, semantics and open gates |
| [Lemma ledger](../proofs/indefinite_stability_003/lemmas.json) | Eight provider and query arguments |
| [C API](../include/scm_certificate.h) | State/configuration/workspace layout and status meanings |
| [C source](../src/scm_certificate.c) | Integer provider and outward target query |
| [Tests](../tests/test_certificate.c) | Boundary, plateau, transaction and retention checks |
| [Audit plan](../experiments/indefinite_stability_003/plan.json) | Source-frozen small falsification specification |
| [Primary receipt](../experiments/indefinite_stability_003/receipt.json) | Exact-reference checks, target ranges, comparison fits and memory |
| [Independent review](../proofs/indefinite_stability_003/independent_review.json) | Provider proofs, availability corollary, source operations and audit review |
| [Build checks](../experiments/indefinite_stability_003/build_checks.json) | Integration suite and targeted address/undefined-behavior checks |
| [Verification](../experiments/indefinite_stability_003/verification.json) | Frozen-source, receipt, archive and earlier-evidence integrity |
| [Earlier arithmetic proof](STABILITY_CONTRACT_002.md) | Charge, exponential and scalar-state kernels inherited unchanged |

## 1. The representation and why it changed

A bare fixed SOC0/capacity grid can be sound yet uninformative. If one surviving
SOC0 cell is wide, its initial-SOC freedom can absorb the voltage change caused
by a different capacity. Intersecting cell masks does not narrow that freedom
inside a cell.

The selected representation therefore uses up to 64 **immutable capacity bins**.
Every original bin is crossed with the same initial-SOC domain and entering-RC
box. Each bin carries a separate, monotonically contracting initial-SOC
interval T_j. The mask records which original bins still have nonempty outer
support.

The generic API permits overlapping cells and gaps. The admitted capacity
domain is their union. A returned min/max hull is an outer range and does not
assert that gaps are covered or feasible. The experiment uses contiguous bins.

The capacity cells never move. Their retained SOC0 intervals describe smaller
outer subsets within the original cells. This is an explicit addition to the
bare-mask contract, with its own induction proof. No earlier Gaussian
likelihood or local-precision result is relabeled as a hard exclusion.

This is a bounded-error set-membership construction: it encloses configurations
compatible with supplied error bounds. Set inversion and interval outer
enclosures are established formulations of that problem; see Jaulin and Walter,
[Set Inversion via Interval Analysis for Nonlinear Bounded-error Estimation](https://webperso.ensta.fr/Jaulin/paper_automatica93.pdf),
Automatica29(4),1993. The fixed representation, integer implementation and
proofs here are specific to this checkpoint; no general SIVIA convergence
claim is imported.

## 2. Exact model and units

The physical equations are

\[
v_{i,n}=a_{i,n}v_{i,n-1}+(1-a_{i,n})I_nR_i,
\qquad a_{i,n}=e^{-\Delta t_n/\tau_i},
\]

\[
z_n=z_0-\frac{P_n}{KQ},
\qquad
V_n=U(z_n)-I_nR_0-\sum_{i=1}^3v_{i,n}.
\]

Here Q is capacity in microAh, current codes are microamperes, time is encoded
at 35,000 ticks/s, and

\[
P_n=\sum_{k\le n}I_{\mu A,k}\,t_k,
\qquad K=35000\cdot3600=126000000.
\]

Positive current discharges. Nominal 35 Hz corresponds to 1,000 ticks, but every
actual supplied interval is used in its original order. Current is constant
within each interval and voltage is observed at its endpoint.

SOC endpoints are integers in units of 1/Z, Z=65536. The exact SOC may be real
between grid points. Voltage uses integer nanovolts. Integer milliohm resistance
times integer microampere current gives an exact nanovolt forcing target.
Write x=Z*z and x0=Z*z0 for grid coordinates. Stored T_j, the preimage S_n and
depletion R_j all use these grid coordinates; the physical z and z0 use
fraction units.

The OCV model is the exact continuous nondecreasing PWL map through its encoded
knots. Knots span SOC0 to1. Flat segments are allowed. This is an illustrative
known curve, not a measured-cell calibration result.

### Representable arithmetic

| Quantity | Admitted range or bound |
| --- | --- |
| Net represented charge P | [-2^44,2^44] |
| SOC numerator PZ | Magnitude at most2^60, inside int64 |
| Capacity denominator KQ | Positive and below2^59 for every uint32 endpoint |
| Current limit | At most200,000 microA |
| R0 and each R_i | Integer0..1,000 milliohm |
| RC interval domain | [-B_i,B_i], B_i<=2^30nV; maximum admitted current target fits |
| Observation and OCV voltage endpoints | [-8e9,8e9]nV |
| OCV inverse numerator | At most16e9*65536<2^50 |

SOC ratio endpoints and intermediate sums stay int64 until clipping into the
SOC domain. This matters for small positive capacities: the ratio can be much
larger than an int32 value before the cell is rejected or clipped.

The charge bound concerns signed net charge in a static episode. It does not
bound the sum of absolute lifetime throughput. For the illustrative capacity
domain up to0.1Ah and a trajectory remaining in SOC[0,1], the maximum required
net magnitude is12.6e12 code-ticks, below2^44; repeated admissible cycling does
not exhaust it merely through age.

## 3. C1-C3: from a measurement to a current-SOC enclosure

### Signed charge-ratio enclosure

For capacity cell [Q_l,Q_u], define N=PZ and d_l=KQ_l, d_u=KQ_u.
The SOC-grid depletion interval R_j(P) is

\[
R_j(P)=
\begin{cases}
[\lfloor N/d_u\rfloor,\;\lceil N/d_l\rceil],&P\ge0,\\
[\lfloor N/d_l\rfloor,\;\lceil N/d_u\rceil],&P<0.
\end{cases}
\]

The denominator endpoint choice reverses for charging. Division uses explicit
quotient/remainder corrections; no potentially overflowing ceiling numerator
is formed. Monotonicity in positive Q and outward rounding enclose the depletion
for every real capacity inside the cell.

### Shared RC propagation and voltage correction

With known fixed R/tau, RC evolution does not depend on SOC0 or capacity. The
same three RC intervals therefore enclose all initial-RC realizations in every
capacity cell. The frozen attenuation/state kernels propagate those intervals
with actual dt and exact I*R targets.

For an admitted terminal-voltage interval [V_l,V_u], form

\[
\mathcal U_n=
[V_l+IR_0+\sum_i v_{i,l},\;
 V_u+IR_0+\sum_i v_{i,u}].
\]

The exact model OCV belongs to this interval. These new sums are exact and fit
int64 under the declared bounds.

### PWL inversion, including plateaus

Scan every OCV segment. For a positive-slope segment with SOC coordinates
[x0,x1] and voltage [u0,u1], intersect the corrected voltage interval with the
segment range. If [w_l,w_u] is nonempty, contribute

\[
\left[
x0+\left\lfloor\frac{(w_l-u0)(x1-x0)}{u1-u0}\right\rfloor,
x0+\left\lceil\frac{(w_u-u0)(x1-x0)}{u1-u0}\right\rceil
\right].
\]

A flat segment contributes its entire SOC span when its voltage is admitted.
Knot and endpoint intersections are inclusive. Taking the hull of all
contributions gives S_n, an outward current-SOC preimage. If none contributes,
the exact preimage is empty.

This avoids assigning one arbitrary SOC value to a voltage plateau. A plateau
can leave SOC unresolved even when the arithmetic is exact.

## 4. C4: the provider's all-prefix soundness theorem

Let F_n be the complete static configurations (z0,Q,initial_RC) consistent with
the declared model, all observations through n, and the SOC trajectory domain.
These exact compatible sets are nested.

For each original capacity cell j, retain an initial-SOC interval T_j,n and
update it by

\[
T_{j,n}=T_{j,n-1}\cap(S_n+R_j(P_n)).
\]

For any configuration in F_n that belongs to original cell j:

1. Nesting and the induction hypothesis place its x0=Z*z0 in T_j,n-1.
2. RC/voltage/OCV enclosure places its x_n=Z*z_n in S_n.
3. The ratio enclosure places its grid depletion in R_j(P_n).
4. The identity x0=x_n+P_n*Z/(K*Q) places x0 in the new intersection.

Thus every globally compatible point survives in **every original cell that
contains it**, including shared closed-bin boundaries and overlapping cells.
Clearing a bit when T_j becomes empty is a sound whole-cell exclusion.

Because SOC is affine during each constant-current interval, initial and
endpoint-domain containment also covers the continuous interval between them.
The retained strips conservatively carry these endpoint constraints forward.

The outer representation can retain false positives. Different points within
a bin can explain different observations, and RC/SOC/Q correlations are not
stored exactly. A nonempty outer set does not prove exact feasibility.

## 5. C5-C6: queries and evidence retention

At any admitted checkpoint, the current-SOC query is the hull across active
cells of

\[
(T_{j,n}-R_j(P_n))\cap[0,Z].
\]

The capacity query is the hull of the original active capacity intervals.
The provider returns bounds, active cells and a support flag. Empty support is
explicit inconsistency; numerical output fields then have no estimate meaning.

Both hulls contain every globally compatible target value by the preceding
invariant. Query width is separate from point-fit convergence, truth error,
local precision and statistical coverage.

The retained lower SOC0 endpoints can only increase, upper endpoints can only
decrease, and excluded bits cannot return. All live bounds belong to a fixed
integer domain. There is no growing weight or sample count.

When P is unchanged, every R_j(P) is unchanged. Contracting T_j or removing a
cell therefore cannot widen either target hull. Positive-time zero-current
updates still propagate RC relaxation. The persistent evidence is retained
even though the complete physical-state object can change.

Queries intentionally use only these persistent constraints. Replacing an
earlier target constraint with a latest-only voltage interval could allow
precision to disappear during an uninformative quiet observation; that
shortcut is not used.

### Composed conditional availability

For the illustrative capacity domain Q<=100000microAh, an admitted physical
trajectory satisfies

\[
|P_n|=KQ|z_0-z_n|
\le126000000\cdot100000
=12600000000000
<2^{44}.
\]

Thus its charge range follows from the static model and SOC domain, independent
of lifetime throughput. Valid configuration and admitted inputs keep all new
arithmetic inside the proved ranges. The retention induction preserves every
cell containing the actual complete configuration, so support remains nonempty
and the bank remains valid.

Consequently every admitted push returns success at arbitrary prefix length;
age alone causes neither range failure nor committed inconsistency. This is a
composed conditional availability/containment/retention theorem for the new
provider. Useful precision and empirical validity of its model/error premises
remain separate requirements.

## 6. C7: one observation is one transaction

The caller supplies a disjoint workspace holding a staged complete bank.
All physical and evidence updates occur in that workspace. Negative errors
return before the final bank assignment, preserving the entire bank unchanged.
The rejected observation was not propagated.

A valid observation that contradicts every model cell has different semantics:
commit the advanced charge and RC state, retain an empty mask, and return
positive inconsistency. Subsequent observations cannot silently restore cells.

This closes in-memory multi-kernel observation atomicity for the new provider.
It does not detect duplicated, missing or reordered inputs, establish durable
recovery, or justify changing a model/cover after an inconsistency. The caller
must keep configuration alive and immutable and preserve acquisition order.

## 7. C8: a concrete conditional-learning condition

A capacity cell is excluded once its new implied SOC0 strip is disjoint from
its stored interval. For example, an SOC band A at P=0 followed by a band B
after positive charge C must satisfy

\[
A\cap(B+C/Q)\ne\varnothing
\]

for a compatible capacity. If A_l>B_u, a necessary continuous-capacity interval
is

\[
\frac{C}{A_u-B_l}\le Q\le\frac{C}{A_l-B_u}.
\]

All quantities in this illustrative relation must use consistent physical
units. The implementation uses the outward integer strips directly, so its
reported capacity hull also includes bin-edge and SOC-grid conservatism.

Sufficiently separated charge levels and informative OCV bands can therefore
exclude whole capacity cells. No fixed convergence time is asserted: wide
voltage/model uncertainty or a flat OCV region can prevent useful refinement.

If P_k=0 at every observation, R_j(P_k)=[0,0] for every bin. Identical initial
priors receive identical SOC0 contractions, so capacity support remains its
initial declared union unless all support becomes inconsistent. Observations
add no capacity discrimination. This is an explicit
anti-sponge case. Returning to P=0 after earlier nonzero-charge observations
does not erase their capacity evidence.

## 8. Experiment, comparison and resource accounting

The source and plan are frozen before the primary experiment; preceding
development checks are disclosed separately. The audit uses an independent
exact-rational reference for charge, SOC, OCV and enclosed RC evolution.
Synthetic truth is confined to generation and scoring. Inference receives
only public configuration and observation rows.

The comparison calls the unchanged retained-history C estimator with SCM_FULL.
Known model parameters are fixed, while SOC0 and Q remain free. It receives the
same encoded PWL model and observations. Its Gaussian objective scale does not
turn the bounded-error trace into Gaussian evidence, and its point estimates
and convergence status are reported separately from certificate widths.

### Frozen primary experiment

Source and plan were committed at
`b3ea96e23896c8909f007e878785e479d5957b56` before primary execution. The primary
receipt SHA-256 is
`8c119ba09227d80a9ac1e7bfec883b89e7722756b36622326f4da456ad5ed475`.
All 17 listed source, proof and plan files matched that commit and remained
unchanged during the run. The audit completed once in about 2.27 seconds.

The 3,675-observation trace spans 105 seconds. Its actual tick pattern is
1000, 999, 1001, 1002, 998 at 35,000 ticks/s, preserving nominal 35 Hz and the
individual intervals. It begins with 5 seconds of zero current, uses 35 seconds
at -120,000 microA, rests for 30 seconds, then repeats the 35-second charge.
This is a synthetic laboratory stimulus, not hardware operating guidance.

The public model uses R0=20 milliohm, R=[30,40,60] milliohm,
tau=[0.05,0.5,30] seconds, an exact nine-knot encoded PWL OCV, and known zero
entering RC voltages for the main comparison. Each observation supplies a
hard +/-1 mV interval. The deterministic generator perturbation is at most
0.9 mV, and the independent oracle checks the complete noiseless enclosure
against every supplied interval. This is an explicit bounded-error assumption;
the original study's Gaussian 1 mV scale does not justify it.

The 64 capacity bins partition 30-100 mAh with shared closed endpoints.
The provider SOC0 prior [13107,62260]/65536 outward-encloses the reference
prior [0.2,0.95] by less than one grid unit at each endpoint. This small support
difference is included in the comparison interpretation.

| Phase endpoint | Time (s) | Active bins | Capacity hull (mAh) | Current-SOC grid hull | SOC width (percentage points) |
| --- | ---: | ---: | --- | --- | ---: |
| Unexcited rest | 5 | 64 | [30,100] | [34730,34739]/65536 | 0.01373 |
| Informative charge | 40 | 2 | [63.906,66.093] | [35890,35936]/65536 | 0.07019 |
| Quiet rest | 70 | 2 | [63.906,66.093] | [35890,35936]/65536 | 0.07019 |
| Renewed charge | 105 | 1 | [63.906,65.000] | [37082,37132]/65536 | 0.07629 |

Both informative phases pass the predeclared strict capacity-narrowing and
persistent-evidence-narrowing gates. Quiet use preserves both target hulls.
Current-SOC width can grow during charging because uncertain capacity affects
the conversion of accumulated charge into SOC. Historical SOC0 constraints
still contract, and capacity cells never return. Monotone historical evidence
does not require monotone width for a changing physical target.

The source-level arguments are supported by 45,408 passing top-level assertions
and 7,615 passing assertions inside nested canary traces, with no failures.
Some top-level gates summarize those nested traces; these counts are not
independent experiments. Checks include shared capacity boundaries, signed
charge and return to zero, uncertain entering RC states, OCV plateaus and
knots, extreme legal integer encodings, partial versus complete SOC-domain
exit, rejected-input atomicity, sticky contradiction and uninformative rest.
All tested modeled truth states remain enclosed. Universal containment follows
from C1-C7, not from the number of sampled cases.

Development checks preceded the freeze. The first reference-harness compilation
reported a misleading-indentation warning under strict flags; formatting was
corrected before numerical execution. The development numerical run then passed.
No provider arithmetic, numerical tolerance or usefulness gate was tuned in
response to a failed numerical run. The primary receipt is preserved unchanged.

### Retained-history comparison

All four restricted SCM_FULL fits converged numerically. Their capacity point
estimates were 60.000000, 64.698520, 64.689448 and 64.686933 mAh. All point SOC and
capacity estimates lay inside the provider hulls, a descriptive observation
rather than a hard-set soundness gate.

The first fit is an important control: at zero charge its conditional log-Q
Gram row and column are exactly zero, although it reports convergence and a
60 mAh capacity point. The provider leaves the complete 30-100 mAh range
unresolved. Convergence therefore cannot be used as capacity identification.
After excitation, the reference point estimates are useful comparisons, while
their local curvature remains distinct from hard interval support or validated
coverage.

Synthetic scoring truth is SOC0=0.53 and Q=64.7 mAh. It is absent from both
inference inputs and all starts. The final reference current SOC is
0.5660676211, with scoring error 0.00037365 percentage points, and its capacity
error is -0.02020 percent. Those errors describe this matched synthetic case;
they do not establish physical accuracy or interval coverage.

### Width bounds that do not grow with runtime

For every future active interval in the declared tick alphabet, finite exact
coefficient enumeration supplies the contraction gap g and coefficient span h
required by stability002 lemma L4. Arbitrarily many exact zero-time identities
may intervene. With the same RC model/domain and admitted current, the theorem
gives the following widths for every finite prefix:

| RC time constant (s) | Proved numerical interval width bound (nV, approximate) | Maximum observed width in the finite trace (nV) |
| ---: | ---: | ---: |
| 0.05 | 5.32055 | 3 |
| 0.5 | 37.06620 | 18 |
| 30 | 2162.77485 | 1027 |

The exact rational bounds are in the receipt. These are represented-model
numerical widths in 1 nV grid units. Sensor error, model mismatch and parameter
uncertainty require their own budgets. The bounds are not extrapolated from
the 105-second trace and do not apply to arbitrary future tick alphabets
without checking the contraction premise.

### Complete owned objects and scoped host stack

| Simultaneous object | Host bytes |
| --- | ---: |
| Full backing configuration, including capacity bins and OCV knots | 872 |
| Persistent bank | 600 |
| Staged observation workspace | 600 |
| Input sample | 24 |
| Query result | 32 |
| **Owned-object subtotal** | **2128** |
| Loose sum of every reported nonrecursive core stack frame | 1120 |
| **Objects plus own-source stack subtotal** | **3248** |

The largest reported individual frame is 640 bytes during initialization.
Summing every reported frame, including mutually exclusive branches and
initialization, is a deliberately loose own-source bound; it is not a measured
stack high-water mark. The new provider and inherited integer core import no
heap allocation or libm functions and contain no mutable global data. Their
host object files have 4,205 bytes of text and 80 bytes of read-only constants;
these are not target flash measurements. The compiler adds an external
`__stack_chk_fail` failure path whose runtime cost is not qualified here.

For comparison, the retained-history API reports 119,672, 942,872, 1,648,472
and 2,471,672 retained bytes at the four prefixes. Those are that API's reported
problem allocations, not complete process memory, and the inference semantics
differ. The fixed provider subtotal includes its full configuration rather
than counting only a pointer to caller-owned bins or OCV data.

Acquisition buffers, source-delivery protocol, persistence, caller/interrupt
stack, linked runtime and target-specific code generation remain additional
costs. The approximately 10 KiB system target is not qualified by this component
subtotal. The complete integration suite and targeted ASAN/UBSAN checks passed;
the sanitizer run disables leak detection and does not constitute a leak audit.

## 9. Remaining work

This provider closes a useful restricted inference path under explicit
assumptions. It does not justify those assumptions for a real cell.

The next concrete extension is one bounded uncertain RC mode: a fixed R/tau
box with outward forcing and attenuation intervals, an all-prefix width
recurrence, and the same informative/quiet/renewed-excitation test. This removes
one known-parameter premise while making any loss of useful SOC/capacity
precision visible. It must retain true configurations for every parameter in
the declared box and cannot reset earlier evidence when uncertainty grows.

Beyond that extension, the requirements are experimentally justified
voltage/current/model uncertainty, other unknown dynamic parameters and
hysteresis, OCV uncertainty, temperature and drift handling, and a proof for
any refinement/transport that changes the finite cells. A per-sample current
error bound alone does not prevent accumulated charge ambiguity from growing;
its treatment needs an explicit lifetime argument. Persistence and
source-delivery semantics remain open. Complete Cortex-M23 memory, stack,
arithmetic timing, flash and power still need target measurements.

The original 35Hz reference, B001/B002 results, their failures and provenance
remain comparison evidence. No long campaign is rerun merely to resume.
