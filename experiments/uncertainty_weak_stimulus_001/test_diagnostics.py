import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from experiments.foster_campaign_001.backend import prepare_c
from experiments.foster_campaign_001.coordinates import prior
from experiments.foster_feedback_001.estimator import Model
from experiments.joint_rate_history_001.field import Field,build
from experiments.foster_uncertainty_audit_001.conditional_packet import partition
from experiments.slow_likelihood_diagnostic_001.numerics import Exact,Compressed,solve,predictive
from .diagnostics import ROOT,Parts,build_parts,partition_audit,attempt_starts,observed_directions,identity


class DiagnosticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.path=Path(cls.temp.name)
        cls.config=json.loads((ROOT/'experiments/foster_feedback_001/calibration.json').read_text())
        cls.config['hysteresis_chart']='bounded';cls.mean,cls.L=prior(cls.config)
        binary,_=prepare_c(cls.path,50,cls.config);cls.model=Model(binary,cls.config)
        cls.binary=build(cls.path/'field');cls.parts=Parts(build_parts(cls.path/'parts'),cls.model)
        i=np.arange(513)
        cls.obs=np.c_[np.where(i%17==0,0.,.02),np.where(i%31<16,.04,-.06),
                      25+5*np.sin(i/60),3.7+.01*np.sin(i),np.full(len(i),.004)]

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def test_component_derivatives_and_archived_model_parity(self):
        v,J,e,F,p,D=self.parts.evaluate(self.mean,self.obs)
        old=self.model.evaluate(self.mean,self.obs)
        for a,b in zip((v,J,e,F),old):np.testing.assert_array_equal(a,b)
        np.testing.assert_allclose(p.sum(axis=1),v,atol=2e-15,rtol=0)
        np.testing.assert_allclose(D.sum(axis=1),J,atol=2e-15,rtol=0)
        for j in range(16):
            delta=np.zeros(16);delta[j]=1e-5
            plus=self.parts.evaluate(self.mean+delta,self.obs)[4]
            minus=self.parts.evaluate(self.mean-delta,self.obs)[4]
            np.testing.assert_allclose((plus-minus)/2e-5,D[:,:,j],rtol=2e-5,atol=8e-10)

    def test_partition_gradient_retains_cross_terms(self):
        w=np.linspace(-.02,.02,16);x=self.mean+self.L@w
        audit=partition_audit(self.parts,self.model,self.obs,x,self.L,self.config,self.binary,chunk=37)
        field=Field(self.config,partition(self.mean)[1],1.,5,self.binary);field.update(0,self.obs)
        exact=Exact(self.model,self.obs,self.mean,self.L,chunk=79)
        compressed=Compressed(field,self.mean,self.L)
        difference=exact(w)[1]-compressed(w)[1]
        np.testing.assert_allclose(np.sum(audit['gradient_contributions'],axis=0),difference,rtol=1e-5,atol=5e-8)
        self.assertLess(audit['contribution_sum_max_abs_error'],2e-8)
        self.assertEqual(max(audit['instrumented_vs_archived_model_max_abs'].values()),0.)

    def test_chunked_joint_objective_dense(self):
        L=self.L.copy();L[5,0]=.02;w=np.linspace(-.02,.02,16)
        c,g,P,e,F=Exact(self.model,self.obs,self.mean,L,chunk=37)(w)
        v,J,ee,FF=self.model.evaluate(self.mean+L@w,self.obs)
        r=(v-self.obs[:,3])/self.obs[:,4];B=J@L/self.obs[:,4,None]
        np.testing.assert_allclose(c,.5*(w@w+r@r),rtol=2e-12)
        np.testing.assert_allclose(g,w+B.T@r,rtol=2e-11,atol=1e-8)
        np.testing.assert_allclose(P,np.eye(16)+B.T@B,rtol=2e-11,atol=1e-8)
        np.testing.assert_allclose(e,ee,atol=1e-12)
        np.testing.assert_allclose(F,FF,atol=1e-12)

    def test_rest_from_origin_has_no_Q_or_gamma_likelihood(self):
        obs=self.obs.copy();obs[:,1]=0
        obj=Exact(self.model,obs,self.mean,self.L,chunk=97)
        c,g,P,_,_=obj(np.zeros(16))
        for j in [5,14,15]:
            self.assertEqual(g[j],0.)
            np.testing.assert_array_equal(P[j],np.eye(16)[j])
            w=np.zeros(16);w[j]=.7
            self.assertAlmostEqual(obj(w)[0]-.5*w@w,c,places=9)

    def test_correlated_fixed_Q_profile_preserves_prior(self):
        rng=np.random.default_rng(8);A=rng.normal(size=(30,16));b=rng.normal(size=30)
        mean=self.mean;L=self.L.copy();L[5,0]=.025
        class Gaussian:
            def __init__(self):self.mean,self.root=mean,L
            def __call__(self,w):
                r=A@w-b
                return .5*(w@w+r@r),w+A.T@r,np.eye(16)+A.T@A,None,None
        obj=Gaussian();P=np.eye(16)+A.T@A;expected=np.linalg.solve(P,A.T@b)
        a=L[5];v=np.linalg.solve(P,a);target=mean[5]+.03
        fit=solve(obj,logq=target,start=expected)
        np.testing.assert_allclose(fit['w'],expected+v*(target-mean[5]-a@expected)/(a@v),atol=1e-12)
        for row in observed_directions(obj,expected,L):
            self.assertAlmostEqual(row['observed_curvature'],row['GN_curvature'],places=10)

    def test_joint_predictive_score_matches_dense(self):
        rng=np.random.default_rng(3);J=rng.normal(size=(9,16));v=rng.normal(size=9)
        obs=np.zeros((9,5));obs[:,3]=rng.normal(size=9);obs[:,4]=.2
        class Linear:
            def evaluate(self,x,o):return v,J,None,None
        got=predictive(Linear(),self.mean,self.L,obs)
        B=J@self.L/.2;r=(v-obs[:,3])/.2;cov=np.eye(9)+B@B.T
        expected=.5*(r@np.linalg.solve(cov,r)+np.linalg.slogdet(cov)[1])
        self.assertAlmostEqual(got['NLL_without_common_noise_constant'],expected,places=10)

    def test_failed_starts_cannot_win_objective_selection(self):
        class Bad:
            mean=np.zeros(16);root=np.eye(16)
            def __call__(self,w):return 0.,np.ones(16),np.eye(16),None,None
        best,records=attempt_starts(Bad(),[('bad',np.zeros(16))])
        self.assertIsNone(best);self.assertEqual(records[0]['diagnostic']['stop'],'no_descent')

    def test_changed_inputs_rejected_before_fitting_or_output(self):
        from .run import analyze
        for changed in ('observations.npy','messages.npz'):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as directory:
                case=Path(directory)/'case';case.mkdir();out=Path(directory)/'out'
                obs=case/'observations.npy';msg=case/'messages.npz'
                obs.write_bytes(b'original observations');msg.write_bytes(b'original joint message')
                (case/'regeneration.json').write_text(json.dumps(dict(status='validated',
                    observations=identity(obs),messages=identity(msg))))
                (case/changed).write_bytes(b'changed after regeneration')
                with self.assertRaisesRegex(ValueError,'changed observations/messages'):
                    analyze(case,out,None,None)
                self.assertFalse(out.exists())


if __name__=='__main__':unittest.main()
