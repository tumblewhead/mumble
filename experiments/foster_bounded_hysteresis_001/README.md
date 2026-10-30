> The owner196-hour run is now reviewed: all8seeds complete in both encodings. See [full-run review](../foster_bounded_196h_review_001/README.md) for sustained errors and remaining uncertainty limitations. The qualification below records the earlier24-hour step.

# Bounded hysteresis history repair

The 50 Hz, 196-hour owner run completed only seeds1000 and1004. Seeds1001,
1002,1003,1005,1006 and1007 stopped at10.88,501.44,384.32,76.16,433.92 and
386.24seconds respectively. The saved C library reproduces all twelve failures
(two encodings) with byte-identical committed messages. Every rejected candidate
has h below−1, while the fitted physical endpoint and candidate SOC are valid.
For seed1001 the candidate is−1.1377895; this is not a rounding-only discrepancy.
See [failure receipt](failures.json).

The local Gaussian likelihood update and affine state transport can leave h's
physical support, even when the nonlinear fit stays inside it. The domain guard
correctly refuses the invalid commit. This repair changes the producer's state
coordinate to eta=atanh(h). The generic compressor, evidence counts, chronology,
full joint covariance, optimizer and physical Foster equations remain unchanged.

For current direction s and a=gamma_dir*abs(I)*dt/(3600*Q_Ah), define
q=(1-s*h)/2. The physical ODE gives q_next=q*exp(-a), hence

```
logq = -softplus(2*s*eta)
L = logq - a
D = -expm1(L)
eta_next = s/2 * (log(D) - L)
d eta_next / d eta = sigmoid(2*s*eta) / D
d eta_next / d a = s / (2*D)
h = tanh(eta)
```

This is an exact re-expression of the constant-input physical flow. Rest and
zero-duration observations leave eta unchanged. Stable log probabilities avoid
computing atanh(tanh(eta)) near saturation. For every finite real eta, physical
h is bounded; floating point tanh can round to an allowed endpoint. No clipping,
bound relaxation, sample skipping, added decay, or hidden health model is used.
Voltage Jacobians include dh/deta; transport Jacobians carry the eta derivatives
and all parameter cross terms. Extreme nonfinite/numerically singular states are
still explicit failures rather than silently repaired.

The prior is explicitly Gaussian in eta, tangent-matched to the public prior's
physical h center and local scale. It is not an exact transformed or truncated
version of the old Gaussian h prior. Gaussian approximation is not coordinate
invariant, so this can change estimates even away from the old failure. Saved
messages and chart arrays declare the new coordinate; plots and trace CSV still
report physical h. The likelihood has no transformation Jacobian because it is
a likelihood of observations conditional on the parameters. This does not remove
the need to specify the prior measure separately.

[Qualification](qualification.json) records43 tests: algebra/chain rule against
the frozen physical model, finite-difference derivatives, saturation/rest,
nonzero prior, physical reporting, C/Python joint messages, exact old-failure
regression, serial/parallel harness behavior and parallel Python model builds.
[Four-hour](four_hour_replay.json) and [24-hour](twenty_four_hour_replay.json)
replays use the original saved observations for all eight seeds and both
encodings. All16 arms finish each duration. At24hours the largest endpoint Q
error is0.43977% and SOC error0.10910percentage points. These are endpoint scores,
not sustained-error or calibrated-coverage guarantees. Seed1006 remains the
largest endpoint Q bias. At4hours its Q error was0.60089%.

The boundary message remains2184B and C context19416B, excluding stack. The new
model cross-compiles for Cortex-M23 with1312B own frame plus32B wrapper frame;
this is partial accounting, not a complete SRAM or16MHz timing qualification.
The saved-observation24-hour replays took about81host seconds across16 arms;
this excludes fresh plant generation, telemetry export and plots.

The campaign CLI defaults to `--hysteresis-chart bounded`; `legacy` retains the
old diagnostic control. Existing configuration files without the chart field
keep legacy interpretation. Original studies and frozen source identities stay
intact. Full196-hour qualification is left to the owner.

To repeat all saved settings into a new `run_bounded_<UTC>` directory beside the
original run, from the repaired worktree:

```sh
python3 -B -m experiments.foster_bounded_hysteresis_001.owner_run   /home/easy/proj/mumble/experiments/foster_campaign_001/run_20261030_175523_166400   --hours 196 --jobs 8
```

Add `--dry-run` to inspect the exact expanded command. The source run is read-only;
outputs use a fresh directory and existing destinations are rejected. This keeps
50Hz, all eight seeds, the same load/noise/temperature settings, both encodings,
and normal V/I/T, state, parameter and error plots.
