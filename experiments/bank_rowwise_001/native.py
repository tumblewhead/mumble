"""Native rowwise inference; NumPy matrices exist only in the desktop adapter."""
import ctypes as C
import subprocess
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
D=C.POINTER(C.c_double)
def ptr(a):return a.ctypes.data_as(D)
class Model(C.Structure):
 _fields_=[(n,D) for n in ['mean','scale','center','map','knots','projected_map']]+[('hu',C.c_double)]+[(n,D) for n in ['legacy','free_rc','forced_rc']]
class Registry(C.Structure):_fields_=[('generation',C.c_uint64),('owner',C.c_uint32),('valid',C.c_uint32)]
class QR(C.Structure):_fields_=[('factor',C.c_double*153),('scratch',C.c_double*33),('lease',Registry)]
class Context(C.Structure):
 _fields_=[('qr',QR)]+[(n,C.c_double*16) for n in ['anchor','point','trial','delta']]+[('phi',C.c_double*34),('m',Model)]+[(n,C.c_double) for n in ['cost','grad_inf','decrement']]+[(n,C.c_uint) for n in ['rounds','rejections','stop']]

def build(directory):
 directory=Path(directory);directory.mkdir(parents=True,exist_ok=True);p=directory/'rowwise.so'
 if not p.exists():subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-fno-fast-math','-ffp-contract=off','-fPIC','-shared',str(HERE/'core.c'),'-lm','-o',str(p)],check=True)
 return p
class Native:
 def __init__(self,field,mean,root,directory):
  mean=np.asarray(mean,dtype=np.float64);root=np.asarray(root,dtype=np.float64)
  if mean.shape!=(16,) or root.shape!=(16,16) or not np.isfinite(mean).all() or not np.isfinite(root).all():raise ValueError('finite prior dimensions required')
  if field.rank!=3 or field.packed.dtype!=np.dtype('float64') or np.any(field.offset):raise ValueError('rowwise requires rank3 float64 uncentered')
  if not np.array_equal(root,np.diag(np.diag(root))):raise ValueError('original diagonal prior required')
  self.field=field;self.mean=mean.copy();self.scale=np.diag(root).copy();self.PA=np.ascontiguousarray(field.P@field.map.A);self.context=Context();self.lib=C.CDLL(str(build(directory).resolve()))
  self.lib.core_bytes.restype=C.c_size_t
  assert self.lib.core_bytes()==C.sizeof(Context)
  self.lib.bind.argtypes=[C.POINTER(Context),C.POINTER(Model)]
  for n in ['initialize','fit']:getattr(self.lib,n).argtypes=[C.POINTER(Context),D,D]
  self.lib.append.argtypes=[C.POINTER(Context),D,C.c_uint];self.lib.estimate.argtypes=[C.POINTER(Context)]
  self.lib.row_query.argtypes=[C.POINTER(Context),D,C.c_uint,D,D]
  self.lib.scalar.argtypes=[C.POINTER(Context),C.c_uint,D,D];self.lib.root_row.argtypes=[C.POINTER(Context),C.c_uint,D,D]
  self.sync()
 def sync(self):
  f=self.field
  self.model=Model(ptr(self.mean),ptr(self.scale),ptr(f.center),ptr(f.map.A),ptr(f.map.um),ptr(self.PA),f.map.hu,ptr(f.state),ptr(f.rc_free),ptr(f.rc_forced))
  self.check(self.lib.bind(C.byref(self.context),C.byref(self.model)))
 @staticmethod
 def check(code):
  if code:raise ValueError('native rowwise failure '+str(code))
 def vector(self,name):return np.ctypeslib.as_array(getattr(self.context,name))
 @staticmethod
 def checked_w(w):
  w=np.ascontiguousarray(w,dtype=np.float64)
  if w.shape!=(16,) or not np.isfinite(w).all():raise ValueError("finite16D coordinates required")
  return w
 def initialize(self,w):
  w=self.checked_w(w);self.sync();self.check(self.lib.initialize(C.byref(self.context),ptr(self.field.packed.values),ptr(np.ascontiguousarray(w))))
 def fit(self,w):
  w=self.checked_w(w);self.sync();self.check(self.lib.fit(C.byref(self.context),ptr(self.field.packed.values),ptr(np.ascontiguousarray(w))))
  s=self.context;stops={1:'GN_decrement_at_cost_roundoff',2:'gradient',3:'round_limit',4:'no_descent'}
  return dict(w=self.vector('point').copy(),diagnostic=dict(stop=stops[s.stop],rounds=s.rounds,cost=s.cost,free_gradient_inf=s.grad_inf,free_GN_decrement_squared=s.decrement,domain_rejections=s.rejections))
 def update(self,rows):
  rows=np.ascontiguousarray(rows,dtype=np.float64)
  if rows.ndim!=2 or rows.shape[1]!=34 or not 1<=len(rows)<=1024 or not np.isfinite(rows).all():raise ValueError("finite full-width rows required")
  self.sync();self.check(self.lib.append(C.byref(self.context),ptr(rows),len(rows)))
 def query(self):
  self.sync();self.check(self.lib.estimate(C.byref(self.context)))
  # Compatibility output belongs to host plotting adapter, outside native core.
  end=np.empty(16);root=np.empty((16,16));value=C.c_double()
  for k in range(16):self.check(self.lib.root_row(C.byref(self.context),k,C.byref(value),ptr(root[k])));end[k]=value.value
  R=np.ctypeslib.as_array(self.context.qr.factor);diagonal=[i*17-i*(i-1)//2 for i in range(16)]
  return dict(w=self.vector('point').copy(),end=end,endpoint_root=root,linearized_cost=.5*R[-1]**2,logdet_precision=float(2*np.log(R[diagonal]).sum()))
 def scalar(self,k):
  self.sync();self.check(self.lib.estimate(C.byref(self.context)))
  value=C.c_double();var=C.c_double();self.check(self.lib.scalar(C.byref(self.context),k,C.byref(value),C.byref(var)));return value.value,var.value
 def row(self,w,k):
  value=C.c_double();out=np.empty(16);w=self.checked_w(w);self.sync();self.check(self.lib.row_query(C.byref(self.context),ptr(w),k,C.byref(value),ptr(out)));return value.value,out
 @property
 def count(self):return self.field.count
 @property
 def anchor(self):return self.vector('anchor')
 @property
 def factor(self):
  R=np.zeros((17,17));R[np.triu_indices(17)]=np.ctypeslib.as_array(self.context.qr.factor);return R
 def snapshot(self):return np.r_[self.anchor,self.factor.ravel()]
 def restore(self,a):
  self.initialize(a[:16]);np.ctypeslib.as_array(self.context.qr.factor)[:]=a[16:].reshape(17,17)[np.triu_indices(17)]
