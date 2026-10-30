# System comparison and the eventual feedback boundary

The current experiment runs three independent estimators on one frozen source.
Each owns that source once. The legacy C rolling estimator still has its original
approximate history; “rolling baseline” does not mean that it forgets every
previous observation. No output from either estimator enters the other.

The binary32 and binary64 arms use identical model, prior, transport, conditioning
and noise assumptions. Their difference isolates weight encoding and its later
effects on conditional moments. The legacy comparison instead evaluates existing
system behavior: it has a different prior, continuous parameters, an approximate
historical likelihood, fixed 1 mV noise, and no temperature/aging compensation.
Its differences cannot be attributed exclusively to the history representation.

## Required semantics for later integration

Let k be the retired-data boundary, x_k the physical state and current health,
and eta the shared nuisance and temperature-response parameters. A marginal
boundary message has the form

    M_k(x_k, eta) = p(x_k, eta | observations[0:k]).

With a recent window, the joint update is proportional to

    M_k(x_k, eta) * p(x_(k+1):n, observations[k:n] | x_k, eta).

The message owns the original prior and retired observations. The window owns
only the new observations. Integrating out boundary variables gives a marginal
objective; minimizing over them gives a different profile objective. Neither
operation can be silently substituted for the other.

The existing provider interface describes a prior-free likelihood in an
original-entering 16-coordinate chart, with a physical endpoint and solver
Gauss–Newton matrix. The new message describes a posterior mixture in current
health and conditional SOC, with discrete shared nuisance hypotheses. It is not
a drop-in scalar penalty for that interface. A Q-only prior would discard its
SOC, thermal and nuisance dependence. Adding it to the existing legacy factor
would also count its observations and prior twice.

A future replacement must therefore specify the boundary epoch and disjoint
source intervals, carry the joint state/nuisance dependence, define normalized
health transport, and retire each raw observation exactly once. Uncertainty
outputs must retain the message semantics; optimizer curvature alone is not
posterior uncertainty. A marginal mixture may be evaluated by a rolling
optimizer only after its latent variables, derivatives, endpoint propagation
and ownership are explicitly defined and checked.

## How this study informs that work

We first test whether the unchanged message remains useful beyond exactly
supported cell values. Four-hour source-once controls cover a cell between the
current health nodes, smooth aging and combined physical/noise variation. A
failure of the binary64 reference is a model/inference issue to understand
before spending effort on codec precision. A binary32/binary64 difference is
instead evidence about encoding. Small point errors do not validate uncertainty;
three-standard-deviation misses and predictive innovations are reported as
descriptive diagnostics from single trajectories.

No feedback adapter or storage optimization is introduced in this experiment.
The source observations are identical across arms; output cadence differs:
history is scored each sample, legacy at each 16-sample block, and the review
also compares their exactly shared saved checkpoints. Any failed arm remains
explicit and does not stop independent arms.
