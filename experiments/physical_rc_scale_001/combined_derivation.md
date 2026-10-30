# Adaptation: combine physical and response information

The preserved endpoint comparison fails to generalize. Physical scaling helps
the slowest mode at8records but worsens its32record predictions. All12fits
meet numerical gradient tolerance. The construction-only derivative at the
constant-F boundary favors physical information strongly for the slow mode
at8records, weakly for one slow component at32records, and opposes it for the
middle mode. These derivatives are registered before the new fit.

For a Gaussian quadratic contribution in physical v and another in F=a*v,
the coefficients of F² add as `J_F+J_v/a²`. Both are nonnegative information
contributions. This motivates a conditional family containing both tested
endpoints:

```
precision_F(tau) = (1-lambda)/s_ref²
                   + lambda*a_ref²/(s_ref²*a(tau)²),
sd_F(tau) = s_ref/sqrt(1-lambda+lambda*(a_ref/a(tau))²),
0 <= lambda <= 1, a_ref = 1-exp(-1).
```

The fixed public reference uses the existing geometric time-constant frame.
Lambda0 recovers constant-F scale; lambda1 recovers physical-v scale with
`s_v=s_ref/a_ref`. Lambda is the physical-coordinate share of precision at
a=a_ref, not an aging rate or an empirical forgetting exponent. The sum law
follows exactly for Gaussian quadratic factors. This fitted bounded posterior
family does not identify actual prior/measurement information separately:
it adds no evidence and does not multiply an already-owned prior again.

The mean remains beta'f, so the overall fit in beta,log(s_ref),lambda need not
be convex. Use constrained first-order checks, not a global-optimum claim.
At lambda0 the feasible gradient condition is g_lambda>=0; at lambda1 it is
g_lambda<=0. Interior solutions require zero gradient. Feasible BFGS solves
its one-bound quadratic subproblem before backtracking, with explicit caps.
Initialize from the saved baseline at lambda0, with no target recentering.

Let rho=(a_ref/a)²-1 and d=1+lambda*rho. The new objective derivative is the
existing per-row log-scale score times `-.5*rho/d`. It includes the bounded
normalizer. Thus the optimizer learns the information balance from construction
samples without manually choosing a scale exponent or predicting from truth.
The matched controls verify both endpoint densities, every derivative and an
interior synthetic fit before battery evaluation. Earlier endpoint failures
remain preserved and the heldout set is used only for the registered comparison.
Because this follow-up was designed after earlier heldout results, it remains
exploratory; those reused heldout populations are not fresh confirmation.

The additional retained cost is one fraction per carried conditional, three
per component, **48bytes total** in binary64. The complete retained numeric
message is **2544bytes**, versus2496before. All other coefficients, frames,
support and source ownership remain unchanged. Complete SRAM/workspace,
causal updates and physical aging are still unqualified.
