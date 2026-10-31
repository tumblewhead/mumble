> New `--loads embedded` profile uses a semi-Markov MCU/radio/flash/LED activity envelope. `--load-seeds` controls workload randomness independently of measurement-noise `--seeds`; both appear in plots and metadata. See the [workload guide](../embedded_workload_001/README.md) for timing assumptions and a crossed-seed command.

> Default plotting keeps all six individual plot families and adds the six all-case overlays in `case_summary/`. Overlays label every seed/arm with consistent colors and precision line styles; no extra `--summary` flag is needed for a new campaign. See [plot controls](../foster_summary_labels_001/README.md).

> The default estimator now uses bounded hysteresis coordinates. See [repair and qualification](../foster_bounded_hysteresis_001/README.md). Use `--hysteresis-chart legacy` for the original control. Physical plot/CSV h remains in [-1,1]; raw chart coordinate4 is eta for bounded runs.

# Local continuous Foster campaigns and telemetry

Run longer durations, independent synthetic cells, load profiles, voltage-noise
levels and noise seeds without changing the continuous estimator or its prior.
The campaign defaults to the optimized C implementation of the
[preserved Foster model](../foster_feedback_001/README.md), with an explicit
`--backend python` reference option. It adds harness controls, saved physical
quantities, plots and summaries.
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

## Compact recording and interval replay

For long runs, add **`--recording compact`** to the campaign command. This opt-in
mode uses the C backend, processes every original observation, and stores compact
plotting summaries plus periodic restart checkpoints. It writes no full sample
arrays, per-block trace/chart arrays, or per-block CSVs. `--recording full` remains
the default for compatibility with existing analysis tools; `--sample-csv` and
the Python backend are rejected in compact mode.

```sh
python3 -B -m experiments.foster_campaign_001.run \
  --recording compact --hours 720 --sample-rate-hz 50 \
  --cells A --loads charge-discharge --noise-v 0.02 \
  --seeds 1100 1101 1102 1103 --jobs 4
```

Each case's `plot_summary.npz` retains counts, means, minima and maxima in at most
`--summary-bins 2000` time bins. Q/SOC errors, voltage residuals and capacitances
are evaluated **before** reduction, so narrow excursions are retained in the
envelopes. Summary bins never enter the estimator. The full-run scores still
include every successful estimator output. Individual plots and `case_summary/`
overlays read these small summaries directly. The default 2,000 bins roughly match a plot’s horizontal pixel budget.
A 6,000-hour run has three hours per bin; zooming these plots cannot recover finer detail.

Checkpoints under `checkpoints/` retain the complete joint C context (including
uncertainty and source/retirement counters), plant state, CC–CV controller state,
and random-generator state. `--checkpoint-hours 1` defaults to approximately
hourly checkpoints; the interval rounds upward to an8192-sample boundary so
generation and all live estimators share a committed boundary. At50Hz the default
is3604.48seconds. An initial checkpoint is always saved. Files and their checksum
index are published atomically. An interrupted write leaves earlier checkpoints
available. This is a local host replay format bound to the exact binary, relevant
sources and runtime; it is not a portable firmware checkpoint format.

To regenerate ten seconds near hour350, with full-resolution arrays and all six
plots, use a fresh destination:

```sh
python3 -B -m experiments.foster_campaign_001.replay \
  experiments/foster_campaign_001/run_TIMESTAMP/case_0000 \
  --start-hour 350 --duration-s 10 --out /tmp/foster_hour350
```

For an explicit three-hour debug window, specify its absolute start and stop:

```sh
python3 -B -m experiments.foster_campaign_001.replay \
  experiments/foster_campaign_001/run_TIMESTAMP/case_0000 \
  --debug-start-hour 350 --debug-stop-hour 353 --out /tmp/foster_350_353
```

Start is inclusive and stop is exclusive in sample indices, rounded down to the
sample grid; stop is clipped to the requested campaign duration. `--start-hour`
is an alias for `--debug-start-hour`, and `--end-hour` aliases `--debug-stop-hour`.
Use either a stop hour or `--duration-s`, not both. Debug output grows with the
selected window, not the whole campaign. A three-hour window at 50 Hz contains
540,000 samples; numeric arrays for both arms need approximately 133 MB, plus
plots and interval event logs. It does not enable raw logging in the original run.

Replay restores the latest preceding checkpoint and advances through the warmup
interval without exporting it. It retains the original source and block
boundaries; the checkpoint posterior is continued without counting old samples
again. The final solve may advance to the next original16-sample boundary, while
saved trajectories cover only the requested interval. `result.json` records
the checkpoint, absolute sample offset, warmup and valid output counts. The full
joint final message corresponds to the recorded solver stop boundary. Failures
remain explicit. Use `--no-plots` to export only the interval's data. This command
creates a separate diagnostic replay; it does not append to the original run.

For both encodings and 2,000 bins, numeric summary arrays occupy about **8.5 MB**
uncompressed, independent of duration and sampling rate. Every bin retains its
count, mean and extrema; it does not preserve the ordering inside the bin.
Temporary reduction buffers, Python/NumPy and plotting need additional RAM.
This controls saved telemetry, not the estimator’s likelihood/history compression.

