# Selected lossless publication artifacts

This recovery preserves both failed export attempts. Exactly one SVG was
recompressed from its unchanged original; the other nine SVG packages and the
two separately selected trace packages are reused unchanged. Full provenance
is in `restoration_manifest.json` and this directory's receipt.

Verify packages and destinations without writes:

```sh
python -B experiments/live_anchor_integration_001/publication_assets_recovery001/restore_assets.py --verify-only
```

Restore only absent original paths:

```sh
python -B experiments/live_anchor_integration_001/publication_assets_recovery001/restore_assets.py
```

Use `--root /absolute/path/to/destination` for another existing directory.
Matching files stay unchanged. Different existing files cause failure; no
capture is repaired or overwritten. Both raw trace roles are installed as
separate files with distinct inodes. Validate the original capture metadata
after restoration before using those bytes as scientific evidence.

`proposed_ignore_paths.json` contains exactly ten original SVGs and two large
raw trace paths. No ignore rule is applied here. Keep PNGs, CSV gzip, metadata,
selected packages, and both damaged old gzip files tracked as evidence.
Packaging/restoration performs no model, fitting, prior or truth-value work
and changes no original success or failure status. Attribution of both export
truncations remains unknown.
