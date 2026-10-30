import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import numpy as np
from experiments.foster_feedback_001.estimator import Model
from experiments.foster_campaign_001.backend import prepare_c,CBackend,PythonBackend
from experiments.foster_campaign_001.coordinates import prior,physical_states
from experiments.foster_campaign_001.telemetry import trace_row
ROOT=Path(__file__).resolve().parents[2]

class BoundedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.folder=Path(cls.tmp.name)
        cls.cfg=json.loads((ROOT/'experiments/foster_feedback_001/calibration.json').read_text())
        cls.cfg['hysteresis_chart']='bounded'
        cls.binary,_=prepare_c(cls.folder,50,cls.cfg);cls.model=Model(cls.binary,cls.cfg)
        legacy=cls.folder/'legacy.so'
        subprocess.run(['cc','-std=c11','-O2','-shared','-fPIC',str(ROOT/'experiments/foster_feedback_001/model.c'),'-lm','-o',str(legacy)],check=True)
        cls.legacy=Model(legacy,cls.cfg)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_same_physics_and_chain_rule(self):
        for eta in [-4.,-1.,0.,2.,4.]:
            x,_=prior(self.cfg);x[4]=eta
            obs=np.array([[.02,i,t,3.7,.02] for i,t in [(-.12,17.),(0,25.),(.04,33.),(-.08,20.)]])
            physical=x.copy();physical[4]=np.tanh(eta)
            a=self.model.evaluate(x,obs);b=self.legacy.evaluate(physical,obs)
            np.testing.assert_allclose(a[0],b[0],atol=2e-14,rtol=2e-14)
            np.testing.assert_allclose(physical_states(a[2],self.cfg),b[2][:5],atol=3e-14,rtol=1e-13)
            D=np.ones(16);D[4]=1-np.tanh(eta)**2
            np.testing.assert_allclose(a[1],b[1]*D,atol=1e-13,rtol=2e-11)
            transformed=a[3].copy();transformed[4]*=1-np.tanh(a[2][4])**2
            np.testing.assert_allclose(transformed,b[3]*D,atol=3e-13,rtol=2e-10)
    def test_full_jacobians_by_finite_difference(self):
        x,_=prior(self.cfg);x[4]=1.3
        obs=np.array([[.02,-.12,22.,3.7,.02],[.02,.04,29.,3.7,.02]])
        _,J,_,F=self.model.evaluate(x,obs)
        for j in range(16):
            d=np.zeros(16);d[j]=1e-5
            a=self.model.evaluate(x+d,obs);b=self.model.evaluate(x-d,obs)
            np.testing.assert_allclose(J[:,j],(a[0]-b[0])/2e-5,atol=2e-9,rtol=2e-5)
            np.testing.assert_allclose(F[:,j],(a[2]-b[2])/2e-5,atol=2e-9,rtol=2e-5)
    def test_saturated_and_zero_duration_states(self):
        for eta in [-1000.,-50.,0.,50.,1000.]:
            for current in [-.12,0.,.04]:
                for dt in [0.,.02]:
                    x,_=prior(self.cfg);x[4]=eta
                    v,J,end,F=self.model.evaluate(x,np.array([[dt,current,25.,3.7,.02]]))
                    self.assertTrue(all(np.isfinite(z).all() for z in [v,J,end,F]))
                    self.assertLessEqual(abs(np.tanh(end[4])),1.)
                    if dt==0 or current==0:self.assertEqual(end[4],eta)
    def test_nonzero_prior_and_physical_reporting(self):
        cfg=copy.deepcopy(self.cfg);cfg['prior_mean_physical']['h']=.3
        x,L=prior(cfg);self.assertAlmostEqual(np.tanh(x[4]),.3)
        self.assertAlmostEqual(L[4,4]*(1-.3**2),cfg['prior_chart_sd'][4])
        read=dict(chart_mean=x.tolist(),records=1,time_s=.02,Q_log_sd=.3,SOC_sd=.12,log_evidence=0.)
        row=trace_row(read,np.array([.02,.04,25.,3.7,.02]),cfg)
        self.assertAlmostEqual(row[10],.3)
    def test_c_python_joint_message_parity(self):
        obs=np.load(ROOT/'tests/fixtures/foster_cccv_prefix_1027.npy')[:513].copy();obs[:,0]=.02
        for enc in ['float32','float64']:
            a=CBackend(self.folder,self.cfg,'a'*64,'b'*64,enc,50);b=PythonBackend(self.folder,self.cfg,'a'*64,'b'*64,enc,50)
            for i in range(0,len(obs),16):
                ra,_=a.advance(i,obs[i:i+16]);rb,_=b.advance(i,obs[i:i+16])
                self.assertLess(abs(100*(ra['Q']/rb['Q']-1)),.01)
                self.assertLess(abs(100*(ra['SOC']-rb['SOC'])),.001)
            np.testing.assert_allclose(a.full_message(),b.full_message(),atol=1e-4,rtol=2e-3)
    def test_cached_build_rejects_wrong_chart(self):
        cfg=copy.deepcopy(self.cfg);cfg['hysteresis_chart']='legacy'
        with self.assertRaises(ValueError):prepare_c(self.folder,50,cfg)

    def test_saved_failure_fixed_without_skipping_observations(self):
        from experiments.foster_c_baseline_001.reference import Baseline,library
        observations=np.load(ROOT/'tests/fixtures/foster_seed1001_50hz_prefix1024.npy')
        folder=self.folder/'legacy_replay';folder.mkdir()
        cfg=copy.deepcopy(self.cfg);cfg['hysteresis_chart']='legacy'
        old,_=prepare_c(folder,50,cfg)
        for width in [4,8]:
            legacy=Baseline(library(old),width)
            status,rows=legacy.replay(observations)
            self.assertEqual(status,-4);self.assertEqual(rows[-1,33],528)
            repaired=Baseline(library(self.binary),width,initial=prior(self.cfg))
            status,rows=repaired.replay(observations)
            self.assertEqual(status,0);self.assertEqual(rows[-1,33],1024)
            self.assertTrue(np.isfinite(repaired.snapshot()).all())
            self.assertTrue(np.all(abs(np.tanh(rows[:,4]))<=1))

    def test_python_parallel_build_once_and_telemetry_chart(self):
        import sys
        destination=self.folder/'parallel_python'
        result=subprocess.run([sys.executable,'-B','-m','experiments.foster_campaign_001.run',
            '--backend','python','--hysteresis-chart','bounded','--hours','0.001',
            '--sample-rate-hz','50','--jobs','2','--cells','A','--loads','rest',
            '--noise-v','0.02','--seeds','1001','1002','--no-plots','--out',str(destination)],
            cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        report=json.loads((destination/'summary.json').read_text())
        self.assertEqual(report['status'],'completed')
        for case in report['cases']:
            self.assertEqual(case['hysteresis_chart'],'bounded')
            telemetry=json.loads((destination/case['directory']/'telemetry.json').read_text())
            self.assertEqual(telemetry['hysteresis_chart'],'bounded')
