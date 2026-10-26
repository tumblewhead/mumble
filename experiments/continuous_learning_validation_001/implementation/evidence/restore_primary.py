#!/usr/bin/env python3
"""Verify or restore the completed primary's lossless evidence archive."""

import argparse
import hashlib
import io
import json
import lzma
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tarfile


EVIDENCE = PurePosixPath("experiments/continuous_learning_validation_001/implementation/evidence")
PRIMARY = PurePosixPath("experiments/continuous_learning_validation_001/implementation/primary")
SCHEMA = "mumble_continuous_lossless_evidence_index_v1"
PART_BYTES = 4 * 1024 * 1024
BUFFER_BYTES = 1024 * 1024
MODES = {"100644": 0o644, "100755": 0o755}


class RestoreError(Exception):
    pass


def relative_path(value):
    if (not isinstance(value, str) or not value or "\\" in value or "\0" in value
            or any(part in ("", ".", "..") for part in value.split("/"))):
        raise RestoreError("Invalid repository-relative path: " + repr(value))
    path = PurePosixPath(value)
    if path.is_absolute() or str(path) != value:
        raise RestoreError("Noncanonical repository-relative path: " + repr(value))
    return path


def below(path, directory):
    return path != directory and directory in path.parents


def digest_value(value, length):
    return isinstance(value, str) and re.fullmatch("[0-9a-f]{" + str(length) + "}", value)


def parent_fd(root_fd, path, create=False):
    """Open every parent relative to a trusted descriptor, without following links."""
    current = os.dup(root_fd)
    try:
        for component in path.parts[:-1]:
            try:
                child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                dir_fd=current)
            except FileNotFoundError:
                if not create:
                    os.close(current)
                    return None
                try:
                    os.mkdir(component, 0o755, dir_fd=current)
                except FileExistsError:
                    pass
                child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                dir_fd=current)
            os.close(current)
            current = child
        return current
    except BaseException:
        os.close(current)
        raise


def open_regular(root_fd, path):
    parent = parent_fd(root_fd, path)
    if parent is None:
        return None
    try:
        try:
            info = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            return None
        if not stat.S_ISREG(info.st_mode):
            raise RestoreError("Refusing nonregular file or link: " + str(path))
        descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                             dir_fd=parent)
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            os.close(descriptor)
            raise RestoreError("File changed to a nonregular file: " + str(path))
        return os.fdopen(descriptor, "rb")
    finally:
        os.close(parent)


def load_index(root_fd):
    path = EVIDENCE / "index.json"
    stream = open_regular(root_fd, path)
    if stream is None:
        raise RestoreError("Archive index is absent: " + str(path))
    with stream:
        index = json.load(stream)
    if not isinstance(index, dict) or index.get("schema") != SCHEMA:
        raise RestoreError("Unexpected archive index schema")
    if relative_path(index.get("primary_directory")) != PRIMARY:
        raise RestoreError("Index does not declare this study's primary directory")
    if not digest_value(index.get("archive_sha256"), 64):
        raise RestoreError("Invalid aggregate archive SHA256")
    parts = index.get("parts")
    members = index.get("members")
    if not isinstance(parts, list) or not parts or not isinstance(members, list) or not members:
        raise RestoreError("Index must contain nonempty parts and members lists")
    seen = set()
    for number, part in enumerate(parts):
        if not isinstance(part, dict):
            raise RestoreError("Invalid part entry")
        path = relative_path(part.get("path"))
        size = part.get("bytes")
        if (not below(path, EVIDENCE) or str(path) in seen or type(size) is not int
                or not 0 < size <= PART_BYTES or (number < len(parts) - 1 and size != PART_BYTES)
                or not digest_value(part.get("sha256"), 64)):
            raise RestoreError("Invalid or duplicated archive part: " + str(path))
        seen.add(str(path))
    by_path = {}
    for member in members:
        if not isinstance(member, dict):
            raise RestoreError("Invalid member entry")
        path = relative_path(member.get("path"))
        if (not below(path, PRIMARY) or str(path) in by_path
                or type(member.get("bytes")) is not int or member["bytes"] < 0
                or member.get("mode") not in MODES
                or not digest_value(member.get("sha256"), 64)
                or not digest_value(member.get("git_blob_sha1"), 40)):
            raise RestoreError("Invalid or duplicated archive member: " + str(path))
        by_path[str(path)] = member
    return index, by_path


def verify_parts(root_fd, index):
    aggregate = hashlib.sha256()
    total = 0
    for part in index["parts"]:
        path = relative_path(part["path"])
        stream = open_regular(root_fd, path)
        if stream is None:
            raise RestoreError("Archive part is absent: " + str(path))
        digest, count = hashlib.sha256(), 0
        with stream:
            if os.fstat(stream.fileno()).st_size != part["bytes"]:
                raise RestoreError("Archive part byte count differs: " + str(path))
            for block in iter(lambda: stream.read(BUFFER_BYTES), b""):
                digest.update(block)
                aggregate.update(block)
                count += len(block)
        if count != part["bytes"] or digest.hexdigest() != part["sha256"]:
            raise RestoreError("Archive part checksum differs: " + str(path))
        total += count
    if aggregate.hexdigest() != index["archive_sha256"]:
        raise RestoreError("Concatenated archive SHA256 differs")
    return total


