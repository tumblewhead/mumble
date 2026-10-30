**Working backward identified a specific coordinate error and produced another
22× improvement on the longer local fixture without adding coefficients.** The
partitioned-history error oscillation falls from 103.494 to 4.7075 NLL when only
hysteresis is represented in its physical rates instead of their logarithms.
The model, original parameter/prior coordinates, uncertainty directions,
degree, query points and separate OCV representation remain unchanged.

This is a representation study, not a new battery learner. Results are in the
[primary receipt](attempt001/receipt.json), with the [plan](plan.json) fixed
before evaluation. A separately registered [follow-up](followup_plan.json)
isolates the newly exposed RC error using exact-component controls; its
[receipt](followup001/receipt.json) is preserved separately. No old result was
overwritten and no long trajectory, optimizer or truth input was used.

**First, separate the two sources of likelihood error.** Write the original
normalized residual at a fixed candidate as r and the approximation error as δ.
Then, exactly,

\[
\widehat L-L=\sum_k r_k\delta_k+\tfrac12\sum_k\delta_k^2.
\]

The first term measures signed correlation with the original residual. The
second is the nonnegative energy of the representation error. Small voltage
errors can accumulate coherently through the first term; they need not behave
like independent observation noise.

For the baseline's worst pair of local queries at 4,096 records, the total
103.494124 NLL span consists of 103.494211 from the linear term and −0.00008665
from the difference of quadratic terms. Across queries the largest quadratic
term is only 0.00020353 NLL. Thus this discrepancy is overwhelmingly a systematic
response approximation interacting with the residual, not the square of its
voltage error and not the raw-moment cancellation failure from the preceding
study. We evaluate the gap identity in long-double accumulation and compare
independent direct residual squares and full QR. No normal-moment objective is
used to rank these interventions.

The fabricated local query candidates have RMS voltage residuals of about
6.68–118.65 mV at 4,096 records, versus the model's 1 mV noise scale. This helps
explain the linear amplification. It does not establish behavior near a fitted
realistic battery trajectory, and the resulting NLL changes are not SOC/Q error
measurements. The historical 0.1 NLL number remains a comparison marker, not a
new physical acceptance requirement or a prerequisite for every future study.

**Second, attribute the same witness pair.** For component errors δj, assign

\[
c_j=\sum_k\delta_{j,k}(r_k+\tfrac12\delta_k),\qquad
\sum_jc_j=\widehat L-L.
\]

We subtract cj at the same two queries attaining the total maximum/minimum.
These signed contributions add to the actual oscillation; independent component
maxima would not. On the baseline local 4,096-record witness:

| Component | Signed contribution, NLL | Share of witness span |
|---|---:|---:|
| Forced hysteresis | 96.8281 | 93.56% |
| Free hysteresis | 3.9396 | 3.81% |
| All RC terms together | 2.7265 | 2.63% |
| OCV | −0.000113 | −0.00011% |

This identifies hysteresis as the first target after the OCV repair. It is not
a universal ranking: at 64 records the slowest RC mode's initial-state response
already contributes about 80.5% of the baseline worst-pair span.

**The symbolic reason.** Define positive and negative accumulated throughput

\[
A_+=\int \max(I,0)\,dt/3600,\qquad
A_-=\int \max(-I,0)\,dt/3600.
\]

The hysteresis free response is exactly

\[
a_h=\exp(-\gamma_+A_+-\gamma_-A_-).
\]

For a finite chronological sequence, the forced response is a sum of terms

\[
b_h=\sum_j s_j(1-e^{-\gamma_{s_j}q_j})
       e^{-\gamma_+A_{+,>j}-\gamma_-A_{-,>j}},
\]

where qj=|Ij|Δtj/3600 and sj is the current sign. Rest contributes no hysteresis
exposure. Multiplying every current by a positive scale ε preserves sign/order
and gives

\[
a_h=1-\epsilon(\gamma_+A_++\gamma_-A_-)+O(\epsilon^2),
\qquad
b_h=\epsilon(\gamma_+A_+-\gamma_-A_-)+O(\epsilon^2).
\]

