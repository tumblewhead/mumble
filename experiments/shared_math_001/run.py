"""Bottom-up math and whole-link controls. Results are experiments, not certificates."""
import argparse,json,subprocess,ctypes as C,math,time,hashlib
from pathlib import Path
from unittest.mock import patch
import numpy as np
from .build import VARIANTS,build
from experiments.sram_size_001 import measure, native
from experiments.bank_memory_001.test_memory import Tests as Fixture
HERE=Path(__file__).resolve().parent

def run(out):
 out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False);results={}
 (out/'source_manifest.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in HERE.glob('*.py')},indent=2))
 for p in HERE.glob('*.py'):(out/('source_'+p.name)).write_bytes(p.read_bytes())
 Fixture.setUpClass()
 try:
  fixture=Fixture()
  for variant in VARIANTS:
   d=build(out/'host',variant)
   (d/'math.c').write_text('#include "shared_math.h"\ndouble evaluate(unsigned op,double x,double y){switch(op){case 0:return exp(x);case 1:return expm1(x);case 2:return log(x);case 3:return sqrt(x);case 4:return hypot(x,y);case 5:return tanh(x);case 6:return atanh(x);default:return NAN;}}\n')
   subprocess.run(['cc','-O2','-fno-fast-math','-ffp-contract=off','-shared','-fPIC',str(d/'math.c'),'-o',str(d/'math.so')],check=True)
   lib=C.CDLL(str(d/'math.so'));fn=lib.evaluate;fn.argtypes=[C.c_uint,C.c_double,C.c_double];fn.restype=C.c_double
   pos=np.exp(np.linspace(-740,709,10001));near=np.r_[np.linspace(-.5,.5,10001),0.,1e-300,-1e-300]
   cases=[('exp',np.linspace(-740,709,10001),math.exp),('expm1',near,math.expm1),('log',pos,math.log),('sqrt',pos,math.sqrt),('hypot',pos,lambda x:math.hypot(x,1)),('tanh',np.r_[near,np.linspace(-21,21,10001)],math.tanh),('atanh',np.r_[near,np.linspace(-.99999,.99999,10001)],math.atanh)]
   error={}
   for op,(name,xs,ref) in enumerate(cases):
    a=np.array([fn(op,x,1) for x in xs]);b=np.array([ref(x) for x in xs]);err=abs(a-b)
    error[name]=dict(max_relative=float(max(err/np.maximum(abs(b),np.finfo(float).tiny))),max_ulp=float(max(err/np.maximum(abs(np.spacing(b)),np.nextafter(0.,1.)))),nonfinite=int(sum(~np.isfinite(a))))
   f=fixture.make(rank=3)
   with patch.object(native,'prepare',return_value=d):n=native.Native(f,fixture.mean,fixture.L,d,'tiny','cardinal',True,64)
   n.initialize(np.zeros(16));n.advance(0,fixture.obs)
   fit=n.fit(np.zeros(16));n.initialize(fit['w']);q=n.query()
   results[variant]=dict(math=error,fixture=dict(fit=fit['diagnostic'],w=fit['w'].tolist(),end=q['end'].tolist(),sd=np.linalg.norm(q['endpoint_root'],axis=1).tolist()))
   original=measure.generate
   def gen(directory,*args,**kw):
    from .build import generate
    return generate(directory,variant,kw.get('history_bits',args[3] if len(args)>3 else 64))
   with patch.object(measure,'generate',side_effect=gen):measure.run(out/'target'/variant,64)
   results[variant]['target']=json.loads((out/'target'/variant/'measurement.json').read_text())
   (out/'results.json').write_text(json.dumps(results,indent=2)+'\n');print(variant,'done',flush=True)
 finally:Fixture.tearDownClass()
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args();run(a.out)
