from pathlib import Path
from experiments.qr_sharing_001.build import generate as base
VARIANTS=('baseline','shared')
def generate(directory,variant='shared',history_bits=48):
 p=base(directory,'shared_loop',history_bits);s=p.read_text()
 if variant=='shared':
  marker='/* Writes only a fully computed finite step; invalid inference refuses queries. */'
  helper='''static __attribute__((noinline,noclone)) int triangular(inference*s,const double*gradient,double*total){
 double*y=s->scratch.y;int transpose=gradient!=0;
 for(int k=0;k<16;k++){
  int i=transpose?k:15-k;
  double x=transpose?gradient[i]:-s->factor[index_of(17,i,16)];
  for(int j=transpose?0:i+1;j<(transpose?i:16);j++)
   x-=s->factor[transpose?index_of(17,j,i):index_of(17,i,j)]*y[j];
  y[i]=x/s->factor[index_of(17,i,i)];
  if(transpose)*total+=y[i]*y[i];else if(!isfinite(y[i]))return -1;
 }
 return 0;
}
'''
  assert s.count(marker)==1;s=s.replace(marker,helper+marker)
  a=s.index(' for(int i=15;i>=0;i--){');b=s.index(' memcpy(out,y,16*sizeof(double));',a)
  s=s[:a]+' if(triangular(s,0,0))goto failed;\n'+s[b:]
  a=s.index(' double *y=s->scratch.y,total=0;');b=s.index(' if(!isfinite(total))goto failed;',a)
  s=s[:a]+' double total=0;\n triangular(s,gradient,&total);\n'+s[b:]
 elif variant!='baseline':raise ValueError(variant)
 p.write_text(s);return p