At order n in ε, each coefficient is a polynomial of total degree at most n in
the physical γ rates. A fixed total-degree-d projector in those rates reproduces
every coefficient through n=d. On a compact fixed rate domain and finite source
history its remaining response error is O(ε^(d+1)). At d=4, this is fifth order.
This follows from the finite sums/products of analytic exponentials and the
projector's exactness on its polynomial space; it is not an assumed aging law.

By contrast, a degree-d polynomial in x+=log γ+ and x−=log γ− must approximate
e^x even in the first-order throughput term. If Π is that projector, its generic
leading free-response error contains

\[
-\epsilon\{A_+(\Pi\gamma_+-\gamma_+)
             +A_-(\Pi\gamma_--\gamma_-)\},
\]

and the forced error has the corresponding difference of the two terms. That
error is generally O(ε), regardless of d being four. Higher orders and signed
cancellations can obscure the asymptotic slope at finite exposure.

The intervention uses an affine coordinate in each physical γ over the SAME
rate interval implied by the frozen log-domain endpoints. Query derivatives
still use the original log parameters, with ∂u/∂log γ=γ/halfwidth. There is no
change to the prior, no Jacobian factor inserted into inference, no domain
shrinkage, no new data weighting and no selected nuisance value. The physical
exponential remains in the response propagation at fixed nodes.

**The prediction was tested.** The fixed 4,096-record current word was scaled by
1, 1/2, 1/4 and 1/8 as a separately declared analytical control. These scaled
currents are not presented as ADC-quantized source records. For the physical-rate
representation:

| Current scale | Peak forced h error | Peak free h error |
|---|---:|---:|
| 1 | 4.48e−8 | 9.69e−8 |
| 1/2 | 1.60e−9 | 3.51e−9 |
| 1/4 | 5.33e−11 | 1.18e−10 |
| 1/8 | 1.72e−12 | 3.83e−12 |

The observed orders approach 4.95 and 4.94 in the final halving, consistent with
the fifth-order prediction. The log-rate arm remains near 3.5–3.7e−6 at scale
1/8, with last-step orders 0.44 and 0.74. Its first-order prediction becomes more
accurate as exposure falls, but these four scales do not fully establish its
asymptotic numerical slope. The closed-form/recurrence free-response comparison
also exposes an approximately 1e−13 arithmetic scale at the smallest exposure;
the smallest measured physical-rate errors should not be extrapolated indefinitely.

**Fixed candidate comparison.** Seven arms, two domains and two prefixes were
registered before evaluation. All retain degree four in dynamic coordinates and
degree twelve in charge-based OCV. Local results use the same 97 available query
points; full-support results use the same 129 points as before.

| Dynamic representation | Local error, 64 records | Local error, 4,096 records |
|---|---:|---:|
| Original log-rate basis | 0.195297 | 103.494 |
| Physical hysteresis rates only | 0.191261 | 4.70751 |
| Physical inverse RC time constants only | 2.80832 | 619.310 |
| Both physical coordinate changes | 2.78205 | 603.951 |
| Full tensor hysteresis, log rates | 0.195308 | 81.3752 |
| Full tensor hysteresis, physical rates | 0.191261 | 4.70250 |
| Full tensor hysteresis and physical RC coordinates | 2.78205 | 603.922 |

The main coordinate change reduces peak forced-hysteresis voltage discrepancy
from 5.46e−7 V to 1.20e−9 V on the longer local fixture. Its total likelihood
improvement is smaller because other terms then dominate. On the full-support
longer fixture it also improves error from 436,272 to 39,983 NLL, but on the
shorter full-support fixture the total error worsens from 2,079.7 to 2,218.2.
Therefore it is a mechanism-supported improvement in the tested regime, not
uniform domination over all queries and histories.

The full tensor restores the ten mixed (i,j) terms with i+j>4 omitted by the
15-term total-degree basis. It helps the baseline but adds little after the
physical-rate correction. The total feature count rises from 75 to 95; packed
QR evidence grows from 22,800 to 36,480 bytes. That is a diagnostic expansion,
not a selected deployment improvement.

**Why the analogous RC change did not work.** With λ=1/τ, the exact RC free and
forced responses are

