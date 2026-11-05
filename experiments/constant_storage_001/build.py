from experiments.response_base_001.build import generate as base,adapt_probe as base_probe
import re,struct,json
VARIANTS=('baseline','byte_indices','f32_coefficients')
def generate(directory,variant='baseline',history_bits=48):
 assert variant in VARIANTS
 p=base(directory,'contiguous',history_bits);s=p.read_text()
 if variant!='baseline':
  old='static const unsigned ip[6]';assert s.count(old)==1;s=s.replace(old,'static const unsigned char ip[6]')
 if variant=='f32_coefficients':
  old='const double *mean,*scale,*center,*projected_map;';assert s.count(old)==1;s=s.replace(old,'const double *mean,*scale,*center;const float *projected_map;')
  old='const double *a=m->config->projected_map+13*pole;';assert s.count(old)==1;s=s.replace(old,'const float *a=m->config->projected_map+13*pole;')
  start=s.index('static void spline(');end=s.index('/* Shared ordered',start)
  s=s[:start]+re.sub(r'\ba\[([^\]]+)\]',r'((double)a[\1])',s[start:end])+s[end:]
  s,n=re.subn(r'const double\s*\*V,','const float *V,',s);assert n==2
  s=re.sub(r'\bV\[([^\]]+)\]',r'((double)V[\1])',s)
 p.write_text(s);return p

def adapt_probe(path,variant,prefix):
 base_probe(path,'contiguous',prefix)
 if variant!='f32_coefficients':return
 h=path.parent/('config.h' if prefix=='config' else 'fixture.h');s=h.read_text();stats={}
 for name in ('P','V'):
  pat=r'static const double '+prefix+'_'+name+r'\[39\]=\{([^}]+)\};';m=re.search(pat,s);assert m,name
  old=[float.fromhex(x) for x in m[1].split(',')];new=[struct.unpack('<f',struct.pack('<f',x))[0] for x in old]
  replacement='static const float '+prefix+'_'+name+'[39]={'+','.join(x.hex()+'f' for x in new)+'};'
  s=s[:m.start()]+replacement+s[m.end():];stats[name]={'max_abs_error':max(abs(x-y) for x,y in zip(old,new)),'coefficient_l1_error':sum(abs(x-y) for x,y in zip(old,new))}
 h.write_text(s);(path.parent/'rounding.json').write_text(json.dumps(stats,indent=2)+'\n')
