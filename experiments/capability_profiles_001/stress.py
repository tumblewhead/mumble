"""Adversarial one-column repeated-evidence accumulation and float math checks."""
import argparse,ctypes,json,subprocess
from pathlib import Path
import numpy as np

def run(core,out,reference_core):
 core=Path(core).resolve();out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
 source='''#include "CORE"
#include <stdio.h>
int main(void){history_store factor[1]={0};unsigned checkpoints[]={1,10,100,1000,10000,100000,1000000,10000000,20000000};unsigned next=0,first_stall=0;
 for(unsigned i=1;i<=20000000;i++){REAL old=history_get(factor,0),row[1]={1};if(history_insert(factor,1,row))return 1;REAL x=history_get(factor,0);if(x==old&&!first_stall)first_stall=i;
 if(i==checkpoints[next]){printf("%u %.17g %.17g %u\\n",i,(double)x,(double)x*x,first_stall);next++;}}
 return 0;}
'''.replace('CORE',str(core))
 lanes={}
 for lane in ('float_shared_math','float_libm','double48'):
  code=source.replace('REAL','double' if lane=='double48' else 'float')
  if lane=='double48':code=code.replace(str(core),str(Path(reference_core).resolve()))
  if lane=='float_libm':code=code.replace('#include "'+str(core)+'"','#include <math.h>\n#define hypot hypotf\n#include "'+str(core.with_name('shared_history.h'))+'"')
  src=out/(lane+'.c');src.write_text(code);exe=out/lane
  subprocess.run(['cc','-std=c11','-O2','-fno-fast-math','-ffp-contract=off','-fsanitize=undefined',str(src),'-lm','-o',str(exe)],check=True)
  r=subprocess.run([str(exe)],capture_output=True,text=True,check=True);assert not r.stderr,r.stderr
  rows=[]
  for line in r.stdout.splitlines():
   n,x,energy,stall=line.split();rows.append(dict(samples=int(n),factor=float(x),represented_information=float(energy),relative_information_error=float(energy)/int(n)-1,first_stall=int(stall)))
  lanes[lane]=rows
 # Dense float-representable inputs against system double libm rounded to float.
 math=core.with_name('shared_math.h')
 src=out/'math.c';src.write_text('#include "'+str(math)+'"\nfloat test_exp(float x){return cp32_fexp(x);}\nfloat test_expm1(float x){return cp32_fexpm1(x);}\nfloat test_sqrt(float x){return cp32_fsqrt(x);}\n')
 lib=out/'math.so';subprocess.run(['cc','-std=c11','-O2','-fno-fast-math','-ffp-contract=off','-shared','-fPIC',str(src),'-lm','-o',str(lib)],check=True);dll=ctypes.CDLL(str(lib));checks={}
 for name,reference in [('exp',np.exp),('expm1',np.expm1),('sqrt',np.sqrt)]:
  f=getattr(dll,'test_'+name);f.argtypes=[ctypes.c_float];f.restype=ctypes.c_float
  x=np.linspace(-104,88.72284,200000,dtype=np.float32) if name!='sqrt' else np.linspace(1,0x7f7fffff,200000,dtype=np.uint32).view(np.float32)
  with np.errstate(over='ignore',invalid='ignore'):truth=reference(x.astype(np.float64)).astype(np.float32)
  y=np.array([f(float(v)) for v in x],dtype=np.float32)
  finite=np.isfinite(truth)&np.isfinite(y)
  ulp=np.abs(y[finite].view(np.int32).astype(np.int64)-truth[finite].view(np.int32).astype(np.int64))
  checks[name]={'max_ulp':int(ulp.max()),'finite_classification_mismatches':int(np.count_nonzero(np.isfinite(y)!=np.isfinite(truth)))}
  assert checks[name]['max_ulp']<=3 and checks[name]['finite_classification_mismatches']==0,checks[name]
 result={'repeated_evidence':lanes,'sampled_math':checks,'status':'diagnostic','scope':'One-column history insertion, identical unit observations, exact information=n. This isolates accumulation; not full battery qualification. Sampled math is not an exhaustive bound.'}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--core',required=True);p.add_argument('--out',required=True);p.add_argument('--reference-core',required=True);a=p.parse_args();run(a.core,a.out,a.reference_core)
