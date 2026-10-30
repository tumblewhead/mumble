import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from .evidence import verify_parent

class EvidenceTests(unittest.TestCase):
    def test_explicit_omission_and_present_integrity(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); (root/'provenance').mkdir()
            identity=dict(bytes=3,sha256=hashlib.sha256(b'abc').hexdigest())
            receipt=root/'provenance/source_checkpoint_20261030.json'
            receipt.write_text(json.dumps(dict(omitted_parent_artifacts={'plot.png':identity})))
            result=verify_parent(root,{'plot.png':identity})
            self.assertEqual(result['unavailable_by_retention_policy'],['plot.png'])
            self.assertEqual(result['verified'],[])
            (root/'plot.png').write_bytes(b'abc')
            self.assertEqual(verify_parent(root,{'plot.png':identity})['verified'],['plot.png'])
            (root/'plot.png').write_bytes(b'bad')
            with self.assertRaises(ValueError):verify_parent(root,{'plot.png':identity})
    def test_unlisted_or_mismatched_omission_fails(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'provenance').mkdir()
            identity=dict(bytes=3,sha256='a'*64)
            receipt=root/'provenance/source_checkpoint_20261030.json'
            receipt.write_text(json.dumps(dict(omitted_parent_artifacts={'plot.png':dict(bytes=4,sha256='a'*64)})))
            for name in ['plot.png','missing.png']:
                with self.assertRaises(ValueError):verify_parent(root,{name:identity})
    def test_missing_source_cannot_be_exempted(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'provenance').mkdir();identity=dict(bytes=1,sha256='a'*64)
            for name in ['model.c','run.py','calibration.json']:
                (root/'provenance/source_checkpoint_20261030.json').write_text(json.dumps(dict(omitted_parent_artifacts={name:identity})))
                with self.assertRaises(ValueError):verify_parent(root,{name:identity})
