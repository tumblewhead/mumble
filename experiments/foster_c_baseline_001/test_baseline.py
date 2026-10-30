import ctypes as C
import json
import unittest
import tempfile
from pathlib import Path
import numpy as np
from .reference import Baseline,Physical,Message,config,library,message,ptr,ROOT,HERE
from experiments.foster_feedback_001.estimator import Model,Rolling,fit,prior
from experiments.foster_feedback_001.history import pack_kernel,kernel,GaussianBackend,pack_message

class BaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lib=library();cls.cfg,_,_=config();cls.model=Model(HERE/'build/baseline.so',cls.cfg)
        cls.obs=np.load(ROOT/'experiments/foster_cccv_stimulus_001/cycle001/case_0000/observations.npy',mmap_mode='r')[:2048].copy()
    def test_dense_solvers(self):
        rng=np.random.default_rng(244)
        for _ in range(20):
            a=rng.normal(size=(16,16));a+=np.eye(16);b=rng.normal(size=16);x=b.copy();ac=a.copy()
            self.assertEqual(self.lib.fb_solve(ptr(ac),ptr(x)),0);np.testing.assert_allclose(a@x,b,rtol=1e-10,atol=1e-11)
            a=a@a.T+np.eye(16);ac=a.copy();self.assertEqual(self.lib.fb_cholesky(ptr(ac)),0)
            np.testing.assert_allclose(ac@ac.T,a,rtol=1e-12,atol=1e-12)
        a=np.zeros((16,16));b=np.ones(16);self.assertEqual(self.lib.fb_solve(ptr(a),ptr(b)),-5)
        self.assertEqual(self.lib.fb_cholesky(ptr(a)),-5)
    def test_qr_preserves_quadratic(self):
        rng=np.random.default_rng(42)
        for n in [1,7,16,17]:
            a=np.zeros((17,17));a[:n]=rng.normal(size=(n,17));q=a.copy()
            self.assertEqual(self.lib.fb_qr(ptr(q)),0)
            np.testing.assert_allclose(q.T@q,a.T@a,atol=1e-12,rtol=1e-12)
            self.assertEqual(np.count_nonzero(np.tril(q,-1)),0)
    def test_subnormal_qr_preserves_orthogonal_residual(self):
        for magnitude in [np.nextafter(0.,1.),1e-320,1e-300,1e-290]:
            a=np.zeros((17,17));a[:2,0]=magnitude;a[:2,16]=[3,4];before=a.copy()
            self.assertEqual(self.lib.fb_qr(ptr(a)),0)
            np.testing.assert_allclose(a.T@a,before.T@before,rtol=1e-14,atol=1e-14)
    def test_generic_history_full_covariance_and_normalizer(self):
        rng=np.random.default_rng(243)
        for encoding in [4,8]:
            for _ in range(12):
                m=rng.normal(size=16);L=rng.normal(size=(16,16))*.03
                anchor=m+rng.normal(size=16)*.01;end=anchor+rng.normal(size=16)*.01
                A=rng.normal(size=(16,16))*3;r=rng.normal(size=16);F=np.eye(16)+rng.normal(size=(16,16))*.02
                token=pack_kernel(anchor,end,F,A,r,.3,'float'+str(encoding*8));t=(C.c_ubyte*len(token)).from_buffer_copy(token)
                out=Message();self.assertEqual(self.lib.fb_history(C.byref(message(m,L,.7)),t,len(token),C.byref(out)),0)
                a,e,f,A,r,c=kernel(token);y=r+A@(m-a);P=L@L.T;S=np.eye(17)+A@P@A.T
                K=np.linalg.solve(S,A@P).T;mu=e+f@(m-K@y-a);cov=f@(P-K@A@P)@f.T
                z=.7-c-.5*(y@np.linalg.solve(S,y)+np.linalg.slogdet(S)[1])
                np.testing.assert_allclose(out.mean,mu,atol=1e-9,rtol=0)
                root=np.array(out.root).reshape(16,16);np.testing.assert_allclose(root@root.T,cov,atol=1e-10,rtol=0)
                self.assertAlmostEqual(out.logZ,z,delta=1e-7)
    def test_token_codec(self):
        m,L=prior(self.cfg);obs=self.obs[:16];anchor,physical,_=fit(self.model,m,L,obs,self.cfg['numerical'])
        v,J,end,F=physical;ph=Physical((C.c_double*16)(*v),(C.c_double*256)(*J.ravel()),(C.c_double*16)(*end),(C.c_double*256)(*F.ravel()))
        for enc in [4,8]:
            dst=(C.c_ubyte*3537)();n=self.lib.fb_token(ptr(anchor),C.byref(ph),ptr(obs),16,enc,dst)
            self.assertEqual(n,265+409*enc)
            decoded=kernel(bytes(dst[:n]));_,_,f,A,r,c=decoded
            raw=np.column_stack([J/obs[:,4,None],(v-obs[:,3])/obs[:,4]])
            aug=np.column_stack([A,r]);tol=2e-7 if enc==4 else 2e-14
            np.testing.assert_allclose(aug.T@aug,raw.T@raw,rtol=tol,atol=tol*np.max(abs(raw.T@raw)))
            np.testing.assert_array_equal(f,F.astype(np.float32).astype(float) if enc==4 else F)
    def test_single_block_python_full_message(self):
        for enc in [4,8]:
            c=Baseline(self.lib,enc);py=Rolling(HERE/'build/baseline.so',self.cfg,'a'*64,'b'*64,'float'+str(enc*8))
            for i,row in enumerate(self.obs[:16]):c.offer(i,row);py.offer(i,*row)
            actual=c.snapshot();expected=np.frombuffer(py.history.read().payload,dtype='<f8')
            np.testing.assert_allclose(actual[:16],expected[:16],rtol=0,atol=1e-9)
            A=actual[16:272].reshape(16,16);B=expected[16:272].reshape(16,16)
            np.testing.assert_allclose(A@A.T,B@B.T,rtol=0,atol=1e-10)
            self.assertAlmostEqual(actual[-1],expected[-1],delta=1e-7 if enc==8 else 1e-6)
    def test_short_stream_python_parity(self):
        for enc in [4,8]:
            c=Baseline(self.lib,enc);py=Rolling(HERE/'build/baseline.so',self.cfg,'a'*64,'b'*64,'float'+str(enc*8))
            for i,row in enumerate(self.obs):
                c.offer(i,row);result=py.offer(i,*row)
                if result:
                    a=c.snapshot();b=np.frombuffer(py.history.read().payload,dtype='<f8')
                    # Report full-stream numerical sensitivity separately; application guard.
                    self.assertLess(abs(np.expm1(a[5]-b[5]))*100,.5)
                    self.assertLess(abs(a[0]-b[0])*100,.5)
            self.assertEqual(c.profile()['tokens'],128)
    def test_order_validation_and_flush(self):
        c=Baseline(self.lib);start=c.snapshot();row=self.obs[0].copy()
        self.assertEqual(c.offer(1,row),-1);np.testing.assert_array_equal(c.snapshot(),start)
        for j,value in [(0,np.nan),(0,-1),(0,.001),(1,np.inf),(2,np.nan),(3,np.inf),(4,0)]:
            bad=row.copy();bad[j]=value;self.assertEqual(c.offer(0,bad),-2)
        self.assertEqual(c.offer(0,row),0);self.assertEqual(c.offer(0,row),-1)
        self.assertEqual(c.flush(),1);after=c.snapshot();self.assertEqual(c.flush(),0)
        np.testing.assert_array_equal(c.snapshot(),after);self.assertEqual(c.profile()['tokens'],1)
    def test_failure_preserves_message_and_pending(self):
        c=Baseline(self.lib);start=c.snapshot();bad=self.obs[0].copy();bad[2]=100
        for i in range(15):self.assertEqual(c.offer(i,bad),0)
        self.assertEqual(c.offer(15,bad),-4);np.testing.assert_array_equal(c.snapshot(),start)
        self.assertEqual(c.offer(16,self.obs[16]),-3);self.assertEqual(c.flush(),-4)
        np.testing.assert_array_equal(c.snapshot(),start);self.assertEqual(c.profile()['tokens'],0)
    def test_irregular_intervals_partial_window(self):
        rows=self.obs[:19].copy();rows[:,0]=np.resize([0,1/35,31/1050,2/35],19)
        c=Baseline(self.lib);py=Rolling(HERE/'build/baseline.so',self.cfg,'a'*64,'b'*64)
        for i,row in enumerate(rows):c.offer(i,row);py.offer(i,*row)
        self.assertEqual(c.flush(),1);py.retire();a=c.snapshot();b=np.frombuffer(py.history.read().payload,dtype='<f8')
        np.testing.assert_allclose(a,b,atol=1e-8,rtol=1e-8)
    def test_failed_replay_does_not_abort_other_arm(self):
        from .run import run
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            case=Path(directory)/'case';case.mkdir();obs=self.obs[:16].copy();obs[:,2]=100
            np.save(case/'observations.npy',obs)
            for enc in ['float64','float32']:
                np.save(case/(enc+'_chart.npy'),np.zeros((1,32)))
                np.save(case/(enc+'_trace.npy'),np.zeros((1,39)))
            (case/'result.json').write_text(json.dumps({'arms':{e:{'outputs':1} for e in ['float64','float32']}}))
            result=run(case,Path(directory)/'out')
            for arm in result['arms'].values():
                self.assertEqual(arm['status'],'failed');self.assertEqual(arm['outputs'],0)
                self.assertEqual(arm['python_comparison']['paired_outputs'],0)
            self.assertEqual(len(result['arms']),2)
    def test_bad_token_rejected(self):
        _,_,m=config();out=Message();t=(C.c_ubyte*1)(ord('8'))
        self.assertEqual(self.lib.fb_history(C.byref(m),t,1,C.byref(out)),-6)
        self.assertEqual(self.lib.fb_history(C.byref(m),t,0,C.byref(out)),-6)
if __name__=='__main__':unittest.main()
