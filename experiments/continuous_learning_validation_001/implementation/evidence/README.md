# Restore the completed primary evidence

Small receipts and score summaries are available directly in Git. The larger
original artifacts are preserved losslessly as `primary.tar.xz.part-NNN`
pieces, each at most 4 MiB, to keep Git transport bounded. `index.json` records
the ordered pieces, their hashes, the concatenated archive hash, and every
original member's path, size, hashes and mode.

From the repository root, verify the archive without writing files:

```sh
python experiments/continuous_learning_validation_001/implementation/evidence/restore_primary.py --verify-only
```

Restore missing original files:

```sh
python experiments/continuous_learning_validation_001/implementation/evidence/restore_primary.py
```

The helper uses only the Python standard library on a POSIX host. Its default
repository root comes from the script location; `--root /path/to/mumble`
selects another checkout containing the index and all pieces. It verifies all
pieces and their aggregate hash before extraction, checks every decompressed
member, skips existing exact matches, and refuses conflicting files, links or
unsafe paths. Verification alone permits absent files and creates nothing.

The restored primary occupies
`experiments/continuous_learning_validation_001/implementation/primary/`.
Historical receipts retain the exact command paths used during execution;
restoration preserves the repository-relative original paths needed for plots
and raw inspection. This archive preserves the completed experiment's
391,584,188 bytes. Restoring it performs no new study, learner or scorer run.
