"""Finite stream comparison; does not fit parameters or certify uncertainty."""
from pathlib import Path
import argparse,json
import numpy as np
from .check import execute

def run(out,baseline,mixed,storage,gram):
 out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False);values={}
 for name,folder,real in [('baseline',baseline,'double'),('mixed',mixed,'float'),('storage',storage,'float'),('gram',gram,'float')]:
  folder=Path(folder).resolve()
  code='''#include "CORE"
#include "CONFIG"
#include <stdio.h>
static collector c;static history_store H[595];static REAL response[93];
static const fixed_config cfg={config_mean,config_scale,config_center,config_P};
int main(void){c.m=(model){&cfg,response};c.valid=1;response[0]=1;for(int j=15;j<54;j++)response[j]=1;
 for(unsigned i=0;i<32768;i++){
 float samples[5]={i%11?1.f/35.f:0,((int)((i/337)%9)-4)*.01f,25,3.7f,.002f};
 REAL o[5];for(int j=0;j<5;j++)o[j]=samples[j];
 if(collect(&c,H,config_V,config_ocv,o))return 1;
 }
 double out[688];for(int j=0;j<595;j++)out[j]=history_get(H,j);for(int j=0;j<93;j++)out[595+j]=response[j];
 if(fwrite(out,sizeof out,1,stdout)!=1)return 2;
 history_store previous[595];REAL before[93];memcpy(previous,H,sizeof H);memcpy(before,response,sizeof response);
 REAL bad[5]={-1,0,25,3.7f,.002f};if(collect(&c,H,config_V,config_ocv,bad)!=-1)return 3;
 bad[0]=.02f;if(collect(&c,H,config_V,config_ocv,bad)!=-1)return 4;
 if(memcmp(previous,H,sizeof H)||memcmp(before,response,sizeof response))return 5;
 return 0;}
'''.replace('CORE',str(folder/'core.c')).replace('CONFIG',str(folder/'config.h')).replace('REAL',real)
  values[name]=np.frombuffer(execute(out,name,code),dtype='<f8');assert len(values[name])==688
 def matrix(name):
  R=np.zeros((34,34));ix=np.triu_indices(34);R[ix]=values[name][:595]
  return R+R.T-np.diag(np.diag(R)) if name=='gram' else R.T@R
 G=matrix('baseline');rec={}
 for name in ('mixed','storage','gram'):
  rec[name]={'max_response_absolute_difference_mixed_units':float(np.max(abs(values[name][595:]-values['baseline'][595:]))),'charge_difference_Ah':float(values[name][607]-values['baseline'][607]),'relative_Gram_Frobenius_difference':float(np.linalg.norm(matrix(name)-G)/np.linalg.norm(G))}
 result={'samples':32768,'nominal_rate_Hz':35,'zero_dt_every':11,'comparisons_to_baseline':rec,'scope':'Same float-representable inputs to all lanes; configuration and recurrence precision differ; no parameter fits/coverage.'}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':
 p=argparse.ArgumentParser();[p.add_argument('--'+n,required=True) for n in ('out','baseline','mixed','storage','gram')];a=p.parse_args();run(a.out,a.baseline,a.mixed,a.storage,a.gram)
