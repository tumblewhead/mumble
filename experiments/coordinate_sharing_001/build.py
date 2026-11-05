from experiments.constant_storage_001.build import generate as base,adapt_probe as base_probe
import re
VARIANTS=('baseline','hys_scalar','hys_pair','exp_chart','combined_scalar')
def generate(directory,variant='baseline',history_bits=48):
 assert variant in VARIANTS
 p=base(directory,'byte_indices',history_bits);s=p.read_text();helper=''
 if variant in ('hys_scalar','combined_scalar'):
  for a,b in [('14','3'),('15','4'),('14+j','3+j')]:
   old='chart(m,w,'+a+')-chart(m,w,5)-log(m->config->center['+b+'])'
   count=s.count(old);assert count==(1 if a=='14+j' else 2),(old,count)
   s=s.replace(old,'hys_coordinate(m,w,'+('j' if a=='14+j' else str(int(a)-14))+')')
  helper+='static __attribute__((noinline,noclone)) double hys_coordinate(const model*m,const double*w,unsigned j){return chart(m,w,14+j)-chart(m,w,5)-log(m->config->center[3+j]);}\n'
 if variant in ('hys_pair',):
  old1='double tp=chart(m,w,14)-chart(m,w,5)-log(m->config->center[3]);\n  double tm=chart(m,w,15)-chart(m,w,5)-log(m->config->center[4]);'
  old2='double tp=chart(m,w,14)-chart(m,w,5)-log(m->config->center[3]),tm=chart(m,w,15)-chart(m,w,5)-log(m->config->center[4]);'
  assert s.count(old1)==1 and s.count(old2)==1
  for old in (old1,old2):s=s.replace(old,'double tp,tm;hys_coordinates(m,w,&tp,&tm);')
  helper+='static __attribute__((noinline,noclone)) void hys_coordinates(const model*m,const double*w,double*tp,double*tm){*tp=chart(m,w,14)-chart(m,w,5)-log(m->config->center[3]);*tm=chart(m,w,15)-chart(m,w,5)-log(m->config->center[4]);}\n'
 if variant in ('exp_chart','combined_scalar'):
  s,n=re.subn(r'exp\(chart\(m,w,([^()]*)\)\)',r'exp_chart(m,w,\1)',s);assert n==9,n
  helper+='static __attribute__((noinline,noclone)) double exp_chart(const model*m,const double*w,unsigned j){return exp(chart(m,w,j));}\n'
 marker='static double cheb(';assert s.count(marker)==1;s=s.replace(marker,helper+marker)
 p.write_text(s);return p

def adapt_probe(path,variant,prefix):base_probe(path,'byte_indices',prefix)
