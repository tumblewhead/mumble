"""Workload replay, bounded event storage and long-duration indexing controls."""
import copy
import ctypes as C
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from .backend import CBackend
from .compact import Bins, StimulusStream, EventSummary, storage_plan
from .plot import render_summary
from .replay import replay
from .workload import EmbeddedWorkload


class CompactWorkloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='compact-workload-')
        cls.root=Path(cls.temp.name)
        for recording in ['full','compact']:
            command=[sys.executable,'-B','-m','experiments.foster_campaign_001.run',
                '--recording',recording,'--hours','0.06002','--sample-rate-hz','50',
                '--loads','embedded','--cells','A','--load-seeds','7','8','--seeds','1000','1001',
                '--cv-voltage','3.7','--taper-end-c','0.4','--taper-hold-s','0.1','--cycle-rest-s','0',
                '--checkpoint-hours','0.01','--summary-bins','31','--jobs','2','--no-plots',
                '--out',str(cls.root/recording)]
            result=subprocess.run(command,capture_output=True,text=True,timeout=90)
            if result.returncode:raise AssertionError(result.stdout+result.stderr)
        cls.campaign=cls.root/'compact'
        cls.plan=json.loads((cls.campaign/'campaign_plan.json').read_text())
        cls.config=json.loads((cls.campaign/'calibration.json').read_text())
        cls.reports=json.loads((cls.campaign/'summary.json').read_text())['cases']

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def test_crossed_load_noise_streams_messages_and_scores_exact(self):
        for report in self.reports:
            case=self.campaign/report['directory'];full=self.root/'full'/case.name
            result=json.loads((full/'result.json').read_text())
            inputs=json.loads((case/'inputs.json').read_text())
            for name,key in [('observations','observation_sha256'),('truth','truth_sha256')]:
                self.assertEqual(hashlib.sha256(np.load(full/(name+'.npy')).astype('<f8').tobytes()).hexdigest(),inputs[key])
            for kind in ['float64','float32']:
                self.assertEqual(report['arms'][kind],result['arms'][kind])
                np.testing.assert_array_equal(np.load(case/(kind+'_message.npy')),np.load(full/(kind+'_message.npy')))
            self.assertEqual(report['workload'],result['workload'])
            self.assertEqual(report['charger'],result['charger'])
            self.assertGreater(report['charger']['phase_records']['discharge'],0)
            self.assertFalse(list(case.glob('*.csv')))
            self.assertLess((case/'events_summary.json').stat().st_size,10000)
        hashes=[json.loads((self.campaign/r['directory']/'events_summary.json').read_text())['workload']['sha256'] for r in self.reports]
        self.assertEqual(hashes[0],hashes[2]);self.assertEqual(hashes[1],hashes[3]);self.assertNotEqual(hashes[0],hashes[1])

    def test_workload_midrun_checkpoint_replay_exact(self):
        for report in self.reports:
            case=self.campaign/report['directory'];out=self.root/('replay_'+case.name)
            result=replay(case,out,190.17/3600,4.13,plots=False)
            self.assertGreater(result['checkpoint']['sequence'],0)
            self.assertEqual(result['scenario']['load_seed'],report['scenario']['load_seed'])
            first=result['record_offset'];end=first+result['records']
            for name in ['observations','truth']:
                np.testing.assert_array_equal(np.load(out/(name+'.npy')),np.load(self.root/'full'/case.name/(name+'.npy'))[first:end])
            for kind in report['arms']:
                rows=np.load(self.root/'full'/case.name/(kind+'_trace.npy'))
                np.testing.assert_array_equal(np.load(out/(kind+'_trace.npy'))[:result['arms'][kind]['outputs']],rows[(rows[:,0]>first)&(rows[:,0]<=end)])

    def test_snapshot_restores_independent_rngs_across_rates(self):
        for rate in [35,50,100]:
            a=EmbeddedWorkload(77,.03,rate)
            for i in range(411):a.current(i);a.take_events()
            state=json.loads(json.dumps(a.snapshot()));b=EmbeddedWorkload(77,.03,rate);b.restore(state)
            for i in range(411,2900):
                self.assertEqual(a.current(i),b.current(i));self.assertEqual(a.take_events(),b.take_events())
            self.assertEqual(a.snapshot(),b.snapshot())
            with self.assertRaisesRegex(ValueError,'configuration mismatch'):
                EmbeddedWorkload(78,.03,rate).restore(state)

    def test_compact_overlays_label_every_seed_arm_and_preserve_extrema(self):
        captured={}
        with patch('experiments.foster_campaign_001.plot.save_plot',side_effect=lambda f,a,d,n,h,t:captured.update({n:a})):
            receipt=render_summary(self.campaign)
        self.assertEqual(len(captured),6);self.assertEqual(len(receipt['included']),4)
        labels=[line.get_label() for line in captured['errors'][0].lines]
        for style in receipt['arm_styles']:
            self.assertIn(style['label']+' (bin mean/range)',labels)
            self.assertIn('load seed',style['label'])
        self.assertEqual(len({tuple(s['color']) for s in receipt['arm_styles']}),8)
        with np.load(self.campaign/'case_0000/plot_summary.npz') as stored:
            line=captured['errors'][0].lines[0]
            np.testing.assert_array_equal(line.get_ydata(),np.repeat(stored['float64_mean'][:,-4],2))

    def test_6000_hour_summary_and_event_storage_do_not_scale_with_samples(self):
        # Sparse synthetic arrivals near the end test integer bin arithmetic;
        # this does not pretend to simulate the intervening battery lifetime.
        for rate in [35,50,100,500]:
            n=6000*3600*rate;a=Bins(n,4000,3)
            counts=np.array([1,n//2,n-1,n],dtype=np.int64)
            a.add(counts,np.array([[0,1,2],[3,4,5],[6,7,8],[9,10,11]]))
            self.assertEqual(int(a.count.sum()),4);self.assertEqual(a.last.max(),n)
            self.assertEqual(a.count[-1],2);self.assertEqual(a.high[-1,-1],11)
            self.assertEqual(a.low.shape,(4000,3))
        plan=storage_plan(6000,50,4000,1.,2)
        self.assertEqual(plan['records'],1_080_000_000)
        self.assertLess(plan['checkpoint_count'],6002)
        self.assertLess(plan['numeric_payload_planning_MB'],300)
        event=EventSummary();row=dict(phase='discharge',reason='scheduled capability/load change',record_count=0)
        for i in range(20000):row['record_count']=i;event.add([row])
        self.assertEqual(event.count,20000);self.assertEqual(len(event.counts),1)
        self.assertLess(len(json.dumps(event.result())),1000)

    def test_c_counter_continuation_above_32_bit_range(self):
        # Probe the actual C ABI offsets via a tiny independently compiled helper.
        # Only test indices/ticks are shifted; this is NOT a long-duration solver qualification.
        helper=self.root/'counter_probe.c';binary=self.root/'counter_probe.so'
        header=Path('experiments/foster_c_history_001/baseline.h').resolve()
        helper.write_text('#include "'+str(header)+'"\nvoid set_counter(FBContext *s, uint64_t n, uint64_t ticks) {\n'
                          's->next_index=n; s->retired_index=n; s->ticks=ticks; s->retired_ticks=ticks; s->generation=n/16;\n}\n')
        subprocess.run(['cc','-shared','-fPIC','-DFB_PROFILE',str(helper),'-o',str(binary)],check=True,capture_output=True)
        probe=C.CDLL(str(binary));probe.set_counter.argtypes=[C.c_void_p,C.c_uint64,C.c_uint64]
        report=self.reports[0];bank=CBackend(self.campaign,self.config,report['source_id'],report['model_id'],'float64',50)
        count=6000*3600*500 # > 2**32, exercises counters beyond 6000h at nominal rates
        ticks=count*(bank.hz//50)
        probe.set_counter(bank.context,count,ticks)
        obs=np.load(self.root/'full/case_0000/observations.npy')[:16]
        readout,_=bank.advance(count,obs)
        self.assertEqual(readout['records'],count+16)
        self.assertEqual(bank.counts()['tokens'],count//16+1)
        self.assertAlmostEqual(readout['time_s'],(count+16)/50)


if __name__=='__main__':unittest.main()
