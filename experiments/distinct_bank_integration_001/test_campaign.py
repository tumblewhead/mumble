"""Campaign usability, ownership, checkpoint and recording parity controls."""
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
from experiments.foster_campaign_001.backend import arm_kinds
from experiments.foster_campaign_001.compact import restore_checkpoint, storage_plan
from experiments.foster_campaign_001.replay import replay
from experiments.foster_campaign_001.run import parser
from experiments.foster_campaign_001.test_field_backend import assert_arm_parity
from experiments.foster_c_baseline_001.reference import ptr
from experiments.slow_likelihood_diagnostic_001.numerics import solve


class BankCampaignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='mumble-bank-campaign-')
        cls.root=Path(cls.temp.name)
        cls.command=[sys.executable,'-B','-m','experiments.foster_campaign_001.run',
            '--hours','.05102','--sample-rate-hz','50','--cells','A','--loads','embedded',
            '--load-seeds','7','--seeds','1100','--noise-v','.002','--history','compare-bank',
            '--temperature','constant','--field-refresh-seconds','17',
            '--checkpoint-hours','.01','--summary-bins','37','--no-plots']
        for recording in ('full','compact'):
            p=subprocess.run([*cls.command,'--recording',recording,'--out',str(cls.root/recording)],
                capture_output=True,text=True,timeout=120,env={**os.environ,'OPENBLAS_NUM_THREADS':'1'})
            if p.returncode:raise AssertionError(p.stdout+p.stderr)
        cls.campaign=cls.root/'compact';cls.case=cls.campaign/'case_0000'
        cls.full=cls.root/'full/case_0000'
        cls.result=json.loads((cls.case/'result.json').read_text())
        cls.config=json.loads((cls.campaign/'calibration.json').read_text())
        cls.plan=json.loads((cls.campaign/'campaign_plan.json').read_text())
        cls.cell=json.loads((cls.case/'scenario.json').read_text())['cell_definition']
        cls.entries=json.loads((cls.case/'checkpoints/index.json').read_text())['checkpoints']

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def restore(self):
        return restore_checkpoint(self.case,self.entries[1],self.config,self.cell,
                                  self.result['scenario'],self.plan['configuration'])

    def test_modes_and_temperature_rejection(self):
        self.assertEqual(arm_kinds(parser().parse_args([])),['field64'])
        self.assertEqual(arm_kinds(parser().parse_args(['--history','distinct-bank'])),['distinct_bank'])
        for extra in ([],['--temperature','constant','--temperature-mean-c','26']):
            out=self.root/'should_not_exist'
            p=subprocess.run([sys.executable,'-B','-m','experiments.foster_campaign_001.run',
                '--history','distinct-bank','--out',str(out),*extra],capture_output=True,text=True)
            self.assertEqual(p.returncode,2);self.assertIn('requires --temperature constant',p.stderr)
            self.assertFalse(out.exists())

    def test_full_compact_same_joint_message_metrics_and_bounded_files(self):
        other=json.loads((self.full/'result.json').read_text())
        self.assertEqual(self.result['status'],'completed')
        for kind in ('field64','distinct_bank'):
            assert_arm_parity(self,self.result,other,kind)
            np.testing.assert_array_equal(np.load(self.case/(kind+'_message.npy')),np.load(self.full/(kind+'_message.npy')))
            audit=self.result['arms'][kind]['field_history']
            self.assertGreater(audit['accepted'],0)
            self.assertEqual(audit['accumulated_records']+audit['buffered_records'],self.result['records'])
        self.assertFalse((self.case/'observations.npy').exists())
        with np.load(self.case/'plot_summary.npz') as z:
            self.assertTrue(all(len(z[key])<=37 for key in z.files))

    def test_nonzero_checkpoint_replay_is_bitwise_and_bound(self):
        stream,banks,meta=self.restore()
        self.assertGreater(banks['distinct_bank'].buffered,0)
        self.assertIn('bank_map',meta['binding']);self.assertIn('bank_h_binary',meta['binding'])
        self.assertIn('experiments/rc_sensitivity_basis_001/response.c',meta['binding']['sources'])
        start=stream.index/50/3600
        dest=self.root/'debug'
        result=replay(self.case,dest,start,plots=False,stop_hour=.05102)
        for kind in banks:
            expected=np.load(self.full/(kind+'_trace.npy'))
            expected=expected[(expected[:,0]>stream.index)&(expected[:,0]<=int(.05102*3600*50))]
            actual=np.load(dest/(kind+'_trace.npy'))[:result['arms'][kind]['outputs']]
            np.testing.assert_array_equal(actual,expected)
            np.testing.assert_array_equal(np.load(dest/(kind+'_message.npy')),np.load(self.case/(kind+'_message.npy')))

    def test_transaction_rejections_and_checkpoint_identity(self):
        stream,banks,_=self.restore();bank=banks['distinct_bank']
        before=bank.checkpoint_arrays();context=bytes(bank.context)
        rows,_,_=stream.read(16)
        for invalid in ('temperature','order'):
            bad=rows.copy();first=stream.index-16
            if invalid=='temperature':bad[-1,2]=26.
            else:first+=1
            with self.assertRaises(ValueError):bank.advance(first,bad)
            self.assertEqual(bytes(bank.context),context)
        # Force a QR failure after the native carrier has advanced.
        bank.interval=16;before=bank.checkpoint_arrays()
        with patch('numpy.linalg.qr',side_effect=np.linalg.LinAlgError('injected QR')):
            with self.assertRaises(np.linalg.LinAlgError):bank.advance(stream.index-16,rows)
        self.assertEqual(bytes(bank.context),context)
        for k,v in before.items():np.testing.assert_array_equal(bank.checkpoint_arrays()[k],v)
        bad={k:v.copy() for k,v in before.items()}
        meta=json.loads(bad['metadata'].tobytes());meta['binding']['map_sha256']='wrong'
        bad['metadata']=np.frombuffer(json.dumps(meta).encode(),dtype=np.uint8)
        with self.assertRaisesRegex(ValueError,'identity/configuration'):bank.restore_arrays(bad)
        for k,v in before.items():np.testing.assert_array_equal(bank.checkpoint_arrays()[k],v)

    def test_full_history_replacement_original_prior_once(self):
        stream,banks,_=self.restore();bank=banks['distinct_bank'];bank._flush_field()
        fit=solve(bank.objective,start=bank.w);end,D=bank.field.transported(fit['x'])
        expected=np.r_[end,(D@fit['root']).ravel()]
        old=bank.full_message();altered=old.copy();altered[5]+=.01
        self.assertEqual(bank.lib.campaign_replace_message(bank.context,stream.index,ptr(altered)),0)
        self.assertTrue(bank._replace(stream.index))
        np.testing.assert_allclose(bank.full_message()[:272],expected,rtol=1e-12,atol=1e-12)
        before=bank.full_message()
        with patch('experiments.foster_campaign_001.field_backend.solve',side_effect=ValueError('test unresolved')):
            self.assertFalse(bank._replace(stream.index))
        np.testing.assert_array_equal(bank.full_message(),before)

    def test_multichunk_flush_failure_restores_all_history(self):
        stream,banks,_=self.restore();bank=banks['distinct_bank'];bank.interval=100000
        while bank.buffered+16<4096:
            first=stream.index;rows,_,_=stream.read(16);bank.advance(first,rows)
        first=stream.index;rows,_,_=stream.read(16)
        before=bank.checkpoint_arrays();context=bytes(bank.context)
        original=np.linalg.qr;calls=0
        def fail_second(*args,**kwargs):
            nonlocal calls
            calls+=1
            if calls==2:raise np.linalg.LinAlgError('second chunk failed')
            return original(*args,**kwargs)
        with patch('numpy.linalg.qr',side_effect=fail_second):
            with self.assertRaises(np.linalg.LinAlgError):bank.advance(first,rows)
        self.assertEqual(calls,2);self.assertEqual(bytes(bank.context),context)
        for k,v in before.items():np.testing.assert_array_equal(bank.checkpoint_arrays()[k],v)
        bank.advance(first,rows)
        self.assertEqual(bank.field.count+bank.buffered,first+len(rows))

    def test_parallel_jobs_load_noise_seeds_and_cycles(self):
        for jobs in (1,2):
            command=[sys.executable,'-B','-m','experiments.foster_campaign_001.run',
                '--hours','.002','--sample-rate-hz','35','--history','distinct-bank',
                '--temperature','constant','--cells','A','--loads','embedded','charge-discharge',
                '--load-seeds','7','8','--seeds','1100','1101','--noise-v','.002',
                '--recording','compact','--summary-bins','11','--field-refresh-seconds','2',
                '--no-plots','--jobs',str(jobs),'--out',str(self.root/('jobs'+str(jobs)))]
            p=subprocess.run(command,capture_output=True,text=True,timeout=120)
            self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        a=self.root/'jobs1';b=self.root/'jobs2'
        sa=json.loads((a/'summary.json').read_text());sb=json.loads((b/'summary.json').read_text())
        self.assertEqual(sa['completed_cases'],6);self.assertEqual(sb['completed_cases'],6)
        self.assertEqual(sb['effective_jobs'],2)
        for ca,cb in zip(sa['cases'],sb['cases']):
            self.assertEqual(ca['scenario'],cb['scenario']);self.assertEqual(ca['status'],'completed')
            name=ca['directory']
            np.testing.assert_array_equal(np.load(a/name/'distinct_bank_message.npy'),np.load(b/name/'distinct_bank_message.npy'))

    def test_checkpoint_plan_and_plots(self):
        plan=storage_plan(.05102,50,37,.01,2,field_arms=2,bank_arms=1)
        with np.load(self.case/'checkpoints'/self.entries[1]['file']) as z:
            payload=sum(z[k].nbytes for k in z.files if k!='metadata')
        self.assertLessEqual(payload,plan['checkpoint_context_MB']*1e6/plan['checkpoint_count'])
        from experiments.foster_campaign_001.plot import render,render_summary,ARM_COLORS
        self.assertNotEqual(ARM_COLORS['field64'],ARM_COLORS['distinct_bank'])
        render(self.case,self.result,self.config,self.cell,self.root/'plots')
        r=render_summary(self.campaign,self.root/'overlay')
        for name in ('signals','states','parameters_reference','parameter_errors','errors'):
            self.assertTrue((self.root/'plots'/(name+'.png')).exists())
            self.assertTrue((self.root/'overlay'/(name+'.png')).exists())
        self.assertTrue(r['parameter_error_comparison'])
        styles={v['arm']:v['linestyle'] for v in r['arm_styles']}
        self.assertNotEqual(styles['field64'],styles['distinct_bank'])


if __name__=='__main__':unittest.main()
