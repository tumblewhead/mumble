from pathlib import Path
import argparse,hashlib,json,subprocess

def run(out):
 root=Path(__file__).resolve().parent;out=Path(out);out.mkdir(parents=True,exist_ok=False);results={}
 for variant in ('baseline','hys_scalar','hys_pair','exp_chart','combined_scalar'):
  results[variant]={};d=root/variant/'tiny_cardinal'
  for kind in ('parity','invalid','numeric'):
   template=(root.parent/'constant_storage_001/numeric.c.in') if kind=='numeric' else (root.parent/'response_base_001'/(kind+'.c.in'))
   s=template.read_text().replace('@CORE@',str(d/'core.c')).replace('@CONFIG@',str(d/'config.h'))
   s=s.replace('response,response+15,response+54','response').replace('bad.legacy','bad.response')
   p=out/(variant+'_'+kind+'.c');p.write_text(s);exe=p.with_suffix('')
   subprocess.run(['cc','-O2','-fno-fast-math','-ffp-contract=off','-fsanitize=undefined',str(p),'-lm','-o',str(exe)],check=True)
   r=subprocess.run([str(exe.resolve())],capture_output=True);assert r.returncode==0 and not r.stderr,(variant,kind,r.returncode,r.stderr)
   results[variant][kind]={'bytes':len(r.stdout),'sha256':hashlib.sha256(r.stdout).hexdigest()}
   if kind=='invalid':results[variant][kind]['output']=r.stdout.decode()
 assert all(v==results['baseline'] for v in results.values())
 result={'status':'pass','results':results,'scope':'Also4096samples32refits512scalarqueryattemptsacross32frames,projectedmap257pointsand34featurerows64points;256 support probes,94feature rows,256samples,8refits,4096scalarqueries,finalhistory,response,jointfactor;159invalidbindings preserve bound core;UBSan clean'}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',required=True);run(p.parse_args().out)
