> Historical scope of the canceled local checkpoint, not the contents of this source-only branch. See `provenance/source_checkpoint_20261030.json`.

# Progress checkpoint,2026-10-30

This checkpoint preserves the development since the posterior-prefix scaling
commit:a continuous Foster rolling estimator, likelihood/state-transport history,
C port and optimizations, campaign tooling, mathematical studies, qualifications,
source snapshots, run summaries and PNG plots. Known failed experiments and
unresolved uncertainty/resource limits remain recorded.

The current continuation is `handoff/CONTINUE.json`. The previous continuation
is archived unchanged. The newest diagnosis is in
`experiments/foster_96h_review_001/README.md`: three bounded-hysteresis failures
reproduced in C/Python, plus a separate sustained-bias seed. A bounded-coordinate
repair has been proposed but has not been implemented.

## Backup scope

[scope.json](scope.json) inventories excluded files and their sizes at capture.
Roughly625GB of owner campaign data stays local: raw observation/truth arrays,
full traces/charts/CSV and duplicate PDF renders. Their original manifests are
retained, with recorded hashes where available. The arrays have not been copied
into Git, and the Git checkpoint is not a backup of that bulk telemetry.
Separate bulk storage is still required if those original arrays must survive
loss of the local machine. No other storage service was used.

All source, public calibration, case definitions, completed summaries, final
joint messages, manifests and PNG plots selected at capture are included.
Frozen development fixtures outside the owner `run_*` directories are included,
including compiler objects explicitly referenced by frozen verification receipts.
Existing earlier exclusions and archive restoration mechanisms remain unchanged.
An ongoing campaign may have provisional metadata; this commit does not imply
that it completed or qualified its estimates.

Run summaries and PNG plots can be reviewed from a clone. Operations requiring
an excluded raw array, including owner-run replay or some plot regeneration,
require that array from local bulk storage. Source-generated new campaigns and
included development controls remain available. See
`experiments/foster_campaign_001/README.md` for the runner.

[checks.json](checks.json) records32 passing targeted tests and a scoped text
scan for common secret patterns. Git objects protect the included checkpoint;
original result manifests preserve the source evidence identities.

## Subsequent experiment ignore preference

During the first checkpoint upload, the user requested `/experiments/` in
`.gitignore`. That rule now excludes future untracked experiment contents.
It does not untrack the experiment files already included in the first checkpoint.
The newly produced196-hour run outputs listed in `followup.json` remain local;
that inventory does not mean their contents were uploaded.
