# Native original-origin tangent update

The C tangent kernel and opt-in campaign adapter are implemented on
`implementation/field-tangent-native-001`, based on `375ef47`. Mainline and the
`joint-field` default are unchanged. The [qualification receipt](qualification.json)
records source hashes, preserved inputs, tests, measurements and limits.

The [fused follow-up](../tangent_fused_001/README.md) now removes the ordinary
lifted-row allocation and combines response/update/readout calls. It preserves
all 12,288 tested window states bitwise and reduces matched host advance time by
28%. The measurements below describe the original port; the follow-up reports
its additional reusable scratch and current resource limits separately.

The original public prior enters once. A packed 17-column square-root factor
retains the joint local likelihood in original field coordinates. New response
rows enter once, in order. Direct physical-partition contractions replace the
82×16 derivative cache. Readout transports the joint estimate through the
nonlinear field state map; the reported Gaussian never becomes the next prior.
Scheduled full-field solves relinearize the accumulated evidence. The native
kernel performs no heap allocation and uses caller-owned workspace.

The standalone adapter does not run the previous rolling fitter. It advances a
live collocation state every window and retains the existing 4,096-record raw
batch for the 82-dimensional field QR. This duplicates response recurrence at
flush, but preserves chronology and avoids a large lifted-row buffer. A rejected
scheduled fit retains the tangent and all its evidence. A readout outside the
physical chart requests a full-field recovery; failed recovery explicitly stops
the arm without publishing an invalid message. There is no clipping, forgetting,
variance inflation or truth-driven correction.

## Storage

| Partial accounting | Bytes | KiB |
|---|---:|---:|
| Previous packed field + dense-cache tangent prototype | 41,368 | 40.40 |
| Existing packed field and live state | 28,864 | 28.19 |
| New persistent C tangent context | 1,376 | 1.34 |
| **New packed field + tangent subtotal** | **30,240** | **29.53** |
| Additional explicit C tangent workspace | 5,880 | 5.74 |
| Subtotal including that workspace | 36,120 | 35.27 |

These are **not whole-system SRAM totals**. The original mean/root require another
2,176 bytes; projection tables, output buffers, input rows, binding metadata,
field QR and nonlinear-fit workspace also need accounting. The compiler's largest
reported individual kernel stack frame is 160 bytes on this host, excluding
nested calls and libm; this is not an ARM stack bound.

The desktop adapter additionally has a 163,840-byte raw batch, a dense 53,792-byte
field root, an extra 888-byte live-state copy and a 2,208-byte readout carrier,
plus Python allocations. It is not an implementation of the packed layout and
is not M23-ready. Neither 16 MHz timing nor the approximately 10 KiB target is
qualified.

## Qualification

Ten native/prototype tests and 37 campaign/recording/default/plot tests pass.
Coverage includes correlated priors, independent finite differences, batch
partition invariance, rest null information, source/count guards, failed refresh
handling, rejected input, explicit failed recovery, and complete checkpoints.
Full and compact recording messages and replay traces match bitwise. Replaying
the final weak-run debug window also reproduces every arm's final message bitwise.

Across five preserved prefixes (836 windows), C versus Python tangent differences
are at rounding scale: maximum endpoint-coordinate difference 4.89e-14 and
covariance-entry difference 4.50e-15. Parent study source and artifact hashes are
unchanged. This checks the port, not accuracy of the approximate field itself.

Two complete four-hour campaigns use continuous estimation from the public prior:

| Control / arm | Final Q error | Final SOC error (pp) | Q local log-SD ×100 |
|---|---:|---:|---:|
| Weak B/cycle, existing field arm | −1.89382% | +0.05549 | 1.11516% |
| Weak B/cycle, native tangent | +0.27749% | +0.04877 | 4.27751% |
| A/embedded seed1103/load7, existing field arm | −0.05551% | −0.00421 | 0.09001% |
| A/embedded seed1103/load7, native tangent | −0.05535% | −0.00421 | 0.09000% |

The tangent accepts all 238 weak and 239 embedded scheduled refreshes, with no
emergency recovery. Its Q three-SD miss counts are zero in both controls; SOC
misses are 330/31,500 weak outputs and zero/45,000 embedded outputs. Those are
correlated, local-uncertainty diagnostics, **not validated coverage**. Startup
errors remain substantial. Improvements are not uniform: embedded Q RMSE is
0.645% for tangent versus 0.566% for the existing field arm, while SOC RMSE improves
from 0.134 to 0.0625 percentage points.

Local generated plots: [weak errors](weak4h002/case_0000/errors.png),
[embedded errors](embedded4h002/case_0000/errors.png). Individual plots and all-arm
summary overlays include the new tangent arm. Large generated evidence remains
local and ignored by Git.

## Timing and next work

Matched suffix measurements give approximately 70.4 microseconds per native
16-record update/readout versus 592.6 microseconds for the Python prototype:
8.42× faster, excluding common accumulation and full fits. Whole backend advance,
including adapter/batching/refresh work, takes 265–278 microseconds per window
versus 176–184 for the existing field arm and 55–57 for plain rolling. The native
candidate is therefore about 1.5× slower than the current field arm in these
host profiles. This is not an end-to-end or MCU speedup claim.

Before promotion, run 24/72-hour weak/mixed controls and inspect capacity, SOC,
uncertainty and hysteresis drift separately. The existing long-duration hysteresis
approximation error and aging remain unresolved. Profile the adapter and duplicate
response recurrence before further optimization; preserve the source and physical
support guards.

From this worktree, a two-case 72-hour follow-up with compact recording is:

```sh
python3 -B -m experiments.foster_campaign_001.run \
  --hours 72 --jobs 2 --sample-rate-hz 50 --cells A B \
  --loads embedded --load-seeds 7 --seeds 1103 --noise-v .002 \
  --history compare-tangent --recording compact
```

`compare-tangent` runs rolling, existing field and native tangent together.
`field-tangent` selects only the new arm. All existing load, noise, rate, recording
and debug replay flags apply. Use a new output directory for every run. Replay
remains bound to the exact source, binary and runtime used for that run.
