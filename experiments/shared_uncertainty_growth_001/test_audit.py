import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from experiments.shared_uncertainty_growth_001.audit import load_inputs,require_identity
from experiments.uncertainty_weak_stimulus_001.diagnostics import identity


class InputGuardTests(unittest.TestCase):
    def test_changed_payload_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'data';p.write_bytes(b'original');expected=identity(p)
            require_identity(p,expected)
            p.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'changed input'):require_identity(p,expected)

    def test_unvalidated_input_rejected_before_model(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'validated.json').write_text(json.dumps({'status':'running'}))
            with self.assertRaisesRegex(ValueError,'unvalidated'):load_inputs(p,16)

    def test_unregistered_prefix_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            np.save(p/'observations.npy',np.zeros((16,5)))
            (p/'calibration.json').write_text('{}')
            (p/'validated.json').write_text(json.dumps(dict(status='validated',
                observations=identity(p/'observations.npy'),calibration=identity(p/'calibration.json'),
                selected=[dict(sequence=16)])))
            (p/'prefix_32.json').write_text(json.dumps(dict(sequence=32)))
            with self.assertRaisesRegex(ValueError,'prefix mismatch'):load_inputs(p,32)

if __name__=='__main__':unittest.main()
