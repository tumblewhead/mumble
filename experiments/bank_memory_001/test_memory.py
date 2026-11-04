import tempfile
from pathlib import Path
import unittest
import numpy as np
from experiments.distinct_bank_integration_001.test_bank import BankTests
from experiments.distinct_bank_integration_001.run import MAP
from .field import Packed,SmallField

class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):BankTests.setUpClass.__func__(cls)
    @classmethod
    def tearDownClass(cls):BankTests.tearDownClass.__func__(cls)
    def make(self,rank=5,precision='float64',center=False):
        return SmallField(self.reg['config'],self.center,self.bins['rc'],self.bins['h'],MAP,'fixture',Path(self.temporary.name)/'qr',rank,precision,self.mean if center else None)
    def test_native_rejects_malformed_inputs(self):
        with self.assertRaises(ValueError):Packed(5,self.temporary.name,'float16')
        r=Packed(5,self.temporary.name)
        for rows in [np.ones(4),np.ones((3,4)),np.full((1,5),np.nan)]:
            with self.assertRaises(ValueError):r.update(rows)
        self.assertTrue(np.all(r.values==0))
    def test_packed_qr_matches_dense(self):
        rng=np.random.default_rng(7);rows=rng.normal(size=(500,46))
        for precision,tol in [('float64',1e-12),('float32',1e-5)]:
            r=Packed(46,self.temporary.name,precision);r.update(rows)
            np.testing.assert_allclose(r.dense().T@r.dense(),rows.T@rows,rtol=tol,atol=tol*500)
    def test_identity_projection_and_transport(self):
        f=self.make(13);full=BankTests.make(self);a=f.update(0,self.obs,return_rows=True);b=full.update(0,self.obs,return_rows=True)
        np.testing.assert_array_equal(a,b);np.testing.assert_array_equal(f.features(self.mean),full.features(self.mean))
        for x,y in zip(f.transported(self.mean),full.transported(self.mean)):np.testing.assert_array_equal(x,y)
    def test_centering_preserves_likelihood_and_derivatives(self):
        a=self.make(center=False);b=self.make(center=True);ar=a.update(0,self.obs,return_rows=True);br=b.update(0,self.obs,return_rows=True)
        x=self.mean+self.L@np.full(16,.01)
        np.testing.assert_allclose(ar@a.features(x),br@b.features(x),atol=1e-11)
        np.testing.assert_allclose(ar@a.features_jacobian(x),br@b.features_jacobian(x),atol=1e-11)
        delta=1e-6;J=np.column_stack([(b.features(x+np.eye(16)[i]*delta)-b.features(x-np.eye(16)[i]*delta))/(2*delta) for i in range(16)])
        np.testing.assert_allclose(J,b.features_jacobian(x),rtol=1e-5,atol=1e-7)

if __name__=='__main__':unittest.main()
