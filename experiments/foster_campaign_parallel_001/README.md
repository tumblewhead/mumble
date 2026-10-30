# Parallel local campaign extension

`experiments.foster_campaign_001.run --jobs N` now schedules independent cases
in separate Python processes. Default N=1 preserves serial execution. Native
math thread limits are set before NumPy loads, in both the CLI and each worker.
The parent compiles/qualifies the model once and owns the shared summaries.
Each case owns a separate directory, estimator history and deterministic seed.
Samples remain chronological and the two encoding arms remain sequential within
a case. No physical model, objective, uncertainty or history coefficients change.

Four new process tests plus the ten existing harness tests pass. Four short cases
were run both serially and with two overlapping workers: input/truth arrays,
both encoding traces, chart arrays and CSVs were byte-identical. Tests also check
the concurrency cap, seed/case ordering, positive integer validation, continuation
after a failed cell, and preservation of partial results after a worker crash.
This establishes execution equivalence on those controls, not a speedup benchmark
or improved scientific accuracy. All earlier accuracy/aging limits still apply.

[reservation.json](reservation.json) records all 246 artifacts of the original
campaign extension before editing. Its original runner and README are archived
under `baseline/` at their original relative paths; all other original artifacts,
including the original summary, verification and smoke results, remain in place.
The old verification describes that original version; use the archive mapping
when checking the two revised source paths. New evidence is kept separately.

See the [updated local guide](../foster_campaign_001/README.md) for commands and
telemetry. More workers increase concurrent memory and I/O; one case cannot use
additional workers, and no M23 resource claim follows from desktop parallelism.
