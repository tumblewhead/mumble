import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from .conditional import FixedShape, chart_amplitude_jacobian
from .run import public_queries, differences
from .domain import instrument, LABELS
from experiments.foster_campaign_001.backend import ROOT, prepare_c
from experiments.foster_feedback_001.estimator import Model
from experiments.foster_uncertainty_audit_001.conditional_packet import make, chart_from, partition


class Architecture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config=json.loads((ROOT/'experiments/foster_feedback_001/calibration.json').read_text())
        cls.config['hysteresis_chart']='bounded'
        _,cls.shapes,cls.amplitudes=public_queries(cls.config)
        cls.temp=tempfile.TemporaryDirectory();cls.path=Path(cls.temp.name)
        cls.model=Model(prepare_c(cls.path,35,cls.config)[0],cls.config)

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def rows(self,n=96,thermal=False):
        i=np.arange(n)
        return np.column_stack((np.full(n,1/35),.05*np.where((i//13)%2,1.,-1.),
            25+8*np.sin(i/17) if thermal else np.full(n,25.),3.7+.01*np.cos(i),np.full(n,.001)))

    def accumulator(self):return FixedShape(self.config,self.shapes[0],'test')

    def test_chunk_composition_matches_direct_C_joint_likelihood(self):
        for thermal in (False,True):
            rows=self.rows(127,thermal)
            for shape in self.shapes:
                packet=FixedShape(self.config,shape,'test')
                for first in range(0,len(rows),7):packet.advance(first,rows[first:first+7],'test')
                for a in self.amplitudes:
                    candidate=packet.evaluate(a,shape)
                    v,J,end,_=self.model.evaluate(chart_from(a,shape),rows)
                    B=(J@chart_amplitude_jacobian(a))/rows[:,4,None];r=(v-rows[:,3])/rows[:,4]
                    nll=.5*r@r+np.log(rows[:,4]).sum()+len(rows)*.5*np.log(2*np.pi)
                    reference=(nll,B.T@r,B.T@B,partition(end)[0])
                    metrics=differences(candidate,reference,np.ones(11))
                    self.assertTrue(metrics['arithmetic_gate'],metrics)

    def test_gradient_matches_finite_difference_at_fixed_gamma_over_Q(self):
        packet=self.accumulator();packet.advance(0,self.rows(),'test')
        a=self.amplitudes[1].copy();g=packet.evaluate(a,self.shapes[0])[1]
        for k in range(11):
            step=1e-5*max(abs(a[k]),.001);plus=a.copy();minus=a.copy()
            plus[k]+=step;minus[k]-=step
            fd=(packet.evaluate(plus,self.shapes[0])[0]-packet.evaluate(minus,self.shapes[0])[0])/(2*step)
            self.assertAlmostEqual(fd,g[k],delta=3e-5*max(abs(g[k]),1))

    def test_chart_derivative_preserves_fixed_shapes(self):
        a=self.amplitudes[1];D=chart_amplitude_jacobian(a)
        for k in range(11):
            step=1e-6*max(abs(a[k]),.001);p=a.copy();m=a.copy();p[k]+=step;m[k]-=step
            numerical=(chart_from(p,self.shapes[0])-chart_from(m,self.shapes[0]))/(2*step)
            np.testing.assert_allclose(D[:,k],numerical,rtol=1e-7,atol=1e-7)

    def test_no_rate_reinterpretation(self):
        packet=self.accumulator()
        with self.assertRaisesRegex(ValueError,'reinterpreted'):packet.evaluate(self.amplitudes[0],self.shapes[1])

    def test_invalid_update_is_atomic(self):
        packet=self.accumulator();packet.advance(0,self.rows(16),'test');before=packet.snapshot()
        bad=self.rows(3);bad[-1,4]=0
        for first,rows,source in ((16,bad,'test'),(15,self.rows(3),'test'),(16,self.rows(3),'other')):
            with self.assertRaises(ValueError):packet.advance(first,rows,source)
            after=packet.snapshot();self.assertEqual(after.end,before.end)
            np.testing.assert_array_equal(after.root,before.root);np.testing.assert_array_equal(after.coeff,before.coeff)

    def test_qr_failure_is_atomic(self):
        packet=self.accumulator();before=packet.snapshot()
        with patch('numpy.linalg.qr',side_effect=np.linalg.LinAlgError('injected')):
            with self.assertRaises(np.linalg.LinAlgError):packet.advance(0,self.rows(),'test')
        self.assertEqual(packet.count,0);np.testing.assert_array_equal(packet.snapshot().root,before.root)

    def test_snapshot_cannot_mutate_history(self):
        packet=self.accumulator();packet.advance(0,self.rows(16),'test')
        before=packet.evaluate(self.amplitudes[0],self.shapes[0])[0]
        view=packet.snapshot();view.root[:]=42;view.shape[:]=42;view.coeff[:]=42
        self.assertEqual(before,packet.evaluate(self.amplitudes[0],self.shapes[0])[0])

    def test_rest_has_no_new_inverse_capacity_likelihood(self):
        packet=self.accumulator();rows=self.rows();rows[:,1]=0;packet.advance(0,rows,'test')
        _,g,P,_=packet.evaluate(self.amplitudes[0],self.shapes[0])
        self.assertEqual(g[4],0.);np.testing.assert_array_equal(P[4],np.zeros(11))

    def test_packed_retention_is_constant(self):
        packet=self.accumulator();before=packet.storage()
        for k in range(20):packet.advance(k*16,self.rows(16),'test')
        self.assertEqual(packet.storage(),before);self.assertEqual(before['packed_likelihood_B'],624)
        self.assertEqual(before['subtotal_B'],768)

    def test_public_inputs_not_borrowed(self):
        config=copy.deepcopy(self.config);shape=self.shapes[0].copy()
        packet=FixedShape(config,shape,'test');shape[:]=42;config['ocv_slope_V_per_SOC']=42
        packet.advance(0,self.rows(),'test')
        expected=make(self.rows(),self.shapes[0],self.config,'test')
        self.assertAlmostEqual(packet.evaluate(self.amplitudes[0],self.shapes[0])[0],expected.nll(self.amplitudes[0]),places=7)

    def test_instrumentation_only_changes_three_return_codes(self):
        directory=self.path/'instrumentation';instrument(directory)
        modified=(directory/'kernel.c').read_text()
        for code in LABELS:modified=modified.replace('return '+str(code)+';','return -3;')
        self.assertEqual(modified,(ROOT/'experiments/field_tangent_native_001/kernel.c').read_text())


if __name__=='__main__':unittest.main()