\[
a(t)=e^{-\lambda t},\qquad
F(t_k)=\sum_{j\le k}I_j\{e^{-\lambda(t_k-t_j)}
                              -e^{-\lambda(t_k-t_{j-1})}\}.
\]

These formulas suggest direct λ coordinates, but the relevant expansion
parameter is elapsed age times λ. Reducing current reduces forced amplitude;
it does not reduce λt or the free transient. Our intervals span small and large
λt across the three RC modes. The weak-throughput argument for hysteresis
therefore does not imply a better fixed-degree RC interpolation. The registered
inverse-time-constant arms worsen the measured discrepancy and are rejected
for this next step. A natural-looking coordinate alone is not a certificate.

**What remains after the hysteresis correction.** On its new worst pair, the
slowest RC mode's free response contributes 4.36090 NLL, or 92.64% of the total
4.70751 span. At 64 records that component contributes 82.17% of the remaining
0.191261 span. It is the parameter-dependent memory of the entering polarization
voltage, v30 exp(−t/τ3), not current-driven polarization or OCV.

The follow-up replaces selected components with the exact source-history
response while leaving all other approximations and queries untouched:

| Exact-component control | Local error, 64 | Local error, 4,096 |
|---|---:|---:|
| None | 0.191261 | 4.70751 |
| Slowest RC free response | 0.057944 | 2.41552 |
| All RC free responses | 0.053108 | 2.42538 |
| All RC forced responses | 0.178374 | 4.43024 |
| All RC responses | 0.00002729 | 0.134332 |

These are diagnostic substitutions using full history, not new bounded
compressors. Removing a component changes which query pair is worst; a 92.64%
contribution at the old pair is not a promise to remove 92.64% of the global
oscillation. Signed cancellation also explains why replacing more terms need
not monotonically improve that maximum. The local historical 0.1 comparison
marker is not used to select an arbitrary stopping point.

**Next symbolic representation target.** Retain the physical-rate hysteresis
coordinate and investigate a separate representation for free RC history.
The endpoint a(t)=exp(−λt) is trivial to evaluate exactly from elapsed time, but
that alone does not repair old voltage evidence. For example, free–free
likelihood products require the source-time Laplace sum

\[
\mathcal L(s)=\sum_k e^{-s t_k},\quad s=\lambda_i+\lambda_j,
\]

and free–observation products require Σyk exp(−λi tk). OCV and forced-response
cross terms require corresponding weighted sums with the same original source
identities. Those weights depend on the other uncertain parameters and cannot
be replaced by fitted point weights. These are concrete functions whose
approximation, chronological transport and complete cost/gradient/GN storage can
be derived next. Discarding old transients merely because the current endpoint
has relaxed would destroy their retained parameter evidence.

**Numerical and resource limits.** The primary completed 28 cases and 1,217
checks. Three full-support inverse-RC arms exceeded the frozen GN comparison
allowance by about 1.092×, with array discrepancies up to 1.71e−4. They are
preserved in the receipt; none is the selected physical-hysteresis-only arm.
All attribution identities, original-C cost/endpoint comparisons, feature
derivative checks and square-root cost controls passed. The exact-component
follow-up completed separately. Total work was 8,715,328 conservative model
steps, below the registered 10,000,000 aggregate cap.

The selected coordinate change adds no features or boundary state. Under the
previous allocation convention its full-QR subsystem remains 30,336 bytes
(29,808 for the previously problematic moment layout); it does not solve SRAM
deployment. This prototype changes response coordinates only in a desktop
diagnostic and has not been connected to the rolling solver. No claim is made
about posterior coverage, calibrated real cells, aging, or a future improvement
factor. The useful result is a predicted error mechanism, a successful targeted
intervention, and a specific next kernel to represent.

Reproduce the primary on a fresh output directory:

```sh
python3 -B experiments/response_symbolic_diagnostic_001/analyze.py /tmp/mumble-response-symbolic-new
```

Numerical mismatches produce a nonzero exit after the complete finite comparison.
The follow-up script binds the saved primary evidence and is not an automatic
retry or an adaptive parameter search.
