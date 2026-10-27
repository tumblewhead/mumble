# Lossless publication artifacts

This directory packages the ten closed SVG figures as deterministic gzip files.
`restoration_manifest.json` binds every raw, compressed and decompressed identity.
It also references the two separately selected trace gzip roles from
`../publication_selection.json`; it does not replace that provenance decision.

After cloning the repository, verify all packages and existing destinations:

```sh
python -B experiments/live_anchor_integration_001/publication_assets001/restore_assets.py --verify-only
```

Restore only absent original files:

```sh
python -B experiments/live_anchor_integration_001/publication_assets001/restore_assets.py
```

Use `--root /absolute/path/to/destination` to restore into another existing
directory. Matching existing files remain unchanged. Any different existing
file causes failure; the helper never repairs or overwrites a damaged capture.
The two raw trace roles are installed as separate files with distinct inodes.
Interrupted restoration can be resumed only when all existing targets match.

`proposed_ignore_paths.json` lists exactly ten original SVG paths and the two
large raw trace paths for the repository owner to exclude from Git. PNGs,
the trajectory CSV gzip, metadata, and the preserved damaged publication gzip
remain tracked. No ignore rule is applied by this packager.

The original failed reporting receipt and the later failed publication-copy
integrity check remain preserved. Packaging or restoring bytes does not alter
any scientific status, candidate, result, or uncertainty claim.
