import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
from numpy.polynomial.chebyshev import chebvander
from .basis import CompletedField
from experiments.response_basis_attribution_001.basis import BasisField
from experiments.conditional_architecture_001.run import public_queries
from experiments.foster_campaign_001.backend import ROOT
from experiments.foster_uncertainty_audit_001.conditional_packet import chart_from
from experiments.hysteresis_refinement_001.field import build, features_jacobian, transported


class Completion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(); cls.binary=build(Path(cls.tmp.name)/'response')
        cls.config=json.loads((ROOT/'experiments/foster_feedback_001/calibration.json').read_text())
        cls.config['hysteresis_chart']='bounded'
        cls.center,_,cls.amplitudes=public_queries(cls.config)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def rows(self):
        k=np.arange(257)
        return np.column_stack((np.full(257,1/35),np.where((k//19)%2,.06,-.04),
                                np.full(257,25.),3.7+.01*np.sin(k),np.full(257,.001)))
    def field(self,kind):return CompletedField(self.config,self.center,self.binary,kind)
    def test_projection_and_central_value_identity(self):
        td=BasisField(self.config,self.center,self.binary); full=self.field('tensor'); single=self.field('c22')
        T=chebvander(0.,2)[0];rng=np.random.default_rng(92)
        for _ in range(30):
            grid=rng.normal(size=9)
            center=lambda f: np.array([T[i]*T[j] for i,j in f.pairs])@(f.p2@grid)
            self.assertAlmostEqual(center(full),grid[4],delta=1e-13)
            self.assertAlmostEqual(center(single),grid[4],delta=1e-13)
            self.assertAlmostEqual(center(td)-grid[4],-(full.p2@grid)[8],delta=1e-13)
    def test_derivatives_and_native_transport(self):
        a=self.amplitudes[1];s=self.center*np.exp([.1,-.2,.15,.3,-.25]);x=chart_from(a,s)
        for kind in ['c22','tensor']:
            f=self.field(kind);f.update(0,self.rows());D=features_jacobian(f,x)
            end,F=transported(f,x)
            for j in range(16):
                xp=x.copy();xm=x.copy();xp[j]+=1e-6;xm[j]-=1e-6
                np.testing.assert_allclose((f.features(xp)-f.features(xm))/2e-6,D[:,j],rtol=2e-6,atol=2e-7)
                np.testing.assert_allclose((transported(f,xp)[0]-transported(f,xm)[0])/2e-6,F[:,j],rtol=2e-6,atol=2e-7)
    def test_joint_factor_and_chunk_order(self):
        obs=self.rows();a=self.amplitudes[1];s=self.center*np.exp([.1,-.2,.15,.3,-.25]);x=chart_from(a,s)
        for kind in ['c22','tensor']:
            f=self.field(kind);g=self.field(kind);rows=f.update(0,obs,return_rows=True)
            for first in range(0,len(obs),17):g.update(first,obs[first:first+17])
            np.testing.assert_allclose(f.root.T@f.root,rows.T@rows,rtol=1e-10,atol=1e-5)
            np.testing.assert_allclose(f.evaluate(a,s)['end'],g.evaluate(a,s)['end'],atol=1e-12)
            self.assertAlmostEqual(f.nll(x),g.nll(x),delta=1e-6)
            # Cross-H/RC evidence remains present, not partitioned into independent roots.
            gram=rows.T@rows; self.assertGreater(np.linalg.norm(gram[3:21,21:-1]),1.)
    def test_domain_atomicity_and_storage(self):
        for kind,width,packed,subtotal in [('c22',36,5328,5736),('tensor',40,6560,6968)]:
            f=self.field(kind);obs=self.rows();f.update(0,obs)
            root=f.root.copy();state=f.state.copy();bad=obs.copy();bad[-1,4]=0.
            for first,rows,source in [(0,obs,None),(257,bad,None),(257,obs,'wrong')]:
                with self.assertRaises(ValueError):f.update(first,rows,source)
                np.testing.assert_array_equal(f.root,root);np.testing.assert_array_equal(f.state,state)
            shape=self.center.copy();shape[3]*=np.exp(1.001)
            with self.assertRaisesRegex(ValueError,'outside computational'):f.evaluate(self.amplitudes[0],shape)
            self.assertEqual(f.width,width);self.assertEqual(f.storage()['packed_factor_B'],packed)
            self.assertEqual(f.storage()['numeric_factor_response_domain_scalars_B'],subtotal)


if __name__=='__main__':unittest.main()
