import json
from pathlib import Path
import unittest
import numpy as np
from experiments.physical_rc_scale_001 import fitting
from experiments.physical_rc_scale_001.message import Message, unchanged, c, log_mass
from experiments.natural_hysteresis_001.message import Message as Parent

HERE=Path(__file__).resolve().parent
CONFIG=json.loads((HERE/'plan.json').read_text())['optimizer']


class Controls(unittest.TestCase):
    def test_scaled_density_and_support(self):
        a=np.array([.2,.4,.7,.9])
        F=np.array([-.02,.03,-.04,.12])
        mu=np.array([.01,-.02,.03,.02])
        s=.08
        logF=-.5*((F-mu)/(a*s))**2-np.log(a*s)-.5*c.old.LOG2PI-log_mass((-.25*a-mu)/(a*s),(.25*a-mu)/(a*s))
        physical=-.5*((F/a-mu/a)/s)**2-np.log(s)-.5*c.old.LOG2PI-log_mass((-.25-mu/a)/s,(.25-mu/a)/s)-np.log(a)
        np.testing.assert_allclose(logF,physical,atol=2e-14,rtol=0)

    def test_all_objective_derivatives(self):
        u=np.linspace(-1,1,80)
        a=-np.expm1(-np.exp(u))
        design=np.column_stack([np.ones(80),u,u*u])/a[:,None]
        y=.03*np.sin(2*u)
        theta=np.array([.02,.01,-.005,np.log(.08)])
        lo,hi=np.full(80,-.25),np.full(80,.25)
        _,g=fitting.objective(theta,design,y,lo,hi)
        for j in range(len(theta)):
            d=np.zeros(len(theta));d[j]=1e-6
            actual=(fitting.objective(theta+d,design,y,lo,hi)[0]-fitting.objective(theta-d,design,y,lo,hi)[0])/2e-6
            self.assertAlmostEqual(actual,g[j],delta=1e-7)

    def test_physical_scale_recovery(self):
        rng=np.random.default_rng(103001)
        u=rng.uniform(-1,1,12000)
        a=-np.expm1(-np.exp(u))
        design=np.column_stack([np.ones(len(u)),u])/a[:,None]
        expected=np.array([.03,.01]);s=.08
        mu=design@expected
        standard,_=c.v.truncated_standard_draw((-.25-mu)/s,(.25-mu)/s,rng)
        target=mu+s*standard
        beta,logsd,diag=fitting.fit(design,target,np.full(len(u),-.25),np.full(len(u),.25),'bounded_likelihood',CONFIG)
        self.assertEqual(diag['status'],'gradient_tolerance_met')
        np.testing.assert_allclose(beta,expected,atol=.0025,rtol=0)
        self.assertAlmostEqual(np.exp(logsd),s,delta=.002)
        # Conditional samples scaled by a preserve the physical variance law.
        F=a*target
        np.testing.assert_allclose(F/a,target,atol=3e-17,rtol=0)

    def test_nonconstant_intercept_without_extra_feature(self):
        u=np.linspace(-1,1,100)
        a=-np.expm1(-np.exp(u))
        raw=np.column_stack([np.ones(100),u])/a[:,None]
        y=raw@np.array([.02,.01])+.005*np.sin(7*u)
        design,target,lo,hi,theta,transform,center,scale=fitting.prepare(raw,y,np.full(100,-.25),np.full(100,.25))
        self.assertEqual(design.shape,raw.shape)
        self.assertEqual(center,0.)
        beta=scale*np.linalg.solve(transform,theta[:-1])
        np.testing.assert_allclose(raw@beta,scale*(design@theta[:-1]),atol=2e-17,rtol=0)

    def test_nonconvergence_explicit(self):
        raw=np.ones((40,1));y=np.linspace(.01,.249,40)
        _,_,diag=fitting.fit(raw,y,np.full(40,-.25),np.full(40,.25),'bounded_likelihood',dict(CONFIG,iterations_per_conditional=0))
        self.assertEqual(diag['status'],'iteration_limit')

    def test_baseline_roundtrip_and_scale_draw(self):
        p=HERE.parent/'natural_hysteresis_001/attempt001/prefix8_natural_refit_message.json'
        parent=Parent.restore(json.loads(p.read_text())['posterior'])
        baseline=Message.from_parent(parent)
        unchanged(parent,baseline)
        x,_=parent.draw(128,103002)
        xx,_=baseline.draw(128,103002)
        np.testing.assert_array_equal(x,xx)
        np.testing.assert_array_equal(parent.logpdf(x),baseline.logpdf(x))
        msg=Message.from_parent(parent,(11,))
        for reg in msg.regions:
            c.coefficients(reg,11)[:]=0.
            reg['shape'][11]=np.log(.04)
        unchanged(parent,msg)
        y,_=msg.draw(8192,103003)
        self.assertAlmostEqual(y[:,14].std(),.04,delta=.002)
        restored=Message.restore(msg.export())
        np.testing.assert_array_equal(msg.logpdf(y[:16]),restored.logpdf(y[:16]))
        with self.assertRaises(c.old.Unavailable):
            Message.restore(parent.export())


if __name__=='__main__':
    unittest.main()
