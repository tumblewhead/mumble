from pathlib import Path
import re,json,struct,math
from experiments.response_base_001.build import generate as base,adapt_probe as base_probe
from .codec import encode,decode
VARIANTS=('baseline','raw','plane','xorplane','word','word_inline')
HERE=Path(__file__).resolve().parent

def generate(directory,variant='baseline',history_bits=48):
 p=base(directory,'contiguous',history_bits)
 if variant=='baseline':return p
 if variant in ('word','word_inline'):
  s=p.read_text().replace('typedef struct { const double *mean,*scale,*center,*projected_map; } fixed_config;',
   'typedef struct { double values[5]; unsigned char index[16]; } scale_dict;\nstatic __attribute__((noinline,noclone)) double cb_scale(const scale_dict*p,unsigned i){return p->values[p->index[i]];}\ntypedef struct { const double *mean;const scale_dict *scale;const double *center,*projected_map; } fixed_config;')
  s=re.sub(r'((?:m->|c->m\.)config->scale)\[([^\]]+)\]',r'cb_scale(\1,\2)',s)
  if variant=='word_inline':s=s.replace('static __attribute__((noinline,noclone)) double cb_scale','static inline double cb_scale')
  p.write_text(s);return p
 s=p.read_text();decoder=(HERE/'decoder.c.in').read_text()
 read={'raw':'bytes[k]=cb_byte(p,8*i+k);','plane':'bytes[k]=cb_byte(p,k*p[1]+i);','xorplane':'bytes[k]=0;for(unsigned j=0;j<=i;j++)bytes[k]^=cb_byte(p,k*p[1]+j);'}[variant]
 s=s.replace('typedef struct { const double *mean,*scale,*center,*projected_map; } fixed_config;',decoder.replace('@READ@',read)+'\ntypedef struct { const unsigned char *mean,*scale,*center,*projected_map; } fixed_config;')
 s=re.sub(r'((?:m->|c->m\.)config->(?:mean|scale|center))\[([^\]]+)\]',r'cb_get(\1,\2)',s)
 s=s.replace('const double *a=m->config->projected_map+13*pole;','const unsigned char *a=m->config->projected_map;')
 # Only spline uses a[]; restrict transform to that function.
 start=s.index('static void spline(');end=s.index('/* Shared ordered',start)
 s=s[:start]+re.sub(r'\ba\[([^\]]+)\]',r'cb_get(a,13*pole+\1)',s[start:end])+s[end:]
 s,n=re.subn(r'const double\s*\*V,','const unsigned char *V,',s);assert n==2
 s=re.sub(r'\bV\[([^\]]+)\]',r'cb_get(V,\1)',s)
 p.write_text(s);return p

def adapt_probe(path,variant,prefix):
 base_probe(path,'contiguous',prefix)
 if variant=='baseline':return
 h=path.parent/('config.h' if prefix=='config' else 'fixture.h');s=h.read_text();stats={}
 if variant in ('word','word_inline'):
  pat=r'static const double '+prefix+r'_scale\[16\]=\{([^}]+)\};';m=re.search(pat,s);assert m
  values=[float.fromhex(v) for v in m[1].split(',')];assert all(math.isfinite(v) and v>0 for v in values);unique=list(dict.fromkeys(values));assert len(unique)==5
  replacement='static const scale_dict '+prefix+'_scale_dict={{'+','.join(v.hex() for v in unique)+'},{'+','.join(str(unique.index(v)) for v in values)+'}};\n#define '+prefix+'_scale (&'+prefix+'_scale_dict)'
  h.write_text(s[:m.start()]+replacement+s[m.end():]);return

 for name in ('mean','scale','center','P','V'):
  pattern=r'static const double '+prefix+'_'+name+r'\[\d+\]=\{([^}]+)\};'
  m=re.search(pattern,s);assert m,name
  values=[float.fromhex(v) for v in m[1].split(',')];raw=b''.join(struct.pack('<d',v) for v in values)
  data=encode(values,variant);assert decode(data,variant)==raw
  stats[name]={'original':len(raw),'encoded':len(data),'rules':data[0]}
  s=s[:m.start()]+'static const unsigned char '+prefix+'_'+name+'['+str(len(data))+']={'+','.join(map(str,data))+'};'+s[m.end():]
 h.write_text(s);(path.parent/'codec.json').write_text(json.dumps(stats,indent=2)+'\n')
