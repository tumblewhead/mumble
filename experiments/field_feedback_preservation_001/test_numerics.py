import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from experiments.foster_campaign_001.coordinates import prior
from experiments.foster_uncertainty_audit_001.conditional_packet import partition
from experiments.joint_rate_history_001.field import Field,build
from experiments.slow_likelihood_diagnostic_001.numerics import Compressed
from .numerics import Tangent,polish_stationary


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.path=Path(cls.tmp.name)
        root=Path(__file__).resolve().parents[2]
        cls.cfg=json.loads((root/'experiments/foster_feedback_001/calibration.json').read_text())
        cls.cfg['hysteresis_chart']='bounded';cls.mean,cls.L=prior(cls.cfg)
        cls.probe=build(cls.path/'field')

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def field(self):return Field(self.cfg,partition(self.mean)[1],1.,5,self.probe)

    def obs(self,n):
        i=np.arange(n);return np.c_[np.full(n,.02),np.where(i%21<10,.03,-.03),25+4*np.sin(i/50),3.7+.01*np.sin(i),np.full(n,.004)]

    def test_tangent_matches_independent_batch_linearized_least_squares(self):
        f=self.field();o=self.obs(257);f.update(0,o[:128]);obj=Compressed(f,self.mean,self.L)
        w=np.linspace(-.02,.02,16);t=Tangent(obj,w,128)
        old_r=f.root@t.phi;old_B=f.root@t.J
        rows=f.update(128,o[128:],return_rows=True);t.update(128,rows);fit=t.query()
        A=np.vstack([np.eye(16),old_B,rows@t.J]);b=-np.r_[w,old_r,rows@t.phi]
        delta=np.linalg.lstsq(A,b,rcond=None)[0]
        np.testing.assert_allclose(fit['w'],w+delta,rtol=1e-10,atol=1e-10)
        expected=self.L@np.linalg.solve(A.T@A,self.L.T)
        np.testing.assert_allclose(fit['root']@fit['root'].T,expected,rtol=1e-8,atol=1e-13)

    def test_linearized_evidence_is_partition_invariant(self):
        f=self.field();o=self.obs(257);f.update(0,o[:128]);obj=Compressed(f,self.mean,self.L)
        a=Tangent(obj,np.zeros(16),128);b=Tangent(obj,np.zeros(16),128)
        rows=f.update(128,o[128:],return_rows=True);a.update(128,rows)
        for first in range(0,len(rows),7):b.update(first+128,rows[first:first+7])
        np.testing.assert_allclose(a.query()['w'],b.query()['w'],atol=1e-10,rtol=1e-10)
        np.testing.assert_allclose(a.P,b.P,rtol=2e-15,atol=1e-8)

    def test_replayed_or_skipped_rows_rejected_without_mutation(self):
        f=self.field();obj=Compressed(f,self.mean,self.L);t=Tangent(obj,np.zeros(16),0)
        rows=f.update(0,self.obs(16),return_rows=True);t.update(0,rows)
        P,g=t.P.copy(),t.g.copy()
        for first in [0,32]:
            with self.assertRaisesRegex(ValueError,'chronology'):t.update(first,rows)
        np.testing.assert_array_equal(t.P,P);np.testing.assert_array_equal(t.g,g)

    def test_source_and_readout_boundary_guards(self):
        f=self.field();obj=Compressed(f,self.mean,self.L)
        with self.assertRaisesRegex(ValueError,'anchor/history'):Tangent(obj,np.zeros(16),16)
        t=Tangent(obj,np.zeros(16),0);rows=f.update(0,self.obs(16),return_rows=True)
        with self.assertRaisesRegex(ValueError,'readout/history'):t.query()
        with self.assertRaisesRegex(ValueError,'ownership'):t.update(0,rows,source='other_source')
        self.assertEqual(t.count,0)
        t.update(0,rows,source=f.source);self.assertEqual(t.count,16)
        self.assertTrue(np.isfinite(t.query()['end']).all())

    def test_rest_null_capacity_information_is_preserved(self):
        f=self.field();t=Tangent(Compressed(f,self.mean,self.L),np.zeros(16),0)
        obs=self.obs(1024);obs[:,1]=0
        rows=f.update(0,obs,return_rows=True);t.update(0,rows);r=t.query()
        self.assertAlmostEqual(r['x'][5],self.mean[5],places=10)
        self.assertAlmostEqual(np.linalg.norm(r['root'][5]),np.linalg.norm(self.L[5]),places=10)

    def test_observed_newton_solves_nonquadratic_stationarity(self):
        expected=np.linspace(.1,.3,16);b=expected+10*expected**3
        class Objective:
            mean=np.zeros(16);root=np.eye(16)
            def __call__(self,w):
                return float((.5*w*w+2.5*w**4-b*w).sum()),w+10*w**3-b,np.eye(16),w,np.eye(16)
        fit=polish_stationary(Objective(),np.zeros(16))
        self.assertEqual(fit['stop'],'observed_decrement_at_cost_roundoff')
        np.testing.assert_allclose(fit['w'],expected,atol=1e-8)
        self.assertGreater(fit['Hessian_min_eigenvalue'],0)


if __name__=='__main__':unittest.main()
