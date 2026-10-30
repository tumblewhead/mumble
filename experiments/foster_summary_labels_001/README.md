# Default individual plots and labeled summary overlays

A normal campaign keeps each case's six PNG/PDF plot families and automatically
adds the same six all-case overlays to `case_summary/`. No extra `--summary`
option is needed. `--no-plots` continues to skip both sets.

Each seed/arm pair now has a distinct, deterministic color and label. Binary64
uses solid lines, binary32 dashed lines, and truth dotted lines. Duplicate seeds
across different cells/loads are disambiguated by case directory. A shared legend
keeps the many-arm overlays readable. Colors remain stable across zooms and worker
completion order. Binned extrema and each arm's valid prefix/time axis are retained.

The owner196h run was rerendered to
`experiments/foster_campaign_001/run_bounded_20261030_185906_868310/case_summary_labeled001/`.
Its original individual and summary plots are unchanged:57original PNG/metadata
identities were checked against the existing manifest. The new folder has all
six families, eight cases and sixteen estimator arms. Its `cases.json` records
labels, colors, skipped cases and time range.

Four targeted plot tests and an actual default two-case campaign verify both
individual and summary output. The full targeted suite passes48tests. See
[summary.json](summary.json). Generated images and bulk telemetry stay local.
