import unittest,ctypes as C,subprocess,math
from pathlib import Path
import numpy as np
from experiments.bank_memory_001.test_memory import Tests as Fixture
from experiments.bank_rowwise_001.native import Native as Reference,ptr,D
from .native import Native,Packed48,CardinalMap,projected_coefficients

class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):Fixture.setUpClass.__func__(cls)
 @classmethod
 def tearDownClass(cls):Fixture.tearDownClass.__func__(cls)
 def make(self):return Fixture.make(self,rank=3)
 def candidate(self,f,bits=64,math='tiny',map='cardinal'):
  return Native(f,self.mean,self.L,Path(self.temporary.name)/'candidate',math,map,True,bits)
 def test_stream_factor_transport_and_covariance(self):
  for bits in (64,48):
   f=self.make();ref=self.make();n=self.candidate(f,bits);n.initialize(np.zeros(16));n.advance(0,self.obs);ref.update(0,self.obs)
   np.testing.assert_allclose(f.rc_free,ref.rc_free,atol=1e-14,rtol=1e-13)
   np.testing.assert_allclose(f.rc_forced,ref.rc_forced,atol=1e-14,rtol=1e-13)
   np.testing.assert_array_equal(f.state[18:],ref.state[18:])
   gram=ref.root.T@ref.root;np.testing.assert_allclose(f.root.T@f.root,gram,rtol=2e-9,atol=1e-4)
   q=n.query();x=self.mean+self.L@q['w'];end,j=f.transported(x)
   np.testing.assert_allclose(q['end'],end,rtol=1e-10,atol=1e-12)
   for w in (np.zeros(16),np.linspace(-.1,.1,16)):
    x=self.mean+self.L@w;v,d=zip(*(n.row(w,k) for k in range(34)))
    np.testing.assert_allclose(v,f.features(x),rtol=1e-10,atol=1e-12);np.testing.assert_allclose(d,f.features_jacobian(x),rtol=1e-10,atol=1e-12)
   fit=n.fit(q['w']);self.assertIn(fit['diagnostic']['stop'],('gradient','GN_decrement_at_cost_roundoff'))
   n.initialize(fit['w']);q=n.query()
   for i in range(16):
    v,var=n.scalar(i);np.testing.assert_allclose([v,var],[q['end'][i],sum(q['endpoint_root'][i]**2)],rtol=1e-10,atol=1e-14)
 def test_partial_failure_is_permanent_quarantine(self):
  f=self.make();n=self.candidate(f,48);n.initialize(np.zeros(16));rows=self.obs[:2].copy();rows[1,4]=0
  with self.assertRaises(ValueError):n.advance(0,rows)
  self.assertFalse(n.context.qr.lease.valid)
  for op in (lambda:n.initialize(np.zeros(16)),n.query,lambda:n.advance(0,self.obs)):
   with self.assertRaises(ValueError):op()
 def test_zero_rest_reverse_and_variable_interval(self):
  f=self.make();ref=self.make();n=self.candidate(f);n.initialize(np.zeros(16))
  obs=np.array([[dt,i,25,3.8,.002] for dt,i in [(0,0),(.02,.03),(1,0),(.01,-.1),(.2,.12)]],dtype=float)
  n.advance(0,obs);ref.update(0,obs)
  np.testing.assert_allclose(f.root.T@f.root,ref.root.T@ref.root,rtol=1e-12,atol=1e-7)
  np.testing.assert_allclose(f.state[18:],ref.state[18:],rtol=1e-12,atol=1e-16)
 def test_packed48_checkpoint_exact_roundtrip(self):
  f=self.make();n=self.candidate(f,48);n.initialize(np.zeros(16));n.advance(0,self.obs)
  old=f.packed.values.copy();f.root=f.root;np.testing.assert_array_equal(old,f.packed.values)
  self.assertEqual(f.packed.values.nbytes,3570)
 def test_small_math_grid(self):
  directory=Path(self.temporary.name);binary=directory/'math.so'
  subprocess.run(['cc','-O2','-fno-fast-math','-ffp-contract=off','-shared','-fPIC',str(Path(__file__).with_name('math_probe.c')),'-o',str(binary)],check=True)
  lib=C.CDLL(str(binary));fn=lib.evaluate;fn.argtypes=[C.c_uint,C.c_double,C.c_double];fn.restype=C.c_double
  grid=np.exp(np.linspace(-740,709,20001))
  cases=[(0,np.linspace(-740,709,20001),math.exp),(1,grid,math.log),(2,grid,math.sqrt),(3,grid,lambda x:math.hypot(x,1)),(4,np.linspace(-21,21,20001),math.tanh),(5,np.linspace(-.99999,.99999,20001),math.atanh)]
  for op,xs,ref in cases:
   for x in xs:
    actual=fn(op,float(x),1);expected=ref(float(x));self.assertLessEqual(abs(actual-expected),max(abs(expected)*2e-15,5e-324))
  self.assertLess(math.copysign(1,fn(4,-0.,0)) ,0)
  self.assertTrue(math.isnan(fn(2,-1,0)));self.assertEqual(fn(0,float('-inf'),0),0)
if __name__=='__main__':unittest.main()
