# Bounded continuous-coefficient feasibility study

Parent af1b180; experiment/conditional-architecture-001. This is an isolated desktop
representation experiment using the existing native response generator. It does
not select or optimize firmware kernels or change a campaign default.

Freeze before observing candidate results: stationary exact-input linear-OCV
reference at25C,35Hz, public calibration/prior; shape center from the public prior,
log halfwidth1 in all five shapes. Compare tensor degree1, tensor degree2 and
total-degree2 sparse coefficients obtained by projecting the same degree2 tensor
interpolant. All78 augmented likelihood entries remain represented, with A0
dependencies. The sparse scheme removes polynomial terms, not cross entries or
physical parameter values. No prior is added to the likelihood in this study.

An unchanged native response generator evaluates exact RC/hysteresis recurrences
at Chebyshev nodes. Accumulate each Gram entry only on the union of its column
dependencies. Transform nodal values into Chebyshev coefficients. Keep endpoint
response states at the nodes and interpolate them separately. In the sparse arm,
project each block increment and add retained coefficients; discarded terms cannot
be recovered later. This is a candidate, not a proven finite-error compressor.

Use rest, multiscale and embedded stimuli, B/noise1103/load7/0.2mV; prefixes
600s,35520records and3600s. These are arithmetic/representation witnesses, not
independent population samples. Use the earlier failure recipe for the embedded
stream and verify its35520record digest. Include its rejected candidate as a
separately labeled outcome-selected domain-exit query, never a training point.
The candidate must refuse it outside the public box; direct reference can still
evaluate it. No widening of the box is inferred to be safe.

Common public queries: center, +/-0.9 along each normalized shape axis and six
fixed random interior points (seed20261102), using the public mean amplitude and
the existing two public amplitude perturbations. Evaluate all three amplitudes at
each point. These queries are finite probes, not uniform error certificates.
Compare all supported queries against the independent direct C model and H7.
Report absolute NLL defect, scaled joint amplitude/shape-gradient defect, amplitude
precision defect, endpoint SOC/RC/hysteresis error, and scaled precision/augmented
Gram eigenvalues. Do not relabel a negative candidate quadratic as a posterior,
clip eigenvalues or continue into a solver that assumes positive precision.

No numerical acceptance threshold is chosen to turn a result into an accuracy
claim. Exact-node and recurrence controls use existing arithmetic parity scales
(1e-8 relative gradient/precision,1e-9 endpoint); those are regression checks only.
Record local errors and unsupported queries, including failures. No fitted Q/SOC
error, physical coverage, aging, deployment or ten-year guarantee follows from
unfitted common-query probes. PSD failures or large observed defects can reject
these candidates; sampled success cannot certify them.

Report coefficient bytes, live response state, domain/rate/projection/index arrays,
bounded chunk/Gram scratch, transaction copies and host CPU. Separate actual Python
array allocation from hypothetical packed numeric counts; original prior, solver,
registry, platform stack/ISR and Python/library overhead remain additional. Do not
call either subtotal total MCU SRAM. Count operation-size proxies alongside host
times because BLAS/native/Python costs do not predict M23 WCET.

Targeted tests: exact-node direct-C likelihood/transport, chunk regrouping, shape
gradient finite differences, rest null Q information, invalid input/order atomicity,
domain rejection, dependency counts, and omitted-term semantics. Independent review
must inspect representation code/results before accepting conclusions. Preserve
source/build/input hashes and original controls. No long campaign by default.
