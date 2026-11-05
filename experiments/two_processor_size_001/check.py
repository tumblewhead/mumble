from pathlib import Path
import json,subprocess,hashlib,argparse
ROOT=Path(__file__).resolve().parent

def run(out):
 out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False);results={};predictions={}
 for variant in ('full','collector','soc','predictor'):
  d=ROOT/variant/('tiny_cardinal' if variant=='full' else '')
  source='''#include "CORE"
#include "CONFIG"
#include <stdio.h>
static void emit_bytes(const void*p,size_t n){if(fwrite(p,1,n,stdout)!=n)__builtin_trap();}
int main(void){
 TYPE c={0};history_store history[595]={0};double response[93]={0};
 static const fixed_config cfg={config_mean,config_scale,config_center,config_P};
 model m={&cfg,response};response[0]=1;for(unsigned j=15;j<54;j++)response[j]=1;
 SETUP
 for(unsigned i=0;i<512;i++){
  double o[5]={.02,((int)(i%17)-8)*.005,25,3.7,.002};
  int rc=INGEST;emit_bytes(&rc,sizeof rc);if(rc)return 3;
  if(i%32==31){emit_bytes(history,sizeof history);emit_bytes(response,sizeof response);}
 }
 PREDICT
 double bad[5]={-1,0,25,3.7,.002};int rc=BAD;emit_bytes(&rc,sizeof rc);if(rc!=-1)return 4;
 history_store before[595];memcpy(before,history,sizeof before);double previous[93];memcpy(previous,response,sizeof previous);
 bad[0]=.02;rc=BAD;emit_bytes(&rc,sizeof rc);if(rc!=-1||memcmp(before,history,sizeof before)||memcmp(previous,response,sizeof previous))return 5;
 return 0;
}
'''.replace('CORE',str(d/'core.c')).replace('CONFIG',str(d/'config.h'))
  full=variant=='full';source=source.replace('TYPE','core' if full else 'collector').replace('SETUP','if(bind(&c,&m)||initialize(&c,history,c.anchor))return 2;' if full else 'c.m=m;c.valid=1;')
  fn='stream_ingest' if full else 'collect';source=source.replace('INGEST',fn+'(&c,history,config_V,config_ocv,o)').replace('BAD',fn+'(&c,history,config_V,config_ocv,bad)')
  # Compare point predictions against the original transport helpers, separately from history bytes.
  prediction=''
  if variant=='soc':prediction='double p[2]={config_mean[0],exp(-config_mean[5])},v;if(predict_soc(&c,p,&v))return 6;double expected=config_mean[0]-p[1]*response[12];if(memcmp(&v,&expected,8))return 7;'
  if variant=='predictor':prediction='double values[16],g[16];if(predict(&c,values,g))return 6;emit_bytes(values,sizeof values);'
  if full:prediction='double values[16],g[16];if(supported(&c.m,c.point))return 6;for(unsigned j=0;j<16;j++)if(transported(&c,j,values+j,g))return 6;emit_bytes(values,sizeof values);'
  source=source.replace('PREDICT',prediction)
  p=out/(variant+'.c');p.write_text(source);exe=p.with_suffix('');subprocess.run(['cc','-O2','-fno-fast-math','-ffp-contract=off','-fsanitize=undefined',str(p),'-lm','-o',str(exe)],check=True)
  r=subprocess.run([str(exe)],capture_output=True);assert r.returncode==0 and not r.stderr,(variant,r.returncode,r.stderr)
  data=r.stdout
  if variant in ('full','predictor'):predictions[variant]=hashlib.sha256(data[-136:-8]).hexdigest();data=data[:-136]+data[-8:]
  results[variant]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
 assert all(v==results['full'] for v in results.values())
 assert predictions['full']==predictions['predictor']
 result={'prediction_sha256':predictions,'status':'pass','results':results,'scope':'512 valid ordered samples;history andresponse checkpoints every32 identical tofullsolver;negative-dt rejection andpoisonedstreamrefusal preserve buffers. Not equivalent inference-failure gating;noactualIPC.'}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',required=True);run(p.parse_args().out)
