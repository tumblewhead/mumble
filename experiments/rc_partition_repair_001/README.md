# RC free/forced partition diagnostic

Run in the h7-campaign worktree with preceding frozen local RC, H-sensitivity and
joint-refit artifacts present. The runner verifies their identities before use.

```sh
OPENBLAS_NUM_THREADS=1 python3 -B -m unittest experiments.rc_partition_repair_001.test_field -v
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.rc_partition_repair_001.run --out experiments/rc_partition_repair_001/run_new
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.rc_partition_repair_001.probe --run experiments/rc_partition_repair_001/run_new --out experiments/rc_partition_repair_001/run_new/probe.json
python3 -B -m experiments.rc_partition_repair_001.summarize --run experiments/rc_partition_repair_001/run_new --out experiments/rc_partition_repair_001/run_new/compact.json
```

Output paths must be new. The two study-only native builds preserve Taylor H and
project free and forced RC independently; the compact joint factor retains cross
terms. Five tests and separately reviewed P4 support the implementation. These
are finite-prefix diagnostics, not a production campaign mode.

Read the [plan](../../specifications/rc_partition_repair_001/README.md),
[P4](../../specifications/rc_partition_repair_001/P4.md) and
[results](../../provenance/rc_partition_repair_001/README.md) before interpretation.
