from pathlib import Path
from experiments.triangular_sharing_001.build import generate as base
ROOT=Path(__file__).resolve().parents[2]
VARIANTS=('baseline','serial_projection','pointer_projection','memset_clear')
def generate(directory,variant='baseline',history_bits=48):
 p=base(directory,'shared',history_bits)
 if variant=='serial_projection':
  s=p.read_text();old=ROOT/'experiments/sram_size_001/stream.c';stream=old.read_text()
  a=stream.index('   for(unsigned k=0;k<3;k++){');b=stream.index('\n  }',a)
  stream=stream[:a]+'''   for(unsigned kind=0;kind<2;kind++){
    double value=kind?forced[ix]:free[ix];
    for(unsigned k=0;k<3;k++)row[3+6*b+3*kind+k]-=value*V[3*j+k]/sigma;
   }'''+stream[b:]
  f=Path(directory)/'stream.c';f.write_text(stream);assert s.count(str(old))==1;p.write_text(s.replace(str(old),str(f.resolve())))
 elif variant in ('pointer_projection','memset_clear'):
  old=ROOT/'experiments/sram_size_001/stream.c';stream=old.read_text();s=p.read_text()
  if variant=='memset_clear':
   oldtext='for(unsigned k=0;k<6;k++)row[3+6*b+k]=0;';assert stream.count(oldtext)==1
   stream=stream.replace(oldtext,'memset(row+3+6*b,0,6*sizeof(double));')
  else:
   a=stream.index('   for(unsigned k=0;k<3;k++){');b=stream.index('\n  }',a)
   stream=stream[:a]+'''   double*rf=row+3+6*b,*rr=rf+3;const double*v=V+3*j;
   for(unsigned k=0;k<3;k++){
    rf[k]-=free[ix]*v[k]/sigma;rr[k]-=forced[ix]*v[k]/sigma;
   }'''+stream[b:]
  f=Path(directory)/'stream.c';f.write_text(stream);assert s.count(str(old))==1;p.write_text(s.replace(str(old),str(f.resolve())))
 elif variant!='baseline':raise ValueError(variant)
 return p
