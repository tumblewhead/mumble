import unittest
import numpy as np
from . import test_field as fixture
from .ablation import restricted,omitted_modes
from .field import Compressed,features_jacobian


class AblationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixture.MixedTests.setUpClass()
    @classmethod
    def tearDownClass(cls):fixture.MixedTests.tearDownClass()
    def test_column_restriction_retains_joint_cost_gradient_curvature(self):
        s=fixture.MixedTests();f=s.field(7);f.update(0,s.obs);g=restricted(f,5)
        w=np.linspace(-.02,.02,16);x=s.mean+s.L@w
        p=f.features(x);D=features_jacobian(f,x)@s.L;start=3+6*f.n
        for k,pair in enumerate(f.pairs):
            if sum(pair)>5:
                ix=[start+k,start+f.b+k];p[ix]=0;D[ix]=0
        r=f.root@p;B=f.root@D
        c,grad,P,_,_=Compressed(g,s.mean,s.L)(w)
        np.testing.assert_allclose(c,.5*(w@w+r@r),rtol=5e-12)
        np.testing.assert_allclose(grad,w+B.T@r,rtol=2e-10,atol=1e-7)
        np.testing.assert_allclose(P,np.eye(16)+B.T@B,rtol=2e-10,atol=1e-7)
    def test_omitted_mode_additive_identity(self):
        s=fixture.MixedTests();f=s.field(7);f.update(0,s.obs)
        result=omitted_modes(f,s.mean+s.L@np.linspace(-.02,.02,16),s.L)
        self.assertLess(result['gradient_identity_max_abs_error'],1e-7)
        self.assertLess(abs(result['projected_identity_Q_error']),1e-8)

if __name__=='__main__':unittest.main()
