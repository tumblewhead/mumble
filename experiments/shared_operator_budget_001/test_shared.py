import json
from pathlib import Path
import unittest
import numpy as np
from .field import SharedField,features_jacobian,transported
from .readouts import add_readouts
from experiments.hysteresis_sensitivity_basis_001.run import field
from experiments.foster_feedback_001.estimator import Model
from experiments.foster_uncertainty_audit_001.conditional_packet import partition,chart_from


class SharedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory=Path('experiments/rc_sensitivity_basis_001/full001');cls.reg=json.loads((cls.directory/'registration.json').read_text())
        cls.bins={k:Path('experiments/hysteresis_sensitivity_basis_001/build001')/k/'response.so' for k in ['collocation','derivative']}
        cls.mean,cls.L,cls.center=map(np.asarray,[cls.reg['prior_mean'],cls.reg['prior_root'],cls.reg['center']])
        cls.model=Model(cls.directory/'backend_c/estimator.so',cls.reg['config'])
    def make(self):return SharedField(self.reg['config'],self.center,self.directory/'response_taylor2/response.so',self.bins['derivative'])
    def old(self):return field('TaylorRC_TaylorH2',self.reg,self.directory,'fixture',self.bins)
    def fixture(self):
        k=np.arange(512)
        return np.c_[np.array([0.,1/35,.2,.7])[k%4],np.array([.12,-.08,0.])[(k//17)%3],np.full(512,25.),np.full(512,3.7),np.full(512,.001)]

    def test_streaming_factor_state_and_storage_unchanged(self):
        obs=self.fixture();f=self.make();g=self.old()
        for k in range(0,512,128):
            np.testing.assert_array_equal(f.update(k,obs[k:k+128],return_rows=True),g.update(k,obs[k:k+128],return_rows=True))
        np.testing.assert_array_equal(f.root,g.root);np.testing.assert_array_equal(f.state,g.state)
        for key in ['packed_factor_B','live_response_B','retained_numpy_arrays_B','numeric_factor_response_domain_scalars_B']:self.assertEqual(f.storage()[key],g.storage()[key])
        self.assertEqual(f.width,34);self.assertEqual(f.storage()['packed_factor_B'],4760)

    def test_central_jet_and_equilibrium(self):
        f=self.make();o=self.fixture();o[:,0]=1/35;o[:,1]=.12;f.rows(0,o)
        F=f.state[:9].reshape(3,3);u=f.state[9:18].reshape(3,3);eps=2e-4
        def value(t):
            s=2*np.tanh(t/2);return F[:,0]+F[:,1]*s+.5*F[:,2]*s*s
        np.testing.assert_allclose((value(eps)-value(-eps))/(2*eps),F[:,1],atol=1e-8,rtol=1e-7)
        np.testing.assert_allclose((value(eps)-2*value(0)+value(-eps))/eps**2,F[:,2],atol=1e-8,rtol=1e-6)
        for t in [-1.,-.4,0.,.4,1.]:
            s=2*np.tanh(t/2);w=np.array([1.,s,.5*s*s]);np.testing.assert_allclose(u@w,.12*(1-F@w),atol=2e-14,rtol=0)

    def test_feature_and_transport_derivatives_full_support(self):
        f=self.make();f.update(0,self.fixture());a,s=partition(self.mean);eps=2e-6
        for offsets in [np.array([-.8,.7,.5]),np.zeros(3)]:
            shapes=s.copy();shapes[:3]*=np.exp(offsets);x=chart_from(a,shapes)
            J=features_jacobian(f,x);end,D=transported(f,x);fd=[];td=[]
            for j in range(16):
                p=x+eps*self.L[:,j];m=x-eps*self.L[:,j]
                fd.append((f.features(p)-f.features(m))/(2*eps));td.append((transported(f,p)[0]-transported(f,m)[0])/(2*eps))
            np.testing.assert_allclose(J@self.L,np.array(fd).T,atol=1e-7,rtol=2e-5)
            np.testing.assert_allclose(D@self.L,np.array(td).T,atol=1e-8,rtol=2e-5)
        shapes=s.copy();shapes[0]*=np.exp(1.01)
        with self.assertRaises(ValueError):f.features(chart_from(a,shapes))

    def test_transfer_identity_and_negative_free_counterexample(self):
        rng=np.random.default_rng(91)
        for _ in range(100):
            a=float(rng.uniform(.1,10));w=float(rng.uniform(-.46,.46));z=complex(rng.uniform(.1,5),rng.uniform(-5,5))
            lam=a*(1-w)/(1+w)
            Fh=1/(z+a)+(2*w-2*w*w)*a/(z+a)**2+4*w*w*a*a/(z+a)**3
            remainder=2*a*w**3*(z-a)**2/((1+w)*(z+a)**3*(z+lam))
            self.assertLess(abs(1/(z+lam)-Fh-remainder),1e-13)
        q=2*np.tanh(.5);d=1/q+.5
        bad=np.exp(-d)*(1-(q+q*q/2)*d+q*q/2*d*d)
        self.assertLess(bad,0)

    def test_joint_QR_and_unresolved_gate(self):
        o=self.fixture();f=self.make();f.update(0,o)
        report={'arms':{name:dict(status='unresolved',selected=dict(x=self.mean,w=np.zeros(16),root=self.L)) for name in ['direct','CayleyRC_TaylorH2']}}
        add_readouts({'CayleyRC_TaylorH2':f},lambda name:self.make(),self.model,o,self.mean,self.L,self.center,report)
        q=report['QR_readouts']['CayleyRC_TaylorH2'];self.assertEqual(q['fit_comparison']['status'],'unresolved_candidate_or_reference')
        self.assertNotIn('forecasts',q);self.assertLess(abs(q['controls']['factor_vs_augmented_QR_SOC_ratio_difference']),1e-7)


if __name__=='__main__':unittest.main()
