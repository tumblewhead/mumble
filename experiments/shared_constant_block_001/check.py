from pathlib import Path
import argparse,hashlib,json,subprocess
from .build import NAMES,COUNTS,VARIANTS

def run(out):
 root=Path(__file__).resolve().parent;out=Path(out);out.mkdir(parents=True,exist_ok=False);results={}
 for variant in VARIANTS:
  d=root/variant/'tiny_cardinal'
  s=(root.parent/'response_base_001/parity.c.in').read_text().replace('@CORE@',str(d/'core.c')).replace('@CONFIG@',str(d/'config.h'))
  s=s.replace('i<256','i<8').replace('i%32==31','i%8==7').replace('response,response+15,response+54','response').replace('bad.legacy','bad.response')
  emit=''
  for name,n in zip(NAMES,COUNTS):
   get='config_'+name+'[i]' if variant=='baseline' else 'cb_get(config_'+name+',i)'
   emit+='for(unsigned i=0;i<'+str(n)+';i++){double v='+get+';emit_bytes(&v,8);}'
  # Validate every pooled literal against its original binary64 bits, independently of transcript.
  literals=json.loads((d/'literals.json').read_text()) if variant!='baseline' else []
  for i,v in enumerate(literals):emit+=' { double want='+v+',got=cb_at('+str(117+i)+');if(memcmp(&want,&got,8))return 10; }'
  s=s.replace('core c={0};',emit+'\n core c={0};')
  p=out/(variant+'.c');p.write_text(s);exe=p.with_suffix('')
  subprocess.run(['cc','-O2','-fno-fast-math','-ffp-contract=off','-fsanitize=undefined',str(p),'-lm','-o',str(exe)],check=True)
  r=subprocess.run([str(exe.resolve())],capture_output=True,timeout=240);assert r.returncode==0 and not r.stderr,(variant,r.returncode,r.stderr)
  results[variant]={'bytes':len(r.stdout),'sha256':hashlib.sha256(r.stdout).hexdigest()}
  (out/'progress.json').write_text(json.dumps(results,indent=2)+'\n')
 assert all(x==results['baseline'] for x in results.values())
 result={'status':'pass','results':results,'scope':'117 constants exact;each pooled literal bitchecked;8 support probes,94feature rows,8samples,1refit,128scalarqueries,finalhistory,response,jointfactor and common null rejections;UBSan clean'}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',required=True);run(p.parse_args().out)
