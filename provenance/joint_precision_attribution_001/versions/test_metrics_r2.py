import json
from pathlib import Path
import unittest
import numpy as np
from . import metrics as m
from .run import field
from experiments.foster_feedback_001.estimator import Model
from experiments.hysteresis_refinement_001.field import features_jacobian
from experiments.foster_uncertainty_audit_001.conditional_packet import chart_from


class AttributionTests(unittest.TestCase):
    def test_physical_chain_and_capacity_coupling(self):
        a = np.array([.6,.001,-.002,.003,18.,.1,.03,.07,.1,.012,.002])
        s = np.array([.07,.7,6.,90.,145.])
        x = chart_from(a,s);_,_,B,K = m.coordinates(x,np.eye(16))
        for k in range(16):
            h = 1e-6*max(abs(a[k]),.01) if k<11 else 1e-6
            ap,am,sp,sm = a.copy(),a.copy(),s.copy(),s.copy()
            if k<11:ap[k]+=h;am[k]-=h
            else:sp[k-11]*=np.exp(h);sm[k-11]*=np.exp(-h)
            finite = (chart_from(ap,sp)-chart_from(am,sm))/(2*h)
            np.testing.assert_allclose(B[:,k],finite,atol=1e-6,rtol=2e-7)
        delta = np.zeros((1,16));delta[0,14]=1.
        rc,h = m.separate(delta)
        self.assertEqual(np.max(abs(rc)),0)
        self.assertAlmostEqual((h@K)[0,5],-1.)
        self.assertAlmostEqual((h@K)[0,14],1.)

    def test_common_qr_and_cross_terms(self):
        rng = np.random.default_rng(13)
        rows = rng.normal(size=(150,51));r = np.zeros((51,51))
        for block in np.array_split(rows,7):r=m.append(r,block)
        np.testing.assert_allclose(r.T@r,rows.T@rows,atol=1e-12,rtol=1e-11)
        J,dr,dh=rows[:,:16],rows[:,16:32],rows[:,32:48]
        base=J.T@J
        total=(J+dr+dh).T@(J+dr+dh)-base
        pieces=(J+dr).T@(J+dr)-base+(J+dh).T@(J+dh)-base
        interaction=dr.T@dh+dh.T@dr
        np.testing.assert_allclose(total,pieces+interaction,atol=1e-12)
        self.assertGreater(np.linalg.norm(total-pieces),1.)

    def test_query_bound_and_inconclusive_status(self):
        rng=np.random.default_rng(3)
        J=rng.normal(size=(100,16));D=.01*rng.normal(size=(100,16))
        P=np.eye(16)+J.T@J;M=np.linalg.solve(np.linalg.cholesky(P).T,np.eye(16))
        eta=np.linalg.norm(D@M,2);eps=2*eta+eta*eta
        g=rng.normal(size=(40,16));gh=g+.01*rng.normal(size=g.shape)
        Ps=np.linalg.qr(np.vstack((np.eye(16),J+D)),mode='r')
        result=m.query_metrics(g,gh,Ps,M,eps)
        self.assertEqual(result['P3']['status'],'sufficient_test_passes_at_sampled_anchor')
        self.assertEqual(m.query_metrics(g,gh,Ps,M,2.)['P3']['status'],'inconclusive_epsilon_ge_1')
        with self.assertRaises(ValueError):m.query_metrics(np.zeros(16),np.zeros(16),Ps,M,eps)

    def test_hybrid_transport_keeps_selected_state_rows(self):
        direct=(np.arange(16,dtype=float),np.eye(16))
        compressed=(direct[0]+.1,direct[1]+.01)
        for mode,indices in [('RC_only',[1,2,3]),('H_only',[4]),('combined',[1,2,3,4])]:
            end,D=m.hybrid_transport(direct,compressed,mode)
            np.testing.assert_equal(end[indices],compressed[0][indices])
            other=[i for i in range(16) if i not in indices]
            np.testing.assert_equal(end[other],direct[0][other])
            np.testing.assert_equal(D[other],direct[1][other])

    def test_native_short_prefix_partition(self):
        directory=Path('experiments/rc_sensitivity_basis_001/full001')
        reg=json.loads((directory/'registration.json').read_text())
        model=Model(directory/'backend_c/estimator.so',reg['config'])
        mean=np.array(reg['prior_mean']);L=np.array(reg['prior_root'])
        a,s,_,_=m.coordinates(mean,L);s*=np.exp([.1,-.1,.12,.15,-.2]);x=chart_from(a,s)
        a,s,B,K=m.coordinates(x,L)
        k=np.arange(96);obs=np.c_[np.array([0.,1/35,.15])[k%3],
            np.array([0.,.03,-.02])[(k//10)%3],np.full(96,25.),np.full(96,3.7),np.full(96,.001)]
        v,J,_,_=model.evaluate(x,obs);Jc=(J@B)/obs[:,4,None];r=(v-obs[:,3])/obs[:,4]
        for name in ['Taylor2_H2','R2_H2','R5_H7']:
            f=field(name,reg,directory,'fixture');rows=f.rows(0,obs)
            Df=features_jacobian(f,x)@B;delta=rows@Df-Jc;dr,dh=m.separate(delta)
            self.assertLess(np.max(abs(delta[:,m.OTHER])),1e-9)
            error=rows@f.features(x)-r
            np.testing.assert_allclose(error,dr[:,:11]@a+dh[:,:11]@a,atol=1e-9,rtol=0)
            np.testing.assert_allclose((Jc+dr+dh)@K,rows@features_jacobian(f,x)@L,atol=1e-9)


if __name__=='__main__':unittest.main()
