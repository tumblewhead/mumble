from pathlib import Path
import random,struct,subprocess,hashlib,json,sys
sys.path.insert(0,str(Path.cwd()))
from experiments.constant_codebook_001.codec import encode
r=random.Random(90217)
patterns=[0,1,0x8000000000000000,0x7ff0000000000000,0xfff0000000000000,0x7ff8000000000001,0xffffffffffffffff]
sets={'edges':patterns*18,'zeros':[0]*132,'random':[r.getrandbits(64) for _ in range(132)],'max_count':[r.getrandbits(64) for _ in range(255)]}
results={};out=Path('/tmp/shared_constant_review')
for mode in ('raw','plane'):
 for label,words in sets.items():
  raw=b''.join(struct.pack('<Q',x) for x in words);values=list(struct.unpack('<'+'d'*len(words),raw));blob=encode(values,mode)
  core=(Path('experiments/shared_constant_block_001')/mode/'tiny_cardinal/core.c').read_text().split('typedef struct { const unsigned short *mean')[0]
  # The prefix includes the inherited core before first model struct; use decoder prefix only.
  end=core.index('static inline double cb_get');end=core.index('\n',end)
  core=core[:end]
  s=core+'\n#include <stdio.h>\nconst unsigned char cb_blob[]={'+','.join(map(str,blob))+'};\nint main(void){for(unsigned i=0;i<'+str(len(words))+';i++){double x=cb_at(i);fwrite(&x,8,1,stdout);}return 0;}\n'
  p=out/(mode+'_'+label+'.c');p.write_text(s);exe=p.with_suffix('');subprocess.run(['cc','-O2','-fsanitize=undefined',str(p),'-o',str(exe)],check=True)
  q=subprocess.run([str(exe)],capture_output=True,check=True);assert q.stdout==raw and not q.stderr
  results[mode+'_'+label]={'words':len(words),'sha256':hashlib.sha256(raw).hexdigest(),'blob_bytes':len(blob)}
(out/'decoder_result.json').write_text(json.dumps(results,indent=2));print(json.dumps(results))
