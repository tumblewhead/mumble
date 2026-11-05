from pathlib import Path
import ctypes as C,json,subprocess
import numpy as np
from .build import generate

def run(out):
 out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False);libs=[]
 for kind in ('baseline','shared'):
  d=out/kind;p=generate(d,kind);probe=d/'check.c'
  probe.write_text('''#include "core.c"
int check(double*f,double*g,double*out,double*y,int trans){
 inference s={0};memcpy(s.factor,f,sizeof(s.factor));s.lease.valid=1;
 int rc=trans?br_variance(&s,g,out):br_step(&s,out);
 memcpy(y,s.scratch.y,16*sizeof(double));
 return rc;
}
''')
  so=d/'check.so';subprocess.run(['cc','-O2','-fno-fast-math','-ffp-contract=off','-shared','-fPIC',str(probe),'-lm','-o',str(so)],check=True)
  lib=C.CDLL(str(so));lib.check.argtypes=[C.c_void_p]*4+[C.c_int];libs.append(lib)
 rng=np.random.default_rng(42);count=0;failed=0;max_residual=0
 for i in range(500):
  R=np.triu(rng.normal(size=(17,17)));R[np.diag_indices(17)]=rng.uniform(2,4,17);g=rng.normal(size=16)
  if i>=480:R[i%16,i%16]=[0,np.nan,np.inf,-np.inf][i%4]
  f=R[np.triu_indices(17)].copy()
  for trans in (0,1):
   vals=[]
   for lib in libs:
    output=np.full(16,123.);y=np.zeros(16)
    code=lib.check(f.ctypes.data,g.ctypes.data,output.ctypes.data,y.ctypes.data,trans);vals.append((code,output,y))
   assert vals[0][0]==vals[1][0]
   for j in (1,2):np.testing.assert_array_equal(vals[0][j],vals[1][j])
   count+=1;failed+=int(vals[0][0]!=0)
   if i<480:
    A=R[:16,:16].T if trans else R[:16,:16];rhs=g if trans else -R[:16,16]
    error=np.linalg.norm(A@vals[1][2]-rhs)/(1+np.linalg.norm(rhs));max_residual=max(max_residual,float(error));assert error<1e-12
    if trans:assert abs(vals[1][1][0]-np.dot(vals[1][2],vals[1][2]))<1e-12
 result=dict(status='pass',paired_solves=count,matched_failures=failed,max_relative_residual=max_residual)
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(result)
if __name__=='__main__':run('experiments/triangular_sharing_001/check001')
