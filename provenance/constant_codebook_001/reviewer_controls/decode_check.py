import ctypes,struct,random,re,subprocess,json,hashlib,sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from experiments.constant_codebook_001.codec import encode
root=Path('/tmp/codebook_review');root.mkdir(exist_ok=True)
template=Path('experiments/constant_codebook_001/decoder.c.in').read_text()
rng=random.Random(83472); arrays=[]
s=Path('experiments/constant_codebook_001/baseline/tiny_cardinal/config.h').read_text()
for name,body in re.findall(r'static const double config_(mean|scale|center|P|V)\[\d+\]=\{([^}]+)\};',s):
 arrays.append((name,[float.fromhex(x) for x in body.split(',')]))
for n in [1,2,5,16,39,169,255]:
 for style in range(4):
  raw=bytes(rng.randrange(256) if style==0 else rng.choice([0,0,0,1,255]) if style==1 else 0 if style==2 else (i%8) for i in range(8*n))
  arrays.append((f'fuzz{n}_{style}',list(struct.unpack('<'+'d'*n,raw))))
results={}
for mode,read in [('raw','bytes[k]=cb_byte(p,8*i+k);'),('plane','bytes[k]=cb_byte(p,k*p[1]+i);'),('xorplane','bytes[k]=0;for(unsigned j=0;j<=i;j++)bytes[k]^=cb_byte(p,k*p[1]+j);')]:
 src='#include <string.h>\n'+template.replace('@READ@',read)+'\nvoid get(const unsigned char *p,unsigned i,unsigned char *out){double v=cb_get(p,i);memcpy(out,&v,8);}\n'
 c=root/(mode+'.c');c.write_text(src);so=root/(mode+'.so')
 subprocess.run(['gcc','-std=c99','-O2','-Wall','-Wextra','-Werror','-shared','-fPIC',str(c),'-o',str(so)],check=True)
 lib=ctypes.CDLL(str(so));lib.get.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_void_p]
 count=0
 for name,values in arrays:
  blob=encode(values,mode); b=ctypes.create_string_buffer(blob); output=ctypes.create_string_buffer(8)
  # Independent grammar validation: unique reserved symbols, backward-only links, declared lengths.
  nr,n=blob[:2]; rules={}; lengths={i:1 for i in range(256)}
  for r in range(nr):
   token,left,right,length=blob[2+4*r:6+4*r]
   assert token not in rules and token not in (left,right)
   assert length==lengths[left]+lengths[right]
   rules[token]=(left,right);lengths[token]=length
  for i,value in enumerate(values):
   lib.get(b,i,output)
   assert output.raw==struct.pack('<d',value),(mode,name,i)
   count+=1
 results[mode]={'arrays':len(arrays),'scalar_reads':count,'exact':True}
print(json.dumps(results,indent=2))
(root/'result.json').write_text(json.dumps(results,indent=2)+'\n')
