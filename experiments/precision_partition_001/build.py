"""Binary32 stream recurrence with binary64 QR and packed 48-bit history."""
from pathlib import Path
from experiments.two_processor_size_001.build import generate as original, function
from experiments.capability_profiles_001.build import convert_float


def generate(out,variant,arithmetic=None):
 if variant not in ('collector','soc'):raise ValueError('precision partition supports collector/SOC')
 p=original(out,variant);s=p.read_text()
 row=convert_float(function(s,'stream_row')).replace('c->phi','c->row.f')
 headers='\n'.join(x for x in s.splitlines() if x.startswith('#include') and 'shared_' in x)
 # History helpers are preprocessed against binary64 math before float aliases.
 out32=Path(out)/'math32.h'
 out32.write_text((Path(__file__).parents[1]/'capability_profiles_001/math32.h').read_text())
 text=headers+'\n'
 text+='\n'.join('#undef '+x for x in ('exp','expm1','log','sqrt','hypot','tanh','atanh','nextafter','ldexp','fmax'))+'\n'
 text+='#include "math32.h"\n'
 text+='typedef struct {const float *mean,*scale,*center,*projected_map;} fixed_config;\n'
 text+='typedef struct {const fixed_config *config;float *response;} model;\n'
 text+='typedef struct {model m;union {float f[34];double d[34];} row;unsigned valid;} collector;\n'
 text+=row+'\n'
 text+='''static int collect(collector*c,history_store*history,const float*V,const float*ocv,const float*o){
 if(!c->valid)return -1;
 if(stream_row(c,V,ocv,o)){c->valid=0;return -1;}
 /* Expand backwards in the same scratch area: every source is read before
    any overlapping destination write. memcpy avoids pointer alias assumptions. */
 for(int j=33;j>=0;j--){float f;memcpy(&f,(unsigned char*)&c->row+sizeof(float)*j,sizeof f);double d=f;memcpy((unsigned char*)&c->row+sizeof(double)*j,&d,sizeof d);}
 if(history_insert(history,34,c->row.d)){c->valid=0;return -1;}
 return 0;
}
'''
 if variant=='soc':text+=convert_float(function(s,'predict_soc'))+'\n'
 p.write_text(text);return p


def generate_gram(out,variant,arithmetic=None):
 from experiments.capability_profiles_001.build import generate as float_base
 p=float_base(out,variant,'float')
 (Path(out)/'shared_history.h').write_text(Path(__file__).with_name('paired_gram.h').read_text())
 return p


def generate_storage(out,variant,arithmetic=None):
 """Float response storage, double intermediates and QR: one arithmetic runtime."""
 if variant!='collector':raise ValueError('storage-only trial supports collector only')
 p=original(out,variant);s=p.read_text()
 s=s.replace('const double *mean,*scale,*center,*projected_map','const float *mean,*scale,*center,*projected_map').replace('double *response','float *response')
 for name in ('V','ocv','o'):s=s.replace('const double*'+name,'const float*'+name)
 old='double *s=(double*)(c->m.response),*free=(double*)(c->m.response+15),*forced=(double*)(c->m.response+54);'
 assert s.count(old)==1;s=s.replace(old,old.replace('double','float'))
 s=s.replace('double*v=s+6*kind,old0','float*v=s+6*kind;double old0').replace('const double*v=s+6*(1-kind)','const float*v=s+6*(1-kind)')
 # Avoid float arithmetic before promotion in the only multi-state expression.
 s=s.replace('(v[0]+.25*v[3]+.25*v[5])','((double)v[0]+.25*v[3]+.25*v[5])')
 for a,b in [('-ocv[1]*s[12]','-(double)ocv[1]*s[12]'),('free[ix]*V[','(double)free[ix]*V['),('forced[ix]*V[','(double)forced[ix]*V['),('(ocv[0]-o[3])','((double)ocv[0]-o[3])')]:
  assert a in s;s=s.replace(a,b)
 p.write_text(s);return p
