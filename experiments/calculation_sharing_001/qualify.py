"""Paired direct controls: full transport, derivatives, support and scratch reuse."""
import argparse,ctypes as C,json,subprocess,hashlib
from pathlib import Path
from unittest.mock import patch
import numpy as np
from .build import build
from experiments.sram_size_001 import native
from experiments.bank_rowwise_001.native import ptr,Context,D
from experiments.bank_memory_001.test_memory import Tests as Fixture
KINDS=('baseline','rc_tau_support')

def make(field,mean,L,d,bits=48):
 with patch.object(native,'prepare',return_value=d):return native.Native(field,mean,L,d,'tiny','cardinal',True,bits)

def run(out):
 out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
 bins={v:build(out/'host',v,48) for v in KINDS}
 # Test-only access to static transport; never linked into measured image.
 for d in bins.values():
  src=d/'test_probe.c';src.write_text('''#include "core.c"
int sharing_endpoint(core*c,unsigned k,double*v,double*d){
 int code=transported(c,k,v,c->trial);memcpy(d,c->trial,16*sizeof(double));return code;
}
int sharing_support(core*c,const double*w){return supported(&c->m,w);}
''')
  subprocess.run(['cc','-std=c11','-O2','-fno-fast-math','-ffp-contract=off','-fPIC','-shared',str(src),'-lm','-o',str(d/'rowwise.so')],check=True)
 Fixture.setUpClass()
 try:
  fixture=Fixture();arms={}
  for v,d in bins.items():
   f=fixture.make(rank=3);f.update(0,fixture.obs)
   n=make(f,fixture.mean,fixture.L,d);n.initialize(np.zeros(16));arms[v]=n
   n.lib.sharing_endpoint.argtypes=[C.POINTER(Context),C.c_uint,D,D]
   n.lib.sharing_support.argtypes=[C.POINTER(Context),D]
  a,b=arms.values();rng=np.random.default_rng(2201);endpoint_count=0;feature_count=0;fd_max=0.
  def endpoint(n,w,k):
   np.copyto(n.vector('point'),w);value=np.array([123.]);gradient=np.full(16,456.)
   code=n.lib.sharing_endpoint(C.byref(n.context),k,ptr(value),ptr(gradient))
   return code,value,gradient
  for i in range(260):
   x=fixture.mean.copy();x[1:4]=rng.uniform(-.04,.04,3)
   u=rng.uniform(-1,1,3) if i>=4 else np.full(3,[-1,-1+1e-12,1-1e-12,1][i])
   taus=fixture.center[:3]*np.exp(u);increments=np.diff(np.r_[0,taus]);assert np.all(increments>0)
   x[[8,10,12]]=np.log(increments);x[[7,9,11]]+=rng.uniform(-1,1,3)
   w=(x-fixture.mean)/np.diag(fixture.L)
   free=rng.uniform(0,1,(3,13));forced=rng.uniform(-.12,.12,(3,13))
   for n in arms.values():n.field.rc_free[:]=free;n.field.rc_forced[:]=forced;n.sync()
   support=[n.lib.sharing_support(C.byref(n.context),ptr(w)) for n in arms.values()];assert support[0]==support[1]
   for k in range(16):
    ra=endpoint(a,w,k);rb=endpoint(b,w,k);assert ra[0]==rb[0]
    np.testing.assert_array_equal(ra[1],rb[1]);np.testing.assert_array_equal(ra[2],rb[2]);endpoint_count+=1
   if support[0]==0:
    for k in range(34):
     va,da=a.row(w,k);vb,db=b.row(w,k);assert va==vb;np.testing.assert_array_equal(da,db);feature_count+=1
   if 4<=i<24:
    for k in (1,2,3):
     analytic=endpoint(b,w,k)[2]
     for j in (1,2,3,7,8,9,10,11,12):
      step=2e-6;delta=np.eye(16)[j]*step
      numeric=(endpoint(b,w+delta,k)[1][0]-endpoint(b,w-delta,k)[1][0])/(2*step)
      err=abs(numeric-analytic[j]);fd_max=max(fd_max,err)
      assert err<2e-8*(1+abs(analytic[j])),(i,k,j,err)
  # Supported large amplitudes with zero carried RC state, the rejected variant's regression.
  w=np.zeros(16);w[7]=(709-fixture.mean[7])/np.diag(fixture.L)[7]
  for n in arms.values():
   n.field.rc_free[:]=0;n.field.rc_forced[:]=0;n.sync()
   assert n.lib.sharing_support(C.byref(n.context),ptr(w))==0
   code,val,grad=endpoint(n,w,1);assert code==0 and val[0]==0 and np.isfinite(grad).all()
   value=C.c_double(123);var=C.c_double(456)
   assert n.lib.scalar(C.byref(n.context),1,C.byref(value),C.byref(var))==0
   assert value.value==0 and var.value==0
  # Malformed query and nonfinite support classification remain unchanged.
  for k in (16,100):assert endpoint(a,np.zeros(16),k)[0]==endpoint(b,np.zeros(16),k)[0]==-1
  for bad in (np.nan,np.inf,-np.inf):
   w=np.zeros(16);w[8]=bad
   assert all(n.lib.sharing_support(C.byref(n.context),ptr(w))==-1 for n in arms.values())
  # Fresh valid arms: query scratch may be overwritten, but retained evidence may not.
  arms={}
  for v,d in bins.items():
   f=fixture.make(rank=3);f.update(0,fixture.obs);n=make(f,fixture.mean,fixture.L,d);n.initialize(np.zeros(16));arms[v]=n
  rounds=[]
  for r in range(5):
   queries=[];fits=[]
   for n in arms.values():
    before=n.field.packed.values.copy();factor=n.factor.copy()
    q=n.query();n.scalar(1);n.scalar(5);np.testing.assert_array_equal(before,n.field.packed.values);np.testing.assert_array_equal(factor,n.factor)
    n.advance(n.count,fixture.obs[:16]);fit=n.fit(n.anchor.copy())
    accepted=fit['diagnostic']['stop'] in ('gradient','GN_decrement_at_cost_roundoff')
    n.initialize(fit['w'] if accepted else n.anchor.copy())
    try:queries.append(n.query())
    except ValueError:queries.append(None)
    fits.append(fit)
   assert fits[0]['diagnostic']==fits[1]['diagnostic']
   assert (queries[0] is None)==(queries[1] is None)
   rounds.append(dict(stop=fits[0]['diagnostic']['stop'],query='rejected' if queries[0] is None else 'accepted'))
   if queries[0] is None:break
   for key in ('w','end','endpoint_root'):np.testing.assert_array_equal(queries[0][key],queries[1][key])
  result=dict(status='pass',endpoint_cases=endpoint_count,feature_cases=feature_count,paired_result='bitwise_equal_on_tested_inputs',max_finite_difference_absolute_error=fd_max,large_supported_amplitude_zero_state='pass',malformed_queries='pass',query_then_stream_refit_cycles=rounds,history_bits=48,source_hashes={str(d/'core.c'):hashlib.sha256((d/'core.c').read_bytes()).hexdigest() for d in bins.values()})
  (out/'results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
 finally:Fixture.tearDownClass()
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args();run(a.out)
