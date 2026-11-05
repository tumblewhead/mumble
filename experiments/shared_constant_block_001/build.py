from pathlib import Path
import re,json,struct
from experiments.response_base_001.build import generate as baseline,adapt_probe as base_probe
from experiments.constant_codebook_001.build import generate as encoded
from experiments.constant_codebook_001.codec import encode,decode
VARIANTS=('baseline','raw','plane','raw_literals','plane_literals')
NAMES=('mean','scale','center','P','V','ocv')
COUNTS=(16,16,5,39,39,2)
TOKEN=re.compile(r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|(?<![\w.])(?:0[xX](?:[0-9a-fA-F]+(?:\.[0-9a-fA-F]*)?|\.[0-9a-fA-F]+)[pP][+-]?\d+|(?:\d+\.\d*|\.\d+)(?:[eE][+-]?\d+)?|\d+[eE][+-]?\d+)(?![\w.])')

def generate(directory,variant='baseline',history_bits=48):
 if variant=='baseline':return baseline(directory,'contiguous',history_bits)
 mode=variant.split('_')[0];p=encoded(directory,mode,history_bits);s=p.read_text()
 begin=s.index('/* Trusted offline-generated');end=s.index('typedef struct { const unsigned char *mean',begin)
 s=s[:begin]+s[end:]
 s=s.replace('const unsigned char *mean,*scale,*center,*projected_map','const unsigned short *mean,*scale,*center,*projected_map')
 s=s.replace('const unsigned char *a=m->config->projected_map','const unsigned short *a=m->config->projected_map').replace('const unsigned char *V,','const unsigned short *V,')
 s,n=re.subn(r'const double\s*\*ocv,','const unsigned short *ocv,',s);assert n==2
 s=re.sub(r'\bocv\[([^\]]+)\]',r'cb_get(ocv,\1)',s)
 literals=[];bits=[]
 def replace(m):
  token=m[0]
  if token.startswith(('/', '"', "'")):return token
  v=float.fromhex(token) if token.lower().startswith('0x') else float(token);b=struct.pack('<d',v)
  if b not in bits:bits.append(b);literals.append(v.hex())
  return 'cb_at('+str(117+bits.index(b))+')'
 if variant.endswith('_literals'):
  s=TOKEN.sub(replace,s)
  mh=p.parent/'shared_math.h';mh.write_text(TOKEN.sub(replace,mh.read_text()))
 decoder=(Path(__file__).resolve().parents[1]/'constant_codebook_001/decoder.c.in').read_text()
 # Byte decoder retains explicit p; scalar accessor uses the one shared payload.
 decoder=decoder.replace('double cb_get(const unsigned char *p,unsigned i){','double cb_at(unsigned i){\n const unsigned char *p=cb_blob;')
 decoder=decoder.replace('@READ@','bytes[k]=cb_byte(p,'+('8*i+k' if mode=='raw' else 'k*p[1]+i')+');')
 prefix='#include <string.h>\nextern const unsigned char cb_blob[];\n'+decoder+'\nstatic inline double cb_get(const unsigned short *segment,unsigned i){return cb_at(*segment+i);}\n'
 p.write_text(prefix+s);(p.parent/'literals.json').write_text(json.dumps(literals,indent=2)+'\n');return p

def adapt_probe(path,variant,prefix):
 base_probe(path,'contiguous',prefix)
 if variant=='baseline':return
 mode=variant.split('_')[0];h=path.parent/('config.h' if prefix=='config' else 'fixture.h');s=h.read_text();values=[];offsets=[]
 for name,count in zip(NAMES,COUNTS):
  pat=r'static const double '+prefix+'_'+name+r'\[\d+\]=\{([^}]+)\};';m=re.search(pat,s);assert m,name
  v=[float.fromhex(x) for x in m[1].split(',')];assert len(v)==count
  offsets.append(len(values));values+=v;s=s[:m.start()]+s[m.end():]
 literals=json.loads((path.parent/'literals.json').read_text());values += [float.fromhex(x) for x in literals]
 blob=encode(values,mode);raw=b''.join(struct.pack('<d',x) for x in values);assert decode(blob,mode)==raw
 extra='const unsigned char cb_blob['+str(len(blob))+']={'+','.join(map(str,blob))+'};\n'
 extra+='static const unsigned short cb_segments[6]={'+','.join(map(str,offsets))+'};\n'
 for i,name in enumerate(NAMES):extra+='#define '+prefix+'_'+name+' (cb_segments+'+str(i)+')\n'
 h.write_text(extra+s);(path.parent/'codec.json').write_text(json.dumps({'tables_bytes':936,'literal_values':len(literals),'uncompressed_bytes':len(raw),'encoded_blob_bytes':len(blob),'descriptor_bytes':12,'rules':blob[0],'offsets':offsets},indent=2)+'\n')
