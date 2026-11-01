"""Streaming H7 integration, original-origin ownership, compact replay and plots."""
import ctypes as C
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import numpy as np
from experiments.foster_campaign_001 import test_field_backend as fixtures
from experiments.foster_campaign_001.backend import arm_kinds
from experiments.foster_campaign_001.run import parser
from experiments.foster_campaign_001.compact import restore_checkpoint
from experiments.foster_campaign_001.replay import replay
from experiments.hysteresis_refinement_001.field import transported
from experiments.slow_likelihood_diagnostic_001.numerics import solve


class H7CampaignTests(unittest.TestCase):
    history='compare-h7';kinds=['tangent64','tangent_h7']
    @classmethod
    def setUpClass(cls):fixtures.FieldCampaignTests.setUpClass.__func__(cls)
    @classmethod
    def tearDownClass(cls):fixtures.FieldCampaignTests.tearDownClass.__func__(cls)
    def restore(self,entry):return restore_checkpoint(self.case,entry,self.config,self.cell,self.result['scenario'],self.settings)
    def test_checkpoint_storage_plan_bounds_numeric_payload(self):
        from experiments.foster_campaign_001.compact import storage_plan
        plan=storage_plan(.1,50,37,.01,2,field_arms=2,h7_arms=1)
        entry=self.entries[1]
        with np.load(self.case/'checkpoints'/entry['file']) as z:
            payload=sum(z[k].nbytes for k in z.files if k!='metadata')
        planned=plan['checkpoint_context_MB']*1e6/plan['checkpoint_count']
        self.assertLessEqual(payload,planned)

    def test_modes_and_full_compact_parity(self):
        self.assertEqual(arm_kinds(parser().parse_args(['--history','tangent-h7'])),['tangent_h7'])
        self.assertEqual(set(self.result['arms']),set(self.kinds))
        other=json.loads((self.full/'result.json').read_text())
        for kind in self.kinds:
            self.assertEqual(self.result['arms'][kind],other['arms'][kind])
            np.testing.assert_array_equal(np.load(self.case/(kind+'_message.npy')),np.load(self.full/(kind+'_message.npy')))
            self.assertGreater(self.result['arms'][kind]['field_history']['accepted'],0)
    def test_checkpoint_pending_rows_replays_bitwise(self):
        entry=self.entries[1];stream,banks,meta=self.restore(entry);self.assertGreater(banks['tangent_h7'].buffered,0)
        self.assertIn('h7_tangent_binary',meta['binding']);self.assertIn('h7_response_binary',meta['binding'])
        start=entry['sequence']/50/3600
        result=replay(self.case,self.root/'replay',start,plots=False,stop_hour=start+.015)
        for kind in self.kinds:
            expected=np.load(self.full/(kind+'_trace.npy'));actual=np.load(self.root/'replay'/(kind+'_trace.npy'))[:result['arms'][kind]['outputs']]
            selected=expected[(expected[:,0]>entry['sequence'])&(expected[:,0]<=int((start+.015)*3600*50))]
            np.testing.assert_array_equal(actual,selected)
    def test_refresh_matches_full_mixed_field(self):
        stream,banks,_=self.restore(self.entries[1]);bank=banks['tangent_h7'];bank._flush_field()
        fit=solve(bank.objective,start=bank.w)
        _,g,P,_,_=bank.objective(fit['w'])
        corrected=bank.mean+bank.prior_root@(fit['w']-np.linalg.solve(P,g))
        expected,D=transported(bank.field,corrected)
        out=bank._refresh('scheduled');self.assertIsNotNone(out)
        # Native readout takes one additional linear GN step from the stopped fit.
        np.testing.assert_allclose(out['end'],expected,rtol=2e-8,atol=3e-10)
        A=out['endpoint_root'];B=D@bank.prior_root@np.linalg.solve(np.linalg.cholesky(P).T,np.eye(16));np.testing.assert_allclose(A@A.T,B@B.T,rtol=3e-5,atol=2e-9)
        self.assertEqual(bank.field.width,112);self.assertEqual(len(bank.live_state),167)
    def test_readout_is_not_feedback_and_refresh_failure_keeps_evidence(self):
        stream,banks,_=self.restore(self.entries[1]);_,others,_=self.restore(self.entries[1])
        a=banks['tangent_h7'];b=others['tangent_h7'];b.carrier.message[5]+=.02
        first=stream.index;rows,_,_=stream.read(16);a.advance(first,rows);b.advance(first,rows)
        np.testing.assert_array_equal(a.full_message(),b.full_message())
        saved=a.native.snapshot();message=a.full_message()
        with patch('experiments.foster_campaign_001.tangent_backend.solve',side_effect=ValueError('test unresolved')):
            self.assertIsNone(a._refresh('scheduled'))
        np.testing.assert_array_equal(saved,a.native.snapshot());np.testing.assert_array_equal(message,a.full_message())
    def test_partial_window_overflow(self):
        stream,banks,_=self.restore(self.entries[1]);a=banks['tangent_h7']
        first=stream.index;rows,_,_=stream.read(8);a.advance(first,rows)
        while a.buffered+16<=4096:
            first=stream.index;rows,_,_=stream.read(16);a.advance(first,rows)
        first=stream.index;rows,_,_=stream.read(16);saved=a.checkpoint_arrays();carrier=bytes(a.context)
        bad=rows.copy();bad[-1,4]=0
        with self.assertRaises(ValueError):a.advance(first,bad)
        self.assertEqual(bytes(a.context),carrier)
        for k,v in saved.items():np.testing.assert_array_equal(a.checkpoint_arrays()[k],v)
        a.advance(first,rows);a._flush_field();np.testing.assert_array_equal(a.field.state,a.live_state)
    def test_cross_degree_checkpoint_rejected(self):
        _,banks,_=self.restore(self.entries[1])
        with self.assertRaisesRegex(ValueError,'shape'):banks['tangent_h7'].restore_arrays(banks['tangent64'].checkpoint_arrays())
    def test_compact_plot_and_summary_error_comparison(self):
        from experiments.foster_campaign_001.plot import render,render_summary,ARM_COLORS
        self.assertNotEqual(ARM_COLORS['tangent64'],ARM_COLORS['tangent_h7'])
        render(self.case,self.result,self.config,self.cell,self.root/'plots',0,None)
        summary=json.loads((self.campaign/'summary.json').read_text())
        r=render_summary(self.campaign,self.root/'overlay')
        self.assertTrue((self.root/'plots/errors.png').exists())
        self.assertTrue((self.root/'overlay/errors.png').exists())
        self.assertTrue(r['parameter_error_comparison'])

if __name__=='__main__':unittest.main()
