# Backward isolation of response error

**The remaining reversal variance mismatch is mainly a carried-RC coupling
error. The reversal mean discrepancy is mostly already present between the
construction and heldout source populations.** The hysteresis shape restriction
is real, but these results change the priority of the next repair.

We derived an exact decomposition of voltage into boundary voltage, OCV
change, ohmic drop, three carried and three forced RC responses, and three
hysteresis terms. All cross covariances are retained. For equal10second charge
and discharge segments under the current fixed-health model, net charge is
zero and the direct OCV-change term vanishes. The algebra reproduces the saved
recurrence within **1.78e-15 V**. Five numerical controls and **1,452 primary
checks** pass. No posterior or conditional fit was rerun.

The [derivation](derivation.md), [primary results](attempt001/result.json) and
[summary](summary.json) distinguish exact identities from finite-sample evidence.
Original construction/heldout populations and all four saved generated batches
were reused at both prefixes, with all13probes preserved. Source histories are
still only0.229/0.914seconds; these future probes do not extend estimator history.

At32records, the10+10second reversal discrepancy separates as:

| Comparison | Mean difference | Variance difference |
|---|---:|---:|
| Message minus heldout | +1.470 mV | +74.673 mV² |
| Construction minus heldout | +1.539 mV | +0.997 mV² |
| Message minus construction | −0.069 mV | +73.677 mV² |

The compressor should not be tuned to cancel mean disagreement in its finite
reference populations. The excess variance persists against construction data
and in every regenerated model batch. Source uncertainty still matters; these
differences and batch ranges are descriptive, not confidence intervals.

A [separately registered follow-up](rc_factor_plan.json) decomposes the carried
response as `r(tau)*F`, where F is the existing stored response amplitude and r
converts its public reference horizon to the probe horizon. Around construction
means, `r*F=mu_r*mu_F+mu_r*dF+mu_F*dr+dr*dF`. All covariances, including the
remaining voltage, are preserved in the [factor result](rc_factor001/result.json).

The change in twice the covariance between amplitude terms and amplitude–gain
interaction terms accounts for **82.69% of the excess variance at32records**
and **97.16% at8records**, relative to construction. The slowest RC mode
dominates this term. Its marginal F standard deviations are already nearly
matched: **14.1601 versus14.1615mV** at32records. This isolates a mixed-moment
defect that marginal variance checks miss. The attribution is algebraic and
coordinate-dependent; it does not uniquely identify a causal conditional.

There is a specific physical reformulation to test. The stored coordinate is
`F=a(tau)*v`, with `a=1-exp(-t_star/tau)`. A physical-v density transforms as
`p_F(F|tau)=p_v(F/a|tau)/a`. Its conditional scale therefore transforms with a.
The current representation instead uses a constant Gaussian scale in F.
Matching marginal F variance while losing its dependence on a can inflate
later response variance. The [reformulation](reformulation.md) gives a symbolic
counterexample and derives a normalized conditional with scale **a(tau)*s**.

The [next repair proposal](next_repair.json) compares the saved baseline,
slowest-carried-mode-only scaling and all-three-carried-mode scaling. It keeps
the means' conditioning features, support, ownership and other fitted
coefficients. The new scale law must be fitted and qualified; this study does
not claim that it has already repaired the posterior. The proposal explicitly
checks mixed response moments, all horizons and heldout generalization.

Separately, the actual truncated log-rate prior has positive physical-rate
log-density curvature above gamma33.37/66.73 for the two directions. The
previous nonnegative-precision family cannot express this within one
conditional. Signed curvature or a known reference density plus a learned
correction remain valid later comparisons. They are not supported as the first
remedy for the RC-dominated variance discrepancy.

**Storage remains2,496bytes of retained numeric payload.** The proposed RC
scale law reuses one scalar per conditional and the existing attenuation;
no additional retained coefficients are required. Full estimator SRAM and
query/build workspace remain unqualified. The offline twelve-term diagnostic
mean/covariance occupies720numeric bytes per probe; the ten-term factor table
occupies520bytes. Neither table is a replacement posterior. The primary desktop
diagnostic took0.909CPU seconds and peaked at66,551,808bytes process RSS.

Original messages and receipts are unchanged; hashes, work caps and new files
are recorded in the [verification receipt](verification.json). The rolling
solver, physical aging and posterior ownership are unchanged. There is no
coverage, long-duration accumulation or firmware qualification.

Reproduce the primary analysis into a new directory:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
python3 -B -m experiments.backward_response_001.analyze \
  --output experiments/backward_response_001/reproduction001
```

The focused controls run with
`python3 -B -m unittest experiments.backward_response_001.test_algebra -v`.
The saved follow-up and closeout scripts use exclusive output paths to protect
the existing evidence.
