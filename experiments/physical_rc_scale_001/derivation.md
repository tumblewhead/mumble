# Physical scaling of carried RC conditionals

The [backward diagnosis](../backward_response_001/reformulation.md) identifies
mixed amplitude–gain moment error, not a marginal amplitude variance deficit.
Keep the existing F=a(tau)*v chart and its full16 Jacobian. Replace selected
conditional scales by a(tau)*s; keep the conditional mean beta'f and all
preceding features. For D=f/a, z=F/a and bounds(-.25,.25),

```
log p_F(F|f) = log Normal(z; D beta, s)
              - log mass((-.25-D beta)/s,(.25-D beta)/s) - log a.
```

The fixed log a term matters for density, but not fitting derivatives. The
joint physical density includes the original chart Jacobian once; the new
conditional factor removes the corresponding F scaling once. Bounds remain
exactly the original scaled bounds. Precision/scale changes here describe
uncertainty, not physical aging or forgetting.

QR whitening must act on the entire D matrix, including its nonconstant
intercept column1/a. Appending another intercept or centering the target and
adding its mean to beta0 would silently change the mean family. We instead
use no target centering, initialize by QR least squares, and standardize the
target, design coefficients and physical support by the residual scale.
The normalized bounded-likelihood objective and analytic derivatives retain
the previous extreme-tail arithmetic repair. BFGS stops with explicit finite
status and no regularization. Report gradient tolerance as a numerical check,
not physical or global mixture convergence.

Fit all12 unique carried conditionals once (three modes, two components, two
prefixes). The slow-only arm reuses the fitted slow conditional of the all-mode
arm. Unchanged conditionals continue to consume sampled preceding F values;
the full16 joint density remains coupled. No observations or prior are added.

Qualification preserves all13probes and separates message-minus-construction
from construction-minus-heldout. Reuse the exact physical partition and the
rate/amplitude product expansion to test the mixed moments behind the repair.
Both new arms and the baseline receive four batches of16384draws. Same seeds
help reproducibility but do not imply exact paired sampling after rejection.

Each selected conditional still stores one scale and the same mean coefficients.
Retained numeric payload remains2496B for two components. Schema semantics,
source metadata, fitting/query scratch and complete subsystem SRAM are extra.
This is an offline research repair; causal rolling integration, aging,
coverage and M23 qualification are separate.
