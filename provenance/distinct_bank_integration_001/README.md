# Distinct-pole history incorporated as a desktop integration reference

The supplied N13e coefficients now drive an experimental Mumble history backend.
It retains all16 fitted coordinates: three RC branches and incoming voltages,
SOC/Q, R0, H, initial hysteresis and both directional hysteresis rates. Existing
TaylorH2 state propagation supplies H; the full joint likelihood and physical
coordinate derivatives are retained. This is a stationary25C integration, not
an update of the long-running campaign or a memory-qualified candidate.

[Run instructions](../../experiments/distinct_bank_integration_001/README.md)
and [scope](../../specifications/distinct_bank_integration_001/README.md) describe
the new API and CLI. Priors, centres and starts remain public; synthetic generator
parameters only produce observations. Every run freshly builds the existing
native direct/RC/H kernels. Original remote study programs are not rerun.

## Imported artifact and limitations

The user-pasted hexadecimal payload is preserved. The importer checks its3400B
length, SHA256, frame/STOP and declared array layout, then extracts literal
binary64 payloads with pickletools/struct. It never executes pickle operations.
The [JSON map](../../experiments/distinct_bank_integration_001/map_n13e.json)
preserves actual A, uj, um and hu=0.0833333333. No exact1/12 substitution or
silent normalization occurs. The binary hash is
`2ccdc212edc1af5406ff7b6a8872ed2179bf6fcb1c7d39a1319aa41af04bc41e`.

The reported physical/error certificate remains unverified NUM. Import consistency,
column sum checks and finite sampled map checks do not certify positivity, passivity
or uniform approximation error. Original response-envelope and lifetime obligations
remain in force. Unknown-temperature and aging histories are outside this adapter.

## Functional evidence

The canonical [registration](registration.json) and [result](result.json) come
from local run003,512records spanning13.1714simulated seconds with zero and varying
intervals, signed current and varying known noise scale. All three optional joint
fits converged numerically from the unchanged public-start protocol. This short
prefix does not establish identification, performance or calibrated coverage.

| Local diagnostic | Direct native | Distinct bank | Taylor RC/Taylor H |
|---|---:|---:|---:|
| Fitted Q, mAh |55.3214793|55.3215263|55.3994168|
| Q log local SD |0.2977733|0.2977735|0.2978362|
| Transported SOC |0.619134902|0.619134875|0.619117724|
| Transported SOC local SD |0.004978993|0.004979007|0.004986288|

These are same-data fit comparisons, not truth errors. Q remains weakly constrained.
Across11public finite shape probes, the largest voltage discrepancy against the
direct model is23.113uV for the bank versus419.345uV for the Taylor control. Those
probes include unchanged H approximation errors; they are not an isolated bank
certificate, a full-support maximum or a long-run result.

Six targeted tests cover exact-node native post-step response/state parity,
full residual/score/precision cross terms, all16feature/transport derivatives,
chunking, invalid source/order/rows and injected QR rejection, and map/storage
checks. Independent reviews exercise the importer and adapter, and replay the
harness with fresh binaries. Original run001 predates final source-binding and
local-readout additions and is preserved locally. Review found missing helper C
source bindings in run002; its source/results are preserved under originals.
Run003 binds both helper C files before build and verifies them at completion;
all numerical results are unchanged. Run003 is the final evidence.

## Resource result and next gate

The transparent separate-bank layout is W94:35720B packed binary64 factor,
936B live response including retained native helper state,3136B map arrays and
spacing, and85160B distinct retained NumPy arrays. Scratch, prior, solver, stack,
Python/BLAS and application memory are additional. W34/4760B and312B comparison
limits fail explicitly. The adapter retains unused legacy RC/root arrays to
avoid changing reviewed H implementation; they are counted, not hidden.

This reference provides the functional comparator for later sharing/reduction;
it does not grow the accepted M23 budget. Next evaluate a shared-bank/free-response
and H representation allocation with joint error and uncertainty preserved, then
quantization/cumulative-error controls. Campaign temperature/checkpoint integration
needs its own gate. Production defaults and existing estimator implementations
were not edited.

[Adapter/import review](adapter_review_r1.json), [initial harness review](harness_review_r1.json), [fresh harness review](harness_review_r2.json),
[validation](validation.json), and [receipt](receipt.json) bind the accepted scope.
