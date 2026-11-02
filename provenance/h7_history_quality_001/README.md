# History-quality and conditional certificate pilot

The new desktop experiments expose a measurable repeated-load compression effect,
one H7 availability failure, and a useful conditional SOC/Q certificate on a
restricted characterized family. The estimator and campaign defaults are unchanged.
Two new proof packets were individually reviewed; the repaired experiment method
received a fresh package review. Seventeen targeted tests pass.

[Findings and evidence hashes](findings.json), [completion receipt](receipt.json),
[proof manifest](manifest.json), [contract](../../specifications/h7_history_quality_001/README.md),
[commands](../../experiments/h7_history_quality_001/README.md).

## History findings

The six-case pilot uses cellB,35Hz, fixed25C,60s refresh and noise seed1103/load
seed7. Five cases reach one hour. The low-noise embedded case stops at35,520
consumed records (16.9143 minutes), with35,504 published. The native readout
reports domain status-3; emergency full-field recovery reaches round_limit.
The arm correctly quarantines and withholds current readout. The specific native
domain condition and whether a better recovery procedure is useful remain open;
the failed search does not exclude a physically admissible solution.

Two60s diagnostic compressed fits also reach round_limit. Their metrics are
diagnostics at the returned anchors, not assertions of numerical convergence.
The final summary preserves all these outcomes and is deliberately unresolved.

Repeated multiscale loads were selected for a separate diagnostic follow-up after
the initial pilot. This is an adaptive mechanism study, not independent confirmation.

| Noise | Prefix | Joint gradient defect in local precision metric | Predicted logQ displacement / local SD | Predicted SOC displacement / local SD |
|---|---:|---:|---:|---:|
|0.2mV|1h|1.322|0.104|-0.084|
|0.2mV|4h|3.446|0.204|-0.165|
|0.2mV|8h|5.125|0.268|-0.212|
|2mV|1h|0.242|0.024|-0.018|
|2mV|4h|0.600|0.026|-0.029|
|2mV|8h|0.918|0.039|-0.036|

The signs describe compressed-minus-direct displacement predictions. These are
GN diagnostics, not measured physical bias or proof of an indefinitely growing
error law. A one-hour low-noise direct refit converges under the existing numerical
stop after4rounds: direct Q changes by-0.03483% from the compressed fit, corresponding
to0.1053 local SD versus the predicted0.1041. This supports that one projection
of the gradient diagnostic; it does not prove a global posterior result.

At8h the streaming Q errors are+0.0495% and-0.2862%, and SOC errors are-0.00895
and+0.03892 percentage points for0.2/2mV noise respectively. Earlier values are
not uniformly within the development target: the2mV run has about-1.073% Q error
at1h. Repeated-history discrepancy is growing relative to local precision even
while these late practical point errors remain small. Do not translate sampled
NLL oscillations into a uniform TV/coverage bound.

The [history plot](../../experiments/h7_history_quality_001/repetition_followup001/history_errors.png)
shows the selected prefixes. Direct model passes regenerate identical observations
from sample zero and verify their complete hashes. No raw history file or particle
solver is used. Exact-real arithmetic, physical mismatch and ADC-likelihood
correctness are separate from this common-likelihood comparison.

## Conditional certificate findings

This is a different fixture: stationary linear OCV, exact current/time/25C inputs,
a declared amplitude box, fixed or1%-uncertain response rates, and a1mV hard
voltage envelope. Bounded generated sensor noise, quantization and numerical
plant discrepancy are checked against that envelope at selected observations.
Neither truth nor H7's covariance enters the certificate construction.

The rest control never authorizes the0.5-percentage-point SOC or1% Q objectives;
capacity retains its complete45–75mAh public support. The informative control
authorizes both the certificate midpoint and the actual H7 point by the30-minute
checkpoint for both rate domains (63,008records,1800.2286seconds; an observed
query boundary, not a proved recovery deadline). All20 queried enclosures contain the scored
truth and all selected measurement-envelope checks pass. These are finite fixture
checks, not20 independent population coverage trials.

With1% rate uncertainty at1h:

| Quantity | Outer enclosure | Worst endpoint error for the H7 point |
|---|---|---:|
|SOC|51.99509%–52.07174%|0.04005 percentage point|
|Capacity|59.89342–60.31558mAh|0.35962% relative|

Rounded table bounds are illustrative; stored rational endpoints and exact
predicates are authoritative. The certificate-midpoint bounds are approximately
0.03833 percentage point SOC and0.35242% capacity. Fixed gamma/Q characterization
couples gamma to unknown Q; this is not a full unconstrained H7 family. Hard
bounded-noise conclusions do not certify the Gaussian-noise history campaign.

The [enclosure plot](../../experiments/h7_history_quality_001/certificate_pilot002/certificate_enclosures.png)
connects selected checkpoints for visualization. Connecting/filling between
those points is not a between-checkpoint authorization or an actual reconstructed
SOC trajectory. Read the exact prefix records for authorization.

## Resources, review and next work

The H7 packed field root remains50,624B (49.44KiB), with a100,352B desktop dense
root and additional native/pending/solver workspace. Certificate storage grows
with retained voltage constraints: its floating LP matrix and RHS alone occupy
140,736B (137.44KiB) per rate lane at1h; Python rational objects and LP workspace
are additional. The proof prototype is not an M23 representation.

Initial experiment review found that integrity failures could be classified as
unsupported probes and that an interrupted run could retain a premature completed
summary. Both were repaired, tested and freshly reviewed. Original pilot001
results and source versions remain preserved; pilot002 binds the repaired code.
The proofs establish conditional response/outer-set/dual-query statements, with
runtime and physical assumptions explicit. No aging or lifetime theorem is
instantiated by these trials.

The next focused work is to diagnose the17-minute readout/recovery failure and
attribute the repeated-load gradient defect to physical partitions. That can
identify an approximation error budget before reducing storage. Certificate
constraint selection/compression is a later bounded-memory experiment; dropping
constraints can preserve outer containment but may harm useful authorization.
