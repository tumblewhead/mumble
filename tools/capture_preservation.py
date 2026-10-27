"""Exclusive host capture transactions for future probes.

This module does not launch children or assign scientific success. A supervisor
copies child stdout through the one writer, waits for that child, closes the
writer, and commits before permitting dependent reads. The returned commit
identity must be pinned in the supervisor's own evidence record.

An independent inode is a second copy, not independent physical storage.
External modification is detected at verification boundaries; this is not a
filesystem immutability or power-loss proof. Original loss always rejects a
verified read, even when the committed object remains recoverable.
"""

import hashlib
import json
import os
from pathlib import Path
import stat


SCHEMA = "mumble_capture_preservation_v1"
ORIGINAL = "raw_probe.json"
RESERVATION = "reservation.json"
STREAM_CLOSED = "stream_closed.json"
COMMIT = "commit.json"
CHUNK_BYTES = 4096
METADATA_MAX_BYTES = 16384


class CaptureError(RuntimeError):
    """A capture is unavailable for dependent use."""


class CaptureIntegrityError(CaptureError):
    pass


class CaptureStateError(CaptureError):
    pass


class CaptureLimitError(CaptureError):
    pass


def _require(condition, message, error=CaptureIntegrityError):
    if not condition:
        raise error(message)


def _fsync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_all(fd, data):
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise OSError("Capture write made no progress")
        view = view[written:]


def _json_bytes(value):
    data = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
    _require(len(data) <= METADATA_MAX_BYTES, "Capture metadata limit", CaptureLimitError)
    return data


