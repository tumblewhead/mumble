from pathlib import Path
import argparse,hashlib,json,subprocess,re

def run(out):
 root=Path(__file__).resolve().parent;out=Path(out);out.mkdir(parents=True,exist_ok=False);results={}
 for variant,folder in [('baseline','baseline'),('raw','raw002'),('plane','plane002'),('xorplane','xorplane002'),('word','word'),('word_inline','word_inline')]:
  d=root/folder/'tiny_cardinal'
  s=(root.parent/'response_base_001/parity.c.in').read_text().replace('@CORE@',str(d/'core.c')).replace('@CONFIG@',str(d/'config.h'))
  s=s.replace('i<256','i<32')
  s=s.replace('response,response+15,response+54','response').replace('bad.legacy','bad.response')
  emit=''
  for name,n in [('mean',16),('scale',16),('center',5),('P',39),('V',39)]:
   get=('cb_scale(config_scale,i)' if name=='scale' else 'config_'+name+'[i]') if variant in ('word','word_inline') else ('config_'+name+'[i]' if variant=='baseline' else 'cb_get(config_'+name+',i)')
   emit+='for(unsigned i=0;i<'+str(n)+';i++){double v='+get+';emit_bytes(&v,8);}'
  s=s.replace('core c={0};',emit+'\n core c={0};')
  p=out/(variant+'.c');p.write_text(s);exe=p.with_suffix('')
  subprocess.run(['cc','-O2','-fno-fast-math','-ffp-contract=off','-fsanitize=undefined',str(p),'-lm','-o',str(exe)],check=True)
  r=subprocess.run([str(exe.resolve())],capture_output=True,timeout=180);assert r.returncode==0 and not r.stderr,(variant,r.returncode,r.stderr)
  results[variant]={'bytes':len(r.stdout),'sha256':hashlib.sha256(r.stdout).hexdigest()}
 assert all(x==results['baseline'] for x in results.values())
 result={'status':'pass','results':results,'scope':'115 binary64 constants exact;32 support probes,94 feature rows,32 samples,1refit,512scalarqueries,finalhistory,response,jointfactor and common null rejections;UBSan clean'}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',required=True);run(p.parse_args().out)