Compact mode also replaces controller/workload event CSVs with bounded counts
and ordered SHA-256 digests in `events_summary.json`. Workload state dwell totals
remain in `result.json`. Both independent workload RNG streams and their event
deadlines are checkpointed. Interval replay exports event detail as well as
V/I/T, states and parameters. No raw event list grows throughout the campaign.

Each uncompressed C context is 19,416 bytes. With two encodings and hourly
checkpoints, 6,000 hours needs about **233 MB of context payload**, plus the fixed
summary and checkpoint metadata/index, plots and source snapshots. NPZ compression
usually reduces the payload; the startup sizing report is an uncompressed numeric
estimate, not a filesystem quota. Checkpoint storage grows with duration; increasing
`--checkpoint-hours` reduces it at the cost of longer replay warmup. This format
supports interval diagnostics, not automatic resumption of campaign scoring after
interruption. None of these host figures changes Cortex-M23 SRAM accounting.

For a long embedded-workload run:

```sh
python3 -B -m experiments.foster_campaign_001.run \
  --hours 6000 --sample-rate-hz 50 --recording compact \
  --loads embedded --cells A --noise-v 0.02 \
  --load-seeds 7 8 --seeds 1100 1103 --jobs 4
```

That command runs four independent cases (two load seeds × two noise seeds),
with both coefficient encodings. Every observation is still simulated and fitted;
CPU time grows with duration. Storage/index tests at 6,000-hour counts do **not**
qualify 6,000-hour estimation accuracy, aging or uncertainty coverage.

Existing full recordings and their running processes are left intact. They do
not acquire historical checkpoints automatically. Preserve the recorded binary,
source snapshots, campaign metadata and compatible runtime with compact runs;
replay rejects changed inputs/code or damaged checkpoints instead of silently
substituting another execution. [Targeted tests](test_compact.py) compare compact
recording and interval replay against full recording, including joint messages,
noise/controller continuation and failure boundaries.


## Backend and sampling rate

The optimized C backend is now the default. Use `--backend python` for the
preserved reference implementation. The C library is compiled once per campaign
before workers start; its exact source snapshots, build commands and binary hash
are saved under `backend_c/`. There is no silent fallback if compilation fails.
Plant generation, telemetry and plotting remain Python.

Set an integer sample rate of at least1Hz with `--sample-rate-hz`, for example:

```sh
python3 -B -m experiments.foster_campaign_001.run \
  --sample-rate-hz 10 --hours 4 --cells A --loads charge-discharge
```

The default is35Hz. This changes plant integration and observation intervals,
estimator clock, charger control intervals and telemetry timestamps together.
The single default is `DEFAULT_RATE` in [rate.py](rate.py); the CLI overrides it
for a run. The physical sample period is exactly `dt = 1/F_s` seconds. The
estimator reads dt from each observation rather than reconstructing it from a
nominal rate. Sample sequence numbers enforce order. History arithmetic receives
likelihood/transport coefficients, with no rate or elapsed-time decay rule.
Legacy files without rate metadata retain their historical35Hz interpretation.
Load and temperature schedules keep their durations in seconds. The fitting
window remains16samples: about0.457s at35Hz,1.6s at10Hz, or0.16s at100Hz.
Lower rates can miss short stimuli and change estimation behavior; they are not
just a playback-speed setting. `--noise-v` remains the per-sample voltage SD,
without noise-density rescaling. Fractional rates are not supported.

The [rate audit](../foster_rate_audit_001/README.md) finds no35Hz multiplier in
the active physical equations or history conditioning. Clock metadata changes
preserve posterior bytes, but nonlinear estimates are sensitive to retirement
grouping and fitting limits. Rate support does not imply rate-invariant accuracy.

The [integration receipt](../foster_campaign_c_001/README.md) records32 passing
controls and paired C/Python campaigns. One short four-case comparison measured
about15.8× faster estimator calls and4.7× faster case execution including plant
and telemetry, excluding plots. Actual speedup depends on workload and machine.

## Load and temperature controls

Positive current discharges and negative current charges. `--current-a 0.06`
sets peak commanded amplitude to 60 mA; the default is 30 mA. The admitted
amplitude is 0–250 mA. Current is quantized to 125 µA, with no random current
noise in this control. Inputs arrive in order at `--sample-rate-hz` (default35). The estimator refines
and retires every16 samples, plus a final partial block.

| `--loads` value | Schedule |
|---|---|
| `cycle` (default) | Repeats every four hours: 90 min pulses, 90 min rest, 60 min pulses. Active periods use +50 s, rest 10 s, −50 s, rest 10 s. Each active stage is charge-balanced. |
| `pulses` | Repeats +70 s, rest 10 s, −70 s, rest 10 s continuously. |
| `multiscale` | Five-minute cycle of balanced pulse pairs lasting 0.2, 2, 20 and 120 s per polarity, at 100%, 50%, 100% and 75% amplitude, with intervening rests. |
| `rest` | Zero current throughout; useful as an intentionally unexcited control. |
| `legacy` | The original 160 s pulse clock, with one rest from 1.5 to 3 hours. After 3 hours pulses continue indefinitely. |
| `charge-discharge` | Measured-voltage CC–CV charger, rest, variable discharge to a voltage cutoff, rest, repeat. Default charger capability 2C/1C/1.5C; discharge 0.2C/0.45C/0.7C. |

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

