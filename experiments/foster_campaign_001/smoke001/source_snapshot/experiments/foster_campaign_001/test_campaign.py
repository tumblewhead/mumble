"""Targeted controls for the harness and exported physical quantities."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import numpy as np
from experiments.foster_feedback_001.plant import generate as legacy_generate
from experiments.foster_feedback_001.estimator import Model, Rolling, prior
from specifications.evidence_feedback_001.protocol import digest
from .stimulus import cells, current, temperatures, generate
from .telemetry import thermal, physical, trace_row, TRACE_COLUMNS
from .run import run_case, parser

BASE = Path(__file__).resolve().parents[1]/'foster_feedback_001'
CONFIG = json.loads((BASE/'calibration.json').read_text())


class CampaignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.binary = cls.root/'model.so'
        subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-pedantic',
                        '-shared','-fPIC',str(BASE/'model.c'),'-lm','-o',str(cls.binary)],check=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def make_input(self, name, n=1201, **kwargs):
        out = self.root/name; out.mkdir()
        return generate(out, CONFIG, n, cells()['B'], kwargs.pop('load','legacy'),
                        .03, kwargs.pop('noise',.004), 42, 'cycle', **kwargs)

    def test_legacy_parity_and_partial_boundary(self):
        obs, truth, status = self.make_input('parity')
        old, old_truth = legacy_generate(CONFIG,1201,'B',.004,42,'cycle')
        np.testing.assert_allclose(obs,old,rtol=0,atol=1e-15)
        np.testing.assert_allclose(truth[:,[5,6,0,16]],old_truth,rtol=0,atol=1e-13)
        arms = [Rolling(self.binary,CONFIG,digest('test'+str(i)),digest('model'),'float32') for i in range(2)]
        for arm, data in zip(arms,[obs,old]):
            for i,row in enumerate(data):
                arm.offer(i,*map(float,row))
            arm.retire()
            self.assertEqual(arm.history.read().boundary.sequence,1201)
            self.assertEqual(len(arm.rows),0)
        np.testing.assert_allclose(arms[0].readout(obs[-1,2])['chart_mean'],
                                   arms[1].readout(old[-1,2])['chart_mean'],atol=1e-8,rtol=1e-8)
        self.assertEqual(status['valid_records'],1201)

    def test_chunk_and_noise_seed_invariance(self):
        a,t,_ = self.make_input('chunk_a',chunk=13)
        b,u,_ = self.make_input('chunk_b',chunk=8192)
        np.testing.assert_array_equal(a,b)
        np.testing.assert_array_equal(t,u)

    def test_zero_noise_retains_adc_uncertainty(self):
        a,t,_ = self.make_input('zero',noise=0,n=48)
        self.assertTrue(np.all(a[:,4]>0))
        self.assertLessEqual(np.max(abs(a[:,3]-t[:,16])),.5/1024)

    def test_balanced_loads_and_repeat(self):
        for load,period in [('pulses',5600),('multiscale',10500),('cycle',504000),('rest',5600)]:
            data = current(np.arange(period),load,.037)
            self.assertAlmostEqual(float(data.sum()),0.,places=10)
            np.testing.assert_array_equal(data,current(np.arange(period)+period,load,.037))
        ix = np.array([188999,189000,377999,378000,504000+189000])
        cyc = current(ix,'cycle',.03)
        self.assertEqual(cyc[1],0);self.assertEqual(cyc[2],0);self.assertEqual(cyc[-1],0)
        self.assertNotEqual(current(ix[-1:],'legacy',.03)[0],0)

    def test_temperature_and_input_validation(self):
        t = temperatures(np.arange(126000),'cycle',25,8,3600)
        self.assertEqual(float(t.min()),17);self.assertEqual(float(t.max()),33)
        np.testing.assert_array_equal(temperatures(np.arange(10),'constant',22,8,3600),np.full(10,22.))
        good = cells(Path(__file__).with_name('cells.example.json'))
        self.assertEqual(good['C']['parameters']['Q_Ah'],.0523)
        for field,value in [('Q_Ah',0),('tau2_s',.001),('R1_ohm',float('nan'))]:
            bad = copy.deepcopy(good['C']);bad['parameters'][field]=value
            path = self.root/('bad_'+field+'.json');path.write_text(json.dumps({'bad':bad}))
            with self.assertRaises(ValueError):cells(path)

    def test_physical_decode_and_endpoint_voltage(self):
        x,_ = prior(CONFIG)
        ref,p = physical(x,CONFIG,19.)
        np.testing.assert_allclose(ref[[3,5,7]],CONFIG['prior_mean_physical']['tau'])
        np.testing.assert_allclose(p/ref,thermal(CONFIG,19.))
        model=Model(self.binary,CONFIG)
        row=np.array([1/35,.02,19.,3.7,.004])
        v,_,end,_=model.evaluate(x,row[None,:])
        record=dict(records=1,chart_mean=end.tolist(),Q_log_sd=.1,SOC_sd=.01,log_evidence=0.)
        out=trace_row(record,row,CONFIG)
        self.assertEqual(len(out),len(TRACE_COLUMNS))
        self.assertAlmostEqual(out[5],v[0],places=13)
        np.testing.assert_allclose(out[33:36],p[[3,5,7]]/p[[2,4,6]])

    def test_full_telemetry_alignment_and_single_arm(self):
        args=parser().parse_args(['--hours','0.001','--encoding','float32','--no-plots','--sample-csv'])
        scenario=dict(cell='B',load='multiscale',noise_v=.002,seed=17)
        out=self.root/'case'
        report=run_case(out,self.root,CONFIG,digest('telemetry_model'),scenario,cells()['B'],args)
        self.assertEqual(report['status'],'completed')
        self.assertIsNone(report['encoding_difference'])
        count=report['arms']['float32']['outputs']
        rows=np.load(out/'float32_trace.npy')[:count]
        obs=np.load(out/'observations.npy');truth=np.load(out/'truth.npy')
        ix=rows[:,0].astype(int)-1
        self.assertEqual(int(rows[-1,0]),126)
        np.testing.assert_array_equal(rows[:,2:5],obs[ix,1:4])
        np.testing.assert_allclose(rows[:,11],rows[:,22]*thermal(CONFIG,rows[:,3])[:,0])
        self.assertEqual(len((out/'samples.csv').read_text().splitlines()),127)
        csv=np.loadtxt(out/'float32_trace.csv',delimiter=',',skiprows=1)
        np.testing.assert_allclose(csv[:,:len(TRACE_COLUMNS)],rows)
        np.testing.assert_allclose(csv[:,len(TRACE_COLUMNS):],truth[ix])

    def test_plant_domain_failure_is_explicit(self):
        bad=copy.deepcopy(cells()['B']);bad['parameters']['Q_Ah']=1e-7
        args=parser().parse_args(['--hours','0.001','--no-plots'])
        report=run_case(self.root/'bad_case',self.root,CONFIG,digest('bad_model'),
                        dict(cell='bad',load='pulses',noise_v=0.,seed=1),bad,args)
        self.assertEqual(report['status'],'plant_failed')
        self.assertEqual(report['valid_records'],0)
        self.assertFalse((self.root/'bad_case'/'float32_trace.npy').exists())


if __name__=='__main__':
    unittest.main()
