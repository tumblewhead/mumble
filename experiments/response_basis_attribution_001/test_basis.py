import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from .basis import BasisField
from .attribution import split_defects,terms
from experiments.conditional_architecture_001.run import public_queries
from experiments.conditional_architecture_001.conditional import chart_amplitude_jacobian
from experiments.partitioned_coefficients_001.run import chart_shape_jacobian
from experiments.foster_campaign_001.backend import ROOT
from experiments.foster_uncertainty_audit_001.conditional_packet import chart_from
from experiments.hysteresis_refinement_001.field import build,features_jacobian
from experiments.joint_rate_history_001.field import Field,build as oldbuild


class Basis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.path=Path(cls.temp.name);cls.binary=build(cls.path/'mixed');cls.oldbinary=oldbuild(cls.path/'old')
        cls.config=json.loads((ROOT/'experiments/foster_feedback_001/calibration.json').read_text());cls.config['hysteresis_chart']='bounded'
        cls.center,_,cls.amplitudes=public_queries(cls.config)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def rows(self,n=257):
        k=np.arange(n)
        return np.column_stack((np.full(n,1/35),np.where((k//17)%2,.06,-.04),np.full(n,25.),3.7+.01*np.cos(k),np.full(n,.001)))
    def field(self,degree=2,coordinate='log'):return BasisField(self.config,self.center,self.binary,degree,coordinate)
    def test_legacy_equivalence_joint_gradient_and_transport(self):
        obs=self.rows();new=self.field();old=Field(self.config,self.center,1.,2,self.oldbinary);old.m=old.n
        new.update(0,obs);old.update(0,obs);s=self.center*np.exp([.2,-.3,.1,.4,-.2])
        for a in self.amplitudes:
            x=chart_from(a,s);q=new.evaluate(a,s);r=old.residual(x);J=old.root@features_jacobian(old,x)@np.column_stack((chart_amplitude_jacobian(a),chart_shape_jacobian(s)))
            self.assertAlmostEqual(q['nll'],old.nll(x),delta=1e-8*max(1,abs(old.nll(x))))
            np.testing.assert_allclose(np.r_[q['gradient_amplitude'],q['gradient_shape']],J.T@r,rtol=1e-8,atol=1e-5)
            np.testing.assert_allclose(q['end'],old.outgoing(x),rtol=1e-10,atol=1e-10)
    def test_all_coordinate_derivatives(self):
        a=self.amplitudes[1];s=self.center*np.exp([.1,-.3,.2,.4,-.2])
        for degree in (2,3):
            for coordinate in ('log','rate'):
                f=self.field(degree,coordinate);f.update(0,self.rows());W,D,_=f.basis_query(a,s)
                for j in range(16):
                    eps=1e-6;ap=a.copy();am=a.copy();sp=s.copy();sm=s.copy()
                    if j<11:ap[j]+=eps;am[j]-=eps
                    else:sp[j-11]*=np.exp(eps);sm[j-11]*=np.exp(-eps)
                    fd=(f.basis_query(ap,sp)[0]-f.basis_query(am,sm)[0])/(2*eps)
                    np.testing.assert_allclose(fd,D[:,j],rtol=1e-6,atol=1e-7)
    def test_inherited_chart_helpers_use_selected_coordinate(self):
        a=self.amplitudes[1];s=self.center*np.exp([.1,-.3,.2,.4,-.2]);x=chart_from(a,s)
        for degree in (2,3):
            for coordinate in ('log','rate'):
                f=self.field(degree,coordinate);f.update(0,self.rows());q=f.evaluate(a,s)
                self.assertAlmostEqual(f.nll(x),q['nll'],delta=1e-8*max(1,abs(q['nll'])))
                np.testing.assert_allclose(f.outgoing(x),q['end'],rtol=1e-12,atol=1e-12)

    def test_rate_domain_same_and_failure_atomicity(self):
        f=self.field(3,'rate');obs=self.rows();f.update(0,obs);root=f.root.copy();state=f.state.copy()
        for j in (3,4):
            for sign in (-1,1):
                s=self.center.copy();s[j]*=np.exp(sign);f.evaluate(self.amplitudes[0],s)
                s[j]*=np.exp(sign*1e-4)
                with self.assertRaisesRegex(ValueError,'outside computational'):f.evaluate(self.amplitudes[0],s)
        bad=obs.copy();bad[-1,4]=0
        for first,o,source in [(0,obs,None),(len(obs),bad,None),(len(obs),obs,'other')]:
            with self.assertRaises(ValueError):f.update(first,o,source)
        np.testing.assert_array_equal(f.root,root);np.testing.assert_array_equal(f.state,state)
    def test_chunk_regrouping_and_counts(self):
        obs=self.rows();a=self.amplitudes[1];s=self.center*np.exp([.1,-.3,.2,.4,-.2])
        for degree,expected in ((2,4760),(3,7224)):
            f=self.field(degree,'rate');g=self.field(degree,'rate');f.update(0,obs)
            for first in range(0,len(obs),13):g.update(first,obs[first:first+13])
            for key,v in f.evaluate(a,s).items():np.testing.assert_allclose(v,g.evaluate(a,s)[key],rtol=1e-8,atol=1e-5)
            self.assertEqual(f.storage()['packed_factor_B'],expected)
    def test_signed_expansion_and_hybrid_semantics(self):
        rng=np.random.default_rng(43);a=self.amplitudes[1];J=rng.normal(size=(80,16));delta=rng.normal(size=J.shape);delta[:,[0,4,5]]=0;r=rng.normal(size=80)
        dr,dJ=split_defects(a,J,J+delta);parts,pairs=terms(r,J,dr,dJ)
        total=(J+delta).T@(r+dr.sum(axis=0))-J.T@r
        np.testing.assert_allclose(parts.sum(axis=(0,1))+pairs.sum(axis=0),total,atol=1e-11)
        for p in range(4):np.testing.assert_allclose(parts[p].sum(axis=0),(J+dJ[p]).T@(r+dr[p])-J.T@r,atol=1e-11)

if __name__=='__main__':unittest.main()
