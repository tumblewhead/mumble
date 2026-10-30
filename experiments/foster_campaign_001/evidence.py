"""Verify retained evidence without requiring deliberately undistributed outputs."""
import hashlib
import json
from pathlib import Path


def verify_parent(root, expected):
    receipt = root / 'provenance/source_checkpoint_20261030.json'
    omitted = json.loads(receipt.read_text()).get('omitted_parent_artifacts', {}) if receipt.exists() else {}
    verified, unavailable = [], []
    for name, identity in expected.items():
        path = root / name
        if path.is_file():
            digest = hashlib.sha256()
            with path.open('rb') as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(block)
            actual = dict(bytes=path.stat().st_size, sha256=digest.hexdigest())
            if actual != identity:
                raise ValueError('preserved parent evidence changed: ' + name)
            verified.append(name)
        else:
            generated = path.suffix in {'.pdf', '.png', '.so', '.npy', '.npz', '.csv', '.bin'} or path.name == 'result.json'
            if not generated or omitted.get(name) != identity:
                raise ValueError('required parent artifact missing: ' + name)
            unavailable.append(name)
    return dict(verified=verified, unavailable_by_retention_policy=unavailable,
                scope='Only present artifacts verified; unavailable outputs are not requalified.')
