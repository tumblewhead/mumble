from pathlib import Path
import ctypes as C,json,subprocess
import numpy as np

def run(out):
 out=Path(out);out.mkdir(parents=True,exist_ok=False);libs=[]
 for name in ('baseline','chart_finite'):
  d=Path('experiments/config_size_001')/name/'tiny_cardinal';src=out/(name+'.c');so=out/(name+'.so')
  src.write_text('#include "'+str((d/'core.c').resolve())+'"\n#include "'+str((d/'config.h').resolve())+'"\n'+'''void defaults(double*m,double*s){memcpy(m,config_mean,128);memcpy(s,config_scale,128);}
int test(double*w,double*mean,double*scale){
 core c={0};double response[93]={0};
 model m={mean,scale,config_center,config_P,config_P,config_P,1.,response,response+15,response+54};
 if(bind(&c,&m))return -2;
 return supported(&c.m,w);
}
''')
  subprocess.run(['cc','-O2','-fno-fast-math','-ffp-contract=off','-shared','-Wl,-Bsymbolic','-fPIC',str(src),'-lm','-o',str(so)],check=True)
  lib=C.CDLL(str(so.resolve()));lib.test.argtypes=[C.c_void_p]*3;lib.defaults.argtypes=[C.c_void_p]*2;libs.append(lib)
 mean=np.zeros(16);scale=np.zeros(16);libs[0].defaults(mean.ctypes.data,scale.ctypes.data)
 rng=np.random.default_rng(909);count=0;accepted=0
 def check(w,m=mean,s=scale):
  nonlocal count,accepted
  a=[l.test(w.ctypes.data,m.ctypes.data,s.ctypes.data) for l in libs];assert a[0]==a[1];count+=1;accepted+=a[0]==0;return a[0]
 for i in range(20000):
  w=rng.normal(size=16) if i%2 else rng.integers(0,2**64,size=16,dtype=np.uint64).view(np.float64)
  check(w)
 for k in range(16):
  for v in (0.,-0.,np.nan,np.inf,-np.inf,np.finfo(float).max,np.nextafter(0.,1.)):
   w=np.zeros(16);w[k]=v;check(w)
  for v in (0.,-1.,np.nan,np.inf,-np.inf):
   s=scale.copy();s[k]=v;assert check(np.zeros(16),s=s)==-2
  for v in (np.nan,np.inf,-np.inf):
   m=mean.copy();m[k]=v;assert check(np.zeros(16),m=m)==-2
  for v in (np.nextafter(0.,1.),np.finfo(float).max):
   s=scale.copy();s[k]=v
   for x in (np.inf,-np.inf,np.nan,0.,1.):
    w=np.zeros(16);w[k]=x;check(w,s=s)
 assert accepted>0, 'test must exercise valid support'
 result=dict(status='pass',paired_classifications=count,accepted=accepted,scope='Return classification under nontrapping IEEE arithmetic; fenv flags not compared')
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(result)
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args();run(a.out)
