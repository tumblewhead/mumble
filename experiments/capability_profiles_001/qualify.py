"""Finite parity and precision diagnostics; not long-run uncertainty certification."""
import argparse,hashlib,json,subprocess
from pathlib import Path
from unittest.mock import patch
import numpy as np
from experiments.two_processor_size_001 import check

HARNESS=r'''
#include "core.c"
#include "config.h"
#include <stdio.h>
static collector c;
static history_store history[595];
static REAL response[93];
static const fixed_config cfg={config_mean,config_scale,config_center,config_P};
int main(void){
 c.m.config=&cfg;c.m.response=response;c.valid=1;
 response[0]=1;for(unsigned j=15;j<54;j++)response[j]=1;
 for(unsigned i=0;i<SAMPLES;i++){
  /* Exact integer driven load identity across arithmetic lanes. */
  double current=((int)((i/337)%9)-4)*.01;
  if((i/8192)%3==2)current=0;
  REAL o[5]={.02,current,25,3.7+current*.1,.002};
  if(collect(&c,history,config_V,config_ocv,o))return 1;
  if((i+1)%4096==0){
   double out[688];for(unsigned j=0;j<595;j++)out[j]=history_get(history,j);
   for(unsigned j=0;j<93;j++)out[595+j]=response[j];
   if(fwrite(out,sizeof(out),1,stdout)!=1)return 2;
  }
 }
 REAL bad[5]={-1,0,25,3.7,.002};
 if(collect(&c,history,config_V,config_ocv,bad)!=-1)return 3;
 history_store saved[595];memcpy(saved,history,sizeof saved);
 REAL previous[93];memcpy(previous,response,sizeof previous);
 bad[0]=.02;if(collect(&c,history,config_V,config_ocv,bad)!=-1)return 4;
 if(memcmp(saved,history,sizeof saved)||memcmp(previous,response,sizeof previous))return 5;
 return 0;
}
'''
def run(baseline,trial,out,samples):
 baseline=Path(baseline).resolve();trial=Path(trial).resolve();out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
 with patch.object(check,'ROOT',baseline):check.run(out/'parity')
 values={};hashes={}
 for lane,folder,real in [('double',baseline/'collector','double'),('float',trial/'collector','float')]:
  s=HARNESS.replace('"core.c"','"'+str(folder/'core.c')+'"').replace('"config.h"','"'+str(folder/'config.h')+'"').replace('REAL',real).replace('SAMPLES',str(samples))
  src=out/(lane+'.c');src.write_text(s);exe=out/lane
  subprocess.run(['cc','-O2','-fno-fast-math','-ffp-contract=off','-fsanitize=undefined',str(src),'-lm','-o',str(exe)],check=True)
  r=subprocess.run([str(exe)],capture_output=True,check=True);assert not r.stderr,r.stderr
  values[lane]=np.frombuffer(r.stdout,dtype='<f8').reshape(-1,688);hashes[lane]=hashlib.sha256(r.stdout).hexdigest()
 a,b=values['double'],values['float'];delta=b-a
 # Compare represented information action at fixed deterministic directions.
 # These are diagnostics, not fitted parameter differences or validated intervals.
 actions=[];direction=np.sin(np.arange(34)+.3)
 for row_a,row_b in zip(a,b):
  R=np.zeros((34,34));S=R.copy();ix=np.triu_indices(34);R[ix]=row_a[:595];S[ix]=row_b[:595]
  gram=R.T@R;other=S.T@S
  actions.append({'relative_Gram_Frobenius':float(np.linalg.norm(other-gram)/np.linalg.norm(gram)), 'fixed_direction_energy_relative_error':float(abs(np.linalg.norm(S@direction)**2/np.linalg.norm(R@direction)**2-1))})
 record={'samples':samples,'duration_s':samples*.02,'status':'finite_diagnostic_complete_not_long_run_qualification','stream_sha256':hashes,'double_profile_parity':json.loads((out/'parity/result.json').read_text()),'checkpoints':actions,'max_response_absolute_difference':float(np.max(abs(delta[:,595:]))),'max_charge_Ah_absolute_difference':float(np.max(abs(delta[:,607]))),'final_charge_Ah_difference':float(delta[-1,607]),'float_min_diagonal':float(min(b[-1,:595][np.cumsum([0]+list(range(34,1,-1)))])),'scope':'Binary32 trial changes config, interfaces, recurrence, QR and history. No fitting, uncertainty, weak-direction guarantee, long-duration or physical-accuracy acceptance.'}
 (out/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps({k:v for k,v in record.items() if k not in ('checkpoints','double_profile_parity')}))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--baseline',required=True);p.add_argument('--trial',required=True);p.add_argument('--out',required=True);p.add_argument('--samples',type=int,default=131072);a=p.parse_args()
 if a.samples<4096 or a.samples%4096:p.error('samples must be a positive multiple of 4096')
 run(a.baseline,a.trial,a.out,a.samples)
