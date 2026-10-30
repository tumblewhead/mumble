import ctypes as C
import unittest
import numpy as np
from experiments.foster_c_baseline_001.test_baseline import BaselineTests as ParentTests
from experiments.foster_c_baseline_001.reference import Baseline,library,ptr
from .build import HERE

class OptimizedTests(ParentTests):
    @classmethod
    def setUpClass(cls):
        super().setUpClass();cls.lib=library(HERE/'build_host_3/baseline.so')
    def test_reuse_and_defer_exact_messages(self):
        for encoding in [4,8]:
            original=Baseline(library(HERE/'build_host_0/baseline.so'),encoding)
            status,expected=original.replay(self.obs[:1027]);self.assertEqual(status,0)
            for stage in [1,2]:
                opt=Baseline(library(HERE/f'build_host_{stage}/baseline.so'),encoding)
                status,actual=opt.replay(self.obs[:1027]);self.assertEqual(status,0)
                np.testing.assert_array_equal(actual[:,:35],expected[:,:35])
                np.testing.assert_array_equal(actual[:,35]+1,expected[:,35])
                np.testing.assert_array_equal(opt.snapshot(),original.snapshot())
                self.assertEqual(original.profile()['model_calls']-opt.profile()['model_calls'],opt.profile()['tokens'])
    def test_spd_solver_backward_error(self):
        self.lib.fb_spd_solve.argtypes=[ptr(np.empty(1)).__class__,ptr(np.empty(1)).__class__]
        rng=np.random.default_rng(771)
        for scale in [.001,1,100]:
            for n in [1,7,16]:
                B=rng.normal(size=(n,16))*scale;A=np.eye(16)+B.T@B;b=rng.normal(size=16)
                lower=A.copy();lower[np.triu_indices(16,1)]=np.nan;x=b.copy()
                self.assertEqual(self.lib.fb_spd_solve(ptr(lower),ptr(x)),0)
                error=np.linalg.norm(A@x-b)/(np.linalg.norm(A)*np.linalg.norm(x)+np.linalg.norm(b))
                self.assertLess(error,1e-14)
        A=np.zeros((16,16));b=np.ones(16)
        self.assertEqual(self.lib.fb_spd_solve(ptr(A),ptr(b)),-5)
    def test_gradient_exit_needs_no_trial_evaluations(self):
        opt=Baseline(self.lib,settings={'gradient_tol':1e100})
        base=Baseline(library(HERE/'build_host_0/baseline.so'),settings={'gradient_tol':1e100})
        for estimator in [opt,base]:self.assertEqual(estimator.replay(self.obs[:16])[0],0)
        np.testing.assert_array_equal(opt.snapshot(),base.snapshot())
        self.assertEqual(opt.profile()['model_calls'],2) # prediction and outgoing-domain check
        self.assertEqual(opt.profile()['fit_evaluations'],0)
        self.assertEqual(opt.profile()['stops'][1],1)
# Only load the subclass: imported parent is already represented by inherited tests.
def load_tests(loader,tests,pattern):return loader.loadTestsFromTestCase(OptimizedTests)
if __name__=='__main__':unittest.main()
