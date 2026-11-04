# Distinct-pole bank integration reference

This opt-in desktop experiment connects the supplied signed N13e RC map to
Mumble's full 16-coordinate battery model. It retains three Foster branches,
uncertain incoming RC states, SOC and capacity, and unknown H amplitude and both
directional H rates. The existing TaylorH2 response supplies hysteresis. The
original calibration, prior, fixed centres and full log-shape support come from
the public fields of the [frozen registration](../../provenance/rc_sensitivity_basis_001/full001_registration.json).
Historical fitted queries in that file are not used.

Run from the repository root:

```sh
python3 -B -m unittest experiments.distinct_bank_integration_001.test_bank
python3 -B experiments/distinct_bank_integration_001/run.py --records 512 --out /tmp/distinct-bank-run --refit
```

The output directory must be new. Omit `--refit` for response, sensitivity and
transport diagnostics only. Each run and test suite builds the native direct
model and RC/H helper kernels from source; no pre-existing `.so` or ignored
experiment output is required. The runner writes the command, source and input
hashes, build receipt, synthetic fixture declaration, local diagnostic results,
storage accounting, and observation/factor snapshot. NumPy and a C11 compiler
are required.

The deterministic fixture varies current, noise scale and actual intervals
around the nominal 35 Hz stream. Temperature stays at 25 C. Observations come
from the direct native model at a separately declared perturbed generator plus
seeded noise. Only observation synthesis uses that generator; priors, starts,
centres and objectives do not. This short fixture checks integration, not
estimation performance. Each native voltage row is measured after advancing
its interval, including zero-length intervals. Sample order and source identity
are enforced; rejected rows, reordered/repeated batches and failed QR updates
leave the previous state and factor unchanged.

Each branch uses a fixed 13-pole bank, shared by its free and forced response.
Signed cubic B-spline readout weights depend continuously on the branch's
log-time-constant offset. The map's original coordinates and coefficients are
used without renormalization. All voltage features enter one joint QR factor,
preserving RC, H, SOC and Q cross terms. The analytic feature and endpoint
Jacobians propagate all 16 coordinates, including gamma/Q coupling. Optional
refits reuse the existing `choose_fit`/`solve` and `Exact` objectives: one original
prior and every ordered voltage observation once. Direct, distinct-bank and
TaylorRC/TaylorH2 arms use identical public starts and the same declared support.
Numerical convergence is reported separately from provisional local Q/SOC
uncertainty; it does not establish identification or coverage.

Six targeted tests cover an independent exact-node map against the native model
and its post-step endpoint, residual/score/full-precision QR parity, all-coordinate
finite differences, chunking, rejected-source/order/row transactions and injected
QR failure, and map derivatives/resource accounting. The exact-node map is a
mechanics control, not a claim that N13e exactly reproduces the physical model.
The runner additionally compares 11 public finite shape probes against both the
direct model and the existing Taylor representation. These samples are not a
uniform approximation, positivity, passivity, or monotonicity certificate.

This first adapter deliberately exposes resource failure: its three separate
banks produce W=94, a 35,720 B packed binary64 factor and 936 B retained response
state, before prior, solver, tables and workspace. Dense Python/NumPy QR needs
substantially more memory. It exceeds the W<=34 and 312 B comparison limits and
the approximately 10 KiB full subsystem target. It is not firmware-ready. A union
bank/free-state reduction remains separate work. The supplied map remains
uncertified NUM evidence; stationary 25 C behavior, finite probes and local fits
do not close thermal evolution, aging, indefinite-history rounding, physical
coverage or complete Cortex-M23 resources. Campaign defaults are unchanged.

The [symbolic contract](../../specifications/distinct_bank_symbolic_001/README.md)
and its B1/U1/C1 packets remain the mathematical context and open obligations.
