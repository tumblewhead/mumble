# Continuous learning validation 001: executable implementation

This directory records implementation qualification and the single staged
execution of `plans/continuous_learning_validation_001.json`. The frozen contract
SHA256 is `8fa48af8ce027cfb82a7bac1f943a48517a30d311825c90e833d90c0ff551851`.
The seven pinned estimator files remain unchanged.

## Responsibilities

| File | Responsibility |
| --- | --- |
| `tools/continuous_source.py` | Independent event-based synthetic source; scalar noise; physical/RNG/charge continuation; checksummed per-index journal. |
| `tools/continuous_probe.c` | Truth-free C observation adapter; unchanged estimator; scalar/full queries; canonical checkpoints; first-failure capture. |
| `tools/score_continuous_learning.py` | Post-inference point, availability, voltage, acquisition/retention and descriptive local-range scoring. |
| `tools/run_continuous_learning.py` | Source/executable verification, process supervision, coupled restore, stage gates, budgets and partial-run preservation. |

The learner receives only index, interval, current and observed voltage, plus
the public source identity. Its process never receives truth files or truth
parameters. Source and scoring helpers run separately. A warm suffix is checked
against the original source bytes and complete source checkpoints before its
learner process starts.

## Qualification and execution

Build with `make build/continuous_probe`. Development evidence under
`development/` retains the original interface checks, targeted corrections,
independent reviews and the coupled six-second integration fixture. Development
fixtures use separate seeds; the two primary seeds are guarded until an exact
executable receipt and its independent review are present.

The final qualification receipt is `preflight.json`. The copied executable is
`reference_binaries/continuous_learning_validation_001/continuous_probe`.
`executable_receipt.json` binds the published source commit, every compile and
harness dependency, compiler flags, executable hash, runtime identity, contract
and preflight receipt. `executable_review.json` binds independent review to that
receipt before the first primary noise draw.

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python tools/run_continuous_learning.py \
  --run \
  --executable-receipt experiments/continuous_learning_validation_001/implementation/executable_receipt.json \
  --review experiments/continuous_learning_validation_001/implementation/executable_review.json \
  --output experiments/continuous_learning_validation_001/implementation/primary
```

The output directory must not exist. This is the once-only primary command,
not a development test or an instruction to rerun completed evidence. Once the
primary has started, a failure closes this study for a named subsequent decision;
it does not authorize edits followed by a retry.

## Evidence and limits

Scalar observation/truth records are32 bytes; scalar metric records are80 bytes.
Full queries retain16 aggregate and component coordinates on the frozen grid.
The source journal has a72-byte header and208-byte records, allowing an exact
entering/current source snapshot at a learner failure without chronological
replay or additional noise draws.

The supervisor preserves completed prefixes, signals workers to stop at safe
record boundaries, and allows at most1s to flush diagnostics before a hard kill.
A breached cap remains a failure even if diagnostic flushing succeeds. A hard
stop or an uncommitted I/O fault may make exact consumption unavailable; receipts
then say so rather than inferring a successful prefix from file length alone.

A admits B only after numerical, accounting, lifecycle and known owned-resource
validity checks pass. A accuracy remains observational for this diagnostic
admission. Capacity has no startup deadline. A partial intended horizon cannot
establish sustained-to-end accuracy or full retention. Local covariance ranges
and hull inclusion are descriptive; they do not establish calibrated coverage,
hard physical support, or firmware readiness.

Primary caps are four learner processes,661500 deliveries,619500 source
evaluations including the duplicated warm suffix,3600s primary wall time and a
separate600s scorer limit; the combined wall limit is4200s. All produced runtime
artifacts and each host process are bounded by512MiB. The core owned subtotal
remains7152 bytes; host logging, checkpointing, Python and supervision resources
are separate. The proposed10032-byte target reservation is not a Cortex-M23
measurement.
