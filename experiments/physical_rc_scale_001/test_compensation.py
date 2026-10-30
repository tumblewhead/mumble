import json
from pathlib import Path
import unittest
import numpy as np
from experiments.physical_rc_scale_001.combined_message import Message as Parent
from experiments.physical_rc_scale_001.compensation_message import Message,unchanged,c
from experiments.physical_rc_scale_001 import compensation_fitting as fit

HERE=Path(__file__).resolve().parent


class Controls(unittest.TestCase):
    def test_zero_extension_and_roundtrip(self):
        parent=Parent.restore(json.loads((HERE/'combined001/prefix32_combined_information_message.json').read_text())['posterior'])
        msg=Message.from_parent(parent)
        unchanged(parent,msg)
        x,_=parent.draw(256,103020)
        np.testing.assert_allclose(msg.logpdf(x),parent.logpdf(x),atol=2e-12,rtol=0)
        np.testing.assert_array_equal(msg.draw(256,103020)[0],x)
        msg.regions[0]['compensation'][:]=[.2,-.3]
        restored=Message.restore(msg.export())
        np.testing.assert_array_equal(msg.logpdf(x),restored.logpdf(x))
        self.assertEqual(msg.numeric_bytes,2576)

    def test_physical_compensation_identity(self):
        rng=np.random.default_rng(103021)
        a=rng.uniform(.2,.99,(200,3));v=rng.normal(0,.02,(200,3));F=a*v
        direct=a[:,2]*(.3*v[:,0]-.7*v[:,1])
        features=F[:,:2]*(a[:,2,None]/a[:,:2]-1)
        expanded=.3*F[:,0]-.7*F[:,1]+features@np.array([.3,-.7])
        np.testing.assert_allclose(direct,expanded,atol=2e-17,rtol=0)

    def test_extended_gradient(self):
        rng=np.random.default_rng(103022);n=80
        a=rng.uniform(.2,.99,(n,3));F=rng.normal(0,.02,(n,2))
        raw=np.column_stack([np.ones(n),F,F*(a[:,2,None]/a[:,:2]-1)])
        t=np.array([.01,.2,-.1,.3,-.4,np.log(.04),.3]);target=rng.normal(0,.02,n)
        _,g=fit.objective(t,raw,target,-.25*a[:,2],.25*a[:,2],a[:,2])
        for j in range(len(t)):
            d=np.zeros(len(t));d[j]=1e-6
            actual=(fit.objective(t+d,raw,target,-.25*a[:,2],.25*a[:,2],a[:,2])[0]-fit.objective(t-d,raw,target,-.25*a[:,2],.25*a[:,2],a[:,2])[0])/2e-6
            self.assertAlmostEqual(actual,g[j],delta=1e-7)


if __name__=='__main__':unittest.main()
