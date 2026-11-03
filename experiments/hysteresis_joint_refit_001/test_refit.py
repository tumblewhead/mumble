import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import numpy as np
from .run import refit, control_parity
from .readouts import covariance_root, direct_trace, add_readouts
from experiments.hysteresis_mixed_completion_001 import run as engine
from experiments.hysteresis_sensitivity_basis_001.run import field
from experiments.foster_feedback_001.estimator import Model


class RefitTests(unittest.TestCase):
    def test_routing_preserves_object_and_arguments(self):
        fields={'TaylorRC_H2':object(),'TaylorRC_TaylorH2':object()}
        args=[object() for _ in range(4)]
        with patch('experiments.hysteresis_joint_refit_001.run.fit_prefix',return_value={'arms':{'direct':1,'R2_H2':2,'TaylorRC_TaylorH2':3}}) as call:
            result=refit(fields,*args)
        self.assertIs(call.call_args.args[0]['R2_H2'],fields['TaylorRC_H2'])
        self.assertEqual(call.call_args.args[1:],tuple(args))
        self.assertEqual(set(result['arms']),{'direct',*fields})

    def test_public_starts_budget_and_domain_gate(self):
        def solve(objective,start,max_rounds):
            return dict(w=start,x=start,root=np.eye(16),diagnostic={'stop':'max_rounds','cost':1.})
        with patch.object(engine,'solve',side_effect=solve) as call:
            _,report=engine.choose_fit(object())
        self.assertEqual(report['status'],'unresolved')
        self.assertEqual(len(call.call_args_list),2)
        for callargs,w in zip(call.call_args_list,[np.zeros(16),.05*(-1.)**np.arange(16)]):
            np.testing.assert_array_equal(callargs.kwargs['start'],w)
            self.assertEqual(callargs.kwargs['max_rounds'],60)
        class Objective:
            mean=np.zeros(16);root=np.eye(16)
            def __call__(self,w):raise AssertionError('objective called beyond support')
        class Gate:
            def features(self,x):raise ValueError('outside')
        with self.assertRaisesRegex(ValueError,'outside'):engine.CommonDomain(Objective(),Gate())(np.zeros(16))

    def test_qr_covariance_dense_and_weak_direction(self):
        rng=np.random.default_rng(45);J=rng.normal(size=(90,16));L=rng.normal(size=(16,16))
        C=covariance_root(J,L)
        expected=L@np.linalg.solve(np.eye(16)+J.T@J,L.T)
        np.testing.assert_allclose(C@C.T,expected,atol=2e-14,rtol=1e-12)
        J=np.diag(np.geomspace(1e-6,1e6,16));C=covariance_root(J,np.eye(16))
        np.testing.assert_allclose(C@C.T,np.diag(1/(1+np.diag(J)**2)),atol=1e-15,rtol=1e-12)

    def test_parity_detects_changed_selected_fit(self):
        fit=dict(status='converged',selected_start=0,selected=dict(w=[0.],x=[1.],root=[[2.]],diagnostic={'stop':'a'}))
        report={'arms':{k:copy.deepcopy(fit) for k in ['direct','TaylorRC_H2','R5_H7']}}
        old={'fits':{'arms':{k:copy.deepcopy(fit) for k in ['direct','Taylor2_H2','R5_H7']}}}
        control_parity(report,old)
        report['arms']['direct']['selected']['root']=[[2.001]]
        with self.assertRaises(ValueError):control_parity(report,old)

    def test_native_readout_consistency_and_unresolved_gate(self):
        directory=Path('experiments/rc_sensitivity_basis_001/full001')
        reg=json.loads((directory/'registration.json').read_text())
        binaries={k:Path('experiments/hysteresis_sensitivity_basis_001/build001')/k/'response.so' for k in ['collocation','derivative']}
        model=Model(directory/'backend_c/estimator.so',reg['config'])
        mean,L,center=map(np.asarray,[reg['prior_mean'],reg['prior_root'],reg['center']])
        k=np.arange(256);obs=np.c_[np.full(256,1/35),np.array([.12,0.,-.08])[k//17%3],np.full(256,25.),np.full(256,3.7),np.full(256,.001)]
        factory=lambda name:field(name,reg,directory,'test',binaries)
        f=factory('TaylorRC_TaylorH2');f.update(0,obs,'test')
        _,J,end,F=model.evaluate(mean,obs)
        root,e,D=direct_trace(model,obs,mean,L)
        np.testing.assert_allclose(root.T@root,((J@L)/obs[:,4,None]).T@((J@L)/obs[:,4,None]),rtol=1e-10,atol=1e-7)
        np.testing.assert_array_equal(e,end);np.testing.assert_array_equal(D,F)
        report={'arms':{name:dict(status='unresolved',selected=dict(x=mean.copy(),w=np.zeros(16),root=L.copy())) for name in ['direct','TaylorRC_TaylorH2']}}
        before=copy.deepcopy(report['arms'])
        add_readouts({'TaylorRC_TaylorH2':f},factory,model,obs,mean,L,center,report)
        for name in before:
            for key in ['x','w','root']:np.testing.assert_array_equal(before[name]['selected'][key],report['arms'][name]['selected'][key])
            self.assertEqual(report['QR_readouts'][name]['fit_comparison']['status'],'unresolved_candidate_or_reference')
            self.assertNotIn('forecasts',report['QR_readouts'][name])
        self.assertLess(abs(report['QR_readouts']['TaylorRC_TaylorH2']['Q_same_anchor_SD_ratio']-1),1e-8)


if __name__=='__main__':unittest.main()
