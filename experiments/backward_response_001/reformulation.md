# Reformulation after the backward decomposition

The finite results change the priority. Hysteresis has a demonstrated family
restriction, but it is not the dominant additive contributor to the reversal
variance discrepancy. The next repair should target carried RC response.

## Separate compression discrepancy from source disagreement

For any response moment functional M, exactly

```
M(message)-M(heldout)
 = [M(message)-M(construction)]
 + [M(construction)-M(heldout)].
```

This identity applies to variances as well as means; each variance is computed
under its own population. It does not turn the construction population into
posterior truth. At32 records the reversal mean discrepancy is
`+1.4703 = -0.0688 + 1.5391 mV`. Adjusting the compressor to cancel +1.4703 mV
would mostly fit disagreement between finite source populations. The variance
discrepancy is instead `74.6735 = 73.6765 + 0.9969 mV²`; nearly all of it
remains relative to the construction population.

## The missing statistic is a weighted amplitude moment

The existing coordinate stores `F_i=a_i(t_star)*v_i`, where
`a_i(t_star)=1-exp(-t_star/tau_i)` uses the original public frame. At a later
time T, carried response is `r_i(T,tau_i)*F_i`, with

```
r_i = (1-exp(-T/tau_i))/a_i(t_star).
```

For the10+10second reversal T=20seconds. About common construction means
`mu_r, mu_F`, define `dF=F-mu_F`, `dr=r-mu_r`. The exact expansion is

```
r*F = mu_r*mu_F + mu_r*dF + mu_F*dr + dr*dF.
```

The follow-up retains all covariances among the three kinds of term, across
all modes, and with the rest of voltage. The change in twice the covariance
between `sum(mu_r*dF)` and `sum(dr*dF)` accounts for:

| Prefix | Excess reversal variance vs construction | This covariance change | Fraction |
|---|---:|---:|---:|
| 8 | 288.154 mV² | 279.970 mV² | 97.16% |
| 32 | 73.677 mV² | 60.923 mV² | 82.69% |

This term includes centered mixed third moments of amplitude, amplitude and
rate-dependent gain. The slowest mode's self-pair contributes 323.490 and
55.694 mV² respectively; cross-mode terms can offset it. Percentages describe
signed algebraic contributions, not causal probabilities or independent error
budgets. They depend on this declared partition and construction centering.

Marginal amplitude variance is already close. The slowest F coordinate has
construction/model SD22.4603/22.4157mV at8records and14.1601/14.1615mV at32.
Preserving that variance alone therefore cannot fix the later response. The
needed statistics include `E[r*F]` and `E[r_i*r_j*F_i*F_j]`, plus cross terms
with forced RC response and boundary voltage. This is why one favorable
response horizon can coexist with a later variance mismatch.

## A scale law from the physical coordinate transform

Suppose physical carried voltage v has conditional density p_v(v|f). For the
already chosen response coordinate F=a(tau)*v, exact change of variables gives

```
p_F(F|f) = p_v(F/a|f)/a.
```

A bounded Gaussian in physical v with scale s therefore becomes a bounded
Gaussian in F with scale `a(tau)*s` and bounds scaled by the same a. The current
message scales the bounds but learns a constant Gaussian scale in F. Its
truncation does create some conditional variance dependence; it does not
generally enforce the physical scale law. This is a concrete candidate source
of the observed amplitude–gain dependence error. The decomposition by itself
does not prove it is the only fitted-conditional defect.

A simple symbolic counterexample illustrates the issue. Take centered v
independent of tau with variance s² and temporarily ignore support truncation.
Then `Var(F|tau)=a²*s²`. A constant-variance F model that matches marginal
`Var(F)=s²*E[a²]` predicts, at complete relaxation,

```
Var_model(F/a) = s²*E[a²]*E[1/a²] >= s² = Var_source(v).
```

The inequality follows from Cauchy–Schwarz, with equality only for constant a.
Thus exact marginal variance matching can produce systematic long-response
overdispersion. This is an explanatory counterexample, not an exact formula
for our bounded, correlated posterior. With finite physical support, using
the transformed density `p_v(F/a)/a` is still exactly valid, including its
normalizer, and removes this particular coordinate-induced mismatch.

## Smallest discriminating repair

Keep the current means, full conditioning features and physical support, but
fit the RC carried conditional with

```
F_j | f ~ bounded Normal(beta_j' f, [a_j(tau_j)*s_j]²).
```

Its fit can be restated in physical units:

```
target: F_j/a_j,
regressors: f/a_j, including the intercept column,
scale: s_j,
support: (-0.25, 0.25).
```

The normalizing term must remain in the objective. The density in F includes
the fixed Jacobian `-log(a_j)`; it does not change the optimizer but is required
for joint density comparisons. Keep the earlier coordinate Jacobian too:
change-of-variables factors must cancel correctly, not be counted twice.

This changes the conditional scale law, not the input chronology, rate prior,
physical recurrence, number of uncertain variables or number of coefficients.
It introduces no aging/forgetting exponential: a(tau) is the existing physical
RC response. The previous natural hysteresis representation remains intact.

Compare the saved baseline against a slowest-mode-only repair and an all-three
carried-mode repair, using the same source populations and all13probes. Fit
only construction data. Report source disagreement, message-vs-construction
and message-vs-heldout separately. Test the exact mixed response moments above,
not just marginal variance or optimizer gradients. Reuse identical fitted
slow-mode conditionals between the two repair arms where appropriate.

This law is a principled restricted candidate, not a claim that physical v
has constant posterior conditional variance. If residual dependence remains,
the next model must represent supported conditional variance or a physical
reference density plus a learned correction. Such additional flexibility must
be justified by the mixed-moment diagnostic and qualified separately.

**Storage:** replacing the stored F scale by a physical-v scale keeps the
two-component numeric payload at2496bytes. The attenuation a is already used
for coordinate decoding and support. Metadata, solver workspace and full
subsystem SRAM still require measurement. Diagnostic covariance tables are
offline evidence and are not retained by the proposed estimator.

The separate hysteresis shape repair remains a valid later comparison:
allow signed quadratic curvature or factor out the known transformed prior,
with correct posterior ownership. The present evidence does not support using
it as the first remedy for this RC-dominated variance discrepancy.
