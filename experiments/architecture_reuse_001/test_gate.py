import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from .gate import verify


class Gate(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        data=json.dumps({'decision':'accepted'}).encode();(self.root/'review.json').write_bytes(data)
        self.manifest={'schema':'architecture_proof_gate_v1',
            'bindings':{'review.json':{'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}},
            'assertions':[{'file':'review.json','keys':['decision'],'equals':'accepted'}]}
    def tearDown(self):self.tmp.cleanup()
    def test_matching_binding(self):self.assertEqual(verify(self.root,self.manifest)['status'],'reviewed_bindings_match')
    def test_changed_review_or_source_rejected(self):
        (self.root/'review.json').write_text('{"decision":"not accepted"}')
        with self.assertRaisesRegex(ValueError,'identity changed'):verify(self.root,self.manifest)
    def test_rejected_decision_not_overridden_by_matching_hash(self):
        self.manifest['assertions'][0]['equals']='rejected'
        with self.assertRaisesRegex(ValueError,'qualification assertion'):verify(self.root,self.manifest)
    def test_unbound_claim_rejected(self):
        self.manifest['assertions'][0]['file']='other.json'
        with self.assertRaisesRegex(ValueError,'unbound assertion'):verify(self.root,self.manifest)


if __name__=='__main__':unittest.main()
