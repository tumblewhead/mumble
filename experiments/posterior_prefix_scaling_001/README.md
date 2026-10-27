# Longer-prefix posterior scaling

This study measures how the unchanged full-path posterior solver scales with
record count. It uses nested prefixes of **8, 32 and 128 records** from one
frozen synthetic stream at nominal 35 Hz, with the actual jittered intervals
preserved. These correspond to 0.229, 0.914 and 3.657 seconds. This is a
computational scaling study, not long-term aging validation.

**Eight records pass the numerical gate. The 32-record comparison remains
unresolved after exhausting the campaign CPU budget; six of eight populations
are saved. The 128-record posterior was not launched.** All three cost probes
completed. The [execution receipt](attempt001/receipt.json) preserves the stop,
and the [saved-evidence summary](reporting001/summary.json) separates completed
inference, interrupted work and unlaunched work. No continuation or retry was
performed.

| Records | Elapsed input | Latent coordinates | Probe CPU per path | Full comparison |
| --- | --- | --- | --- | --- |
|8|0.229 s|32|3.89 microseconds|Pass;73.7 worker CPU seconds;62.5 MiB peak RSS|
|32|0.914 s|80|15.60 microseconds|Interrupted;285.1 worker CPU seconds;68.1 MiB peak RSS|
|128|3.657 s|272|66.27 microseconds|Posterior not launched; probe only|

Probe timings cover likelihood/prior evaluation on 256 paths, not an entire
population refinement. The eight-record elapsed input is shorter than the
older four-record 0.57-second fixture because this study restores nominal 35 Hz.
The controlled scaling axis here is record count and latent dimension; physical
aging duration has not been extended.

The [registered plan](plan.json) fixes the original prior, artificial health
profile, particle counts 2048/4096, four independent populations at each count,
48 Metropolis mutations per stage, proposal factor0.5 and all inherited
numerical thresholds. The posterior queries are conditioned current marginals;
separate prediction/conditioning pairs are not rerun at every length.

The independent cost probes run at every length before gated inference. Full
posterior refinement advances only after the preceding length passes, and stops
on unresolved precision or exhausted resources. No tolerance change, automatic
retry, new proposal policy or extra particles are permitted in this study.

## Work accounting and inputs

The adapter in [common.py](common.py) reserves `batch_size * prefix_length`
before every call into the inherited density evaluator, including prior-draw
validation. Rejected reservations do not enter the model. The ledger is shared
across all populations at a given prefix, so creating a new target does not
reset the allowance. Each completed population is written before later
accounting or adequacy checks.

The campaign additionally limits total CPU to 360 seconds, wall time to 480
seconds, combined supervisor/worker RSS to 512 MiB and output to 64 MiB. The
inherited process supervisor enforces those limits. The three cost probes split
a 1M-step allowance; posterior step limits are 300M, 1B and 3B for 8/32/128 records.
The CPU limit can stop a population before these conservative step caps.

The recorded whole-campaign CPU is **365.413 seconds against the 360-second
budget**, an explicit 5.413-second overrun. The inherited supervisor sets a child
CPU limit from the remaining budget, but parent monitoring consumes additional
CPU while the child runs. It recognizes the combined excess after child
accounting. That aggregate CPU guard needs live accounting and stopping
headroom before a new completion is registered. The new prospective model-step
adapter did not deny or overrun an admitted step budget. The interrupted
population's final model-step count is unavailable; captured-population counts
are a lower bound, not a fabricated total.

[Targeted qualification](attempt001/qualification/receipt.json) passed 31
checks, including exact-limit admission, rejection before physical work,
shared accounting across targets, bitwise parity with the unchanged evaluator,
source order, unknown-input gaps and exact prefix nesting.

The generator uses separate scalar equations and a declared latent plant.
Solver workers read only their observation-prefix file and `inference.json`,
which excludes the plant initial state, latent path and generation seed.
No truth scoring is performed. The inputs are floating-point fabricated
measurements with 1 mV Gaussian noise, not ADC12 hardware data. The nonzero
health coefficients are inherited engineering fixtures, not calibrated aging.

## Interpretation

The eight-record refinement passes every registered mean, covariance,
percentile and evidence check. Its maximum mean Monte Carlo error is 0.0367
posterior SD against the 0.08 limit; maximum percentile change on doubling
particles is 0.136 SD against 0.3. The low-capacity mixture responsibility remains
about 0.526 with Monte Carlo error 0.00524, so both prior components remain
represented. This is numerical evidence for this fixture, not a proof of global
mixing or physical identification.

The cost probes show roughly linear density-evaluation cost with record count.
They exclude the repeated resampling, covariance construction and Metropolis
work of a full refinement, and therefore are not complete solver-runtime
predictions. A single 4096-particle path array grows from 1 MiB at 8 records to
2.5 MiB at 32 and 8.5 MiB at 128. Those are individual arrays, not total peak
memory. They belong to the memory-exempt desktop reference; the complete
deployment target remains 10240 bytes of SRAM with no history archive fallback.

The most useful next decision is based on the closed execution receipt: retain
passing prefixes, distinguish numerical failure from resource exhaustion, and
register any continuation or solver change separately. Sample-moment precision
still does not qualify the 0.1 NLL message-density criterion for compression.
All earlier solver, kernel and canonical experiment sources and results remain
unchanged.

At 32 records the four completed 2048-particle populations used 32.7–34.2 CPU
seconds each; the two completed 4096-particle populations used 65.1–66.8 seconds.
Those completed populations needed 28–29 tempering stages, versus 21 at 8 records.
Their surviving initial ancestry was about 2.4–3.0%, versus about 9% at 8 records.
That ancestry diagnostic is not a posterior ESS or evidence that the posterior
is wrong. The required four high-count replicates are incomplete, so no final
32-record adequacy comparison is reported.

The next bounded action is to correct aggregate CPU supervision and register
only the two missing 4096-particle populations at 32 records, reusing the six
saved populations. Keep the model, solver and precision thresholds fixed. If
the completed comparison fails, use that evidence to select a sampler repair
before increasing prefix length. The current cost already argues against a
direct leap to long cell/load/noise/duration campaigns.

`analyze.py` recomputes the 8-record gate from saved arrays and verifies original
source identities without new inference. It takes an existing attempt and a
new exclusive output directory. The reporting file bindings preserve all input,
population, process and source artifacts. The successful 8-record result and
all partial 32-record work remain available for reuse.
