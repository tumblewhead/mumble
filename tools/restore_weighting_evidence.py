#!/usr/bin/env python3
"""Restore only the three immutable members named by weighting diagnostic 001."""

import argparse
import hashlib
import importlib.util
import io
import json
import lzma
import os
from pathlib import Path
import resource
import sys
import tarfile
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    started = time.monotonic()
    root = args.root.resolve()
    plan_path = root / 'plans/weighting_output_diagnostic_001.json'
    plan_bytes = plan_path.read_bytes()
    plan = json.loads(plan_bytes)
    selected = {item['path']: item for item in plan['inputs']['archive_members']}
    if len(selected) != 3 or sum(item['bytes'] for item in selected.values()) > plan['resource_bounds']['restore_selected_bytes_max']:
        raise RuntimeError('Unexpected member selection or byte budget')
    helper_path = root / 'experiments/continuous_learning_validation_001/implementation/evidence/restore_primary.py'
    spec = importlib.util.spec_from_file_location('preserved_primary_restore', helper_path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    if args.destination.exists():
        raise RuntimeError('Destination must be absent; existing evidence is never overwritten')
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    if args.receipt.exists():
        raise RuntimeError('Receipt already exists; preserve it')
    args.destination.mkdir(parents=True)
    source_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    destination_fd = os.open(args.destination, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    seen = set()
    restored = []
    try:
        index, expected = helper.load_index(source_fd)
        if index['archive_sha256'] != plan['inputs']['archive_sha256']:
            raise RuntimeError('Archive identity differs from frozen plan')
        for name, item in selected.items():
            if expected.get(name) != item:
                raise RuntimeError('Indexed selected member differs: ' + name)
        archive_bytes = helper.verify_parts(source_fd, index)
        with io.BufferedReader(helper.PartStream(source_fd, index['parts'])) as pieces:
            with lzma.LZMAFile(pieces, 'rb') as decoded:
                with tarfile.open(fileobj=decoded, mode='r|') as archive:
                    for member in archive:
                        name = str(helper.relative_path(member.name))
                        if name not in expected or name in seen:
                            raise RuntimeError('Unexpected or duplicated archive member: ' + name)
                        record = expected[name]
                        if not member.isreg() or member.sparse is not None or member.size != record['bytes'] or member.mode != helper.MODES[record['mode']]:
                            raise RuntimeError('Member metadata mismatch: ' + name)
                        seen.add(name)
                        if name in selected:
                            with archive.extractfile(member) as stream:
                                helper.restore_member(destination_fd, record, stream, len(seen))
                            restored.append(record)
                        if time.monotonic() - started > plan['resource_bounds']['restoration_wall_s_max']:
                            raise RuntimeError('Frozen restoration wall-time limit exceeded')
                while decoded.read(helper.BUFFER_BYTES):
                    pass
        if seen != set(expected) or set(item['path'] for item in restored) != set(selected):
            raise RuntimeError('Archive or selection is incomplete')
        elapsed = time.monotonic() - started
        if elapsed > plan['resource_bounds']['restoration_wall_s_max']:
            raise RuntimeError('Frozen restoration wall-time limit exceeded')
        receipt = {
            'schema': 'mumble_weighting_evidence_restoration_v1', 'status': 'verified_selected_members_restored',
            'base_revision': plan['base_revision'],
            'plan_sha256': hashlib.sha256(plan_bytes).hexdigest(),
            'restorer_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'preserved_helper_sha256': hashlib.sha256(helper_path.read_bytes()).hexdigest(),
            'archive_sha256': index['archive_sha256'], 'archive_bytes_verified': archive_bytes,
            'parts_sha256_verified': len(index['parts']), 'archive_member_headers_checked': len(seen),
            'selected_members_SHA256_and_Git_blob_verified': restored,
            'selected_bytes_restored': sum(item['bytes'] for item in restored),
            'XZ_footer_checked': True, 'destination': str(args.destination.resolve()),
            'wall_s': elapsed, 'own_peak_RSS_bytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1024 if sys.platform != 'darwin' else 1),
            'new_learner_calls': 0, 'new_generator_calls': 0, 'old_scorer_calls': 0,
            'primary_artifacts_modified': False,
        }
        with args.receipt.open('x') as stream:
            json.dump(receipt, stream, indent=2)
            stream.write('\n')
        print(json.dumps({'status': receipt['status'], 'selected_bytes': receipt['selected_bytes_restored'], 'wall_s': elapsed, 'receipt': str(args.receipt)}))
    finally:
        os.close(source_fd)
        os.close(destination_fd)


if __name__ == '__main__':
    main()
