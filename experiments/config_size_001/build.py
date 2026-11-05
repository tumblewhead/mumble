from pathlib import Path
from experiments.triangular_sharing_001.build import generate as base
VARIANTS=('baseline','chart_finite','cached_exp','combined')
def generate(directory,variant='chart_finite',history_bits=48):
 p=base(directory,'shared',history_bits);s=p.read_text()
 if variant in ('chart_finite','combined'):
  old='!isfinite(w[j])||!isfinite(chart(m,w,j))';assert s.count(old)==1
  s=s.replace(old,'!isfinite(chart(m,w,j))')
 if variant in ('cached_exp','combined'):
  old='for(unsigned j=6;j<16;j++)if(!isfinite(exp(chart(m,w,j)))||!(exp(chart(m,w,j))>0))return -1;'
  assert s.count(old)==1;s=s.replace(old,'for(unsigned j=6;j<16;j++){double a=exp(chart(m,w,j));if(!isfinite(a)||!(a>0))return -1;}')
 if variant not in VARIANTS:raise ValueError(variant)
 p.write_text(s);return p
