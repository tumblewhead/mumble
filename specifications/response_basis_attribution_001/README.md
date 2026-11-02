# Response-basis attribution before another compression candidate

Parent2ffa4fa, existing experiment/conditional-architecture-001 branch. Isolated
stationary desktop diagnostics; no production/default or target-kernel change.
Read the partitioned_coefficients_001 report first. Its raw outputs and source
receipts remain unchanged.

Freeze attribution before results: replay the same rest/multiscale/embedded
recipes,35Hz,25C,0.2mV, public prior center, log-rate halfwidth1,51 public queries,
and prefixes21008/35520/126000. Verify each observation digest against followup002.
The domain-exit query remains a refusal test and is not a fit/training point.
The reference is independent direct C; the candidate is the existing response
degree2 square-root field. No plant truth enters a query or attribution.

For whitened residual r, query Jacobian J and approximate counterparts
r+dr,J+dJ, split response/Jacobian defects into RC1,RC2,RC3 and joint directional
hysteresis. Each RC group has its initial-state/resistance columns and its own
log-tau derivative. H has H/B columns and both log(kplus),log(kminus) derivatives.
Do not pretend the two hysteresis rates have independent response histories.
Report their derivative channels separately within the joint H group.

The exact algebraic identity for this diagnostic is

    dg = J^T dr + dJ^T r + dJ^T dr.

For group p, define the one-group replacement defect
`v_p = J^T dr_p + dJ_p^T r + dJ_p^T dr_p`.
For p<q define interaction
`v_pq = dJ_p^T dr_q + dJ_q^T dr_p`.
Expanding dr=sum dr_p,dJ=sum dJ_p gives dg=sum v_p+sum v_pq. The first
term is response error acting through exact sensitivity; the second is sensitivity
error acting through exact residual; the third includes self/cross interactions.
This is signed vector attribution, not additive norms or causal cell-health
probabilities. Record closure defects against the independent total and QR field.
Floating-point errors in nominally exact columns belong in the closure residual.
These are diagnostics over original evidence, not extra independent observations.

Accumulate group row RMS/max voltage and derivative defects, signed gradient terms,
one-group hybrid gradients and group-pair interactions. Only afterward scale
amplitude coordinates as in the previous study and report relative norms against
max(1,||scaled direct gradient||). Prespecify ranking by group norm, but do not
interpret ratios as fractions of statistical uncertainty or fitted parameter error.
Include all groups and interactions even if one dominates. Preserve signed vectors
so cancellation is visible. A small relative norm at an unfitted query does not
certify the posterior neighborhood or coverage.

After attribution, register a separate paired basis intervention chosen from the
identified physical group. Keep inputs/support/probes unchanged. Preserve a common
joint square-root factor and all amplitude cross terms. Record changed polynomial
space/coordinates, degree, dynamic node state, factor and other memory, major
scratch and host CPU; no complete10KiB claim from factor bytes. A new coordinate
must describe the same continuous batteries and use the correct chain derivative.
Do not shrink/recenter the computational box using successful outcomes.

Tests must check attribution expansion/closure, direct-C partition and derivatives,
legacy-baseline parity, shape derivative finite differences, domain handling,
source/order and invalid update behavior. Every new proof/optimization and the
result interpretation require independent review. Finite probes are not uniform
bounds or long-run tests; no long campaign or fitted accuracy claim in this step.

## Registered intervention after attribution001

At one hour H-only replacement dominates the active-load gradient defect (roughly
0.577 versus0.00304 for the largest RC group on multiscale;0.0631 versus0.000120
on embedded). This motivates the following paired exploratory arms before results:

- R2/H2/log: legacy-equivalent response baseline.
- R2/H3/log: increase only hysteresis total degree from2 to3.
- R2/H2/rate: keep degree2 but use normalized linear hysteresis rates.
- R2/H3/rate: combine the two changes to distinguish coordinate/degree interaction.

For either directional rate k, keep exactly the same support
`[k_center*exp(-1),k_center*exp(1)]`. Log coordinate t=log(k/k_center) changes to
`u=(k/k_center-cosh(1))/sinh(1)` in rate-coordinate arms. Nodes are mapped through
this inverse affine transform; the chain derivative is
`du/dlog(k)=k/(k_center*sinh(1))`. RC coordinates remain log-tau degree2. The model,
original prior and reference base measure are unchanged: this is a response basis,
not a reweighted parameter prior. Both hysteresis directions remain joint through
a total-degree tensor subset. All cross terms remain in one QR factor.

Use unchanged native mixed response recurrence; new Python configuration/evaluation
only. Same51public probes,9prefixes and hashes as attribution. Preserve the rejected
out-of-domain query as a refusal. Keep original response-degree2/H7 metrics as
controls. The interventions are outcome-informed exploration, not independent
confirmation. No model domain shrinking, likelihood clipping or parameter fitting.

Packed factors have width34/42 and sizes4760/7224B; live response state312/424B.
Add domain/scalars96B for lower numeric subtotals5168/7744B. These omit rate/projection
and calibration tables, error metadata, prior, solver, stacks/ISR and all scratch.
Report actual retained NumPy arrays and major update/query scratch separately.
A better sampled gradient does not prove a useful fitted estimate or10year bound.
If either intervention improves sampled behavior, the next step remains an
application-query/local-fit check and resource/approximation feasibility, not
automatic promotion. Preserve every worse query and every unsupported outcome.
