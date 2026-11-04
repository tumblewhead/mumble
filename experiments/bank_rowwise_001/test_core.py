import unittest
from pathlib import Path
import numpy as np
from experiments.bank_memory_001.test_memory import Tests as Fixture
from experiments.distinct_bank_integration_001.field import Compressed
from experiments.slow_likelihood_diagnostic_001.numerics import solve
from .native import Native
class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):Fixture.setUpClass.__func__(cls)
 @classmethod
 def tearDownClass(cls):Fixture.tearDownClass.__func__(cls)
 def make(self):return Fixture.make(self,rank=3)
 def native(self,f):return Native(f,self.mean,self.L,Path(self.temporary.name)/'native')
 def test_features_transport_and_scalar_covariance(self):
  f=self.make();f.update(0,self.obs);n=self.native(f)
  for w in [np.zeros(16),np.linspace(-.02,.02,16)]:
   x=self.mean+self.L@w;values,J=zip(*(n.row(w,k) for k in range(34)))
   np.testing.assert_allclose(values,f.features(x),rtol=1e-10,atol=1e-9)
   np.testing.assert_allclose(J,f.features_jacobian(x),rtol=1e-9,atol=1e-9)
   n.initialize(w);q=n.query();end,D=f.transported(self.mean+self.L@q['w']);np.testing.assert_allclose(q['end'],end,atol=1e-10)
   B=f.root@f.features_jacobian(x)@self.L;P=np.eye(16)+B.T@B
   covariance=D@self.L@np.linalg.solve(P,self.L.T@D.T)
   np.testing.assert_allclose(q['endpoint_root']@q['endpoint_root'].T,covariance,rtol=1e-7,atol=1e-9)
   for k in range(16):
    v,var=n.scalar(k);self.assertAlmostEqual(v,end[k],places=10);self.assertAlmostEqual(var,covariance[k,k],places=8)
 def test_native_input_validation_and_scalar_first(self):
  f=self.make();n=self.native(f)
  for bad in [np.zeros(15),np.zeros((16,1)),np.full(16,np.nan)]:
   for method in [n.initialize,n.fit]:
    with self.assertRaises(ValueError):method(bad)
  for bad in [np.zeros((2,33)),np.zeros(34),np.full((1,34),np.nan)]:
   with self.assertRaises(ValueError):n.update(bad)
  n.initialize(np.zeros(16,dtype=np.float32));rows=f.update(0,self.obs,return_rows=True);n.update(rows)
  v,var=n.scalar(0);q=n.query();self.assertAlmostEqual(v,q['end'][0],places=13);self.assertAlmostEqual(var,sum(q['endpoint_root'][0]**2),places=13)
 def test_scalar_refuses_invalid_h_endpoint_even_for_Q(self):
  f=self.make();n=self.native(f);n.initialize(np.zeros(16))
  f.state[27]=2.
  with self.assertRaises(ValueError):n.scalar(5)
 def test_fit_matches_dense(self):
  f=self.make();f.update(0,self.obs);n=self.native(f);a=n.fit(np.zeros(16));b=solve(Compressed(f,self.mean,self.L));print('fit',a['diagnostic'],b['diagnostic'])
  self.assertIn(a['diagnostic']['stop'],('gradient','GN_decrement_at_cost_roundoff'))
  np.testing.assert_allclose(a['w'],b['w'],rtol=1e-4,atol=1e-5)
 def test_incremental_factor_and_no_dense_dependency(self):
  f=self.make();n=self.native(f);n.initialize(np.zeros(16));rows=f.update(0,self.obs,return_rows=True);n.update(rows)
  q=n.query();B=rows@f.features_jacobian(self.mean)@self.L;r=rows@f.features(self.mean)
  np.testing.assert_allclose(q['w'],np.linalg.solve(np.eye(16)+B.T@B,-B.T@r),rtol=1e-7,atol=1e-8)
if __name__=='__main__':unittest.main()