def verify_content(stream, expected, output=None):
    digest = hashlib.sha256()
    git_digest = hashlib.sha1(b"blob " + str(expected["bytes"]).encode("ascii") + b"\0")
    count = 0
    for block in iter(lambda: stream.read(BUFFER_BYTES), b""):
        count += len(block)
        if count > expected["bytes"]:
            raise RestoreError("Member exceeds indexed size: " + expected["path"])
        digest.update(block)
        git_digest.update(block)
        if output is not None and output.write(block) != len(block):
            raise RestoreError("Short output write: " + expected["path"])
    if (count != expected["bytes"] or digest.hexdigest() != expected["sha256"]
            or git_digest.hexdigest() != expected["git_blob_sha1"]):
        raise RestoreError("Member bytes/checksum differ: " + expected["path"])


def existing_match(root_fd, expected):
    stream = open_regular(root_fd, relative_path(expected["path"]))
    if stream is None:
        return False
    with stream:
        info = os.fstat(stream.fileno())
        git_mode = "100755" if info.st_mode & 0o111 else "100644"
        if info.st_size != expected["bytes"] or git_mode != expected["mode"]:
            raise RestoreError("Existing file size/mode differs; refusing overwrite: " + expected["path"])
        verify_content(stream, expected)
    return True


class PartStream(io.RawIOBase):
    """A bounded reader over the verified parts; never constructs a temporary archive."""
    def __init__(self, root_fd, parts):
        super().__init__()
        self.root_fd = root_fd
        self.parts = iter(parts)
        self.current = None

    def readable(self):
        return True

    def readinto(self, buffer):
        view, count = memoryview(buffer), 0
        while count < len(view):
            if self.current is None:
                part = next(self.parts, None)
                if part is None:
                    break
                self.current = open_regular(self.root_fd, relative_path(part["path"]))
                if self.current is None:
                    raise RestoreError("Verified archive part disappeared: " + part["path"])
            got = self.current.readinto(view[count:])
            if not got:
                self.current.close()
                self.current = None
            else:
                count += got
        return count

    def close(self):
        if self.current is not None:
            self.current.close()
            self.current = None
        super().close()


def restore_member(root_fd, expected, stream, serial):
    path = relative_path(expected["path"])
    parent = parent_fd(root_fd, path, create=True)
    temporary = None
    try:
        for attempt in range(100):
            name = ".restore_primary." + str(os.getpid()) + "." + str(serial) + "." + str(attempt) + ".tmp"
            try:
                descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                     0o600, dir_fd=parent)
            except FileExistsError:
                continue
            temporary = name
            break
        else:
            raise RestoreError("Cannot create an exclusive temporary file for " + str(path))
        with os.fdopen(descriptor, "wb") as output:
            verify_content(stream, expected, output)
            output.flush()
            os.fchmod(output.fileno(), MODES[expected["mode"]])
        # link() publishes an absent destination atomically; it never overwrites.
        os.link(temporary, path.name, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
    finally:
        if temporary is not None:
            os.unlink(temporary, dir_fd=parent)
        os.close(parent)


def restore(root, verify_only):
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise RestoreError("A POSIX host with directory-descriptor and O_NOFOLLOW support is required")
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        index, expected = load_index(root_fd)
        archive_bytes = verify_parts(root_fd, index)
        # Detect existing conflicts before creating any directories or files.
        existing = {path for path, member in expected.items() if existing_match(root_fd, member)}
        seen, restored = set(), 0
        with io.BufferedReader(PartStream(root_fd, index["parts"])) as pieces, lzma.LZMAFile(pieces, "rb") as decoded:
            with tarfile.open(fileobj=decoded, mode="r|") as archive:
                for member in archive:
                    path = relative_path(member.name)
                    name = str(path)
                    if name not in expected or name in seen or not below(path, PRIMARY):
                        raise RestoreError("Unexpected or duplicated archive member: " + name)
                    record = expected[name]
                    if (not member.isreg() or member.sparse is not None or member.size != record["bytes"]
                            or member.mode != MODES[record["mode"]]):
                        raise RestoreError("Archive member type, size or mode differs: " + name)
                    stream = archive.extractfile(member)
                    if stream is None:
                        raise RestoreError("Cannot read regular archive member: " + name)
                    with stream:
                        if verify_only or name in existing:
                            verify_content(stream, record)
                        else:
                            restore_member(root_fd, record, stream, len(seen))
                            restored += 1
                    seen.add(name)
            # Validate the XZ footer/checksum even after tar's end marker.
            while decoded.read(BUFFER_BYTES):
                pass
        if seen != set(expected):
            raise RestoreError("Archive is missing indexed members: " + ", ".join(sorted(set(expected) - seen)))
        return {"status": "verified" if verify_only else "restored", "root": str(root),
                "archive_sha256": index["archive_sha256"], "archive_bytes": archive_bytes,
                "parts_verified": len(index["parts"]), "members_verified": len(seen),
                "member_bytes_verified": sum(member["bytes"] for member in expected.values()),
                "existing_exact_matches": len(existing), "files_created": restored,
                "absent_members": len(expected) - len(existing) if verify_only else 0,
                "study_runs": 0, "learner_calls": 0, "scorer_calls": 0}
    finally:
        os.close(root_fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[4],
                        help="Repository root containing the index/parts and restored primary paths")
    parser.add_argument("--verify-only", action="store_true", help="Verify archive and existing files; write nothing")
    args = parser.parse_args()
    try:
        result = restore(args.root.expanduser().resolve(), args.verify_only)
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": type(exc).__name__ + ": " + str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
