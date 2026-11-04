"""Dense arrays are test oracles only; the C kernel requests one derivative row."""
import ctypes as C
import subprocess,tempfile,unittest
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
D=C.POINTER(C.c_double)
CALLBACK=C.CFUNCTYPE(C.c_int,C.c_void_p,C.c_uint,D)

class ScratchTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();p=Path(cls.tmp.name)/'scratch.so'
  subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-fno-fast-math','-ffp-contract=off','-shared','-fPIC',str(HERE/'scratch_kernel.c'),'-lm','-o',str(p)],check=True)
  cls.lib=C.CDLL(str(p));cls.lib.inference_bytes.restype=C.c_size_t
  cls.lib.rebuild.argtypes=[C.c_void_p,C.c_uint,D,D,D,CALLBACK,C.c_void_p]
  cls.lib.step.argtypes=[C.c_void_p,D];cls.lib.variance.argtypes=[C.c_void_p,D,D]
  cls.lib.acquire.argtypes=[C.c_void_p,C.c_uint];cls.lib.acquire.restype=C.c_uint64
  cls.lib.release.argtypes=[C.c_void_p,C.c_uint,C.c_uint64]
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def setUp(self):self.state=C.create_string_buffer(self.lib.inference_bytes())
 def fixture(self,width):
  rng=np.random.default_rng(76);R=np.linalg.qr(rng.normal(size=(width+50,width)),mode='r');phi=rng.normal(size=width);J=rng.normal(size=(width,16));w=rng.normal(size=16)
  def emit(context,j,out):np.ctypeslib.as_array(out,shape=(16,))[:]=J[j];return 0
  return R,phi,J,w,CALLBACK(emit)
 @staticmethod
 def ptr(a):return a.ctypes.data_as(D)
 def test_joint_step_variance_and_history_immutable(self):
  for width in [34,40,94]:
   R,phi,J,w,emit=self.fixture(width);packed=R[np.triu_indices(width)].copy();saved=packed.copy()
   self.assertEqual(self.lib.rebuild(self.state,width,self.ptr(packed),self.ptr(phi),self.ptr(w),emit,None),0)
   B=np.vstack((np.eye(16),R@J));r=np.r_[w,R@phi];P=B.T@B
   out=np.empty(16);self.assertEqual(self.lib.step(self.state,self.ptr(out)),0)
   np.testing.assert_allclose(out,np.linalg.solve(P,-B.T@r),atol=1e-11,rtol=1e-11)
   grad=np.linspace(-1,2,16);v=C.c_double()
   self.assertEqual(self.lib.variance(self.state,self.ptr(grad),C.byref(v)),0)
   self.assertAlmostEqual(v.value,grad@np.linalg.solve(P,grad),places=12)
   np.testing.assert_array_equal(packed,saved)
 def test_lease_and_failure_invalidation(self):
  g=self.lib.acquire(self.state,7);self.assertGreater(g,0)
  self.assertEqual(self.lib.acquire(self.state,8),0)
  self.assertEqual(self.lib.release(self.state,7,g+1),-1)
  out=np.full(16,42.);self.assertEqual(self.lib.step(self.state,self.ptr(out)),-2)
  self.assertEqual(self.lib.release(self.state,7,g),0)
  R,phi,J,w,emit=self.fixture(34);p=R[np.triu_indices(34)].copy()
  self.assertEqual(self.lib.rebuild(self.state,34,self.ptr(p),self.ptr(phi),self.ptr(w),emit,None),0)
  J[4,3]=np.nan
  self.assertEqual(self.lib.rebuild(self.state,34,self.ptr(p),self.ptr(phi),self.ptr(w),emit,None),-1)
  self.assertEqual(self.lib.step(self.state,self.ptr(out)),-1);np.testing.assert_array_equal(out,42.)
  self.assertEqual(self.lib.lease_bytes(),16);self.assertEqual(self.lib.inference_bytes(),1504)

if __name__=='__main__':unittest.main()
