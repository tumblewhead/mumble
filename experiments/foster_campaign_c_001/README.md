# Optimized C campaign backend and configurable sample rate

The local campaign runner now defaults to the optimized C rolling/history core.
`--backend python` retains the reference implementation. `--sample-rate-hz`
accepts integer rates of at least1Hz, with35Hz retained as the nominal default.

```sh
python3 -B -m experiments.foster_campaign_001.run \
  --sample-rate-hz 10 --jobs 4 --hours 12 --cells A B \
  --loads charge-discharge --noise-v 0.002 0.008
```

The backend receives indexed dt/I/T/V/sigma observations and public calibration,
with no plant truth or charger state. The campaign still generates the physical
plant, exports telemetry and plots in Python. Full joint mean/root/normalizer
messages are now saved alongside the existing traces, marginal SDs and CSVs.

The C adapter uses the stage2 structured-history/workspace core. Its only copied
core adaptation is the observation clock:1050Hz becomes a build-time constant
equal to lcm(1050, sample rate), bounded to signed32-bit range. At35Hz, the C
adapter's final messages are byte-equal to the frozen optimized C replay on the
1027-record control in both encodings. Existing numerical/model/history sources
are otherwise reused verbatim and checked against their frozen hashes.

Each campaign builds once before parallel workers start, compiles archived source
snapshots and saves commands and hashes under `backend_c/`. A missing or failed
C build is an explicit error. Source identity and chronology remain recorded;
the native in-process source tag is64bits, while the full source/model identities
remain in host evidence. This is not a distributed SHA transaction implementation.

Sample-rate changes affect plant integration, observation intervals, estimator
clock, charger control intervals and plot timestamps together. Schedules keep
their physical durations. The fitting window stays16records, so its duration is
16/rate seconds. Per-sample noise SD stays unchanged. Lower rates can miss short
pulses and change inference; no equivalent information content across rates is
claimed. Old telemetry without rate metadata still renders as35Hz.

## Validation and speed

[validation.json](validation.json) records four matched180-second cases per
backend: cells A/B, cycle/CC–CV loads,4mV noise, both coefficient encodings.
Observations and truth are byte-equal between paired backends. Maximum C/Python
differences are0.002265%Q and0.000231SOC percentage points, well below the0.5
application scales on these controls. These comparisons are implementation
agreement, not evidence of absolute physical accuracy or validated coverage.

One measurement per backend gives:

| Scope, summed across four cases | Python | C | Speedup |
|---|---:|---:|---:|
| Estimator calls including adapter/readout |1.690s|0.107s|15.8×|
| Cases including generation/export, excluding plots |2.067s|0.440s|4.7×|
| Entire command including build/startup checks |2.493s|1.189s|2.1×|

This is a short host integration measurement, not a repeated timing study or an
M23 timing prediction. Workload, plotting and machine affect the overall speedup.

A separate100Hz,540-second CC–CV case retires54000records per arm, enters CV,
and completes all six case plots and six summary overlays. The signals plot
was visually inspected for duration, temperature and CC–CV behavior.

Thirty-two targeted tests pass: ten campaign controls, four parallel-worker
controls, eight charger controls, two summary-plot controls, and eight new
integration controls. New coverage includes10/35/70/100Hz, partial windows,
exact input-order/failure watermarks, clock/timestamp consistency, charger dwell
and charge integration, and preserved35Hz stimulus behavior. Parallel controls
exercise the new default C path, including byte-identical serial/parallel arrays
and CSVs. See [tests.json](tests.json) and [verification.json](verification.json).

The prior editable campaign sources are archived under `baseline/`, mapped by
[plan.json](plan.json); original scientific results and frozen C receipts remain
unchanged. The validation campaigns also contain their exact source snapshots.

## Resource and interpretation limits

Each C estimator context remains19416B, excluding stack. The frozen core's known
context-plus-C-call-chain accounting is22096B before math/runtime, acquisition
and interrupts. The2,184B boundary message and6,269B two-message-plus-compact-token
figures are payload subsets, not full SRAM. The10KiB M23 target is still unmet
and16MHz target cycles remain unmeasured. Host telemetry files grow with duration.

Reference parameters remain stationary; aging, weak-excitation bias, Gaussian
coverage and ten-year behavior remain open. The sampling-rate and backend work
does not change those scientific limits. See the [campaign guide](../foster_campaign_001/README.md)
for loads, cells, noise, plots and rerendering saved results.
