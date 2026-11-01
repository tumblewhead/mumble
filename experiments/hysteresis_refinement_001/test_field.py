import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from experiments.foster_campaign_001.coordinates import prior
from experiments.foster_campaign_001.field_backend import transported as old_transport
from experiments.joint_rate_history_001.field import Field,build as old_build
from experiments.foster_uncertainty_audit_001.conditional_packet import partition
from experiments.slow_likelihood_diagnostic_001.numerics import features_jacobian as old_jac
from .field import MixedField,build,features_jacobian,transported,Compressed


class MixedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();d=Path(cls.tmp.name)
        cls.cfg=json.loads(Path('experiments/foster_feedback_001/calibration.json').read_text());cls.cfg['hysteresis_chart']='bounded'
        cls.mean,cls.L=prior(cls.cfg);cls.center=partition(cls.mean)[1]
        cls.binary=build(d/'mixed');cls.old=old_build(d/'old')
        i=np.arange(257)
        cls.obs=np.c_[np.where(i%13==0,0.,.02),np.where(i%37<18,.04,-.06),25+7*np.sin(i/33),3.7+.01*np.sin(i),np.full(len(i),.004)]
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def field(self,degree):return MixedField(self.cfg,self.center,1.,degree,self.binary)

    def test_degree5_matches_original_rows_features_gradient_transport(self):
        a=self.field(5);b=Field(self.cfg,self.center,1.,5,self.old)
        ar=a.update(0,self.obs,return_rows=True);br=b.update(0,self.obs,return_rows=True)
        for x,y in ((ar,br),(a.state,b.state),(a.root,b.root),(a.features(self.mean),b.features(self.mean)),
                    (features_jacobian(a,self.mean),old_jac(b,self.mean))):np.testing.assert_array_equal(x,y)
        for x,y in zip(transported(a,self.mean),old_transport(b,self.mean)):np.testing.assert_array_equal(x,y)

    def test_outgoing_amplitude_matches_joint_chart_transport(self):
        from experiments.foster_uncertainty_audit_001.conditional_packet import partition
        for degree in (5,6,7):
            f=self.field(degree);f.update(0,self.obs)
            np.testing.assert_allclose(f.outgoing(self.mean),partition(transported(f,self.mean)[0])[0],rtol=2e-14,atol=1e-14)

    def test_nonhysteresis_rows_unchanged(self):
        rows=[self.field(d).rows(0,self.obs) for d in (5,6,7,8)]
        for r in rows[1:]:
            np.testing.assert_array_equal(r[:,:39],rows[0][:,:39])
            np.testing.assert_array_equal(r[:,-1],rows[0][:,-1])

    def test_analytic_features_and_transport(self):
        for degree in (6,7):
            f=self.field(degree);f.rows(0,self.obs);x=self.mean+self.L@np.linspace(-.1,.1,16)
            J=features_jacobian(f,x);_,D=transported(f,x)
            for j in range(16):
                e=np.eye(16)[j]*1e-5
                np.testing.assert_allclose((f.features(x+e)-f.features(x-e))/2e-5,J[:,j],rtol=2e-6,atol=2e-8)
                np.testing.assert_allclose((transported(f,x+e)[0]-transported(f,x-e)[0])/2e-5,D[:,j],rtol=2e-5,atol=2e-8)

    def test_chronology_and_invalid_input_transaction(self):
        f=self.field(7);f.update(0,self.obs[:16]);state=f.state.copy();root=f.root.copy()
        for first,rows in [(0,self.obs[:16]),(17,self.obs[:16]),(16,self.obs[:16]*np.nan)]:
            with self.assertRaises(ValueError):f.update(first,rows)
            np.testing.assert_array_equal(f.state,state);np.testing.assert_array_equal(f.root,root);self.assertEqual(f.count,16)

    def test_chunked_evidence_joint_equivalence(self):
        a=self.field(7);b=self.field(7);a.update(0,self.obs)
        for i in range(0,len(self.obs),31):b.update(i,self.obs[i:i+31])
        np.testing.assert_array_equal(a.state,b.state)
        w=np.linspace(-.03,.03,16)
        for x,y in zip(Compressed(a,self.mean,self.L)(w)[:3],Compressed(b,self.mean,self.L)(w)[:3]):np.testing.assert_allclose(x,y,atol=2e-7,rtol=5e-12)

    def test_rest_does_not_create_Q_information(self):
        f=self.field(7);o=self.obs.copy();o[:,1]=0;f.update(0,o)
        c,g,P,_,_=Compressed(f,self.mean,self.L)(np.zeros(16))
        for j in (5,14,15):
            self.assertAlmostEqual(g[j],0.,places=10)
            np.testing.assert_allclose(P[j],np.eye(16)[j],atol=1e-10)

if __name__=='__main__':unittest.main()
