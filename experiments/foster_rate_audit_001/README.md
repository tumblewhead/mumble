# Sampling-rate and elapsed-interval audit

The campaign has one user setting, `--sample-rate-hz F_s`, and derives the physical
interval as **dt = 1/F_s seconds**. The default now comes from one definition,
`DEFAULT_RATE` in [rate.py](../foster_campaign_001/rate.py), shared by the CLI,
stimulus and charger APIs. Legacy telemetry lacking rate metadata keeps its
historical35Hz interpretation. The multiscale stimulus is now expressed in fifths
of a second, removing its confusing historical35Hz schedule units with byte-equal
default behavior. No estimator or history arithmetic was changed.

The physical estimator needs dt: SOC uses I·dt/(3600Q), RC decay uses exp(−dt/τ),
and hysteresis uses γ|I|dt/(3600Q). The3600 converts Ah to coulombs. Sample count
alone cannot distinguish the same current applied for10ms from100ms. Identity
and ordering already use source identity and sample sequence; elapsed interval
and evidence identity serve different purposes.

The generic history conditioner consumes likelihood coefficients and transport
matrices. It has no sampling rate, clock, aging multiplier or time-decay rule.
Elapsed physics is already represented in the producer's transport matrix.

## Constants and checks

The active C ingestion layer still has a clock-grid admission check, defaulting
to1050ticks/s and compiled by the campaign with lcm(1050, F_s):2100ticks/s for
100Hz. It verifies that dt is representable and accumulates elapsed metadata;
it passes the original double dt to the physical model. It never substitutes a
rounded interval. Unsupported intervals are rejected before consumption.

The Python adapter supplies the same generalized clock. The frozen original
Python estimator and original standalone plant generator retain1050/35Hz
constants, but the campaign overrides ingestion where needed and uses its own
rate-aware generator. Importing the original plant's `scalar_step` does not call
its old fixed-rate generator. Remaining35°C constants are temperature bounds.
The35.5 in the disk estimate is bytes per sample per encoding, not a time factor.

[result.json](result.json) records eight paired clock controls covering both
backends and coefficient encodings. Identical observation streams, including
variable intervals, produce **byte-identical full posterior messages** under
different admissible clock units. Constant-I/T physical propagation over one
second in1/35/100 steps agrees to4.33e−15 in endpoint coordinates and2.56e−15 in
transport coefficients. No measurement likelihood is added in that propagation
check. These controls do not establish physical identifiability or coverage.

## What does change at100Hz

The fixed16-record window spans0.16s at100Hz versus0.457s at35Hz. There are2.86×
as many nonlinear fitting, local-Gaussian approximation and token encoding steps
per simulated second. The current noise model also draws2.86× as many independent
samples with the same per-sample SD. Sampling times, noise realizations and noisy
charger switching can differ. Thus changing Fs is not only changing clock units.

Replaying the **same54000 observations** from the earlier nine-minute100Hz
integration case, retiring every8 instead of16 samples, changes final binary64
Q by1.876% and SOC by0.295percentage points. Keeping16samples but increasing
the fitter cap from4 to12 rounds changes Q by0.367% and SOC by0.227points.
Each observation is consumed exactly once; no prior or truth is changed.
Binary32 shows similar sensitivity. These are diagnostic differences, not proposed
improvements or measured errors against truth. The two controls respectively
demonstrate partition sensitivity and stopping-limit sensitivity, not an isolated
cause of the owner's long-run RC bias.

Two existing48-hour,20mV-noise owner campaigns were inspected without rerunning:

| Endpoint binary64 diagnostic |35Hz|100Hz|
|---|---:|---:|
| Q error, percent |+0.0523|+0.00532|
| SOC error, percentage points |−0.01734|+0.001274|
| R0 error, percent |−7.65|+40.54|
| τ1 error, percent |+26.73|+466.35|

Their directories are `run_20261030_101732_461642` and
`run_20261030_100426_239149` under `experiments/foster_campaign_001`.
The full endpoint parameter comparisons and source-result hashes are in the
receipt. The binary32 and binary64 arms are close in the100Hz run, so its RC bias
also exists without compact coefficient encoding. Good Q/SOC does not establish
that individual RC branches are resolved. The user's exact intended plot has
not been confirmed; these are the matching local runs found during the audit.

The next useful diagnostic is to separate slow/fast RC information from local
approximation and optimizer stopping, using common observation evidence and
controlled physical window lengths. No threshold adjustment, arbitrary decay,
or claim that more iterations fixes this run follows from these controls.

All32 campaign/integration tests pass after default consolidation. Original
campaign source versions are archived in `baseline/`; old results and receipts
remain unchanged. [verification.json](verification.json) maps the adapted files
back to their preserved versions. The investigation branch is
`investigation/foster-rate-audit-001`.
