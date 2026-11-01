import unittest
import numpy as np
from .diagnostic import soc_gaussian_moments,unpack

class Controls(unittest.TestCase):
    def test_gaussian_moments_against_quadrature(self):
        # Independent 2-D Gaussian quadrature includes correlated z0/logQ.
        nodes,weights=np.polynomial.hermite.hermgauss(24)
        mu=np.zeros(16);mu[0]=.6;mu[5]=-2.8
        C=np.zeros((16,16));C[0,0]=.003;C[5,5]=.02;C[0,5]=C[5,0]=-.003
        B=np.linalg.cholesky(C[np.ix_([0,5],[0,5])]);values=[];probs=[]
        for i,x in enumerate(nodes):
            for j,y in enumerate(nodes):
                z,q=mu[[0,5]]+B@(np.sqrt(2)*np.array([x,y]))
                values.append(z-.01*np.exp(-q));probs.append(weights[i]*weights[j]/np.pi)
        values=np.array(values);probs=np.array(probs);m=probs@values;v=probs@((values-m)**2)
        m2,v2=soc_gaussian_moments(mu,C,.01)
        self.assertAlmostEqual(m,m2,places=14);self.assertAlmostEqual(v,v2,places=14)
        self.assertEqual(soc_gaussian_moments(mu,C,0),(mu[0],C[0,0]))

    def test_native_packing_and_origin_covariance(self):
        rng=np.random.default_rng(45);A=rng.normal(size=(80,16));P=np.eye(16)+A.T@A
        R=np.linalg.cholesky(P).T;full=np.zeros((17,17));full[:16,:16]=R;full[16,16]=1
        anchor=rng.normal(size=16);data=np.r_[full[np.triu_indices(17)],anchor].view(np.uint8)
        restored,w=unpack(data);np.testing.assert_array_equal(restored,full);np.testing.assert_array_equal(w,anchor)
        inverse=np.linalg.solve(restored[:16,:16],np.eye(16))
        np.testing.assert_allclose(inverse@inverse.T,np.linalg.inv(P),rtol=2e-14,atol=1e-16)

if __name__=='__main__':unittest.main()
