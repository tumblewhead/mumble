"""SRAM candidate full/compact/replay and ownership controls, including48bit history."""
import ctypes as C
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from experiments.foster_campaign_001.compact import restore_checkpoint
from experiments.foster_campaign_001.replay import replay

class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.root=Path(cls.tmp.name)
        for recording in ('full','compact'):
            p=subprocess.run([sys.executable,'-B','-m','experiments.foster_campaign_001.run',
              '--history','compare-rowwise','--rowwise-implementation','sram','--sram-history-bits','48','--bank-rank','3','--bank-precision','float64','--hours','.051','--sample-rate-hz','50',
              '--temperature','constant','--loads','embedded','--load-seeds','7','--seeds','1100',
              '--noise-v','.002','--field-refresh-seconds','17','--checkpoint-hours','.01',
              '--summary-bins','37','--recording',recording,'--no-plots','--out',str(cls.root/recording)],
              capture_output=True,text=True,env={**os.environ,'OPENBLAS_NUM_THREADS':'1'},timeout=120)
            if p.returncode:raise AssertionError(p.stdout+p.stderr)
        cls.case=cls.root/'compact/case_0000';cls.full=cls.root/'full/case_0000'
        cls.plan=json.loads((cls.case.parent/'campaign_plan.json').read_text());cls.config=json.loads((cls.case.parent/'calibration.json').read_text())
        cls.scenario=json.loads((cls.case/'scenario.json').read_text());cls.result=json.loads((cls.case/'result.json').read_text())
        cls.entries=json.loads((cls.case/'checkpoints/index.json').read_text())['checkpoints']
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def restore(self):return restore_checkpoint(self.case,self.entries[1],self.config,self.scenario['cell_definition'],self.result['scenario'],self.plan['configuration'])
    def test_full_compact_and_replay(self):
        stream,banks,_=self.restore();start=stream.index/50/3600
        r=replay(self.case,self.root/'debug',start,plots=False,stop_hour=.051)
        for k in banks:
            np.testing.assert_array_equal(np.load(self.full/(k+'_message.npy')),np.load(self.case/(k+'_message.npy')))
            np.testing.assert_array_equal(np.load(self.full/(k+'_message.npy')),np.load(self.root/'debug'/(k+'_message.npy')))
            a=np.load(self.full/(k+'_trace.npy'));a=a[(a[:,0]>stream.index)&(a[:,0]<=int(.051*3600*50))]
            b=np.load(self.root/'debug'/(k+'_trace.npy'))[:r['arms'][k]['outputs']];np.testing.assert_array_equal(a,b)
    def test_fixed_anchor_dense_normal_equations(self):
        _,banks,_=self.restore();b=banks['rowwise_bank'];n=b.native
        x=b.mean+b.prior_root@n.anchor
        B=b.field.root@b.field.features_jacobian(x)@b.prior_root;r=b.field.root@b.field.features(x)
        P=np.eye(16)+B.T@B;g=n.anchor+B.T@r
        np.testing.assert_allclose(n.factor[:16,:16].T@n.factor[:16,:16],P,rtol=3e-8,atol=1e-4)
        np.testing.assert_allclose(n.query()['w'],n.anchor-np.linalg.solve(P,g),rtol=1e-5,atol=1e-7)
    def test_output_not_feedback_and_failure_quarantine(self):
        stream,aa,_=self.restore();_,bb,_=self.restore();a=aa['rowwise_bank'];b=bb['rowwise_bank']
        b._message_view[5]+=.02
        first=stream.index;rows,_,_=stream.read(16)
        a.advance(first,rows);b.advance(first,rows);np.testing.assert_array_equal(a.full_message(),b.full_message())
        with patch.object(a.native,'advance',side_effect=ValueError('injected')):
            with self.assertRaises(ValueError):a.advance(first+16,rows)
        with self.assertRaises(ValueError):a.full_message()
        self.assertEqual(a.publication_status()['execution'],'quarantined')
    def test_bad_restore_quarantines(self):
        _,banks,_=self.restore();b=banks['rowwise_bank'];a=b.checkpoint_arrays();a['projection']=np.zeros(1)
        with self.assertRaises(ValueError):b.restore_arrays(a)
        with self.assertRaises(ValueError):b.full_message()

if __name__=='__main__':unittest.main()
