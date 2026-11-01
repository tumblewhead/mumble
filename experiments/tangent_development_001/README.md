# Tangent resource and proposed-load study

The [registered plan](../../specifications/tangent_development_001/README.md) now
has a runnable desktop checkpoint study. It compares field64 and tangent64 on
matched evidence and adds a separately labeled tangent nonlinear-geometry
diagnostic. Estimator sources, mainline and the default backend are unchanged.

Run the full first study from this worktree:

```sh
cd /home/easy/proj/mumble/.worktrees/field-comparison-plots
python3 -B experiments/tangent_development_001/run.py --jobs 1
```

This restores the 12 registered checkpoints, replays 16,384 subsequent records
per prefix, repeats timing five times from freshly restored state, and evaluates
20 tasks at three refresh phases: 720 paired forecasts plus 720 geometry
diagnostics. It does not repeat the preceding 72-hour campaign. A new local
output directory is created automatically; existing directories are never
overwritten. The final line prints the `summary.json` path to share for review.

Keep `--jobs 1` for the CPU comparison and avoid other heavy work while it runs.
`--jobs N` can process prefixes concurrently, but then every timing summary is
labeled as contended. BLAS is limited to one thread per worker. Simulation,
state restoration, scoring, disk writes and plotting are outside advance timings.
Existing instrumentation compiled into the frozen C backend remains present.

A small smoke command is:

```sh
python3 -B experiments/tangent_development_001/run.py \
  --cases case_0006 --prefix-hours 3 --records 4096 --repetitions 1 \
  --workloads rest60 pulse_120mA_1s
```

Selections are recorded as adaptations, not silently called the full study.
`--campaign` and `--replay-root` can relocate the original evidence and frozen
source worktree. Their contents must still pass the original source, binary,
runtime, calibration and checkpoint checks. The wrapper does not weaken them.
Use the same Python environment as the original campaign; a mismatch is an
explicit failure. The new scripts are copied into each output's source snapshot
before execution. Bulk outputs stay ignored and local.

## Outputs

- `summary.json`: completion, failure and forecast scorecard; diagnostic status
  does not mean calibrated uncertainty or acceptable brownout risk.
- `scorecard.png`: paired host mean/max advance cost and worst voltage-minimum
  error per prefix. Each prefix also gets `forecast_errors.png`, with separate
  minimum/recovery errors before, after and midway between refreshes.
- Per-prefix `binding_parity.json`: original binding and bitwise numerical
  export/import continuation checks. The context imports byte-for-byte; host
  timing counters are excluded from subsequent raw-context comparisons.
- `initial_estimator_state.npz` and `anchor_*_estimator.npz`: full contexts,
  field/root, tangent factor, transport and pending state, with public calibration
  and prior in accompanying initial metadata/arrays. These remain tied to the
  original ABI; they are not portable firmware checkpoints.
- `profile.json` and `timing_windows.json`: uninstrumented repetitions,
  nested inclusive/exclusive phase timings, refresh bursts, C counters, actual
  QR dimensions, solve rounds, persistent object census and separate allocation
  tracing. Inclusive nested times must not be summed.
- `forecasts.json` and `forecast_*.npz`: task predictions, full-joint local SD,
  64 signed latent-direction probes per variant, unsupported directions,
  point-minimum cutoff disagreement intervals and scoring-only attribution.
- `scoring_truth*` and `anchor_*_scoring.json`: harness truth kept separate from
  estimator exports. No truth or future observed voltage enters a predictor.

Plots can be regenerated without estimator work:

```sh
python3 -B experiments/tangent_development_001/plot.py /path/to/study-output
```

The predictor retains inherited SOC, RC voltages and hysteresis. Tasks use public
absolute current commands and constant measured anchor temperature. It includes
both sides of current edges and finds intra-segment stationary points by
recursively isolating roots of exponential sums. The sampling-grid discrepancy
and closed-form/compiled/scalar differences are reported separately. The current
50 Hz tasks have exact integral durations; other rates explicitly report rounding.
No sample selection, estimator smoothing or history feedback is added.

## Qualification and remaining work

The [receipt](../../provenance/tangent_development_001/receipt.json) records 13
focused new tests and 23 existing native/campaign tests, a negative checksum
control, and four selected checkpoint smoke controls. The two late controls
exercise all 20 tasks; the middle-age embedded control exercises the full
16,384-record profile suffix. The full 12-prefix/five-repeat study is left for
the owner to run locally.

These smoke controls score 135 paired tasks and 135 geometry ablations. All
point forecasts complete. The early weak-cycle geometry control retains two
unsupported probe directions explicitly. Across the controls, maximum
closed-form/compiled disagreement is below 2e-13 V. The two late witnesses have
maximum voltage-minimum errors around 0.10 mV in both primary arms; this small
selected result is not a promotion decision or coverage qualification.

The implementation covers the initial T0/T1/T2 diagnostic workflow, with explicit
limits rather than invented completion claims:

- The memory ledger includes persistent host payloads and observed allocation
  peaks, but native LAPACK workspace, nested C/libm stack, allocator overhead
  and complete target solver storage remain unknown. It is not a whole-system
  SRAM bound. The packed shared factor alone is 27,224 B (float64) or 13,612 B
  (float32), already above 10 KiB.
- Actual kernel calls, QR shapes, rolling counters and full-solve diagnostics
  are recorded. Exact dynamic scalar/transcendental operation counts and ARM
  cycles are not instrumented. Native query currently combines transport and
  covariance; the report does not manufacture a finer timing split.
- Local covariance and finite direction probes are not a posterior probability
  certificate or simultaneous path bound. Unsupported probes remain visible;
  they are never discarded and renormalized into a confidence claim.
- Existing anchors do not certify low-SOC coverage. A causal discharge
  continuation, regulated constant-power tasks, temperature changes and hardware
  voltage/transient requirements remain follow-up studies. No low-SOC estimate
  is synthesized from truth.
- The scoring substitutions overlap and are not additive error components.
  Selected witnesses do not replace independent noise/load validation. Aging,
  rare-event risk and long-term qualification remain open.

Use the full scorecard to choose one measured optimization or shared-model
repair. No optimization or default promotion is bundled into this runner.
