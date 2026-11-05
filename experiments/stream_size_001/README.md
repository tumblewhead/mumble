# Observable-input harness and stream-size trials

This applies the ArghtOS pattern: freeze the old measurement, establish a more
observable boundary, compare small rewrites in the same lane, and reject
regressions without carrying them into the estimator.

The previous probe made only current volatile. Interval, temperature, voltage
and sigma were compile-time constants. Scalar results were not explicitly
published across a volatile output boundary. The new `physical` lane reads five
volatile sample slots and publishes each scalar value/variance to two volatile
slots. This prevents those constant-input and dead-output assumptions. It is
still a synthetic link probe, not device firmware or an executable sample driver;
its slots start at zero and no hardware supplies samples in this harness.

| Build | Text | BSS | Complete static SRAM | Delta within physical lane |
|---|---:|---:|---:|---:|
| Frozen legacy control | 16,696 B | 6,928 B | 24,672 B | separate lane |
| Observable-input control | 16,744 B | 6,976 B | 24,768 B | 0 |
| Serial free/forced projection | 16,752 B | 6,976 B | 24,776 B | +8 B |
| Pointer-based projection | 16,768 B | 6,976 B | 24,792 B | +24 B |
| memset row clearing | 16,788 B | 6,976 B | 24,808 B | +40 B |

Constants, vectors and alignment are included in static totals. The96B lane
increase comprises48B text and48B extra synthetic input/output slots. We count
those slots rather than silently excluding them. This is a measurement-class
change, not a96B estimator implementation regression. Legacy results remain
reproducible and are not rewritten.

All three stream rewrites are rejected at the static-size screen; the original
stream implementation remains selected. None receives functional or stack
qualification. The old664B stack witness is not a measured stack bound for this
new harness. Adding a provisional1024B allowance to the physical control gives
25792B, excluding any additional device integration costs.

The earlier optimization deltas remain evidence within their historical lane.
Their exact deltas have not been individually rerun in this new lane.

Commands (new output directories required):

```
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.stream_size_001.target --lane legacy --out experiments/stream_size_001/new_legacy
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.stream_size_001.target --out experiments/stream_size_001/new_physical
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.stream_size_001.target --variant serial_projection --out experiments/stream_size_001/new_serial
```

Use `pointer_projection` or `memset_clear` for the other trials. Mainline and
campaign defaults are unchanged. Independent review covers measurement and
rejection, not the numerical equivalence of rejected variants. Next: inspect
initialization/configuration ownership and redundant internal checks under the
observable-input control; remove checks only when their preconditions are proved.

ArghtOS source lessons:
- https://github.com/tumblewhead/arghtos/blob/implementation/r6-size-research-001/implementation/FOOTPRINT-HARNESS-METHODOLOGY.md
- https://github.com/tumblewhead/arghtos/blob/implementation/r6-size-research-001/implementation/R4c-looped-crash-copy.md
