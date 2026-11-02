import json
import tempfile
from pathlib import Path
import unittest
import numpy as np
from .run import Direct, chart_shape_jacobian
from experiments.joint_rate_history_001.field import Field, build
from experiments.hysteresis_refinement_001.field import features_jacobian
from experiments.conditional_architecture_001.run import public_queries
from experiments.conditional_architecture_001.conditional import chart_amplitude_jacobian
from experiments.foster_campaign_001.backend import ROOT, prepare_c
from experiments.foster_feedback_001.estimator import Model
from experiments.foster_uncertainty_audit_001.conditional_packet import chart_from

class Controls(unittest.TestCase):
    def test_reference_derivatives_and_response_control(self):
        config=json.loads((ROOT/'experiments/foster_feedback_001/calibration.json').read_text());config['hysteresis_chart']='bounded'
        center,_,amplitudes=public_queries(config);a=amplitudes[1];shape=center*np.exp([.2,-.3,.4,-.2,.1]);x=chart_from(a,shape)
        k=np.arange(257);obs=np.column_stack((np.full(len(k),1/35),np.where((k//13)%2,.06,-.04),np.full(len(k),25.),3.7+.01*np.cos(k),np.full(len(k),.001)))
        with tempfile.TemporaryDirectory() as d:
            directory=Path(d);binary=build(directory/'response');model=Model(prepare_c(directory,35,config)[0],config)
            whole=Direct(model,a,shape);whole.advance(obs);parts=Direct(model,a,shape)
            for first in range(0,len(obs),11):parts.advance(obs[first:first+11])
            for key,v in whole.evaluate().items():np.testing.assert_allclose(v,parts.evaluate()[key],rtol=1e-8,atol=1e-5)
            D=chart_shape_jacobian(shape)
            for j in range(5):
                delta=np.zeros(5);delta[j]=1e-5
                fd=(chart_from(a,shape*np.exp(delta))-chart_from(a,shape*np.exp(-delta)))/2e-5
                np.testing.assert_allclose(fd,D[:,j],atol=1e-9,rtol=1e-9)
            for degree in (1,2):
                field=Field(config,center,1.,degree,binary);field.m=field.n;field.update(0,obs)
                J=field.root@features_jacobian(field,x)@np.column_stack((chart_amplitude_jacobian(a),D))
                r=field.residual(x);g=J.T@r
                for j in range(5):
                    delta=np.zeros(5);delta[j]=1e-4
                    fd=(field.nll(chart_from(a,shape*np.exp(delta)))-field.nll(chart_from(a,shape*np.exp(-delta))))/2e-4
                    self.assertAlmostEqual(fd,g[11+j],delta=.02+2e-5*abs(g[11+j]))
                P=J.T@J;e=np.linalg.eigvalsh(P)
                self.assertGreaterEqual(e[0],-1e-13*max(1,e[-1]))

if __name__=='__main__':unittest.main()
