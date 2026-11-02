"""Joint-history replacement, analytic transport, recording and replay controls."""
import ctypes as C
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np
from .backend import CBackend,make_backend
from .compact import restore_checkpoint
from .field_backend import transported
from .replay import replay
from .telemetry import trace_row
from experiments.foster_c_baseline_001.reference import ptr
from experiments.slow_likelihood_diagnostic_001.numerics import solve


def assert_arm_parity(test, left, right, kind):
    a=copy.deepcopy(left['arms'][kind]);b=copy.deepcopy(right['arms'][kind])
    # Full recording names the observation file; compact names its exact recipe.
    # Both must retain their own real identity in the new status envelope.
    for case,arm in [(left,a),(right,b)]:
        if 'publication' in arm:
            test.assertEqual(arm['publication'].pop('source_id'),case['source_id'])
            test.assertEqual(arm['publication']['model_id'],case['model_id'])
    test.assertEqual(a,b)


class FieldCampaignTests(unittest.TestCase):
    history="compare"
    kinds=["float64","field64"]
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='mumble-field-campaign-');cls.root=Path(cls.temp.name)
        for recording in ['full','compact']:
            command=[sys.executable,'-B','-m','experiments.foster_campaign_001.run',
                     '--hours','.10002','--sample-rate-hz','50','--cells','A',
                     '--loads','embedded','--load-seeds','7','--seeds','1100','--noise-v','.002',
                     '--history',cls.history,'--encoding','float64','--field-refresh-seconds','17',
                     '--recording',recording,'--checkpoint-hours','.01','--summary-bins','37',
                     '--no-plots','--out',str(cls.root/recording)]
            proc=subprocess.run(command,capture_output=True,text=True,timeout=90)
            if proc.returncode:raise AssertionError(proc.stdout+proc.stderr)
        cls.campaign=cls.root/'compact';cls.case=cls.campaign/'case_0000';cls.full=cls.root/'full/case_0000'
        cls.config=json.loads((cls.campaign/'calibration.json').read_text())
        cls.result=json.loads((cls.case/'result.json').read_text())
        cls.settings=json.loads((cls.campaign/'campaign_plan.json').read_text())['configuration']
        cls.cell=json.loads((cls.case/'scenario.json').read_text())['cell_definition']
        cls.entries=json.loads((cls.case/'checkpoints/index.json').read_text())['checkpoints']

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def restore(self,entry):
        return restore_checkpoint(self.case,entry,self.config,self.cell,self.result['scenario'],self.settings)

    def test_full_compact_joint_message_and_metrics_match(self):
        other=json.loads((self.full/'result.json').read_text())
        for kind in self.kinds:
            np.testing.assert_array_equal(np.load(self.case/(kind+'_message.npy')),np.load(self.full/(kind+'_message.npy')))
            assert_arm_parity(self,self.result,other,kind)
        audit=self.result['arms']['field64']['field_history']
        self.assertGreater(audit['accepted'],0)
        self.assertEqual(audit['accumulated_records']+audit['buffered_records'],self.result['records'])
        self.assertFalse((self.case/'observations.npy').exists())
        self.assertIsNone(self.result['encoding_difference'])

    def test_baseline_arm_unchanged_by_field(self):
        r=json.loads((self.full/'result.json').read_text())
        b=CBackend(self.full.parent,self.config,r['source_id'],r['model_id'],'float64',50)
        obs=np.load(self.full/'observations.npy');expected=np.load(self.full/'float64_trace.npy')
        for start in range(0,len(obs),16):
            rows=obs[start:start+16];read,_=b.advance(start,rows)
            np.testing.assert_array_equal(trace_row(read,rows[-1],self.config),expected[start//16])

    def test_checkpoint_with_pending_field_rows_replays_exactly(self):
        entry=self.entries[1];stream,banks,_=self.restore(entry)
        self.assertGreater(banks['field64'].buffered,0)
        dest=self.root/'debug';start=entry['sequence']/50/3600
        result=replay(self.case,dest,start,plots=False,stop_hour=start+.015)
        for kind in self.kinds:
            expected=np.load(self.full/(kind+'_trace.npy'))
            actual=np.load(dest/(kind+'_trace.npy'))[:result['arms'][kind]['outputs']]
            selected=expected[(expected[:,0]>entry['sequence'])&(expected[:,0]<=int((start+.015)*3600*50))]
            np.testing.assert_array_equal(actual,selected)
            self.assertEqual(result['arms'][kind]['status'],'completed')

    def test_transport_matches_native_and_independent_difference(self):
        _,banks,_=self.restore(self.entries[1]);bank=banks['field64'];bank._flush_field()
        x=bank.mean+bank.prior_root@bank.w;end,D=transported(bank.field,x)
        from experiments.foster_uncertainty_audit_001.conditional_packet import chart_from,partition
        def native(y):return chart_from(bank.field.outgoing(y),partition(y)[1])
        np.testing.assert_allclose(end,native(x),rtol=1e-12,atol=1e-12)
        delta=1e-6;J=np.column_stack([(native(x+delta*np.eye(16)[i])-native(x-delta*np.eye(16)[i]))/(2*delta) for i in range(16)])
        np.testing.assert_allclose(D,J,rtol=2e-6,atol=2e-7)

    def test_replacement_uses_original_prior_once_and_keeps_counters(self):
        stream,banks,_=self.restore(self.entries[1]);bank=banks['field64'];bank._flush_field()
        fit=solve(bank.objective,start=bank.w);end,D=transported(bank.field,fit['x'])
        expected=np.r_[end,(D@fit['root']).ravel()]
        counts=super(type(bank),bank).counts();old=bank.full_message();altered=old.copy();altered[5]+=.01
        self.assertEqual(bank.lib.campaign_replace_message(bank.context,stream.index,ptr(altered)),0)
        self.assertTrue(bank._replace(stream.index))
        np.testing.assert_allclose(bank.full_message()[:272],expected,rtol=1e-12,atol=1e-12)
        self.assertEqual(super(type(bank),bank).counts(),counts)

    def test_failed_refresh_preserves_committed_distribution(self):
        stream,banks,_=self.restore(self.entries[1]);bank=banks['field64'];bank._flush_field()
        before=bank.full_message().copy()
        with patch('experiments.foster_campaign_001.field_backend.solve',side_effect=ValueError('outside computational rate box')):
            self.assertFalse(bank._replace(stream.index))
        np.testing.assert_array_equal(bank.full_message(),before)
        self.assertIn('outside computational',bank.audit['last_rejection']['reason'])
        self.assertGreater(bank.audit['rejected'],0)

    def test_replacement_wrong_boundary_and_nonfinite_rejected(self):
        stream,banks,_=self.restore(self.entries[1]);bank=banks['field64'];before=bank.full_message()
        self.assertLess(bank.lib.campaign_replace_message(bank.context,stream.index+1,ptr(before)),0)
        bad=before.copy();bad[0]=np.nan
        self.assertLess(bank.lib.campaign_replace_message(bank.context,stream.index,ptr(bad)),0)
        np.testing.assert_array_equal(bank.full_message(),before)


if __name__=='__main__':unittest.main()
