#!/usr/bin/env python3
"""Restore only the two registered inputs, without interpreting observations/truth."""
import gzip
import hashlib
import importlib.util
import io
import json
import lzma
import os
from pathlib import Path
import tarfile
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def module(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def identity(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1048576), b''):
            h.update(block)
    return {'bytes': path.stat().st_size, 'sha256': h.hexdigest()}


def main():
    plan = json.loads((HERE / 'plan.json').read_text())
    receipt_path = HERE / 'input_restoration001.json'
    if receipt_path.exists():
        raise ValueError('Restoration receipt already exists; verify inputs without repeating restoration')
    restorer_path = ROOT / 'experiments/continuous_learning_validation_001/implementation/evidence/restore_primary.py'
    restore = module(restorer_path)
    target = plan['input']['observations']
    root_fd = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        index, members = restore.load_index(root_fd)
        expected = members[target['path']]
        assert all(expected[k] == target[k] for k in ('bytes', 'sha256'))
        compressed_bytes = restore.verify_parts(root_fd, index)
        found = False
        with io.BufferedReader(restore.PartStream(root_fd, index['parts'])) as parts, lzma.LZMAFile(parts) as decoded:
            with tarfile.open(fileobj=decoded, mode='r|') as archive:
                for entry in archive:
                    if entry.name != target['path']:
                        continue
                    if found or not entry.isreg() or entry.sparse is not None or entry.size != target['bytes']:
                        raise ValueError('Invalid or duplicated selected member')
                    found = True
                    with archive.extractfile(entry) as stream:
                        if restore.existing_match(root_fd, expected):
                            restore.verify_content(stream, expected)
                        else:
                            restore.restore_member(root_fd, expected, stream, 0)
            while decoded.read(1048576):
                pass  # Validate XZ footer; other member values are never parsed.
        assert found
    finally:
        os.close(root_fd)
    transport_dir = ROOT / 'experiments/live_anchor_integration_001/publication_transport001'
    transport = module(transport_dir / 'restore_transport.py')
    bound = json.loads((transport_dir / 'receipt.json').read_text())
    assert identity(transport_dir / 'manifest.json') == bound['manifest_identity']
    assert identity(transport_dir / 'restore_transport.py') == bound['restore_helper_identity']
    manifest = json.loads((transport_dir / 'manifest.json').read_text())
    row = next(r for r in manifest['roles'] if r['original_path'].endswith('/trace_original.jsonl.gz'))
    trace = plan['input']['trace']
    destination = transport.safe(ROOT, trace['path'])
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Keep temporary compression outside the historical artifact directories.
    with tempfile.TemporaryFile() as compressed:
        transport.concatenate(ROOT, row, compressed)
        compressed.seek(0)
        with gzip.GzipFile(fileobj=compressed) as raw, tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as output:
            temporary = Path(output.name)
            try:
                size = 0
                while block := raw.read(1048576):
                    size += len(block)
                    if size > trace['bytes']:
                        raise ValueError('Trace decompressed extent exceeded')
                    output.write(block)
                output.flush()
                os.fsync(output.fileno())
                assert identity(temporary) == {k: trace[k] for k in ('bytes', 'sha256')}
                if destination.exists():
                    assert identity(destination) == identity(temporary), 'Existing trace differs'
                else:
                    os.link(temporary, destination)
            finally:
                temporary.unlink()
    result = {
        'schema': 'mumble_fixed_prefix_input_restoration_v1', 'status': 'verified_restored',
        'method': 'existing_lossless_archives_only', 'source_generation_calls': 0,
        'model_calls': 0, 'optimizer_calls': 0, 'truth_value_reads': 0,
        'compressed_archive_bytes_verified': compressed_bytes,
        'archive_sha256': index['archive_sha256'], 'archive_parts': len(index['parts']),
        'observations': {'path': target['path'], **identity(ROOT / target['path'])},
        'trace': {'path': trace['path'], **identity(destination)},
        'script': identity(Path(__file__)),
        'command': 'python3 -B experiments/fixed_prefix_shape_001/restore_inputs.py',
        'correction': 'Original uncompressed observation path was absent, but exact bytes were already preserved in the tracked primary archive.'}
    with receipt_path.open('x') as f:
        json.dump(result, f, indent=2); f.write('\n'); f.flush(); os.fsync(f.fileno())
    print(json.dumps(result))


if __name__ == '__main__':
    main()
