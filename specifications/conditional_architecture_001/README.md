# Conditional architecture experiment, stage A

Parent ea3bd99; branch experiment/conditional-architecture-001. This stage
diagnoses the preserved H7 failure and establishes the fixed-public-shape
conditional likelihood control. It does not implement continuous shape
uncertainty, change an estimator/default, or claim a complete M23 design.

## Registered questions

1. Which native domain predicate rejects the embedded B/noise1103/load7/0.2mV
   prefix at35520 records? Change only diagnostic return codes in an experiment
   binary. Compare with the unchanged H7 binary through the same input prefix.
   Preserve all published values and native context parity before failure.
2. At public shapes chosen before data, does a streaming packed conditional
   factor agree with direct chronological C-model likelihood, amplitude gradient,
   joint precision and endpoint transport? Compare H7 at the same queries.
3. Which storage is conditional and which is additional? Do not count fixed
   rates as an optimization of the unknown-rate inference problem.

The reviewed R0 identity supplies the restricted stationary linear-OCV basis.
The implementation reuses existing conditional_packet response/composition,
including public Arrhenius coefficients; finite varying-temperature tests are
checks, not an extension of R0's constant-temperature proof.

## Protocol and predeclared interpretation

Use immutable new output directories and source/build/input hashes. Public
amplitude and shape probes derive from calibration prior values, never plant
truth. Compare prior-free likelihoods; the same original chart prior would add
identically at every common query and is not converted into an amplitude
Gaussian. Fixed-shape q changes must change both gammas to preserve gamma/Q.

Initial representation pilot: rest, multiscale and embedded loads; B, seed1103,
load7,0.2mV,35Hz,25C;600 and3600second prefixes rounded to16samples. Three
public rate vectors (central and two fixed perturbations) and three amplitude
queries; these are probes, not nodes constraining battery support or a posterior.
No truth-based performance selection or fitting is performed in this stage.

Pass fixed-shape parity on supported queries with relative cost error<=1e-9,
scaled gradient/precision error<=1e-8 and endpoint amplitude max error<=1e-9.
Use max(1,norm(reference)) for relative denominators and report absolute errors
as well. These numerical regression gates are not application accuracy budgets
or uniform bounds. Every unsupported query stays visible. H7 deviations are
measured, not judged against these fixed-shape arithmetic gates.

The packed factor is78binary64 entries=624B; shape40B, response72B,
noise/charge-extrema/counter32B give768B of numeric retained payload. This
excludes calibration, identities, object overhead, QR/block scratch, prior and
optimizer. Multiple diagnostic shape factors are NOT a continuous-rate history.

## Next stage and acceptance boundary

Only after this control, compare representations of the coefficient functions
over continuous unknown shapes. Preserve joint evidence, physical transport,
and prior/support semantics. Budget practical SOC/Q and proposed-load forecast
error separately from posterior fidelity. An application allocation remains
open; do not promote a representation until it is chosen and tested.

No replay-free rate adaptation, aging, calibrated coverage, firmware timing,
bounded complete SRAM or autonomous recovery is established in stage A.
All implementation and optimization findings require independent review;
review receipts belong in provenance/conditional_architecture_001.
