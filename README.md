# mumble

C research reference for battery estimation from a 35 Hz voltage/current stream.

The goal is to **estimate what the available stimulus supports, retain earlier
evidence, and explicitly report what remains unknown**. The longer-term target
is a streaming Cortex-M23 implementation. The present fitting path retains and
replays history; it is not yet bounded-memory firmware.

## Start here

| Resource | Contents |
| --- | --- |
| [Implementation guide](README.txt) | Model, units, constraints, interfaces, assumptions and reproduction commands |
| [Study report](report/SCM-35Hz-Results.html) | Self-contained HTML report; download and open locally |
| [Convergence figure](report/SCM-35Hz-Convergence.png) | Stimulus and six-run error versus elapsed physical time |
| [Knowledge figure](report/SCM-35Hz-Knowledge.png) | Per-target unexcited, unresolved and provisional statuses |
| [Project state](PROJECT_STATE.json) | Compact machine-readable checkpoint and next work |
| [Continuation handoff](handoff/CONTINUE.json) | Repository-based instructions and context for the next agent |
| [Study specification](specification.json) | Experiment contract |
| [Input manifest](data/manifest.json) | Six traces, truth for scoring, stimulus and input hashes |
| [Results](results/) | Frozen fit outputs, profiles, compression comparison and verification receipts |
| [Import provenance](provenance/) | Original release hashes and repository portability checks |

## Build and run

The C executable needs a C99 compiler, `make` and `libm`. Python is only needed
for the combined test target, orchestration, independent validation and plots.

```bash
git clone https://github.com/tumblewhead/mumble.git
cd mumble
make

python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements-reference.txt
make test

./build/scm_estimator \
  --data data/cell_a_35hz_s202610240.csv \
  --case cell_a_35hz_s202610240 \
  --modes 3 --method full --sigma 0.001 \
  --starts 3 --max-iter 120 --prefix 31500
```

The example fits the first 900 seconds and prints estimates and uncertainty
qualification as JSON. Sample index is the ordering authority, with an explicit
interval in seconds. Positive current discharges; current is measured in A and
voltage is sampled at the end of each constant-current interval.

Use `--ocv path/to/ocv.csv` for a measured 25 C curve with columns `z,voltage`.
The included benchmark uses a known illustrative curve because the numerical
measured curve was not supplied. It must not be described as real-cell validation.

## Completed 35 Hz study

The main campaign contains two synthetic cells, three noise seeds per cell,
73,500 samples per trace, and ten chronological prefixes: **60 fits**. All
sixteen model quantities, including entering states, are unknown to fitting.
Truth enters independent scoring only.

| Result across six runs | Observation |
| --- | --- |
| Current SOC error below 0.5 percentage points | From the 600 s checkpoint onward |
| Capacity error below 0.5% | From the 900 s checkpoint onward |
| Every resistance and RC time constant below 10% point error | By the 220 s checkpoint |
| Worst final current-SOC error | 0.00350642 percentage points |
| Worst final capacity error | 0.0163354% |
| Numerical stopping status | 50 converged; 10 iteration limits |

“From” means the first tested checkpoint passing the threshold at that and every
remaining tested checkpoint. These are stimulus-specific results under a matched
25 C model, exact current/time, known OCV, and independent 1 mV Gaussian noise.
Local precision and truth accuracy are reported separately. Some R0 and fastest
pole estimates remain unresolved despite useful SOC/capacity estimates.

![35 Hz convergence](report/SCM-35Hz-Convergence.png)

The supplemental event-local comparison retains 723 one-anchor features or
1,442 five-anchor features from 73,500 voltage samples, across 106 event blocks.
Both preserve close fits in the two tested traces. Explicit basis storage still
costs megabytes and increases CPU time. Small feature payload is not complete
firmware memory consumption.

The final quiet-window control shows why earlier evidence matters. A complete
history fit retains useful SOC/capacity estimates; a fit to the last weak-use
window alone remains unresolved despite a similar voltage RMSE.

## Reproduce or inspect

Included results can be inspected without repeating optimization. To regenerate
the study, see [README.txt](README.txt). These commands overwrite their named
generated outputs, so use a work branch when making a new campaign:

```bash
git pull --ff-only
git switch -c experiment/my-next-study
make
make test
OPENBLAS_NUM_THREADS=1 python3 tools/run_streaming.py --workers 3
OPENBLAS_NUM_THREADS=1 python3 tools/run_profiles.py --workers 3
OPENBLAS_NUM_THREADS=1 python3 tools/run_compression.py
MPLCONFIGDIR=/tmp/mumble-mpl python3 tools/make_report.py
git status --short
```

Record the source revision, commands, assumptions and validation before committing
new results. Keep machine-to-machine handoffs compact JSON. Source and evidence
belong in this repository; chat summaries are supporting context.

## Implementation map

- `src/scm_model.c`, `include/scm_model.h`: chronological state propagation and sensitivities.
- `src/scm_features.c`, `include/scm_features.h`: orthogonal projections.
- `src/scm_estimator.c`, `include/scm_estimator.h`: host variable-projection estimator.
- `src/scm_assess.c`, `include/scm_assess.h`: fixed-workspace per-target qualification.
- `src/main.c`: CSV/JSON host CLI.
- `tests/`: model, estimator, projection, constraint and qualification checks.
- `tools/`: data generation, runners, independent scoring and report construction.
- `reference_binaries/`: preserved Linux x86-64 executables for exact study provenance;
  build the source for your own host. These are not MCU images.

## Next work and limits

The priority is a bounded event representation that preserves conditional learning
and earlier evidence. Subsequent experiments should cover measured OCV, sensor
offsets, filtered/correlated noise, model mismatch and parameter drift. The current
study does not validate aging, temperature variation, EOD prediction, or Cortex-M23
latency, SRAM, flash or power. The requested 35 Hz operating point was tested;
20 Hz and 1 kHz comparisons remain separate work.

The original study release manifest is preserved in
[`provenance/study_release.json`](provenance/study_release.json). Repository
adaptations are limited to documentation and relocation of verification helpers;
the recorded study outputs and numerical C implementation are preserved.
