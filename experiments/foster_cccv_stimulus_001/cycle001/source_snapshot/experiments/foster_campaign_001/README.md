# Local continuous Foster campaigns and telemetry

Run longer durations, independent synthetic cells, load profiles, voltage-noise
levels and noise seeds without changing the continuous estimator or its prior.
The campaign uses the preserved [Foster implementation](../foster_feedback_001/README.md)
and adds only harness controls, saved physical quantities, plots and summaries.
The history backend receives no cell definitions or truth. The original four-hour
results and source files remain untouched.

From the repository root, a single 24-hour case is:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -B -m experiments.foster_campaign_001.run \
  --hours 24 --cells B --loads cycle --noise-v 0.004
```

For eight cases, each lasting 12 simulated hours, with up to four running at once:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -B -m experiments.foster_campaign_001.run \
  --jobs 4 --hours 12 --cells A B --loads cycle multiscale \
  --noise-v 0.002 0.008 --seeds 314159 --encoding both
```

The runner takes the Cartesian product of cells, loads, noise levels and seeds.
Both coefficient encodings are compared by default. Use `--encoding float32`
for a compact-only run when that comparison is not needed.
Add another number after `--seeds` to repeat every case with another noise
realization. `--jobs N` runs independent cases in separate processes, up to the
smaller of N and the number of cases. The default is `--jobs 1` (serial).
Samples and the two encoding arms within a case remain sequential. Each process
gets one native math thread; the CLI sets BLAS/OpenMP thread limits before
loading NumPy, so the environment prefix above is optional. More workers increase
concurrent RAM and disk activity. A single case cannot use extra workers.

Case IDs, seeds and summary ordering are fixed by the scenario list, even if
cases finish out of order. The parent updates summary files after each finished
case. A failed cell/arm is recorded and independent cases continue. Worker exits
also produce an explicit failure receipt without overwriting partial evidence.
The exit status is nonzero if any case is unresolved or fails.
The output directory is unique by default; `--out PATH` requires a new path.
Each completed case prints its result location, and the final line gives
`summary.json`. `summary.csv` compares arm statuses, final/max errors, target
fractions and three-SD misses. The campaign qualifies the unchanged solver once
before cases and snapshots source, public calibration and exact cell definitions.

Dependencies are Python with NumPy/Matplotlib and a C compiler. No network,
SciPy or interactive display is needed. `--help` lists all options.

## Load and temperature controls

Positive current discharges and negative current charges. `--current-a 0.06`
sets peak commanded amplitude to 60 mA; the default is 30 mA. The admitted
amplitude is 0–250 mA. Current is quantized to 125 µA, with no random current
noise in this control. Every input is delivered at 35 Hz in order; the unchanged
estimator refines and retires every 16 samples, plus a final partial block.

| `--loads` value | Schedule |
|---|---|
| `cycle` (default) | Repeats every four hours: 90 min pulses, 90 min rest, 60 min pulses. Active periods use +50 s, rest 10 s, −50 s, rest 10 s. Each active stage is charge-balanced. |
| `pulses` | Repeats +70 s, rest 10 s, −70 s, rest 10 s continuously. |
| `multiscale` | Five-minute cycle of balanced pulse pairs lasting 0.2, 2, 20 and 120 s per polarity, at 100%, 50%, 100% and 75% amplitude, with intervening rests. |
| `rest` | Zero current throughout; useful as an intentionally unexcited control. |
| `legacy` | The original 160 s pulse clock, with one rest from 1.5 to 3 hours. After 3 hours pulses continue indefinitely. |

The `legacy` schedule's rest cuts through its pulse clock, leaving a small net
charge imbalance. The new repeating `cycle` uses a 120 s period that divides
both active stages. Balanced commanded charge does not force SOC or inferred
parameters to return to their initial values under changing temperature. There
is no truth-based SOC reset, endpoint reflection or hidden current intervention.
A cell leaving the admitted physical/ADC domain produces an explicit failure.

Temperature defaults to a measured, quantized 25 ± 8 °C sine wave with a one-hour
period. Change it with `--temperature-mean-c`, `--temperature-amplitude-c`, and
`--temperature-period-s`; `--temperature constant` uses the specified mean.
The selected temperature range must stay inside the model's 15–35 °C domain.
Arrhenius and linear OCV coefficients remain the same known public calibration.
`--noise-v` is Gaussian **voltage noise SD in volts**. Zero is allowed, but
voltage ADC quantization remains and its variance is included in declared sigma.
There is no random temperature noise or unknown sensor bias in these controls.

## More cells

A and B are the two existing synthetic controls. Custom cells may have arbitrary
positive continuous parameters and ordered time constants; they are not estimator
codebook entries. Copy [cells.example.json](cells.example.json), add named objects,
and select them with `--cell-file` and `--cells`:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -B -m experiments.foster_campaign_001.run \
  --hours 12 --cell-file experiments/foster_campaign_001/cells.example.json \
  --cells A B C --loads multiscale --noise-v 0.004
