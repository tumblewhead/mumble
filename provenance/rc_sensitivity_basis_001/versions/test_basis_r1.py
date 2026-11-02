import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from numpy.polynomial.chebyshev import chebvander,chebder,chebval
from .basis import SensitivityField,build
from experiments.hysteresis_refinement_001.field import build as original_build,features_jacobian,transported
from experiments.response_basis_attribution_001.basis import BasisField
from experiments.foster_campaign_001.backend import ROOT
from experiments.conditional_architecture_001.run import public_queries
from experiments.foster_uncertainty_audit_001.conditional_packet import chart_from


class Sensitivities(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();p=Path(cls.tmp.name)
        cls.binaries={k:build(p/k,k) for k in ['taylor2','hermite3']}
        cls.binaries['chebyshev3']=original_build(p/'ordinary')
        cls.config=json.loads((ROOT/'experiments/foster_feedback_001/calibration.json').read_text());cls.config['hysteresis_chart']='bounded'
        cls.center,_,cls.amps=public_queries(cls.config)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def field(self,kind):return SensitivityField(self.config,self.center,self.binaries[kind],kind)
    def rows(self,n=511):
        k=np.arange(n);dt=np.array([0.,1/35,1/50,.2,.8])[k%5]
        I=np.array([0.,.06,-.04,.013])[k//19%4]
        return np.c_[dt,I,np.full(n,25.),3.7+.01*np.sin(k),np.full(n,.001)]
    def test_polynomial_reproduction_values_and_slopes(self):
        for kind in self.binaries:
            f=self.field(kind);rng=np.random.default_rng(57)
            for _ in range(20):
                c=rng.normal(size=f.n)
                if kind=='taylor2':samples=np.array([chebval(0,c),chebval(0,chebder(c)),chebval(0,chebder(c,2))])
                elif kind=='hermite3':samples=np.r_[chebval(f.anchors,c),chebval(f.anchors,chebder(c))]
                else:samples=chebval(f.anchors,c)
                np.testing.assert_allclose(f.p1@samples,c,atol=1e-13,rtol=1e-13)
    def test_constant_current_free_forced_derivative_identities(self):
        for kind in ['taylor2','hermite3']:
            f=self.field(kind);obs=self.rows();obs[:,1]=.03;f.rows(0,obs)
            total=obs[:,0].sum()
            for j in range(3):
                dose=total/(self.center[j]*np.exp(f.anchors));E=np.exp(-dose)
                expected=np.r_[E,dose*E] if kind=='hermite3' else np.r_[E,dose*E,(dose*dose-dose)*E]
                actual=f.state[j*f.n:(j+1)*f.n]
                np.testing.assert_allclose(actual,expected,rtol=1e-10,atol=1e-13)
                u=f.state[(3+j)*f.n:(4+j)*f.n];start=np.zeros(f.n);start[:len(f.anchors)]=1.
                np.testing.assert_allclose(u,.03*(start-actual),rtol=1e-10,atol=1e-13)
    def test_native_sensitivity_recursions_under_irregular_signed_input(self):
        obs=self.rows()
        def ordinary(tau):
            F=1.;u=0.
            for dt,I,*_ in obs:
                e=np.exp(-dt/tau);F*=e;u=e*u-np.expm1(-dt/tau)*I
            return np.array([F,u])
        for kind in ['taylor2','hermite3']:
            f=self.field(kind);f.rows(0,obs);nanchor=len(f.anchors)
            for j in range(3):
                for k,t in enumerate(f.anchors):
                    tau=self.center[j]*np.exp(t);eps=1e-4
                    zero=ordinary(tau);plus=ordinary(tau*np.exp(eps));minus=ordinary(tau*np.exp(-eps))
                    values=np.array([f.state[j*f.n+k],f.state[(3+j)*f.n+k]])
                    slopes=np.array([f.state[j*f.n+nanchor+k],f.state[(3+j)*f.n+nanchor+k]])
                    np.testing.assert_allclose(values,zero,rtol=1e-11,atol=1e-13)
                    np.testing.assert_allclose(slopes,(plus-minus)/(2*eps),rtol=2e-5,atol=1e-9)
                    if kind=='taylor2':
                        second=np.array([f.state[j*f.n+2],f.state[(3+j)*f.n+2]])
                        np.testing.assert_allclose(second,(plus-2*zero+minus)/eps**2,rtol=1e-3,atol=2e-8)
    def test_features_and_transport_derivatives(self):
        a=self.amps[1];s=self.center*np.exp([.2,-.25,.15,.2,-.1]);x=chart_from(a,s)
        for kind in self.binaries:
            f=self.field(kind);f.update(0,self.rows());J=features_jacobian(f,x);_,F=transported(f,x)
            for j in range(16):
                xp=x.copy();xm=x.copy();xp[j]+=1e-6;xm[j]-=1e-6
                np.testing.assert_allclose((f.features(xp)-f.features(xm))/2e-6,J[:,j],rtol=3e-6,atol=2e-7)
                np.testing.assert_allclose((transported(f,xp)[0]-transported(f,xm)[0])/2e-6,F[:,j],rtol=3e-6,atol=2e-7)
    def test_joint_factor_H_parity_and_chunking(self):
        obs=self.rows();old=BasisField(self.config,self.center,self.binaries['chebyshev3']);original=old.rows(0,obs)
        for kind in self.binaries:
            f=self.field(kind);g=self.field(kind);rows=f.update(0,obs,return_rows=True)
            np.testing.assert_array_equal(rows[:,3+6*f.n:],original[:,21:])
            np.testing.assert_array_equal(f.state[6*f.n:],old.state[18:])
            np.testing.assert_allclose(f.root.T@f.root,rows.T@rows,rtol=1e-10,atol=1e-5)
            for first in range(0,len(obs),31):g.update(first,obs[first:first+31])
            np.testing.assert_array_equal(f.state,g.state)
            x=chart_from(self.amps[1],self.center)
            self.assertAlmostEqual(f.nll(x),g.nll(x),delta=1e-6)
    def test_atomicity_storage_and_kernel_binding(self):
        for kind in self.binaries:
            f=self.field(kind);obs=self.rows();f.update(0,obs);state=f.state.copy();root=f.root.copy()
            bad=obs.copy();bad[-1,4]=0.
            for first,o,source in [(0,obs,None),(len(obs),bad,None),(len(obs),obs,'other')]:
                with self.assertRaises(ValueError):f.update(first,o,source)
                np.testing.assert_array_equal(f.state,state);np.testing.assert_array_equal(f.root,root)
            s=self.center.copy();s[1]*=np.exp(1.01)
            with self.assertRaises(ValueError):f.evaluate(self.amps[0],s)
            expected=(4760,5168) if kind=='taylor2' else (6560,7016)
            self.assertEqual((f.storage()['packed_factor_B'],f.storage()['numeric_factor_response_domain_scalars_B']),expected)
        with self.assertRaises(ValueError):SensitivityField(self.config,self.center,self.binaries['hermite3'],'taylor2')


if __name__=='__main__':unittest.main()
