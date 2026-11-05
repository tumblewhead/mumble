"""QR storage/mutation differential tests and retained-factor mathematical check."""
import argparse,ctypes as C,json,subprocess,hashlib
from pathlib import Path
import numpy as np
from .build import build
from experiments.calculation_sharing_001.qualify import make
KINDS=('baseline','shared_loop')

def storage(values,packed):
 a=np.ascontiguousarray(values,dtype='<f8')
 if not packed:return a.view('uint8').copy()
 u=a.view('<u8');u=(u+np.uint64(0x7fff)+((u>>np.uint64(16))&np.uint64(1)))>>np.uint64(16)
 return u.astype('<u8').view('uint8').reshape(-1,8)[:,:6].copy().ravel()

def run(out):
 out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
 dirs={v:build(out/'host',v) for v in KINDS};libs=[]
 for d in dirs.values():
  p=d/'qr_probe.c';p.write_text('''#include "core.c"
int test_insert(void*R,int n,double*x,unsigned packed){
 return packed?history_insert((history_store*)R,n,x):qr_insert((double*)R,n,x);
}
''')
  so=d/'qr_probe.so';subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-fno-fast-math','-ffp-contract=off','-fPIC','-shared',str(p),'-lm','-o',str(so)],check=True)
  lib=C.CDLL(str(so));lib.test_insert.argtypes=[C.c_void_p,C.c_int,C.c_void_p,C.c_uint];libs.append(lib)
 rng=np.random.default_rng(7351);calls=0;failures=0;zero_skips=0
 def paired(raw,n,row,packed):
  nonlocal calls,failures
  result=[];prefix=17 if packed else 16
  for lib in libs:
   buf=np.full(prefix+len(raw)+19,0xa7,dtype=np.uint8);buf[prefix:prefix+len(raw)]=raw
   x=np.r_[np.array([-123.]),row,np.array([456.])].astype('float64')
   code=lib.test_insert(buf.ctypes.data+prefix,n,x.ctypes.data+8,packed)
   assert np.all(buf[:prefix]==0xa7) and np.all(buf[prefix+len(raw):]==0xa7)
   assert x[0]==-123 and x[-1]==456
   result.append((code,buf[prefix:prefix+len(raw)].copy(),x[1:-1].copy()))
  assert result[0][0]==result[1][0]
  assert result[0][1].tobytes()==result[1][1].tobytes()
  assert result[0][2].tobytes()==result[1][2].tobytes()
  calls+=1;failures+=int(result[0][0]!=0);return result[0]
 gram=[]
 for packed in (0,1):
  for n in (0,1,2,3,17,34):
   raw=storage(np.zeros(n*(n+1)//2),packed)
   for j in range(600):
    row=rng.normal(size=n)
    if j%11==0:row[:]=0;zero_skips+=1
    if j%13==0:row[::2]=-0.
    code,raw,x=paired(raw,n,row,packed);assert code==0
   # Shape- and magnitude-sensitive updates; each case starts with fresh data.
   for scale in (1e-300,1e-150,1.,1e150,1e300):
    factor=rng.normal(size=n*(n+1)//2)*scale;row=rng.normal(size=n)*scale
    paired(storage(factor,packed),n,row,packed)
  for n in (1,2,17,34):
   count=n*(n+1)//2
   for bad in (np.nan,np.inf,-np.inf,np.finfo(float).max):
    for k in (0,n-1):
     row=np.zeros(n);row[k]=bad;paired(storage(np.zeros(count),packed),n,row,packed)
    for k in set((0,min(1,count-1),count-1)):
     factor=np.zeros(count);factor[k]=bad
     paired(storage(factor,packed),n,np.ones(n),packed)
   if n>1:
    factor=np.zeros(count);factor[1]=np.nan
    paired(storage(factor,packed),n,np.zeros(n),packed) # zero pivot skips off-diagonal
    factor=np.zeros(count);factor[0]=1;factor[1]=np.finfo(float).max
    row=np.ones(n);row[1]=np.finfo(float).max
    paired(storage(factor,packed),n,row,packed) # partial-write overflow
 # Named edge checks ensure these failures actually occur, not just parity.
 max64=np.finfo(float).max
 assert paired(storage(np.zeros(1),1),1,np.array([max64]),1)[0]==-1
 assert paired(storage(np.zeros(1),0),1,np.array([max64]),0)[0]==0
 max48=np.array([0x7fefffffffff0000],dtype='<u8').view('<f8')[0]
 for packed in (0,1):
  code,raw,x=paired(storage(np.array([1.,-max48,0.]),packed),2,np.array([1.,max48]),packed)
  assert code==-1 and np.isinf(x[1])
 # Independent algebra check for finite well-scaled binary64 retained factor.
 for n in (3,17,34):
  rows=rng.normal(size=(500,n));raw=storage(np.zeros(n*(n+1)//2),0)
  for row in rows:code,raw,x=paired(raw,n,row,0);assert code==0
  R=np.zeros((n,n));R[np.triu_indices(n)]=raw.view('<f8');exact=rows.T@rows
  error=float(np.linalg.norm(R.T@R-exact)/np.linalg.norm(exact));assert error<2e-13;gram.append(dict(width=n,relative_gram_error=error))
 # A late history failure occurs after the local tangent and state can mutate.
 # Both adapters must poison the stream, preventing a refit/query from reviving it.
 from experiments.bank_memory_001.test_memory import Tests as Fixture
 Fixture.setUpClass();quarantine=[]
 try:
  fixture=Fixture()
  for variant,d in dirs.items():
   f=fixture.make(rank=3);n=make(f,fixture.mean,fixture.L,d);n.initialize(np.zeros(16))
   n.advance(0,fixture.obs[:16])
   # Last history diagonal is corrupted, independent of the valid local tangent.
   f.packed.values[-6:]=storage(np.array([np.inf]),1)
   try:n.advance(n.count,fixture.obs[16:32]);raise AssertionError('failure not detected')
   except ValueError:pass
   assert n.poisoned and n.context.qr.lease.valid==0
   for operation in (lambda:n.query(),lambda:n.fit(n.anchor.copy()),lambda:n.advance(n.count,fixture.obs[32:48])):
    try:operation();raise AssertionError('poisoned adapter revived')
    except ValueError:pass
   quarantine.append(dict(variant=variant,poisoned=True,query_fit_advance_rejected=True))
 finally:Fixture.tearDownClass()
 result=dict(status='pass',paired_insertions=calls,matched_failures=failures,zero_row_cases=zero_skips,quarantine=quarantine,checks=['Every tested status, mutated factor byte and row byte identical','Canaries unchanged; history tested at byte-unaligned address','Widths0,1,2,3,17,34 and scales1e-300..1e300','NaN/Inf/DBL_MAX, overflow readback, skipped pivots and partial mutations','Named finite-to-infinity history48 rounding and late row overflow assertions'],gram=gram,source_hashes={str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for d in dirs.values() for p in d.iterdir() if p.suffix in ('.c','.h','.so')})
 (out/'results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args();run(a.out)
