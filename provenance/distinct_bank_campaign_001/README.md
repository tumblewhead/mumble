# Distinct-bank campaign integration

The N13e/TaylorH2 stationary desktop history now runs through the existing Foster
campaign harness with `--history distinct-bank` or `--history compare-bank`.
The latter adds the unchanged mainline field arm. Public calibration/prior and
fixed centres are shared, truth remains in the simulator/scorer, and refreshes
replace the same-prefix joint rolling distribution rather than multiplying it
into the history likelihood. The original short bank diagnostic remains intact.

The runner retains independent cell/load/noise cases, parallel workers, embedded
and CC/CV stimuli, nominal35Hz and configurable1/Fs, compact plots, complete local
checkpoints, explicit debug start/stop replay and automatic labeled overlays.
Constant25C is enforced at CLI and backend boundaries. The optional backend
retains TaylorH2 approximation and the supplied unverified NUM coefficient map.
This is a usability integration, not physical certification or promotion.

Eight new campaign tests passed, together with six bank mechanics, seven existing
field integration, and three default-selection tests (24 distinct tests). The
new checks include full/compact bitwise final-message parity, exact trace replay
from an8192-record checkpoint with pending history rows, identity rejection,
rollback after a failure on the second1024-row QR chunk, original-prior-only
replacement, and serial/two-worker parity across six embedded/charge cases with
independent load and noise seeds. The existing field/default tests passed after
the small construction/objective/transport hook refactor. Final summary styling
was additionally checked after making bank curves solid versus dashed control.

A retained two-worker smoke campaign ran two36-second cases at35Hz, noise seeds
1100/1101 and load seed7. Both arms completed in both cases; all22 bank and22
field refresh attempts were accepted. Individual and summary rendering completed,
including11 parameter-comparison pages:32 PNGs and corresponding PDFs in total.
These are integration checks, not convergence or comparative-performance evidence.
The smoke was archived before a presentation-only change making the bank overlay
solid; its source snapshot and hashes remain original. That final style was
validated separately by the plot test. Bulk trajectories/builds/plots stay ignored.

The independent review is recorded in `review_r1.json`; source/evidence bindings
are in `receipt.json`. The review scope is a stationary desktop comparator.
The previous integration receipt's mutable top-level README/PROJECT_STATE/handoff
bindings resolve at base revision31d7a1e. Its original mathematical and numerical
artifacts were not modified.

Memory did not shrink: W94 implies a35,720 B packed binary64 bank factor plus936 B
response state. The C rolling context, tables, prior,4096-row buffer, solver,
transaction backups and Python/QR workspace are additional and reported separately.
No10KiB fit or16MHz timing qualification is asserted. Widths remain provisional
local Gaussians; no deterministic bias floor, temperature/aging history, coverage
or lifetime qualification is implemented. Comparing bank and mainline field also
changes H representation, so it does not isolate RC effects.

See the [usage guide](../../experiments/distinct_bank_campaign_001/README.md).
The next useful action is a user-run stationary campaign, inspecting refresh audit
statuses alongside SOC/Q/RC/H errors; representation and resource reduction remain
separate work.
