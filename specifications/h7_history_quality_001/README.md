# Desktop history-quality and small certificate experiments

The frozen estimator is H7 on parent40c3f04. No estimator, campaign defaults or
production authorization is changed. This branch adds two diagnostic runners,
targeted tests and two individually reviewed conditional proof packets. Review
decisions and exact versions are in the completion receipt; tests alone do not
establish uniform physical bounds.

## History experiment

`experiments/h7_history_quality_001/history.py` compares the H7 compressed
likelihood with direct uncompressed C model evaluation from sample zero. Both
use exactly the same public prior once, Gaussian residual likelihood, source
prefix and coordinate anchor. This isolates compression and transport effects
from ADC-likelihood misspecification and physical-model error. The direct model
uses binary64/libm; its name `Exact` is historical and does not mean exact-real
or globally validated posterior inference.

At each prefix, copy/flush the field without changing the streaming estimator,
locally refit that compressed field from the current public-data estimate, and
evaluate the direct cost, gradient, joint GN precision and transported state at
the same anchor. A returned round_limit/no_descent is retained as a convergence
limitation, not declared a resolved fit. The gradient difference is distinct from
the direct objective's remaining solver gradient.

Compare the full precision through generalized eigenvalues; use the exact-anchor
SOC/logQ query rows to project the gradient defect and report its predicted local
SD displacement. These are local linear/GN diagnostics, not established movement
between global optima or calibrated uncertainty. Optional `--refit` performs a
bounded local direct refit; it cannot prove global uniqueness either.

Probe plus/minus one local SD in each query direction and the weakest
prior-whitened precision direction. Report the sampled range of compressed-minus-
direct NLL, removing additive constants. Unsupported physical/representation
probes remain explicit. Sampling does not prove a uniform oscillation bound and
cannot be substituted into K2 as a certified global posterior error. Cost/ULP
metadata expose a rough cancellation scale, not an arithmetic certificate.

Each direct pass regenerates the identical chronological observations with
bounded chunk buffers; its complete byte hash must match the estimator input
prefix. Hash/order/incomplete-stream errors abort that diagnostic, rather than
being counted as unsupported parameter points. Every input interval is retained.
No posterior is added as fresh evidence, no truth selects an anchor, and no raw
V/I/T file grows with duration. Truth is used only in a final scoring field.

The registered pilot crosses rest, multiscale repeated loads and embedded loads
with0.2/2mV Gaussian sensor noise, cellB, noise seed1103/load seed7,35Hz and60s
refresh. Prefix requests60,600,3600s round upward to original16-sample boundaries.
It is a small mechanism diagnostic, not independent population confirmation.

## Certificate experiment

`certificate_run.py` uses an independent bounded-error fixture, not the Gaussian
noise campaign above. The public family has exact linear OCV/reference temperature,
exact current and duration with zero-order holds, stationary unknown amplitudes
and fixed or1%-uncertain response rates. The eleven uncertain amplitudes include
all initial states, inverse capacity, resistances, H and B=H*h0. Physical gamma
is coupled to Q when gamma/Q is characterized. The1% box is a declared engineering
fixture, not a measured characterization of the earlier cells or a deployment law.

[R0](R0.md) derives validated dyadic interval response coefficients using exact
integer/rational arithmetic and a rigorously bracketed exponential. [C0](C0.md)
derives outer voltage strips and exact verification of LP-proposed dual bounds.
The result is a full joint amplitude polytope outer relaxation over the shape
box. It is not a posterior or a product of independently estimated quantities.
Floating LP solver success is never the certificate: primal feasibility and dual
residual correction are checked with exact rational arithmetic.

Voltage constraints use every175th observation by default while response state
propagates through every sample. Certificate support is a new explicit hard
box, not a truncation silently applied to H7's Gaussian prior. The prototype uses
SOC tolerance0.005 (0.5 percentage point) and Q relative tolerance0.01 as development
objectives, not a device safety specification. Certificate-midpoint authorization
and authorization of the actual H7 point are reported separately. H7 itself
continues to label its output provisional.

The plant generates bounded uniform noise up to0.4mV followed by1/1024V ADC
quantization. The declared total error bound is1mV. At selected observations,
the harness verifies that the complete exact-real physical voltage enclosure
at the hidden fixture amplitude lies within that1mV measurement envelope. This
check includes floating simulator discrepancy and is scoring-only: neither its
truth nor tighter per-sample bounds enter the certificate. Invalid assumptions
make the run fail; they cannot be repaired by enlarging the bound after observing
the result. Common response mathematics is a remaining common-cause risk; the
test suite separately checks independent high-precision physical recurrences.

Rest is a negative availability control; discharge/rest/charge/rest is an
informative control. Both begin with the same broad public support. Successful
authorization proves the endpoint test only under the declared family/envelope.
Unresolved is not proof of physical exclusion or a bad H7 point. Source/configuration,
consumed prefix, exact query endpoints, tested point and observation digest must
be interpreted together from the registration/prefix/result bundle.

## Execution, storage and acceptance

Use an isolated environment with NumPy, Matplotlib and SciPy for the certificate
runner. SciPy1.18.1 is the recorded LP proposal engine; sound dual verification
does not rely on that optimizer being exact. See the experiment guide for commands.
Each output directory is new; prior attempts, failures and hashes are preserved.
Summaries stay running until all cases and final source verification complete.

History retains the existing H7 field/workspace plus bounded raw buffers and
small per-prefix diagnostics. The H7 packed root alone remains50,624B, excluding
the desktop dense100,352B root, pending buffer, native state and workspace.
The certificate retains selected linear constraints and thus grows with selected
observations; its floating LP matrix size is reported, while exact rational/Python
objects and solver workspace cost more. It is proof scaffolding, not an SRAM-ready
history replacement. No target timing, ten-year availability, physical-population
coverage, aging, fault-recovery or brownout certification follows from this pilot.