## CC–CV charging and variable-load discharge

For longer charge/discharge excursions and a voltage-regulated taper:

```sh
python3 -B -m experiments.foster_campaign_001.run \
  --jobs 4 --hours 12 --cells A B --loads charge-discharge \
  --charge-c 2 1 1.5 --charge-step-s 900 \
  --discharge-c 0.2 0.45 0.7 --discharge-step-s 600 \
  --noise-v 0.002 0.008
```

The capability/load schedules step on the global simulation clock, including
while the other phase is active or the cell rests. `--charge-c 2` keeps the
charger capability fixed at 2C; multiple values model changing charger capability.
During CC the negative current equals the active capability. Once measured V
reaches `--cv-voltage` (default4.06V), a finite-bandwidth integral voltage loop
reduces current, constrained by the active capability. Its declared gain is
`--cv-gain 0.5` A/(V·s). Voltage measurement noise also enters this controller;
there is no truth-based voltage clamp or true-SOC switching.

CV ends after current stays at or below `--taper-end-c 0.05` for
`--taper-hold-s 30`, with measured voltage within one ADC step below the CV
setpoint or higher at termination. `--cycle-rest-s 300` follows charging and
discharging. Discharge uses positive current, steps within each discharge, and
ends at `--discharge-cutoff-v 3.18`. Then charging repeats. All physical states
remain continuous across phase changes; there are no SOC resets.

`--nominal-capacity-ah 0.06` converts C-rates to amperes using an explicitly
declared nameplate capacity, shared across selected cells. At this setting,
2C is120mA and0.2–0.7C is12–42mA. It does not use the cell's hidden actual Q.
The estimator receives the resulting V/I/T samples and declared noise only;
neither the charger schedule nor truth enters its prior or history. For this
profile `--current-a` is unused. Quantization remains125µA; commands outside
the physical model's250mA limit are rejected before execution.

The4.06V default is an **operating setting for this synthetic linear-OCV model**,
chosen for CV entry near90%SOC at2C. It does not force an exact SOC transition
or imply a fully charged100%SOC endpoint. In the first4h cellA control, CV began
at89.1% and89.2%SOC and charge ended near93.4%; discharge reached about16.4%.
Rates, cell parameters, temperature and voltage noise change these values.
Temperature remains the existing exogenous T(t); battery self-heating and a
charger temperature-derating law are not introduced by this profile.

Each case writes `stimulus_events.csv` with measured-voltage triggers, phase
boundaries and scheduled capability/load changes. `inputs.json` and `result.json`
record settings, phase counts, transferred charge and completed cycles. This
adds research logging only, with no change to estimator history payload.
The [CC–CV implementation receipt](../foster_cccv_stimulus_001/README.md) links
the complete four-hour example and targeted validation.

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

After all cases finish, `case_summary/` contains the same six PNG/PDF plots with
all available case trajectories overlaid at 25% opacity. Colors retain their
meaning (truth, float64, float32); each trajectory keeps its own simulated time
axis and min/max envelopes. Individual `case_000x` plots remain available.
`case_summary/cases.json` lists included cases and any skipped cases lacking
telemetry. Unresolved arms contribute their recorded valid output prefix.
`--no-plots` also skips this summary. To create overlays from an existing campaign
without running the estimator, use a fresh destination:

```sh
python3 -B -m experiments.foster_campaign_001.plot \
  experiments/foster_campaign_001/run_TIMESTAMP --summary \
  --out experiments/foster_campaign_001/run_TIMESTAMP/case_summary
```

The summary command also accepts `--start-hour` and `--end-hour` for a shared zoom.

Data files preserve full precision and cadence:

- `observations.npy`: every sample at the selected rate, columns dt, I, T, V and sigma.
- `truth.npy`: every plant endpoint, five states, eleven effective parameters and
  noiseless V. Truth is never passed to the estimator.
- `float32_trace.csv` / `float64_trace.csv`: every estimated boundary in physical
  units, effective/reference parameters, derived C, Q/SOC local uncertainty and
  matched truth. There is no averaging or decimation in these CSV files.
- Matching `*_trace.npy` arrays contain the estimated columns. `*_chart.npy`
  records all sixteen chart means and marginal SDs, including log/gap coordinates.
  The exported marginals alone do not reconstruct the live full joint covariance.
- `*_message.npy` saves the final full joint mean, covariance root and log
  normalizer (273 binary64 values), including cross terms.
- `telemetry.json` declares backend, sample rate, clock, columns, cadence and valid output row counts.
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
encodings at35Hz**, or27MB with one encoding, scaling linearly with sample rate,
plus block CSV, plots and snapshots.
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
  experiments.foster_campaign_parallel_001.test_parallel \
  experiments.foster_cccv_stimulus_001.test_charger \
  experiments.foster_campaign_001.test_plot_summary \
  experiments.foster_campaign_c_001.test_integration -v
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