```

Each object contains all eleven named reference-temperature parameters and
`initial_state: [SOC, v1, v2, v3, h]`. Q is in Ah, resistances in ohms, time
constants in seconds, H and RC states in volts; gamma+/gamma− and h are
dimensionless. Branch capacitances are derived as tau/R. Initial states and
parameters belong only to the synthetic plant/scorer; the estimator's public
prior does not change with the selected cell. The example C is a synthetic
variation, not a measured battery or a claim of physical characterization.

## What you can inspect

Each `case_0000`, `case_0001`, … contains the following PNG and PDF plots:

| Plot | Contents |
|---|---|
| `signals` | Measured/noiseless V and reconstructed estimated V, commanded/measured I, exogenous T. Estimated V uses the assimilated boundary state; it is not a forecast. |
| `states` | Truth and estimates for SOC, v1, v2, v3 and h. SOC is a fraction. |
| `parameters_effective` | Truth and estimates for all eleven parameters at measured T(t). |
| `parameters_reference` | The same parameters at 25 °C, separating reversible temperature response from reference-parameter estimation. |
| `capacitances` | Derived C1, C2, C3 = tau/R at measured temperature. |
| `errors` | Q relative error (%) and SOC error (percentage points), with preferred ±0.5 bands; voltage-fit residuals against measured V and noiseless plant V, each in mV on separate panels. |

Voltage residuals use the assimilated estimate at the same retired-block endpoint
as the Q/SOC errors (estimate minus reference). They are in-sample fit diagnostics,
not forecasts. Only Q/SOC panels have the ±0.5 application bands; voltage panels
use a linear mV scale and a zero reference line.

For long plots, bins retain minimum/maximum envelopes and draw the bin mean;
short pulses are not silently discarded. For a closer view, rerender a saved
interval without rerunning the estimator, substituting your case path:

```sh
python3 -B -m experiments.foster_campaign_001.plot \
  experiments/foster_campaign_001/run_TIMESTAMP/case_0000 \
  --start-hour 2.95 --end-hour 3.05 --out /tmp/foster_zoom
```

Use a fresh output directory. `--no-plots` skips plots during large sweeps; the
same command generates them later. Original plots/results are never overwritten.

Data files preserve full precision and cadence:

- `observations.npy`: every 35 Hz sample, columns dt, I, T, V and sigma.
- `truth.npy`: every plant endpoint, five states, eleven effective parameters and
  noiseless V. Truth is never passed to the estimator.
- `float32_trace.csv` / `float64_trace.csv`: every estimated boundary in physical
  units, effective/reference parameters, derived C, Q/SOC local uncertainty and
  matched truth. There is no averaging or decimation in these CSV files.
- Matching `*_trace.npy` arrays contain the estimated columns. `*_chart.npy`
  records all sixteen chart means and marginal SDs, including log/gap coordinates.
  The exported marginals alone do not reconstruct the live full joint covariance.
- `telemetry.json` declares columns, cadence and valid output row counts.
  **Only the declared valid rows of preallocated arrays may be read after a
  failure.** `inputs.json` likewise declares the valid input/truth prefix.
- Add `--sample-csv` to export every input/truth sample to `samples.csv` as well.
  This can be substantially larger than the binary arrays.

Example loading an estimate array without loading the entire file into RAM:

```python
import json
from pathlib import Path
import numpy as np

case = Path("experiments/foster_campaign_001/run_TIMESTAMP/case_0000")
meta = json.loads((case / "telemetry.json").read_text())
n = meta["valid_trace_rows"]["float32"]
trace = np.load(case / "float32_trace.npy", mmap_mode="r")[:n]
q = trace[:, meta["trace_columns"].index("Q_Ah")]
```

Binary telemetry uses about **31 MB per simulated hour per case with both
encodings**, or 27 MB with one encoding, plus block CSV, plots and snapshots.
Generation, hashing and derived plot reductions use bounded chunks, and arrays
are disk-backed. Files still grow with simulation duration; that is research
logging, not history SRAM. The unchanged history payload is 2,184 bytes per
message; two messages plus a float32 token are 6,269 bytes, before raw samples,
solver workspace and runtime. No complete M23 memory/timing claim is made.

## Checks and interpretation

Run focused harness checks with:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -B -m unittest \
  experiments.foster_campaign_001.test_campaign \
  experiments.foster_campaign_parallel_001.test_parallel -v
```

The ten tests check legacy-input/estimate parity, chunk/seed invariance, load balance,
custom-cell rejection, temperature/chart decoding, reconstructed voltage,
aligned full telemetry, partial retirement, zero-noise ADC behavior, single-arm
reporting and continuation after a failed cell. The parent solver's 55 checks
also run at campaign startup. The [short eight-case smoke](smoke001/summary.json)
covers two cells, two loads, two noise levels and both encodings, with complete
plots. It checks the runner, not long-duration estimation accuracy. All sixteen
arms retired their 1,260 records with no pending samples.

Four additional process-level tests verify serial/parallel byte-identical arrays
and CSVs, actual worker overlap within the selected limit, single native math
threads, failure continuation, stable ordering, invalid-job rejection and worker
crash receipts. The [parallel extension receipt](../foster_campaign_parallel_001/README.md)
records the adaptation separately; original source versions are archived there
and the original smoke results/hashes remain preserved.

The smoke also exposes a limitation that must not be hidden by its completed
status: with zero added voltage noise, the largest float32/float64 Q difference
was **6.73%** (cell A, multiscale load). The largest SOC difference there was
0.247 percentage points. Across the 8 mV cases, maximum Q differences were at
most 0.00199%. These are 36-second learning transients, not converged estimates.
The original four-hour encoding result therefore cannot be generalized to all
noise/stimulus settings; retain both encodings when exploring new regimes.

Reference cell parameters are **stationary**. Effective values change with
temperature; learned aging trajectories are still unimplemented. Uncertainty
is a local Gaussian approximation with unvalidated coverage. The previous
four-hour test's rest-period capacity bias and overly narrow uncertainty remain
unrepaired. Longer runs and varied stimuli now make those behaviors easier to
inspect; they do not establish approximately indefinite operation.
