"""Native tangent campaign recording, recovery and checkpoint controls."""
import ctypes as C
import json
import unittest
from unittest.mock import patch
import numpy as np
from . import test_field_backend as fixtures
from .compact import restore_checkpoint
from experiments.field_feedback_preservation_001.numerics import Tangent

class TangentCampaignTests(fixtures.FieldCampaignTests):
    history='compare-tangent';kinds=['float64','field64','tangent64']
    def test_tangent_checkpoint_state_matches_python_tangent(self):
        stream,banks,_=self.restore(self.entries[1]);bank=banks['tangent64']
        self.assertGreater(bank.buffered,0);bank._flush_field()
        self.assertIsNotNone(bank._refresh('scheduled'))
        # Reconstruct Python tangent at the exact native anchor (factor follows
        # an additional GN step, so the last readout is not the anchor).
        anchor=np.frombuffer(bytes(bank.native.context),dtype=np.float64,count=16,offset=153*8).copy()
        reference=Tangent(bank.objective,anchor,stream.index)
        obs,_,_=stream.read(16);rows=bank.field.update(bank.field.count,obs,return_rows=True)
        reference.update(stream.index-16,rows);bank.native.update(stream.index-16,rows)
        expected=reference.query();actual=bank.native.query()
        np.testing.assert_allclose(actual['end'],expected['end'],rtol=2e-9,atol=2e-11)
        a=actual['endpoint_root'];b=expected['endpoint_root']
        np.testing.assert_allclose(a@a.T,b@b.T,rtol=2e-8,atol=2e-13)
    def test_tangent_refresh_rejection_retains_all_evidence(self):
        stream,banks,_=self.restore(self.entries[1]);bank=banks['tangent64'];bank._flush_field()
        before=bank.native.snapshot();message=bank.full_message()
        with patch('experiments.foster_campaign_001.tangent_backend.solve',side_effect=ValueError('test unresolved')):
            self.assertIsNone(bank._refresh('scheduled'))
        np.testing.assert_array_equal(before,bank.native.snapshot());np.testing.assert_array_equal(message,bank.full_message())
        self.assertEqual(bank.native.count,stream.index)
    def test_tangent_bad_order_and_input_leave_committed_state(self):
        stream,banks,_=self.restore(self.entries[1]);bank=banks['tangent64'];first=stream.index
        obs,_,_=stream.read(16);context=bytes(bank.context);native=bank.native.snapshot();state=bank.live_state.copy()
        for start,rows in [(first-16,obs),(first,obs*np.nan)]:
            with self.assertRaises(ValueError):bank.advance(start,rows)
            self.assertEqual(bytes(bank.context),context);np.testing.assert_array_equal(bank.native.snapshot(),native)
            np.testing.assert_array_equal(bank.live_state,state)
    def test_tangent_outgoing_readout_is_not_feedback(self):
        stream,banks,_=self.restore(self.entries[1]);bank=banks['tangent64']
        _,others,_=self.restore(self.entries[1]);other=others['tangent64'];other.carrier.message[5]+=.02
        first=stream.index;obs,_,_=stream.read(16)
        bank.advance(first,obs);other.advance(first,obs)
        np.testing.assert_array_equal(bank.full_message(),other.full_message())
    def test_tangent_failed_recovery_explicitly_stops_arm(self):
        stream,banks,_=self.restore(self.entries[1]);bank=banks['tangent64'];first=stream.index;before=bank.full_message()
        obs,_,_=stream.read(16)
        with patch.object(bank.native,'query',side_effect=ValueError('test outside domain')),patch('experiments.foster_campaign_001.tangent_backend.solve',side_effect=ValueError('test unresolved')):
            with self.assertRaisesRegex(ValueError,'recovery unresolved'):bank.advance(first,obs)
        self.assertTrue(bank.failed);self.assertEqual(bank.counts()['retired_records'],first)
        self.assertEqual(bank.counts()['pending_records'],16);np.testing.assert_array_equal(bank.full_message(),before)
        with self.assertRaisesRegex(ValueError,'already unresolved'):bank.advance(first,obs)
    def test_tangent_restore_wrong_count_rejected(self):
        _,banks,_=self.restore(self.entries[1]);bank=banks['tangent64'];arrays=bank.checkpoint_arrays()
        meta=json.loads(arrays['metadata'].tobytes());meta['live_count']+=1
        arrays['metadata']=np.frombuffer(json.dumps(meta).encode(),dtype=np.uint8)
        with self.assertRaisesRegex(ValueError,'chronology'):bank.restore_arrays(arrays)

if __name__=='__main__':unittest.main()
