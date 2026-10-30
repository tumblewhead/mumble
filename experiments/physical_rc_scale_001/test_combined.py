import json
from pathlib import Path
import unittest
import numpy as np
from experiments.physical_rc_scale_001 import combined_fitting as fit
from experiments.physical_rc_scale_001.combined_message import Message,c
from experiments.physical_rc_scale_001.message import Message as Physical
from experiments.natural_hysteresis_001.message import Message as Parent

HERE=Path(__file__).resolve().parent
CONFIG=json.loads((HERE/'combined_plan.json').read_text())['optimizer']


class Controls(unittest.TestCase):
    def test_all_derivatives(self):
        u=np.linspace(-1,1,100);a=-np.expm1(-np.exp(u))
        design=np.column_stack([np.ones(100),u,u*u]);y=.03*np.sin(3*u)
        t=np.array([.03,.01,-.005,np.log(.07),.4])
        lo,hi=-.25*a,.25*a
        _,g=fit.objective(t,design,y,lo,hi,a)
        for j in range(len(t)):
            d=np.zeros(len(t));d[j]=1e-6
            actual=(fit.objective(t+d,design,y,lo,hi,a)[0]-fit.objective(t-d,design,y,lo,hi,a)[0])/2e-6
            self.assertAlmostEqual(actual,g[j],delta=1e-7)

    def test_both_density_endpoints_and_schema(self):
        parent=Parent.restore(json.loads((HERE.parent/'natural_hysteresis_001/attempt001/prefix8_natural_refit_message.json').read_text())['posterior'])
        x,_=parent.draw(128,103010)
        msg=Message.from_parent(parent)
        self.assertEqual(msg.numeric_bytes,2544)
        np.testing.assert_allclose(msg.logpdf(x),parent.logpdf(x),atol=2e-12,rtol=0)
        physical=Physical.from_parent(parent,(9,10,11))
        for reg in msg.regions:
            reg['mix'][:]=1.
            reg['shape'][9:12]+=np.log(fit.AREF)
        np.testing.assert_allclose(msg.logpdf(x),physical.logpdf(x),atol=2e-11,rtol=0)
        restored=Message.restore(msg.export())
        np.testing.assert_array_equal(msg.logpdf(x),restored.logpdf(x))

    def test_interior_recovery(self):
        rng=np.random.default_rng(103011);n=12000
        u=rng.uniform(-1,1,n);a=-np.expm1(-np.exp(u))
        design=np.column_stack([np.ones(n),u]);beta=np.array([.01,.005]);s=.04;fraction=.4
        sd=s/np.sqrt(1+fraction*((fit.AREF/a)**2-1));mu=design@beta
        lo,hi=-.25*a,.25*a
        z,_=c.v.truncated_standard_draw((lo-mu)/sd,(hi-mu)/sd,rng)
        y=mu+sd*z
        b,logsd,mix,diag=fit.fit(design,y,lo,hi,a,np.zeros(2),np.log(.05),CONFIG)
        self.assertEqual(diag['status'],'constrained_gradient_tolerance_met')
        np.testing.assert_allclose(b,beta,atol=.002,rtol=0)
        self.assertAlmostEqual(np.exp(logsd),s,delta=.002)
        self.assertAlmostEqual(mix,fraction,delta=.06)

    def test_constraint_residual_and_nonconvergence(self):
        self.assertEqual(fit.residual(np.array([0.,0.]),np.array([0.,1.])),0.)
        self.assertEqual(fit.residual(np.array([0.,1.]),np.array([0.,-1.])),0.)
        self.assertEqual(fit.residual(np.array([0.,0.]),np.array([0.,-1.])),1.)
        n=40;a=np.linspace(.3,.9,n)
        _,_,_,diag=fit.fit(np.ones((n,1)),np.linspace(.01,.04,n),-.25*a,.25*a,a,np.zeros(1),np.log(.03),dict(CONFIG,iterations_per_conditional=0))
        self.assertEqual(diag['status'],'iteration_limit')


if __name__=='__main__':unittest.main()
