"""Failure recording and survivor replay through the real campaign entry points."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from experiments.foster_campaign_001 import run
from experiments.foster_campaign_001.h7_backend import H7Backend
from experiments.foster_campaign_001.replay import replay


ORIGINAL_PUBLISH = H7Backend._publish


def fail_second_publication(self, result, sequence, ticks, tokens=None):
    if sequence == 32:
        raise ValueError('injected second H7 publication failure')
    return ORIGINAL_PUBLISH(self, result, sequence, ticks, tokens)


class RecordingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='h7-failed-recording-')
        cls.root = Path(cls.temp.name)
        cls.results = {}
        for recording in ('full', 'compact'):
            out = cls.root / recording
            argv = ['campaign', '--hours', '.05', '--sample-rate-hz', '50',
                    '--cells', 'A', '--loads', 'embedded', '--load-seeds', '7',
                    '--seeds', '1100', '--noise-v', '.002', '--history', 'compare-h7',
                    '--field-refresh-seconds', '17', '--recording', recording,
                    '--checkpoint-hours', '.01', '--summary-bins', '37',
                    '--jobs', '1', '--no-plots', '--out', str(out)]
            with patch.object(sys, 'argv', argv), \
                 patch.object(H7Backend, '_publish', fail_second_publication), \
                 contextlib.redirect_stdout(io.StringIO()):
                status = run.main()
            if status != 1:
                raise AssertionError('injected failure must produce unsuccessful campaign status')
            cls.results[recording] = json.loads((out/'case_0000/result.json').read_text())

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def assert_failed_arm(self, arm):
        self.assertEqual(arm['status'], 'unresolved')
        self.assertEqual(arm['received_records'], 32)
        self.assertEqual(arm['retired_records'], 16)
        self.assertEqual(arm['pending_records'], 16)
        self.assertEqual(arm['publication']['execution'], 'quarantined')
        self.assertEqual(arm['publication']['readout'], 'unavailable')
        self.assertEqual(arm['publication']['authorization'], 'unresolved')
        self.assertEqual(arm['outputs'], 1)

    def test_full_and_compact_save_diagnostic_message_and_surviving_arm(self):
        for recording, result in self.results.items():
            self.assert_failed_arm(result['arms']['tangent_h7'])
            self.assertEqual(result['arms']['tangent64']['status'], 'completed')
            self.assertEqual(result['arms']['tangent64']['retired_records'], 9000)
            message = np.load(self.root/recording/'case_0000/tangent_h7_message.npy')
            self.assertTrue(np.isfinite(message).all())
        for kind in ('tangent64', 'tangent_h7'):
            np.testing.assert_array_equal(
                np.load(self.root/'full/case_0000'/(kind+'_message.npy')),
                np.load(self.root/'compact/case_0000'/(kind+'_message.npy')))

    def test_failed_arm_absent_from_resumable_payload_survivor_replays(self):
        case = self.root/'compact/case_0000'
        entries = json.loads((case/'checkpoints/index.json').read_text())['checkpoints']
        entry = next(e for e in entries if e['sequence'] == 8192)
        with np.load(case/'checkpoints'/entry['file']) as arrays:
            metadata = json.loads(arrays['metadata'].tobytes())
            self.assertEqual(metadata['active'], ['tangent64'])
            self.assertEqual(metadata['stats']['tangent_h7']['status'], 'unresolved')
            self.assertFalse(any(k.startswith('tangent_h7') for k in arrays.files))
        out = self.root/'survivor_replay'
        with contextlib.redirect_stdout(io.StringIO()):
            result = replay(case, out, 8192/50/3600, duration_s=5, plots=False)
        self.assertEqual(set(result['arms']), {'tangent64'})
        self.assertEqual(result['arms']['tangent64']['status'], 'completed')
        reference = np.load(self.root/'full/case_0000/tangent64_trace.npy')
        expected = reference[(reference[:,0] > 8192) & (reference[:,0] <= 8442)]
        actual = np.load(out/'tangent64_trace.npy')[:result['arms']['tangent64']['outputs']]
        np.testing.assert_array_equal(actual, expected)

    def test_debug_replay_records_failed_publication_without_aborting_survivor(self):
        case = self.root/'compact/case_0000'
        out = self.root/'failure_replay'
        with patch.object(H7Backend, '_publish', fail_second_publication), \
             contextlib.redirect_stdout(io.StringIO()):
            result = replay(case, out, 0, duration_s=10, plots=False)
        self.assert_failed_arm(result['arms']['tangent_h7'])
        self.assertEqual(result['arms']['tangent64']['status'], 'completed')
        np.testing.assert_array_equal(np.load(out/'tangent_h7_message.npy'),
                                      np.load(case/'tangent_h7_message.npy'))


if __name__ == '__main__':
    unittest.main()
