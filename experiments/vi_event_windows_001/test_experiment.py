import ctypes as C,json,tempfile,unittest
from pathlib import Path
import numpy as np
from .build import build,ROOT
from .run import Bank,UP
from .schedule import schedules
from experiments.foster_c_baseline_001.reference import Baseline,library,ptr,Physical,UP as BYTEP
from experiments.foster_campaign_001.coordinates import prior

class ExperimentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.cfg=json.loads((ROOT/'experiments/foster_feedback_001/calibration.json').read_text());cls.cfg['hysteresis_chart']='bounded'
        cls.gaussian=build(Path(cls.tmp.name)/'gaussian',50,cls.cfg,0.);cls.mixture=build(Path(cls.tmp.name)/'mixture',50,cls.cfg,.001)
        cls.obs=np.load(ROOT/'tests/fixtures/foster_seed1001_50hz_prefix1024.npy')
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_gaussian_original_byte_parity(self):
        old=Baseline(library(self.gaussian.parent/'backend_c/estimator.so'),initial=prior(self.cfg));status,expected=old.replay(self.obs)
        bank=Bank(self.gaussian,self.cfg);trace,final,r=bank.replay(self.obs,np.arange(16,len(self.obs)+1,16))
        self.assertEqual(status,0);self.assertEqual(r['C_status'],0);np.testing.assert_array_equal(trace,expected);np.testing.assert_array_equal(final,old.snapshot())
    def test_schedule_ownership_and_lengths(self):
        obs=self.obs[:997];plans,report=schedules(obs,self.cfg['prior_mean_physical']['tau'])
        for ends in plans.values():
            self.assertEqual(ends[-1],len(obs));lengths=np.diff(np.r_[0,ends]);self.assertTrue(np.all((lengths>=1)&(lengths<=16)))
            b=Bank(self.gaussian,self.cfg);trace,_,r=b.replay(obs,ends);self.assertEqual(r['retired_records'],len(obs));self.assertEqual(r['tokens'],len(ends));self.assertEqual(r['C_status'],0)
            self.assertEqual(r['retired_ticks'],round(obs[:,0].sum()*1050))
        np.testing.assert_array_equal(np.sort(np.diff(np.r_[0,plans['joint_vi']])),np.sort(np.diff(np.r_[0,plans['displaced_vi']])))
    def test_invalid_schedule_transactional(self):
        bank=Bank(self.gaussian,self.cfg);before=np.empty(273);bank.lib.fb_get_message(bank.context,ptr(before))
        for ends in [[16,16,32],[17,32],[16,31],[16,40]]:
            trace,after,r=bank.replay(self.obs[:32],ends);self.assertLess(r['C_status'],0);self.assertEqual(len(trace),0);np.testing.assert_array_equal(before,after)
    def noise(self,r):
        lib=library(self.mixture);lib.experiment_noise.argtypes=[C.c_double,C.POINTER(C.c_double),C.POINTER(C.c_double)];lib.experiment_noise.restype=C.c_double
        w=C.c_double();p=C.c_double();rho=lib.experiment_noise(r,C.byref(w),C.byref(p));return rho,w.value,p.value
    def test_mixture_gradient_and_tails(self):
        for r in [-1000.,-20.,-5.,-1.,0.,1.,5.,20.,1000.]:
            rho,w,p=self.noise(r);h=1e-4
            numerical=(self.noise(r+h)[0]-self.noise(r-h)[0])/(2*h)
            self.assertAlmostEqual(numerical,w*r,delta=2e-7);self.assertTrue(.0025<=w<=1);self.assertTrue(0<=p<=1);self.assertTrue(np.isfinite(rho))
    def test_token_value_and_gradient_at_anchor(self):
        lib=library(self.mixture);lib.experiment_token.argtypes=lib.fb_token.argtypes
        rng=np.random.default_rng(22);ph=Physical();v=np.array([3.7,3.8,4.1]);J=rng.normal(size=(3,16));anchor=rng.normal(size=16)
        for i in range(3):ph.v[i]=v[i]
        for i,x in enumerate(J.ravel()):ph.J[i]=x
        for i in range(16):ph.end[i]=anchor[i];ph.F[16*i+i]=1.
        obs=np.array([[.02,.04,25.,3.71,.02],[.02,.04,25.,3.65,.02],[.02,.04,25.,3.7,.02]])
        token=(C.c_ubyte*3537)();size=lib.experiment_token(ptr(anchor),C.byref(ph),ptr(obs),3,8,token);self.assertEqual(size,3537)
        values=np.frombuffer(bytes(token)[1:],dtype='<f8');constant=values[32];R=np.zeros((17,17));R[np.triu_indices(17)]=values[33:186];a=R[:,-1];B=R[:,:16]
        r=(v-obs[:,3])/obs[:,4];expected=sum(self.noise(x)[0]+np.log(s)+.5*np.log(2*np.pi) for x,s in zip(r,obs[:,4]))
        self.assertAlmostEqual(constant+.5*a@a,expected,places=11)
        gradient=J.T@np.array([self.noise(x)[1]*x/s for x,s in zip(r,obs[:,4])]);np.testing.assert_allclose(B.T@a,gradient,atol=1e-10,rtol=1e-11)
    def test_matcher_step_polarity_and_baseline(self):
        for k in [8,10,12,16]:
            rows=np.zeros((24,5));rows[:,0]=.02;rows[:,2]=25;rows[:,4]=.002;rows[:,1]=np.arange(24)>=k;rows[:,3]=3.7-.1*rows[:,1]
            for sign in [-1,1]:
                x=rows.copy();x[:,1]*=sign;x[:,3]=3.7+sign*(rows[:,3]-3.7)
                plans,_=schedules(x,[.07,.7,6]);self.assertEqual(plans['joint_vi'][0],k)
                x[:,3]+=1.+np.arange(24)*.001
                plans,_=schedules(x,[.07,.7,6]);self.assertEqual(plans['joint_vi'][0],k)
        rows[:,1]=.1;plans,r=schedules(rows,[.07,.7,6]);self.assertEqual(plans['joint_vi'][0],12);self.assertEqual(r['flat_current_tiles'],1)
    def test_sparse_fallback_and_accounting(self):
        from .sparse import sparse_schedules
        obs=self.obs[:997].copy();obs[:,1]=.1
        plans,_=sparse_schedules(obs,[.07,.7,6]);expected=np.minimum(np.arange(16,1013,16),997).astype(np.uint64)
        np.testing.assert_array_equal(plans['sparse_vi'],expected)
        obs[100:200,1]=-.1;plans,_=sparse_schedules(obs,[.07,.7,6])
        for ends in plans.values():
            self.assertEqual(ends[-1],997);self.assertTrue(np.all(np.diff(np.r_[0,ends])<=16))
        np.testing.assert_array_equal(np.sort(np.diff(np.r_[0,plans['sparse_vi']])),np.sort(np.diff(np.r_[0,plans['sparse_displaced']])))
