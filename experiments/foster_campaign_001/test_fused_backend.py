"""Campaign integration for fused scratch and failure publication semantics."""
import numpy as np
from . import test_tangent_backend as fixtures
from .field_backend import BUFFER_RECORDS


class FusedCampaignTests(fixtures.TangentCampaignTests):
    def test_storage_includes_scratch_before_first_observation(self):
        _,banks,_=self.restore(self.entries[0])
        self.assertEqual(banks['tangent64'].storage()['native_fused_workspace_B'],3360)

    def test_nonfinite_publication_does_not_change_committed_message(self):
        _,banks,_=self.restore(self.entries[1]);bank=banks['tangent64']
        result=bank.native.query(state=bank.live_state,count=bank.live_count)
        before=bytes(bank.context);old_w=bank.w.copy()
        for key in ('end','endpoint_root'):
            bad={k:v.copy() if hasattr(v,'copy') else v for k,v in result.items()}
            bad[key].flat[0]=np.nan
            with self.assertRaisesRegex(ValueError,'nonfinite'):bank._publish(bad,bank.live_count,bank.carrier.ticks)
            self.assertEqual(bytes(bank.context),before);np.testing.assert_array_equal(bank.w,old_w)

    def test_irregular_partial_window_overflow_preserves_transport(self):
        stream,banks,_=self.restore(self.entries[1]);bank=banks['tangent64']
        # Shift the retirement partition by8records. No scheduled16-aligned
        # refresh will hide the rare raw-buffer-overflow path under test.
        first=stream.index;rows,_,_=stream.read(8);bank.advance(first,rows)
        while bank.buffered+16<=BUFFER_RECORDS:
            first=stream.index;rows,_,_=stream.read(16);bank.advance(first,rows)
        self.assertEqual(bank.buffered,BUFFER_RECORDS-8)
        first=stream.index;rows,_,_=stream.read(16)
        before=bank.checkpoint_arrays();context=bytes(bank.context)
        invalid=rows.copy();invalid[-1,4]=0
        with self.assertRaises(ValueError):bank.advance(first,invalid)
        self.assertEqual(context,bytes(bank.context))
        for key,val in before.items():np.testing.assert_array_equal(bank.checkpoint_arrays()[key],val)
        bank.advance(first,rows)
        self.assertEqual(bank.field.count,first)
        self.assertEqual(bank.buffered,16)
        self.assertEqual(bank.native.count,first+16)
        bank._flush_field()
        np.testing.assert_array_equal(bank.field.state,bank.live_state)
