import ctypes as C
import unittest
import numpy as np
from experiments.foster_c_model_001.test_model import ModelTests as ParentTests
from experiments.foster_c_baseline_001.reference import Baseline,library,message,Message,DP,ptr
from experiments.foster_feedback_001.estimator import Model
from experiments.foster_feedback_001.history import pack_kernel,kernel
from .build import HERE

class HistoryTests(ParentTests):
    @classmethod
    def setUpClass(cls):
        super().setUpClass();old=cls.lib;cls.lib=library(HERE/'build_host_2/baseline.so')
        for name in ['foster_thermal','foster_predict_cached']:getattr(cls.lib,name).argtypes=getattr(old,name).argtypes
        cls.cached=Model(HERE/'build_host_2/baseline.so',cls.cfg)
        cls.lib.fb_history_work.argtypes=[C.POINTER(Message),C.POINTER(C.c_ubyte),C.c_size_t,C.POINTER(Message),C.c_void_p]
    def advance(self,m,L,token,z=.2,work=None):
        before=message(m,L,z);saved=bytes(before);out=Message();t=(C.c_ubyte*len(token)).from_buffer_copy(token)
        if work is None:status=self.lib.fb_history(C.byref(before),t,len(token),C.byref(out))
        else:status=self.lib.fb_history_work(C.byref(before),t,len(token),C.byref(out),work)
        self.assertEqual(status,0);self.assertEqual(bytes(before),saved)
        return np.array(out.mean),np.array(out.root).reshape(16,16),out.logZ
    def test_mixed_identity_dense_and_singular_transport(self):
        rng=np.random.default_rng(812)
        for enc in [4,8]:
            for n in [1,5,17]:
                m=rng.normal(size=16);L=rng.normal(size=(16,16))*.02;L[2]=L[1]
                anchor=m+rng.normal(size=16)*.01;end=rng.normal(size=16)
                A=rng.normal(size=(n,16));r=rng.normal(size=n)
                F=rng.normal(size=(16,16))*.2;F[5:]=np.eye(16)[5:];F[0]=0
                token=pack_kernel(anchor,end,F,A,r,.7,'float'+str(enc*8))
                a,e,f,A,r,c=kernel(token);y=r+A@(m-a);P=L@L.T;S=np.eye(17)+A@P@A.T;K=np.linalg.solve(S,A@P).T
                mu=e+f@(m-K@y-a);cov=f@(P-K@A@P)@f.T;z=.2-c-.5*(y@np.linalg.solve(S,y)+np.linalg.slogdet(S)[1])
                got,root,gz=self.advance(m,L,token)
                np.testing.assert_allclose(got,mu,atol=1e-9,rtol=0);np.testing.assert_allclose(root@root.T,cov,atol=1e-10,rtol=0)
                self.assertAlmostEqual(gz,z,delta=1e-7)
    def test_orthogonal_residual_is_not_discarded(self):
        m=np.linspace(-1,1,16);L=np.eye(16);A=np.zeros((17,16));r=np.zeros(17);r[-1]=3.25
        for enc in [4,8]:
            token=pack_kernel(m,m,np.eye(16),A,r,.7,'float'+str(enc*8));got,root,z=self.advance(m,L,token)
            np.testing.assert_array_equal(got,m);np.testing.assert_array_equal(root,L)
            self.assertEqual(z,.2-.7-.5*3.25**2)
    def test_workspace_poison_guards_and_repeat(self):
        size=593*8;buf=(C.c_ubyte*(size+64))(*([165]*(size+64)));work=C.c_void_p(C.addressof(buf)+32)
        rng=np.random.default_rng(9)
        for _ in range(3):
            m=rng.normal(size=16);L=np.eye(16)*.1;A=rng.normal(size=(17,16));r=rng.normal(size=17)
            token=pack_kernel(m,m,np.eye(16),A,r,.1,'float64')
            a=self.advance(m,L,token);b=self.advance(m,L,token,work=work)
            for x,y in zip(a,b):np.testing.assert_array_equal(x,y)
            self.assertEqual(list(buf[:32])+list(buf[-32:]),[165]*64)
    def test_post_history_domain_failure_retry_atomic(self):
        for stage in [1,2]:
            c=Baseline(library(HERE/f'build_host_{stage}/baseline.so'),settings={'gradient_tol':1e100})
            saved=c.snapshot();row=self.obs[0].copy();row[3]=100.
            for i in range(15):self.assertEqual(c.offer(i,row),0)
            self.assertEqual(c.offer(15,row),-4);np.testing.assert_array_equal(c.snapshot(),saved)
            self.assertGreater(c.profile()['history_s'],0);self.assertEqual(c.profile()['model_calls'],2)
            self.assertEqual(c.flush(),-4);np.testing.assert_array_equal(c.snapshot(),saved)
            self.assertEqual(c.profile()['model_calls'],4);self.assertEqual(c.profile()['tokens'],0)
            self.assertEqual(c.offer(16,self.obs[16]),-3)
    def test_workspace_and_structured_replay_exact(self):
        for enc in [4,8]:
            a=Baseline(library(HERE/'build_host_1/baseline.so'),enc);b=Baseline(self.lib,enc)
            for start,end in [(0,7),(7,23),(23,1027)]:
                sa,ta=a.replay(self.obs[start:end]);sb,tb=b.replay(self.obs[start:end]);self.assertEqual((sa,sb),(0,0))
                self.assertEqual(ta.tobytes(),tb.tobytes());self.assertEqual(a.snapshot().tobytes(),b.snapshot().tobytes())

def load_tests(loader,tests,pattern):return loader.loadTestsFromTestCase(HistoryTests)
if __name__=='__main__':unittest.main()
