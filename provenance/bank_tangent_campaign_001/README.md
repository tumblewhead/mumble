# Bank tangent integration

Restored tangent64 as the reference and added bank_tangent with original-prior
augmented QR updates. Outgoing messages are readouts, never new priors.
Independent review accepted with limits; one missing inherited-lifecycle source
binding was repaired before acceptance. Four new tests and eleven existing
campaign/default tests pass. Tests cover original-anchor dense normal equations,
full/compact and nonzero checkpoint replay, no readout feedback and quarantine.

Two four-hour50Hz embedded-load cases completed, seeds1100/1101, load7,2mVnoise,
constant25C. Each arm accepted239/239scheduled refits. The summary is preserved;
raw artifacts are in /tmp/banktangent4h001 and are not committed. About51seconds
per case on this host with two concurrent workers includes both arms; this is
not an isolated backend benchmark or target timing estimate.

Bank tangent is a dense Python reference with94-column QR each block,17-column
tangent QR and full analytic transport. It retains TaylorH2 rather than H5.
There is no emergency readout-domain refit: failure quarantines the arm.
Covariance is provisional local precision; bias-aware intervals, certification,
aging and MCU deployment remain open. Factor35720B + response936B plus dense
tangent2312B and derivative cache12032B excludes other substantial workspace.

Use experiments/bank_tangent_campaign_001/README.md for reruns. D001 remains the
older field-feedback observational control; new rate runs must be labeled with
the new arms. Same-seed runs at different rates are exploratory, not physically
matched-noise controls. The equal-duration-window study remains separate.
