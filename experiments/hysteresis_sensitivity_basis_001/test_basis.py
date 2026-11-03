import ctypes as C
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from numpy.polynomial.chebyshev import chebvander
from .basis import HField,build
from .reference import jet,INDICES,SLOTS,constants,envelope
from experiments.rc_sensitivity_basis_001.basis import SensitivityField
from experiments.foster_feedback_001.estimator import Model
from experiments.foster_uncertainty_audit_001.conditional_packet import chart_from
from experiments.joint_precision_attribution_001.metrics import coordinates
from experiments.hysteresis_refinement_001.field import features_jacobian,transported


class HTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='mumble-h-sens-')
        cls.binary={k:build(Path(cls.temp.name)/k,k) for k in ['collocation','derivative']}
        cls.directory=Path('experiments/rc_sensitivity_basis_001/full001')
        cls.reg=json.loads((cls.directory/'registration.json').read_text())
        cls.rc=cls.directory/'response_taylor2/response.so'
        cls.model=Model(cls.directory/'backend_c/estimator.so',cls.reg['config'])
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def make(self,kind='TaylorH2'):
        return HField(self.reg['config'],self.reg['center'],self.rc,
            self.binary['derivative' if kind=='TaylorH2' else 'collocation'],kind)
    def fixture(self):
        k=np.arange(512)
        return np.c_[np.array([0.,1/35,.2,1.])[k%4],
            np.array([0.,.12,-.08,.2,-.18])[(k//11)%5],np.full(512,25.),np.full(512,3.7),np.full(512,.001)]

    def test_mode_binding_and_storage(self):
        for kind in ['H2','c22','tensor','TaylorH2','H7']:
            f=self.make(kind)
            self.assertEqual(f.storage()['packed_factor_B'],{'H2':4760,'c22':5328,'tensor':6560,'TaylorH2':4760,'H7':35720}[kind])
            wrong=self.binary['collocation' if kind=='TaylorH2' else 'derivative']
            with self.assertRaises(ValueError):HField(self.reg['config'],self.reg['center'],self.rc,wrong,kind)
        for binary in self.binary.values():
            self.assertFalse(hasattr(C.CDLL(str(binary)),'response_rows'))
            with self.assertRaises((AttributeError,ValueError)):
                SensitivityField(self.reg['config'],self.reg['center'],binary,'taylor2')
        self.assertEqual(self.make().storage()['numeric_factor_response_domain_scalars_B'],5168)

    def test_native_derivatives_and_uniform_majorants(self):
        obs=self.fixture();f=self.make();f.rows(0,obs)
        ref=jet(obs,np.array(self.reg['center'])[3:]);Cbound=constants()
        for j,a in enumerate(INDICES):
            if a==(0,0):continue
            self.assertLessEqual(np.max(abs(ref[:,0,j])),Cbound[a]+1e-12)
            self.assertLessEqual(np.max(abs(ref[:,1,j])),2*Cbound[a]+1e-12)
        expected=ref[-1][:,[INDICES.index(a) for a in SLOTS]]
        actual=np.array([f.state[18:24],f.state[27:33]])
        np.testing.assert_allclose(actual,expected,atol=1e-13,rtol=1e-11)
        self.assertTrue(np.array_equal(f.state[np.r_[24:27,33:36]],np.zeros(6)))
        plus=sum(obs[obs[:,1]>0,0]*obs[obs[:,1]>0,1])/3600*self.reg['center'][3]
        minus=-sum(obs[obs[:,1]<0,0]*obs[obs[:,1]<0,1])/3600*self.reg['center'][4]
        free=np.exp(-plus-minus)*np.array([1,-plus,-minus,plus*plus-plus,plus*minus,minus*minus-minus])
        np.testing.assert_allclose(actual[0],free,atol=1e-13,rtol=1e-11)
        self.assertEqual(Cbound[(3,0)],13);self.assertEqual(Cbound[(2,1)],3)

    def test_constant_sign_and_rest(self):
        for sign in [-1,1]:
            obs=self.fixture();obs[:,1]=sign*.12;f=self.make();f.rows(0,obs)
            F=f.state[18:24];u=f.state[27:33];wanted=-sign*F;wanted[0]+=sign
            np.testing.assert_allclose(u,wanted,atol=2e-13,rtol=1e-10)
            before=f.state[18:36].copy();rest=obs[:12].copy();rest[:,1]=0
            f.rows(len(obs),rest)
            np.testing.assert_array_equal(f.state[18:36],before)

    def test_polynomial_reproduction_and_centre_gradients(self):
        f=self.make();rng=np.random.default_rng(7)
        for t in rng.uniform(-1,1,size=(10,2)):
            v=rng.normal(size=6);T=chebvander(t,2)
            h=np.array([T[0,i]*T[1,j] for i,j in f.pairs])
            expected=v[0]+v[1]*t[0]+v[2]*t[1]+v[3]*t[0]**2/2+v[4]*t[0]*t[1]+v[5]*t[1]**2/2
            self.assertAlmostEqual(h@f.p2@np.r_[v,np.zeros(3)],expected,places=13)
        obs=self.fixture();rows=f.rows(0,obs);x=np.array(self.reg['prior_mean'])
        a,s,B,K=coordinates(x,np.array(self.reg['prior_root']))
        v,J,_,_=self.model.evaluate(x,obs)
        np.testing.assert_allclose(rows@f.features(x),(v-obs[:,3])/obs[:,4],atol=1e-9,rtol=0)
        np.testing.assert_allclose(rows@features_jacobian(f,x)@B,(J@B)/obs[:,4,None],atol=1e-8,rtol=1e-9)

    def test_mixed_derivative_finite_difference_and_remainders(self):
        obs=self.fixture();f=self.make();f.rows(0,obs);rates=np.array(self.reg['center'])[3:]
        h=2e-4
        def direct(t):return jet(obs,rates*np.exp(t))[-1,:,0]
        mixed=(direct([h,h])-direct([h,-h])-direct([-h,h])+direct([-h,-h]))/(4*h*h)
        np.testing.assert_allclose([f.state[22],f.state[31]],mixed,atol=3e-8,rtol=3e-6)
        a,s,_,_=coordinates(np.array(self.reg['prior_mean']),np.array(self.reg['prior_root']))
        a[10]=.002
        for offset in [[.35,-.35],[.9,.9],[-.9,.9]]:
            shape=s.copy();shape[3:]*=np.exp(offset);b,vbound=envelope(a,shape,self.reg['center'])
            ref=jet(obs,shape[3:])[-1];Tc=chebvander(np.array(offset),2)
            hv=np.array([Tc[0,i]*Tc[1,j] for i,j in f.pairs])
            approximate=hv@f.p2@(a[10]*f.state[18:27]+a[9]*f.state[27:36])
            true=a[10]*ref[0,0]+a[9]*ref[1,0]
            self.assertLessEqual(abs(approximate-true),vbound+1e-12)

    def test_unchanged_RC_chunking_atomicity_and_transport(self):
        obs=self.fixture();base=SensitivityField(self.reg['config'],self.reg['center'],self.rc,'taylor2')
        control=base.rows(0,obs);f=self.make();rows=f.update(0,obs,return_rows=True)
        np.testing.assert_array_equal(rows[:,:21],control[:,:21])
        g=self.make()
        for start in range(0,len(obs),64):g.update(start,obs[start:start+64])
        np.testing.assert_array_equal(g.state,f.state)
        np.testing.assert_allclose(g.root.T@g.root,f.root.T@f.root,atol=1e-5,rtol=2e-12)
        before=(f.state.copy(),f.root.copy(),f.count,f.noise)
        bad=obs[:4].copy();bad[-1,4]=-1
        with self.assertRaises(ValueError):f.update(len(obs),bad)
        np.testing.assert_array_equal(f.state,before[0]);np.testing.assert_array_equal(f.root,before[1])
        self.assertEqual((f.count,f.noise),before[2:])
        x=np.array(self.reg['prior_mean']);end,D=transported(f,x)
        for k in [4,5,13,14,15]:
            dx=np.eye(16)[k]*1e-5
            finite=(transported(f,x+dx)[0]-transported(f,x-dx)[0])/(2e-5)
            np.testing.assert_allclose(D[:,k],finite,atol=1e-8,rtol=1e-7)


if __name__=='__main__':unittest.main()