def _write_json_exclusive(path, value):
    data = _json_bytes(value)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        _write_all(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    _fsync_directory(path.parent)
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def _stat_signature(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _read_regular(path, max_bytes, collect=False):
    """Hash a bounded regular file, rejecting replacement during this read."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as error:
        raise CaptureIntegrityError("Required capture file unavailable: " + str(path)) from error
    data, count, digest = [], 0, hashlib.sha256()
    try:
        before = os.fstat(fd)
        _require(stat.S_ISREG(before.st_mode), "Capture member is not a regular file")
        _require(before.st_size <= max_bytes, "Capture member exceeds its bound")
        while True:
            chunk = os.read(fd, CHUNK_BYTES)
            if not chunk:
                break
            count += len(chunk)
            _require(count <= max_bytes, "Capture member grew beyond its bound")
            digest.update(chunk)
            if collect:
                data.append(chunk)
        after = os.fstat(fd)
        current = path.lstat()
        _require(_stat_signature(before) == _stat_signature(after) == _stat_signature(current),
                 "Capture member changed during read")
        _require(stat.S_ISREG(current.st_mode), "Capture path became nonregular")
    except OSError as error:
        raise CaptureIntegrityError("Capture member changed or became unavailable") from error
    finally:
        os.close(fd)
    return ({"bytes": count, "sha256": digest.hexdigest()},
            b"".join(data) if collect else None, (after.st_dev, after.st_ino))


def file_identity(path, max_bytes=16777216):
    return _read_regular(Path(path), max_bytes)[0]


def _valid_identity(value):
    return (isinstance(value, dict) and set(value) == {"bytes", "sha256"} and
            type(value["bytes"]) is int and value["bytes"] >= 0 and
            isinstance(value["sha256"], str) and len(value["sha256"]) == 64 and
            all(c in "0123456789abcdef" for c in value["sha256"]))


def _no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "Duplicate capture metadata key")
        result[key] = value
    return result


def _read_json_bound(path, expected):
    _require(_valid_identity(expected), "Invalid expected metadata identity")
    observed, data, _ = _read_regular(path, METADATA_MAX_BYTES, collect=True)
    _require(observed == expected, "Capture metadata identity mismatch: " + path.name)
    try:
        value = json.loads(data, object_pairs_hook=_no_duplicates,
                           parse_constant=lambda token: (_ for _ in ()).throw(
                               CaptureIntegrityError("Nonfinite capture metadata")))
    except (UnicodeError, ValueError) as error:
        raise CaptureIntegrityError("Invalid capture metadata") from error
    _require(isinstance(value, dict), "Capture metadata must be an object")
    return value


def _bound(record, role):
    row = record[role]
    _require(isinstance(row, dict) and set(row) == {"path", "bytes", "sha256"},
             "Malformed capture binding")
    identity = {"bytes": row["bytes"], "sha256": row["sha256"]}
    _require(_valid_identity(identity), "Invalid capture binding")
    return row["path"], identity


class _CaptureWriter:
    def __init__(self, transaction):
        self.transaction = transaction
        self.fd = os.open(transaction.directory / ORIGINAL,
                          os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        self.digest, self.bytes = hashlib.sha256(), 0
        self.closed, self.failure = False, None
        self.stream_closed_identity = None
        _fsync_directory(transaction.directory)

    @property
    def identity(self):
        return {"bytes": self.bytes, "sha256": self.digest.hexdigest()}

    def write(self, data):
        _require(not self.closed and self.failure is None, "Writer is not available", CaptureStateError)
        if not isinstance(data, bytes):
            raise TypeError("Capture writes require bytes")
        remaining = self.transaction.max_bytes - self.bytes
        accepted = memoryview(data)[:remaining]
        try:
            while accepted:
                count = os.write(self.fd, accepted)
                if count <= 0:
                    raise OSError("Capture write made no progress")
                self.digest.update(accepted[:count])
                self.bytes += count
                accepted = accepted[count:]
        except OSError as error:
            self.failure = "write_failed"
            raise CaptureError("Original capture write failed") from error
        if len(data) > remaining:
            self.failure = "output_cap_exceeded"
            raise CaptureLimitError("Original capture output cap exceeded")
        return len(data)

    def close(self):
        if self.closed:
            return
        try:
            os.fsync(self.fd)
        except OSError:
            self.failure = "original_fsync_failed"
            raise
        finally:
            os.close(self.fd)
            self.closed = True
        _fsync_directory(self.transaction.directory)
        self.stream_closed_identity = _write_json_exclusive(
            self.transaction.directory / STREAM_CLOSED,
            {"schema": SCHEMA, "kind": "stream_closed", "expected_stream_identity": self.identity,
             "failure": self.failure, "within_cap": self.failure is None,
             "max_bytes": self.transaction.max_bytes})


class CaptureTransaction:
    def __init__(self, directory, max_bytes, reservation_identity):
        self.directory, self.max_bytes = directory, max_bytes
        self.reservation_identity = reservation_identity
        self.writer = None
        self.commit_identity = None

    @classmethod
    def reserve(cls, new_directory, *, max_bytes, context):
        _require(type(max_bytes) is int and max_bytes >= 0, "Invalid capture cap", CaptureStateError)
        _require(isinstance(context, dict), "Capture context must be a dictionary", CaptureStateError)
        directory = Path(new_directory).absolute()
        # Validate metadata before reserving, then retain all partial work.
        reservation = {"schema": SCHEMA, "kind": "reservation", "max_bytes": max_bytes,
                       "original_path": ORIGINAL, "context": context}
        _json_bytes(reservation)
        directory.mkdir(mode=0o700, parents=False, exist_ok=False)
        _fsync_directory(directory.parent)
        (directory / "objects").mkdir(mode=0o700)
        _fsync_directory(directory)
        identity = _write_json_exclusive(directory / RESERVATION, reservation)
        return cls(directory, max_bytes, identity)

    def open_original(self):
        _require(self.writer is None, "Original writer already reserved", CaptureStateError)
        self.writer = _CaptureWriter(self)
        return self.writer

    def commit(self):
        _require(self.commit_identity is None and not (self.directory / COMMIT).exists(),
                 "Capture is already committed", CaptureStateError)
        writer = self.writer
        _require(writer is not None and writer.closed and writer.failure is None and
                 writer.stream_closed_identity is not None,
                 "Capture writer must be successfully closed before commit", CaptureStateError)
        _read_json_bound(self.directory / RESERVATION, self.reservation_identity)
        closed = _read_json_bound(self.directory / STREAM_CLOSED, writer.stream_closed_identity)
        expected = writer.identity
        _require(closed["expected_stream_identity"] == expected and closed["failure"] is None,
                 "Closed stream identity differs")
        original = self.directory / ORIGINAL
        _require(file_identity(original, self.max_bytes) == expected,
                 "Original differs from successfully written stream")
        relative = "objects/" + expected["sha256"] + ".bin"
        target = self.directory / relative
        source_fd = os.open(original, os.O_RDONLY | os.O_NOFOLLOW)
        target_fd = None
        copied, digest = 0, hashlib.sha256()
        try:
            source_before = os.fstat(source_fd)
            _require(stat.S_ISREG(source_before.st_mode), "Original is no longer regular")
            target_fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            _require((source_before.st_dev, source_before.st_ino) !=
                     (os.fstat(target_fd).st_dev, os.fstat(target_fd).st_ino),
                     "Object is not independent of original")
            while True:
                chunk = os.read(source_fd, CHUNK_BYTES)
                if not chunk:
                    break
                copied += len(chunk)
                _require(copied <= self.max_bytes, "Original grew during copy")
                _write_all(target_fd, chunk)
                digest.update(chunk)
            _require(_stat_signature(source_before) == _stat_signature(os.fstat(source_fd)),
                     "Original changed during copy")
            _require({"bytes": copied, "sha256": digest.hexdigest()} == expected,
                     "Copied bytes differ from written stream")
            os.fsync(target_fd)
        finally:
            os.close(source_fd)
            if target_fd is not None:
                os.close(target_fd)
        _fsync_directory(target.parent)
        original_identity, _, original_inode = _read_regular(original, self.max_bytes)
        object_identity, _, object_inode = _read_regular(target, self.max_bytes)
        _require(original_identity == object_identity == expected, "Precommit capture verification failed")
        _require(original_inode != object_inode, "Capture copies share an inode")
        record = {"schema": SCHEMA, "kind": "committed_capture", "max_bytes": self.max_bytes,
                  "reservation": {"path": RESERVATION, **self.reservation_identity},
                  "stream_closed": {"path": STREAM_CLOSED, **writer.stream_closed_identity},
                  "original": {"path": ORIGINAL, **expected},
                  "object": {"path": relative, **expected},
                  "independent_inodes": True, "scientific_status_unchanged": True}
        self.commit_identity = _write_json_exclusive(self.directory / COMMIT, record)
        return dict(self.commit_identity)


def load_verified(directory, expected_commit):
    """Return committed bytes only while every independently bound role agrees.

    Pin expected_commit outside this directory before passing it to dependent
    work. A surviving object never silently substitutes for a missing original.
    """
    directory = Path(directory).absolute()
    record = _read_json_bound(directory / COMMIT, expected_commit)
    _require(record.get("schema") == SCHEMA and record.get("kind") == "committed_capture",
             "Wrong capture commit schema")
    _require(record.get("independent_inodes") is True and record.get("scientific_status_unchanged") is True,
             "Capture commit policy differs")
    cap = record["max_bytes"]
    _require(type(cap) is int and cap >= 0, "Invalid committed cap")
    reservation_path, reservation_identity = _bound(record, "reservation")
    closed_path, closed_identity = _bound(record, "stream_closed")
    original_path, expected = _bound(record, "original")
    object_path, object_expected = _bound(record, "object")
    _require(reservation_path == RESERVATION and closed_path == STREAM_CLOSED and
             original_path == ORIGINAL and object_path == "objects/" + expected["sha256"] + ".bin",
             "Unexpected capture role path")
    _require(object_expected == expected and expected["bytes"] <= cap, "Capture role identities differ")
    reservation = _read_json_bound(directory / RESERVATION, reservation_identity)
    closed = _read_json_bound(directory / STREAM_CLOSED, closed_identity)
    _require(reservation.get("schema") == SCHEMA and reservation.get("kind") == "reservation" and
             reservation.get("max_bytes") == cap and reservation.get("original_path") == ORIGINAL,
             "Reservation does not bind this capture")
    _require(closed.get("schema") == SCHEMA and closed.get("kind") == "stream_closed" and
             closed.get("expected_stream_identity") == expected and closed.get("max_bytes") == cap and
             closed.get("failure") is None and closed.get("within_cap") is True,
             "Stream was not closed within its bound")
    original_identity, _, original_inode = _read_regular(directory / ORIGINAL, cap)
    object_identity, payload, object_inode = _read_regular(directory / object_path, cap, collect=True)
    _require(original_identity == object_identity == expected, "Capture content identity mismatch")
    _require(original_inode != object_inode, "Capture copies are no longer independent")
    # Recheck after the object read; no fallback on lost/changed original.
    _require(file_identity(directory / ORIGINAL, cap) == expected, "Original changed before dependent read")
    return payload
