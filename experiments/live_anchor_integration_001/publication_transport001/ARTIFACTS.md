# Chunked distribution of three existing gzip files

The repository connector failed to upload the 14,400,050-byte trajectory gzip
before returning a Git SHA. This was a distribution failure. Its cause and any
transport size limit are not established; no scientific status changed.

This package splits only the trajectory gzip and the two selected trace gzip
roles into opaque chunks of at most 4,000,000 bytes. Identical chunk bytes are
stored once by SHA256. The original gzip files remain unchanged locally.
`manifest.json` binds their ordered parts and exact whole-file identities.
No compression, decompression, plotting, or data-value interpretation occurs.

After cloning, first verify and restore absent gzip originals:

```sh
python -B experiments/live_anchor_integration_001/publication_transport001/restore_transport.py --verify-only
python -B experiments/live_anchor_integration_001/publication_transport001/restore_transport.py
```

Then use the existing selected asset restorer to reconstruct absent SVG and
raw trace roles:

```sh
python -B experiments/live_anchor_integration_001/publication_assets_recovery001/restore_assets.py --verify-only
python -B experiments/live_anchor_integration_001/publication_assets_recovery001/restore_assets.py
```

Both helpers accept `--root /absolute/path/to/destination` for another existing
directory. They preserve matching files and fail if an existing destination
has different bytes. They never repair or overwrite a damaged capture. New
targets are installed atomically without replacement.

`proposed_ignore_paths.json` adds exactly these three original gzip paths to
the earlier twelve raw-asset exclusions. It applies no Git changes. Keep all
chunk files, metadata, source helpers, PNGs and preserved damaged export
artifacts tracked. Earlier success/failure receipts remain unchanged.
