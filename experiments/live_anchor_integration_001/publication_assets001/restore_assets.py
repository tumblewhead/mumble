#!/usr/bin/env python3
"""Restore the explicitly packaged SVG and two independent RAW capture roles.

An existing different file is an error, never a repair request. No plot, data,
model, prior, optimizer or truth-value interpretation occurs here.
"""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile


def require(value, message):
    if not value:
        raise ValueError(message)


def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, "Duplicate JSON key")
        result[key] = value
    return result


def read_json(path):
    return json.loads(path.read_bytes(), object_pairs_hook=pairs,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))


def identity(path):
    digest, size = hashlib.sha256(), 0
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as handle:
        require(stat.S_ISREG(os.fstat(handle.fileno()).st_mode), "Expected regular file")
        while block := handle.read(1048576):
            digest.update(block)
            size += len(block)
    return {"bytes": size, "sha256": digest.hexdigest()}


def safe(root, relative):
    p = Path(relative)
    require(not p.is_absolute() and ".." not in p.parts, "Unsafe restoration path")
    target = root / p
    for candidate in (target, *target.parents):
        if candidate == root:
            break
        require(not candidate.is_symlink(), "Symlink in restoration path")
    require(target.resolve().is_relative_to(root), "Restoration path escapes root")
    return target


def decompressed_identity(path, expected, destination=None):
    digest, size = hashlib.sha256(), 0
    with gzip.open(path, "rb") as source:
        while block := source.read(1048576):
            size += len(block)
            require(size <= expected["bytes"], "Decompressed extent exceeds the declared raw identity")
            digest.update(block)
            if destination is not None:
                destination.write(block)
    actual = {"bytes": size, "sha256": digest.hexdigest()}
    require(actual == expected, "Decompressed content differs")
    return actual


def fsync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def main():
    source_root = Path(__file__).resolve().parents[3]
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=source_root,
                        help="Existing destination repository/directory; sources stay beside this helper")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    require(root.is_dir(), "Destination root must already exist")
    receipt = read_json(here / "receipt.json")
    require(receipt["status"] == "completed", "Asset packaging did not complete")
    require(identity(Path(__file__).resolve()) == receipt["restore_helper_identity"], "Restore helper source differs")
    manifest_path = here / "restoration_manifest.json"
    require(identity(manifest_path) == receipt["restoration_manifest_identity"], "Restoration manifest differs")
    manifest = read_json(manifest_path)
    require(manifest["schema"] == "mumble_live_anchor_restoration_manifest_v1", "Wrong restoration schema")
    rows = manifest["roles"]
    require(len(rows) == 12 and len({r["raw_path"] for r in rows}) == 12, "Unexpected or duplicate restoration inventory")
    trace_rows = [r for r in rows if r["kind"] == "primary_raw_capture"]
    require(len(trace_rows) == 2 and {r["capture_role"] for r in trace_rows} == {"original", "independent_object"},
            "Two separate primary trace roles are required")
    # Validate every package and existing destination before writing any role.
    for row in rows:
        archive = safe(source_root, row["gzip_path"])
        require(identity(archive) == row["gzip_identity"], "Packaged gzip identity differs")
        decompressed_identity(archive, row["raw_identity"])
        target = safe(root, row["raw_path"])
        if target.exists():
            require(identity(target) == row["raw_identity"], "Existing destination differs; refusing to repair or overwrite: " + str(target))
    existing = [safe(root, r["raw_path"]) for r in trace_rows]
    if all(p.exists() for p in existing):
        require((existing[0].stat().st_dev, existing[0].stat().st_ino) !=
                (existing[1].stat().st_dev, existing[1].stat().st_ino), "Existing raw captures share an inode")
    outcomes = []
    for row in rows:
        target = safe(root, row["raw_path"])
        if args.verify_only:
            outcomes.append({"path": row["raw_path"], "status": "matching_existing" if target.exists() else "verified_restorable"})
            continue
        if target.exists():
            require(identity(target) == row["raw_identity"], "Existing destination changed after preflight")
            outcomes.append({"path": row["raw_path"], "status": "matching_existing_preserved"})
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target = safe(root, row["raw_path"])
        temp = None
        try:
            with tempfile.NamedTemporaryFile(mode="wb", prefix=".restore_asset_", dir=target.parent, delete=False) as handle:
                temp = Path(handle.name)
                archive = safe(source_root, row["gzip_path"])
                require(identity(archive) == row["gzip_identity"], "Package changed before restoration")
                decompressed_identity(archive, row["raw_identity"], handle)
                handle.flush()
                os.fsync(handle.fileno())
            # link() creates the destination atomically and fails if it exists;
            # unlike replace/rename it cannot overwrite a concurrent writer.
            os.link(temp, target)
            fsync_directory(target.parent)
            require(identity(target) == row["raw_identity"], "Restored target changed")
            outcomes.append({"path": row["raw_path"], "status": "restored_absent_role"})
        finally:
            if temp is not None:
                temp.unlink(missing_ok=True)
                fsync_directory(target.parent)
    if not args.verify_only:
        a, b = [safe(root, r["raw_path"]) for r in trace_rows]
        require((a.stat().st_dev, a.stat().st_ino) != (b.stat().st_dev, b.stat().st_ino),
                "Restored raw captures are not independent files")
    print(json.dumps({"status": "verified" if args.verify_only else "restored_or_already_identical",
                      "roles": outcomes, "scientific_status_changed": False,
                      "model_prior_optimizer_truth_value_calls": 0}, indent=2))


if __name__ == "__main__":
    main()
