"""Isolate observed weak-run normalization discrepancy without changing evidence."""
import ctypes as C,json
import numpy as np
from .reference import *
from experiments.foster_feedback_001.estimator import Model,fit
from experiments.foster_feedback_001.history import pack_kernel,kernel,pack_message,GaussianBackend
case=ROOT/'experiments/foster_campaign_001/run_20261030_064220_507192/case_0001'
obs=np.load(case/'observations.npy',mmap_mode='r');block=20104
c=Baseline();c.replay(obs[:block*16]);prior=c.snapshot();m=prior[:16];L=prior[16:272].reshape(16,16);rows=obs[block*16:(block+1)*16].copy()
anchor,ph,d=fit(Model(HERE/'build/baseline.so',c.cfg),m,L,rows,c.cfg['numerical']);v,J,end,F=ph
physical=Physical((C.c_double*16)(*v),(C.c_double*256)(*J.ravel()),(C.c_double*16)(*end),(C.c_double*256)(*F.ravel()))
for enc in [8,4]:
 dst=(C.c_ubyte*3537)();n=c.lib.fb_token(ptr(anchor),C.byref(physical),ptr(rows),16,enc,dst);ct=bytes(dst[:n]);pt=pack_kernel(anchor,end,F,J/rows[:,4,None],(v-rows[:,3])/rows[:,4],float(np.log(rows[:,4]).sum()+8*np.log(2*np.pi)),'float'+str(enc*8))
 outcomes={}
 for name,t in [('c',ct),('py',pt)]:
  a,e,f,A,r,noise=kernel(t);aug=np.column_stack([A,r]);raw=np.column_stack([J/rows[:,4,None],(v-rows[:,3])/rows[:,4]])
  out=Message();c.lib.fb_history(C.byref(message(m,L,0)),(C.c_ubyte*len(t)).from_buffer_copy(t),len(t),C.byref(out))
  token=type('Token',(),{'payload':t})();pout=np.frombuffer(GaussianBackend().advance(pack_message(m,L,0),token),dtype='<f8')
  outcomes[name]=dict(c_increment=out.logZ,py_increment=pout[-1],quadratic_error=float(np.max(abs(aug.T@aug-raw.T@raw))),residual_norm=float(r@r),row_norms=np.linalg.norm(aug,axis=1).tolist())
 print(enc,outcomes)
