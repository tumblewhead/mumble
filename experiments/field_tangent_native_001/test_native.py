import ctypes as C
import unittest
import numpy as np
from experiments.field_feedback_preservation_001 import test_numerics as fixtures
from experiments.field_feedback_preservation_001.numerics import Tangent
from experiments.slow_likelihood_diagnostic_001.numerics import Compressed,features_jacobian
from .native import Native,build

class Tests(fixtures.Tests):
    @classmethod
    def setUpClass(cls):
        super().setUpClass();cls.binary=build(cls.path/'native')
    def native(self,f,L=None):return Native(self.binary,f,self.mean,self.L if L is None else L)
    def test_structured_projection_dense_and_finite_difference(self):
        f=self.field();a=self.native(f);rng=np.random.default_rng(2026)
        for _ in range(12):
            x=self.mean+self.L@rng.uniform(-.2,.2,16);row=rng.normal(size=82)
            r,g=a.projection(x,row)
            self.assertAlmostEqual(r,float(row@f.features(x)),places=11)
            np.testing.assert_allclose(g,row@features_jacobian(f,x),rtol=2e-13,atol=2e-12)
            fd=[]
            for k in range(16):
                d=np.zeros(16);d[k]=1e-6
                fd.append((row@f.features(x+d)-row@f.features(x-d))/2e-6)
            np.testing.assert_allclose(g,fd,rtol=2e-6,atol=2e-7)
    def test_native_python_parity_correlated_prior_and_restart(self):
        f=self.field();obs=self.obs(512);f.update(0,obs[:128])
        L=self.L@(np.eye(16)+np.tril(np.full((16,16),.015),-1));w=np.linspace(-.02,.02,16)
        t=Tangent(Compressed(f,self.mean,L),w,128);a=self.native(f,L);a.initialize(w)
        for first in range(128,512,16):
            rows=f.update(first,obs[first:first+16],return_rows=True);t.update(first,rows);a.update(first,rows)
            expected=t.query();actual=a.query()
            for key in ('w','x','end'):np.testing.assert_allclose(actual[key],expected[key],rtol=2e-9,atol=3e-11)
            E=expected['endpoint_root'];A=actual['endpoint_root']
            np.testing.assert_allclose(A@A.T,E@E.T,rtol=2e-8,atol=2e-13)
        b=self.native(f,L);b.restore(a.snapshot(),512)
        np.testing.assert_array_equal(a.query()['endpoint_root'],b.query()['endpoint_root'])
    def test_native_partition_and_failure_atomicity(self):
        f=self.field();a=self.native(f);b=self.native(f);a.initialize(np.zeros(16));b.initialize(np.zeros(16))
        rows=f.update(0,self.obs(256),return_rows=True);a.update(0,rows)
        for i in range(0,256,7):b.update(i,rows[i:i+7])
        np.testing.assert_array_equal(a.snapshot(),b.snapshot())
        before=a.snapshot()
        for first,data,source in [(0,rows,None),(257,rows,None),(256,rows,'other'),(256,rows*np.nan,None)]:
            with self.assertRaises(ValueError):a.update(first,data,source)
            np.testing.assert_array_equal(a.snapshot(),before)
        bad=before.copy();bad[-1]^=1
        with self.assertRaises(ValueError):a.restore(bad,256)
        np.testing.assert_array_equal(a.snapshot(),before)
        with self.assertRaises(ValueError):a.query(count=255)
    def test_native_rest_and_domain(self):
        f=self.field();a=self.native(f);a.initialize(np.zeros(16));obs=self.obs(1024);obs[:,1]=0
        rows=f.update(0,obs,return_rows=True);a.update(0,rows);r=a.query()
        self.assertAlmostEqual(r['x'][5],self.mean[5],places=10)
        self.assertAlmostEqual(np.linalg.norm(r['endpoint_root'][5]),np.linalg.norm(self.L[5]),places=10)
        state=f.state.copy();state[-1]=100
        with self.assertRaises(ValueError):a.query(state=state)
        self.assertEqual(C.sizeof(a.context),1376)

if __name__=='__main__':unittest.main()
