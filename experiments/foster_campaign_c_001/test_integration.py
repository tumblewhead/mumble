import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from experiments.foster_campaign_001.backend import CBackend,PythonBackend,prepare_c
from experiments.foster_campaign_001.rate import clock_hz
from experiments.foster_campaign_001.run import parser,run_case
from experiments.foster_campaign_001.stimulus import current,temperatures,cells,generate
from experiments.foster_campaign_001.charger import ChargeDischarge,DEFAULTS
from experiments.foster_campaign_001.telemetry import trace_row
from experiments.foster_c_baseline_001.reference import Baseline,library
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
CONFIG=json.loads((ROOT/'experiments/foster_feedback_001/calibration.json').read_text())

class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.root=Path(cls.tmp.name)
        # Rebuild the frozen reference from source; no committed shared library.
        from experiments.foster_c_baseline_001.build import FLAGS
        core=ROOT/'experiments/foster_c_history_001'
        base=ROOT/'experiments/foster_c_baseline_001'
        model=ROOT/'experiments/foster_c_model_001'
        cls.frozen_binary=cls.root/'frozen_baseline.so'
        subprocess.run(['cc',*FLAGS,'-fPIC','-shared','-DFB_PROFILE',
                        '-D_POSIX_C_SOURCE=200809L','-DFB_OPT_STAGE=3',
                        '-DFB_MODEL_STAGE=2','-DFB_HISTORY_STAGE=2',
                        '-include',str(core/'baseline.h'),
                        str(core/'rolling.c'),str(base/'numeric.c'),
                        str(core/'history.c'),str(model/'model.c'),
                        '-lm','-o',str(cls.frozen_binary)],check=True)
        for rate in [10,35,70,100]:
            folder=cls.root/str(rate);folder.mkdir()
            subprocess.run(['cc','-std=c11','-O2','-fno-fast-math','-ffp-contract=off','-shared','-fPIC',str(ROOT/'experiments/foster_feedback_001/model.c'),'-lm','-o',str(folder/'model.so')],check=True)
            prepare_c(folder,rate)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_35hz_stimuli_match_archive(self):
        path=HERE/'baseline/experiments/foster_campaign_001/stimulus.py'
        spec=importlib.util.spec_from_file_location('experiments.foster_campaign_001.archived_stimulus',path)
        archived=importlib.util.module_from_spec(spec);spec.loader.exec_module(archived)
        ix=np.arange(504100)
        for load in ['legacy','cycle','pulses','multiscale','rest']:
            np.testing.assert_array_equal(current(ix,load,.037),archived.current(ix,load,.037))
        np.testing.assert_array_equal(temperatures(ix,'cycle',25,8,3600),archived.temperatures(ix,'cycle',25,8,3600))
    def test_schedule_seconds_at_other_rates(self):
        seconds=np.arange(14401)
        for rate in [10,35,70,100]:
            for load in ['cycle','pulses','multiscale','legacy']:
                np.testing.assert_array_equal(current(seconds*rate,load,.03,rate),current(seconds*35,load,.03))
            np.testing.assert_array_equal(temperatures(seconds[1:]*rate-1,'cycle',25,8,3600,rate),temperatures(seconds[1:]*35-1,'cycle',25,8,3600))
    def test_backend_parity_and_timestamps_all_rates(self):
        for rate in [10,35,70,100]:
            for enc in ['float64','float32']:
                folder=self.root/str(rate);out=folder/('inputs_'+enc);out.mkdir()
                obs,_,_=generate(out,CONFIG,257,cells()['B'],'multiscale',.03,.004,42,'cycle',sample_rate_hz=rate)
                py=PythonBackend(folder,CONFIG,'a'*64,'b'*64,enc,rate);c=CBackend(folder,CONFIG,'a'*64,'b'*64,enc,rate)
                for i in range(0,len(obs),16):
                    a,_=py.advance(i,obs[i:i+16]);b,_=c.advance(i,obs[i:i+16])
                    self.assertLess(abs(100*(b['Q']/a['Q']-1)),.5);self.assertLess(abs(100*(a['SOC']-b['SOC'])),.5)
                    self.assertEqual(a['time_s'],b['time_s']);self.assertAlmostEqual(b['time_s'],min(i+16,len(obs))/rate)
                    self.assertEqual(trace_row(b,obs[min(i+15,len(obs)-1)],CONFIG)[1],b['time_s'])
                self.assertEqual(c.counts(),py.counts());self.assertEqual(c.counts()['pending_records'],0)
    def test_c_adapter_matches_frozen_core_at_35(self):
        obs=np.load(ROOT/'tests/fixtures/foster_cccv_prefix_1027.npy',mmap_mode='r')[:1027]
        for enc in ['float64','float32']:
            c=CBackend(self.root/'35',CONFIG,'a'*64,'b'*64,enc,35)
            frozen=Baseline(library(self.frozen_binary),8 if enc=='float64' else 4)
            for i in range(0,len(obs),16):c.advance(i,obs[i:i+16])
            self.assertEqual(frozen.replay(obs)[0],0)
            self.assertEqual(c.full_message().tobytes(),frozen.snapshot().tobytes())
    def test_error_watermarks_and_input_order(self):
        c=CBackend(self.root/'100',CONFIG,'a'*64,'b'*64,'float64',100);initial=c.full_message()
        rows=np.tile([.01,.01,25.,3.7,.004],(16,1));rows[7,4]=0
        with self.assertRaises(ValueError):c.advance(0,rows)
        self.assertEqual(c.failure_index,7);self.assertEqual(c.counts()['received_records'],7);self.assertEqual(c.counts()['pending_records'],7)
        np.testing.assert_array_equal(c.full_message(),initial)
        with self.assertRaises(ValueError):c.advance(0,rows[:1])
    def test_charger_uses_seconds_and_elapsed_charge(self):
        for rate in [10,35,70,100]:
            c=ChargeDischarge({**DEFAULTS,'charge_c':[2.,1.],'charge_step_s':1.},rate)
            for i in range(rate):self.assertEqual(c.current(i),-.12);c.observe(i,3.8)
            self.assertEqual(c.current(rate),-.06)
            self.assertAlmostEqual(c.charge_Ah,.12/3600,places=14)
            events=c.take_events();self.assertEqual(events[-1]['time_s'],1.)
            c=ChargeDischarge({**DEFAULTS,'taper_hold_s':1.,'cycle_rest_s':1.},rate)
            c.current(0);c.observe(0,4.07);c.cv_magnitude=.002
            for i in range(1,rate+1):c.current(i);c.observe(i,4.06)
            self.assertEqual(c.phase,'rest_after_charge')
            for i in range(rate+1,2*rate+1):c.current(i);c.observe(i,4.)
            self.assertEqual(c.phase,'discharge')
    def test_rate_validation_and_defaults(self):
        args=parser().parse_args([]);self.assertEqual(args.backend,'c');self.assertEqual(args.sample_rate_hz,35)
        self.assertEqual(clock_hz(35),1050);self.assertEqual(clock_hz(100),2100)
        for rate in [0,-1,1.5]:
            with self.assertRaises(ValueError):clock_hz(rate)
    def test_plot_sample_time_at_100hz(self):
        import matplotlib;matplotlib.use('Agg')
        from experiments.foster_campaign_001.plot import render
        folder=self.root/'100';out=folder/'plot_case'
        args=parser().parse_args(['--hours','0.001','--sample-rate-hz','100','--no-plots','--encoding','float64'])
        result=run_case(out,folder,CONFIG,'b'*64,dict(cell='B',load='rest',noise_v=.004,seed=9),cells()['B'],args)
        seen=[]
        def save(fig,axes,destination,name,heading,title):
            if name=='signals':seen.extend(line.get_xdata()[-1] for ax in axes for line in ax.lines if len(line.get_xdata()))
            import matplotlib.pyplot as plt;plt.close(fig)
        with patch('experiments.foster_campaign_001.plot.save_plot',side_effect=save):render(out,result,CONFIG,cells()['B'])
        self.assertTrue(seen);self.assertAlmostEqual(max(seen),.001)

if __name__=='__main__':unittest.main()
