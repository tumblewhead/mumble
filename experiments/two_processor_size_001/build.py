from pathlib import Path
import re
from experiments.coordinate_sharing_001.build import generate as base
VARIANTS=('collector','soc','predictor')

def function(source,name):
 m=re.search(r'(?m)^[^\n]*\b'+name+r'\([^;\n]*\)\s*\{',source);assert m,name
 start=m.start();i=m.end();depth=1
 while depth:
  if source[i]=='{':depth+=1
  if source[i]=='}':depth-=1
  i+=1
 return source[start:i]

def generate(directory,variant):
 assert variant in VARIANTS
 p=base(directory,'combined_scalar',48);s=p.read_text()
 headers='\n'.join(x for x in s.splitlines() if x.startswith('#include') and ('shared_math.h' in x or 'shared_history.h' in x))
 out=headers+'\n#include <stddef.h>\n'
 out+='typedef struct {const double *mean,*scale,*center,*projected_map;} fixed_config;\ntypedef struct {const fixed_config *config;double *response;} model;\n'
 out+='typedef struct { model m;double phi[34];unsigned valid;'+('double point[16];' if variant=='predictor' else '')+'} collector;\n'
 out+=function(s,'stream_row').replace('core*c','collector*c').replace('c->qr.lease.valid','c->valid')+'\n'
 out+='''static int collect(collector*c,history_store*history,const double*V,const double*ocv,const double*o){
 if(!c->valid)return -1;
 if(stream_row(c,V,ocv,o)||history_insert(history,34,c->phi)){c->valid=0;return -1;}
 return 0;
}
'''
 if variant=='soc':
  out+='''static int predict_soc(collector*c,const double*parameters,double*out){
 if(!c->valid||!isfinite(parameters[0])||!isfinite(parameters[1])||!(parameters[1]>0))return -1;
 double z=parameters[0]-parameters[1]*c->m.response[12];
 if(!isfinite(z)||z<0||z>1)return -1;*out=z;return 0;
}
'''
 if variant=='predictor':
  for name in ('chart','hys_coordinate','exp_chart','cardinal','spline','rc_tau','supported','transported'):
   out+=function(s,name).replace('core *c','collector *c')+'\n'
  out+='''static int predict(collector*c,double*out,double*gradient){
 if(!c->valid||supported(&c->m,c->point))return -1;
 for(unsigned j=0;j<16;j++)if(transported(c,j,out+j,gradient))return -1;
 return out[0]<0||out[0]>1?-1:0;
}
'''
 p.write_text(out);return p
