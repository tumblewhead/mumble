> Retention update (2026-10-30): the owner requested removal of large,
> reproducible experiment CSV payloads from GitHub. The four chunks for
> `trajectory_csv_gzip` (14,400,050 bytes combined) are no longer retained in
> this branch's current tree. Local chunks were preserved and their individual
> and combined SHA-256 identities verified. The original manifest, reproduction
> code, and non-CSV chunks are unchanged. Earlier Git commits still contain the
> removed chunks; this cleanup does not purge Git history.
>
> The restoration instructions below describe the original complete bundle.
> A fresh checkout no longer contains all parts needed by the full-bundle
> restore/verify commands. Supply the preserved CSV chunks to use those commands.
> See `provenance/experimental_csv_cleanup_20261030.json` for the removal receipt.

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
