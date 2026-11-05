import argparse,json,subprocess
from pathlib import Path
import numpy as np

def run(out,folders):
 out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False);results={}
 for name,folder in zip(('digit','cordic'),folders):
  folder=Path(folder).resolve();src='''#include "CORE"
#include "config.h"
#include <stdio.h>
static collector c,ref;static float state[93],copy[93];static history_store H[595];static double G[595];
static const fixed_config cfg={config_mean,config_scale,config_center,config_P};
int main(void){c.m=(model){&cfg,state};ref.m=(model){&cfg,copy};c.valid=ref.valid=1;state[0]=1;for(int j=15;j<54;j++)state[j]=1;
 for(unsigned i=0;i<4096;i++){
 float o[5]={.02f,((int)((i/31)%9)-4)*.005f,25,3.7f,.002f};memcpy(copy,state,sizeof state);
 if(stream_row(&ref,config_V,config_ocv,o)||collect(&c,H,config_V,config_ocv,o))return 1;
 unsigned p=0;for(int j=0;j<34;j++)for(int k=j;k<34;k++)G[p++]+=(double)ref.phi[j]*ref.phi[k];
 }
 double r[595];for(int j=0;j<595;j++)r[j]=history_get(H,j);
 if(fwrite(r,sizeof r,1,stdout)!=1||fwrite(G,sizeof G,1,stdout)!=1)return 2;
 return 0;}
'''.replace('CORE',str(folder/'core.c'))
  p=out/(name+'.c');p.write_text(src);exe=out/name;subprocess.run(['cc','-std=c11','-O2','-fsanitize=undefined','-fno-fast-math','-ffp-contract=off','-I'+str(folder),str(p),'-lm','-o',str(exe)],check=True)
  r=subprocess.run([str(exe)],capture_output=True,check=True);assert not r.stderr,r.stderr
  a=np.frombuffer(r.stdout,dtype='<f8');R=np.zeros((34,34));G=R.copy();ix=np.triu_indices(34);R[ix]=a[:595];G[ix]=a[595:];G=G+G.T-np.diag(np.diag(G));results[name]={'relative_Gram_error':float(np.linalg.norm(R.T@R-G)/np.linalg.norm(G)),'samples':4096,'scope':'Float-generated features vs accumulated integer history, no fitted parameter/coverage claims'}
 (out/'result.json').write_text(json.dumps(results,indent=2)+'\n');print(results)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--digit',required=True);p.add_argument('--cordic',required=True);a=p.parse_args();run(a.out,[a.digit,a.cordic])
