import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from .representation import Coefficients
from experiments.hysteresis_refinement_001.field import build
from experiments.conditional_architecture_001.run import public_queries
from experiments.conditional_architecture_001.conditional import chart_amplitude_jacobian
from experiments.foster_campaign_001.backend import ROOT, prepare_c
from experiments.foster_feedback_001.estimator import Model
from experiments.foster_uncertainty_audit_001.conditional_packet import chart_from, partition


class Representation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.path=Path(cls.temp.name)
        cls.config=json.loads((ROOT/'experiments/foster_feedback_001/calibration.json').read_text());cls.config['hysteresis_chart']='bounded'
        cls.center,_,cls.amplitudes=public_queries(cls.config)
        cls.binary=build(cls.path/'response');cls.model=Model(prepare_c(cls.path,35,cls.config)[0],cls.config)

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def packet(self,degree=2,sparse=False):return Coefficients(self.config,self.center,self.binary,degree,sparse)
    def rows(self,n=143):
        k=np.arange(n)
        return np.column_stack((np.full(n,1/35),np.where((k//17)%2,.06,-.04),np.full(n,25.),3.7+.01*np.cos(k),np.full(n,.001)))

    def test_exact_node_matches_independent_C(self):
        rows=self.rows()
        for degree in (1,2):
            p=self.packet(degree);p.advance(0,rows,'fixture')
            for offset in range(p.n):
                t=p.nodes[(np.arange(5)+offset)%p.n];shape=self.center*np.exp(t)
                for a in self.amplitudes:
                    q=p.evaluate(a,shape);v,J,end,_=self.model.evaluate(chart_from(a,shape),rows)
                    B=(J@chart_amplitude_jacobian(a))/rows[:,4,None];r=(v-rows[:,3])/rows[:,4]
                    cost=.5*r@r+np.log(rows[:,4]).sum()+len(rows)*.5*np.log(2*np.pi)
                    self.assertAlmostEqual(q['nll'],cost,delta=1e-8*max(1,abs(cost)))
                    np.testing.assert_allclose(q['gradient_amplitude'],B.T@r,rtol=1e-8,atol=1e-5)
                    np.testing.assert_allclose(q['precision_amplitude'],B.T@B,rtol=1e-8,atol=1e-5)
                    np.testing.assert_allclose(q['end'],partition(end)[0],atol=1e-9,rtol=1e-9)

    def test_chunk_regrouping_and_sparse_projection(self):
        rows=self.rows();t=np.array([.1,-.2,.3,-.4,.5]);shape=self.center*np.exp(t)
        for sparse in (False,True):
            p=self.packet(sparse=sparse);p.advance(0,rows,'fixture')
            q=self.packet(sparse=sparse)
            for first in range(0,len(rows),7):q.advance(first,rows[first:first+7],'fixture')
            for key,value in p.evaluate(self.amplitudes[0],shape).items():
                np.testing.assert_allclose(value,q.evaluate(self.amplitudes[0],shape)[key],rtol=1e-8,atol=1e-5)
        dense=self.packet();dense.advance(0,rows,'fixture')
        for e,f in zip(dense.entries,p.entries):np.testing.assert_allclose(e['coeff'][f['mask']],f['coeff'],rtol=1e-10,atol=1e-7)

    def test_shape_gradient_finite_difference(self):
        p=self.packet();p.advance(0,self.rows(),'fixture');t=np.array([.2,-.3,.1,.4,-.2]);a=self.amplitudes[0]
        g=p.evaluate(a,self.center*np.exp(t))['gradient_shape']
        for j in range(5):
            delta=np.zeros(5);delta[j]=1e-4
            fd=(p.evaluate(a,self.center*np.exp(t+delta))['nll']-p.evaluate(a,self.center*np.exp(t-delta))['nll'])/2e-4
            self.assertAlmostEqual(fd,g[j],delta=.02+2e-5*abs(g[j]))

    def test_rest_no_inverse_capacity_information(self):
        rows=self.rows();rows[:,1]=0;p=self.packet();p.advance(0,rows,'fixture')
        q=p.evaluate(self.amplitudes[0],self.center)
        self.assertEqual(q['gradient_amplitude'][4],0)
        np.testing.assert_array_equal(q['precision_amplitude'][4],np.zeros(11))

    def test_invalid_update_and_domain_rejection(self):
        p=self.packet();rows=self.rows();p.advance(0,rows,'fixture');saved=p.evaluate(self.amplitudes[0],self.center)
        bad=rows.copy();bad[-1,4]=0
        for first,obs,source in [(len(rows),bad,'fixture'),(0,rows,'fixture'),(len(rows),rows,'other')]:
            with self.assertRaises(ValueError):p.advance(first,obs,source)
        self.assertEqual(p.count,len(rows))
        for k,v in saved.items():np.testing.assert_array_equal(v,p.evaluate(self.amplitudes[0],self.center)[k])
        outside=self.center.copy();outside[3]*=np.exp(-1.062915)
        with self.assertRaisesRegex(ValueError,'outside computational'):p.evaluate(self.amplitudes[0],outside)

    def test_coefficient_counts_and_fixed_retention(self):
        for degree,sparse,count in [(1,False,264),(2,False,640),(2,True,367)]:
            p=self.packet(degree,sparse);before=p.storage();self.assertEqual(before['coefficients_B'],count*8)
            p.advance(0,self.rows(),'fixture');self.assertEqual(before,p.storage())

if __name__=='__main__':unittest.main()
