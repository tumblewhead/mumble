"""Isolated QR sharing atop the reviewed pole-sum baseline; no model change."""
from pathlib import Path
import hashlib,json,subprocess
from experiments.calculation_sharing_001.build import generate as base_generate
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
VARIANTS=('baseline','shared_loop','shared_access')
def generate(directory,variant='shared_loop',history_bits=48):
 if variant not in VARIANTS or history_bits!=48:raise ValueError('QR experiment requires history48')
 directory=Path(directory);p=base_generate(directory,'rc_tau_support',48);s=p.read_text()
 if variant!='baseline':
  h=(ROOT/'experiments/sram_size_001/history48.h').read_text();h=h[:h.index('static int history_insert(')]
  engine=(HERE/'shared_qr.h').read_text()
  if variant=='shared_access':
   engine=engine.replace('static double qr_read','static __attribute__((noinline,noclone)) double qr_read').replace('static void qr_write','static __attribute__((noinline,noclone)) void qr_write')
  h+=engine+'\nstatic int history_insert(history_store*R,int n,double*x){return shared_insert(R,n,x,1);}\n'
  hp=directory/'shared_history.h';hp.write_text(h)
  old=str(ROOT/'experiments/sram_size_001/history48.h');assert s.count(old)==1;s=s.replace(old,str(hp.resolve()))
  old=(ROOT/'experiments/bank_memory_001/qr.c').read_text();assert s.count(old)==1
  s=s.replace(old,'typedef double store;\nint insert(store*R,int n,double*x){return shared_insert(R,n,x,0);}\n')
 p.write_text(s)
 (directory/'qr_generation.json').write_text(json.dumps(dict(variant=variant,history_bits=48,core_sha256=hashlib.sha256(p.read_bytes()).hexdigest()),indent=2)+'\n')
 return p

def build(directory,variant,history_bits=48):
 d=Path(directory).resolve()/variant;src=generate(d,variant,history_bits);binary=d/'rowwise.so'
 cmd=['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-fno-fast-math','-ffp-contract=off','-fPIC','-shared',str(src),'-lm','-o',str(binary)]
 subprocess.run(cmd,check=True)
 (d/'build.json').write_text(json.dumps(dict(configuration=dict(variant=variant,history_bits=48),binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),command=cmd),indent=2)+'\n')
 return d
