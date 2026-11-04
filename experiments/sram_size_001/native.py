"""Isolated math/map controls. Original fixed response states and factor retained."""
from pathlib import Path
import subprocess,json,hashlib,fcntl
import numpy as np
from experiments.bank_rowwise_001.native import Native as Original,ptr,C,D
from experiments.distinct_bank_integration_001.field import DistinctMap
from .generate import generate

class CardinalMap(DistinctMap):
 def __init__(self,old):
  self.__dict__.update(vars(old));self.sha256='cardinal13_fixed_quarter_grid_v1'
 def weights(self,u,derivative=0):
  u=np.asarray(u,dtype=float)
  if derivative not in (0,1,2) or not np.isfinite(u).all() or np.any(abs(u)>1):raise ValueError('map domain/derivative')
  x=4*u+6;out=[]
  for j in range(13):
   p=np.ones_like(x);q=np.zeros_like(x);r=np.zeros_like(x);den=1
   for k in range(13):
    if k==j:continue
    r=r*(x-k)+2*q;q=q*(x-k)+p;p=p*(x-k);den*=j-k
   out.append((p,q*4,r*16)[derivative]/den)
  return np.stack(out,axis=-1)

def projected_coefficients(field):
 # Fixed degree12 polynomial; change of basis only, no degree truncation.
 nodes=np.cos(np.pi*(np.arange(13)+.5)/13)
 values=CardinalMap(field.map).weights(nodes)@field.P.T
 return np.ascontiguousarray(np.linalg.solve(np.polynomial.chebyshev.chebvander(nodes,12),values).T)

class Packed48:
 def __init__(self,original):
  self.width=original.width;self.dtype=np.dtype('uint8')
  self.set_dense(original.dense())
 def set_dense(self,r):
  a=np.ascontiguousarray(r[np.triu_indices(self.width)],dtype='<f8')
  if not np.isfinite(a).all():raise ValueError('finite history')
  u=a.view('<u8');rounded=u+np.uint64(0x7fff)+((u>>np.uint64(16))&np.uint64(1))
  self.values=rounded.astype('<u8').view('uint8').reshape(-1,8)[:,2:].copy().reshape(-1)
  if not np.isfinite(self.dense()).all():raise ValueError('history48 overflow')
 def dense(self):
  u=np.zeros((self.values.size//6,8),dtype=np.uint8);u[:,2:]=self.values.reshape(-1,6)
  r=np.zeros((self.width,self.width));r[np.triu_indices(self.width)]=u.reshape(-1).view('<f8');return r

DEPENDENCIES=[str(p.relative_to(Path(__file__).resolve().parents[2])) for p in [
 Path(__file__).with_name(n) for n in ('native.py','generate.py','tiny_math.h','stream.c','history48.h','soft_sub.c')]]+[
 'experiments/bank_rowwise_001/core.c','experiments/bank_rowwise_001/native.py','experiments/bank_rowwise_001/backend.py',
 'experiments/bank_memory_001/scratch_kernel.c','experiments/bank_memory_001/qr.c','experiments/bank_memory_001/field.py']

def prepare(directory,math_kind='tiny',map_kind='cardinal',compact=True,history_bits=64):
 if math_kind not in ('tiny','libm') or map_kind not in ('spline','cardinal') or history_bits not in (48,64):raise ValueError('candidate variant')
 directory=Path(directory)/f'{math_kind}_{map_kind}_{int(compact)}_{history_bits}'
 directory.mkdir(parents=True,exist_ok=True)
 binary=directory/'rowwise.so';manifest=directory/'build.json'
 root=Path(__file__).resolve().parents[2]
 sources={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in DEPENDENCIES}
 expected=dict(math=math_kind,map=map_kind,compact=compact,history_bits=history_bits,sources=sources)
 with (directory/'.build.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  sources={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in DEPENDENCIES}
  expected['sources']=sources
  if binary.exists():
   if not manifest.exists():raise ValueError('unbound SRAM binary; use a fresh output directory')
   saved=json.loads(manifest.read_text())
   if saved['configuration']!=expected or saved['binary_sha256']!=hashlib.sha256(binary.read_bytes()).hexdigest():raise ValueError('stale SRAM build; use a fresh output directory')
  else:
   source=generate(directory,math_kind,map_kind,compact,history_bits)
   command=['cc','-std=c11','-Os','-Wall','-Wextra','-Werror','-fno-fast-math','-ffp-contract=off','-fPIC','-shared',str(source),'-lm','-o',str(binary)]
   subprocess.run(command,check=True)
   if sources!={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in DEPENDENCIES}:raise ValueError('sources changed during SRAM build; use a fresh output directory')
   manifest.write_text(json.dumps(dict(configuration=expected,command=command,binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),generated_sha256=hashlib.sha256(source.read_bytes()).hexdigest()),indent=2)+'\n')
  if sources!={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in DEPENDENCIES}:raise ValueError('sources changed during SRAM build validation')
 return directory

class Native(Original):
 def __init__(self,field,mean,root,directory,math_kind='tiny',map_kind='spline',compact=False,history_bits=64):
  self.compact=compact
  directory=prepare(directory,math_kind,map_kind,compact,history_bits)
  self.build_identity=json.loads((directory/'build.json').read_text())
  if map_kind=='cardinal':field.base.map=CardinalMap(field.map)
  super().__init__(field,mean,root,directory)
  if map_kind=='cardinal':self.PA=projected_coefficients(field);self.sync()
  if compact:self.lib.stream_ingest.argtypes=[C.POINTER(type(self.context)),D,D,D,D]
  if history_bits==48:field.packed=Packed48(field.packed)
  self.ocv=np.array([field.base.config['ocv_intercept_V'],field.base.config['ocv_slope_V_per_SOC']],dtype=float)


 def sync(self):
  if getattr(self,'poisoned',False):raise ValueError('SRAM native stream quarantined')
  super().sync()
  if self.compact:
   state=self.field.state
   self.compact_state=np.r_[state[18:24],state[27:33],state[36:39]]
   self.model.legacy=ptr(self.compact_state)
   self.check(self.lib.bind(C.byref(self.context),C.byref(self.model)))

 def advance(self,first,rows):
  try:return self._advance(first,rows)
  except Exception:
   self.poisoned=True
   raise

 def _advance(self,first,rows):
  rows=np.ascontiguousarray(rows,dtype=np.float64);f=self.field
  if not self.compact or type(first) not in (int,np.int64) or first!=f.count or rows.ndim!=2 or rows.shape[1]!=5 or not 1<=len(rows)<=1024:raise ValueError('stream chronology/shape')
  self.sync()
  for row in rows:self.check(self.lib.stream_ingest(C.byref(self.context),ptr(f.packed.values),ptr(f.V),ptr(self.ocv),ptr(row)))
  state=f.state.copy();state[18:24]=self.compact_state[:6];state[27:33]=self.compact_state[6:12];state[36:39]=self.compact_state[12:]
  noise=f.noise+float(np.log(rows[:,4]).sum()+len(rows)*.5*np.log(2*np.pi))
  if not np.isfinite(noise):raise ValueError('normalizer')
  f._commit(state,f.rc_free,f.rc_forced,first+len(rows),noise)
