import ctypes as C
import unittest
import numpy as np
from experiments.foster_c_baseline_001.test_baseline import BaselineTests as ParentTests
from experiments.foster_c_baseline_001.reference import Baseline,library,ptr,DP
from experiments.foster_feedback_001.estimator import Model,prior
from .build import HERE

class ModelTests(ParentTests):
    @classmethod
    def setUpClass(cls):
        super().setUpClass();cls.lib=library(HERE/'build_host_2/baseline.so')
        cls.old=Model(HERE/'build_host_0/baseline.so',cls.cfg)
        cls.sparse=Model(HERE/'build_host_1/baseline.so',cls.cfg)
        cls.cached=Model(HERE/'build_host_2/baseline.so',cls.cfg)
        cls.lib.foster_thermal.argtypes=[DP,C.c_int,DP,DP]
        cls.lib.foster_predict_cached.argtypes=[DP,DP,C.c_int,DP,DP,DP,DP,DP,DP]
    def cached_eval(self,x,obs):
        obs=np.ascontiguousarray(obs);cache=np.empty((len(obs),11));cal=self.cached.cal
        self.assertEqual(self.lib.foster_thermal(ptr(obs),len(obs),ptr(cal),ptr(cache)),0)
        v=np.empty(len(obs));J=np.empty((len(obs),16));end=np.empty(16);F=np.empty((16,16))
        self.assertEqual(self.lib.foster_predict_cached(ptr(x),ptr(obs),len(obs),ptr(cal),ptr(cache),ptr(v),ptr(J),ptr(end),ptr(F)),0)
        return v,J,end,F
    def test_randomized_sparse_derivatives_and_cache(self):
        rng=np.random.default_rng(9001);m,L=prior(self.cfg)
        for case in range(60):
            x=m+rng.normal(size=16)*np.array([.05,.003,.003,.003,.2]+[.15]*11)
            n=[0,1,7,16][case%4];obs=np.zeros((n,5))
            obs[:,0]=rng.choice([0,1/35,31/1050,.2,1.],n)
            obs[:,1]=rng.choice([-.12,-.03,0,.012,.042],n)
            obs[:,2]=rng.uniform(15,35,n);obs[:,4]=.004
            old=self.old.evaluate(x,obs);new=self.sparse.evaluate(x,obs);cached=self.cached_eval(x,obs)
            for i,(a,b,c) in enumerate(zip(old,new,cached)):
                np.testing.assert_allclose(b,a,rtol=1e-12,atol=1e-12 if i in [0,2] else 1e-10)
                np.testing.assert_array_equal(c,b)
    def test_finite_difference_all_coordinates(self):
        x,_=prior(self.cfg);obs=self.obs[:16].copy()
        obs[:,0]=np.resize([0,1/35,.2,1.],16);obs[:,1]=np.resize([-.12,0,.04,.012],16);obs[:,2]=np.linspace(15,35,16)
        v,J,end,F=self.sparse.evaluate(x,obs)
        for j in range(16):
            delta=np.zeros(16);delta[j]=1e-6
            plus=self.sparse.evaluate(x+delta,obs);minus=self.sparse.evaluate(x-delta,obs)
            np.testing.assert_allclose(J[:,j],(plus[0]-minus[0])/2e-6,rtol=1e-5,atol=1e-6)
            np.testing.assert_allclose(F[:,j],(plus[2]-minus[2])/2e-6,rtol=1e-5,atol=1e-6)
    def test_cache_lifecycle_contexts_and_partial_windows(self):
        rows=self.obs[:259].copy();rows[:,0]=np.resize([0,1/35,31/1050,2/35],len(rows))
        rows[:,2]=np.resize([15.,35.,17.1,24.9,25.,25.001],len(rows))
        rows[:,1]=np.resize([-.12,0,.042],len(rows))
        for enc in [4,8]:
            sparse=Baseline(library(HERE/'build_host_1/baseline.so'),enc);cached=Baseline(self.lib,enc)
            for start,end in [(0,7),(7,23),(23,259)]:
                a,ta=sparse.replay(rows[start:end]);b,tb=cached.replay(rows[start:end]);self.assertEqual((a,b),(0,0))
                np.testing.assert_array_equal(ta,tb);np.testing.assert_array_equal(sparse.snapshot(),cached.snapshot())
    def test_changed_arrhenius_coefficients(self):
        # Equal branch coefficients in public calibration are not assumed by cache.
        x,_=prior(self.cfg);rows=self.obs[:16].copy();rows[:,2]=np.linspace(15,35,16)
        for k in range(11):
            cfg={**self.cfg,'arrhenius_A_K':list(self.cfg['arrhenius_A_K'])};cfg['arrhenius_A_K'][k]+=13
            old=Model(HERE/'build_host_0/baseline.so',cfg);new=Model(HERE/'build_host_2/baseline.so',cfg)
            for a,b in zip(old.evaluate(x,rows),new.evaluate(x,rows)):np.testing.assert_allclose(a,b,rtol=1e-12,atol=1e-10)
            cache=np.empty((16,11));self.assertEqual(self.lib.foster_thermal(ptr(rows),16,ptr(new.cal),ptr(cache)),0)
            expected=np.exp(np.array(cfg['arrhenius_A_K'])*(1/(rows[:,2,None]+273.15)-1/cfg['reference_temperature_K']))
            np.testing.assert_allclose(cache,expected,rtol=1e-15,atol=0)
    def test_domain_controls_match_acceptance(self):
        x,_=prior(self.cfg)
        for col,value in [(0,-.1),(0,1.1),(1,.3),(2,14.9),(2,35.1)]:
            obs=self.obs[:1].copy();obs[0,col]=value
            for model in [self.old,self.sparse]:
                with self.assertRaises(ValueError):model.evaluate(x,obs)
        for j,value in [(0,-.1),(0,1.1),(4,1.1),(5,float('inf'))]:
            y=x.copy();y[j]=value
            for model in [self.old,self.sparse]:
                with self.assertRaises(ValueError):model.evaluate(y,self.obs[:1])

def load_tests(loader,tests,pattern):return loader.loadTestsFromTestCase(ModelTests)
if __name__=='__main__':unittest.main()
