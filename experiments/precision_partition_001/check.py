"""Precision partition controls: expansion, accumulation, and weak directions."""
import argparse,json,subprocess,hashlib
from pathlib import Path
import numpy as np

def execute(folder,name,source):
 p=folder/(name+'.c');p.write_text(source);exe=folder/name
 subprocess.run(['cc','-std=c11','-O2','-fstrict-aliasing','-fno-fast-math','-ffp-contract=off','-fsanitize=undefined',str(p),'-lm','-o',str(exe)],check=True)
 r=subprocess.run([str(exe)],capture_output=True,check=True);assert not r.stderr,r.stderr;return r.stdout

def run(mixed,gram,out):
 mixed=Path(mixed).resolve();gram=Path(gram).resolve();out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
 # Direct production mixed collect vs the same float row expanded out-of-place.
 source='''#include "CORE"
#include "CONFIG"
#include <stdio.h>
static collector a,b;static history_store A[595],B[595];static float sa[93],sb[93];
static const fixed_config cfg={config_mean,config_scale,config_center,config_P};
int main(void){a.m=(model){&cfg,sa};b.m=(model){&cfg,sb};a.valid=b.valid=1;sa[0]=sb[0]=1;for(int j=15;j<54;j++)sa[j]=sb[j]=1;
 for(unsigned i=0;i<32768;i++){
 float o[5]={i%11?1.f/35.f:0,((int)((i/337)%9)-4)*.01f,25,3.7f,.002f};
 if(collect(&a,A,config_V,config_ocv,o)||stream_row(&b,config_V,config_ocv,o))return 1;
 double row[34];for(int j=0;j<34;j++)row[j]=b.row.f[j];
 if(history_insert(B,34,row)||memcmp(A,B,sizeof A)||memcmp(sa,sb,sizeof sa))return 2;
 }
 float bad[5]={-1,0,25,3.7f,.002f};if(collect(&a,A,config_V,config_ocv,bad)!=-1)return 3;
 if(memcmp(A,B,sizeof A)||memcmp(sa,sb,sizeof sa))return 4;
 bad[0]=.02f;if(collect(&a,A,config_V,config_ocv,bad)!=-1)return 5;
 if(memcmp(A,B,sizeof A)||memcmp(sa,sb,sizeof sa))return 6;
 return 0;}
'''.replace('CORE',str(mixed/'core.c')).replace('CONFIG',str(mixed/'config.h'))
 execute(out,'expansion',source)
 lanes={}
 for lane,root,real in [('mixed_QR',mixed,'double'),('paired_Gram',gram,'float')]:
  source='''#include "CORE"
#include <stdio.h>
int main(void){history_store H[1]={0};unsigned stops[]={1000000,10000000,20000000},next=0;for(unsigned i=1;i<=20000000;i++){
 REAL x[1]={1};if(history_insert(H,1,x))return 1;
 if(i==stops[next]){double g=history_get(H,0);VALUE;printf("%u %.17g\\n",i,g);next++;}}
 history_store weak[3]={0};REAL row[2]={1,1+0x1p-12};if(history_insert(weak,2,row))return 2;
 for(int j=0;j<3;j++)printf("%.17g\\n",history_get(weak,j));return 0;}
'''.replace('CORE',str(root/'core.c')).replace('REAL',real).replace('VALUE','g*=g' if lane=='mixed_QR' else '')
  raw=execute(out,lane,source).decode().splitlines();rows=[]
  for line in raw[:3]:
   n,v=line.split();rows.append({'updates':int(n),'information':float(v),'relative_error':float(v)/int(n)-1})
  p=np.array([float(x) for x in raw[3:]])
  if lane=='mixed_QR':R=np.array([[p[0],p[1]],[0,p[2]]]);G=R.T@R
  else:G=np.array([[p[0],p[1]],[p[1],p[2]]])
  v=np.array([-(1+2**-12),1.]);lanes[lane]={'repetition':rows,'weak_matrix':G.tolist(),'weak_direction_energy':float(v@G@v),'weak_eigenvalues':np.linalg.eigvalsh(G).tolist()}
 # Exactly represented float feature pair is rank one. Rounded products break it.
 result={'expansion_parity_samples':32768,'lanes':lanes,'status':'diagnostic_not_promoted','scope':'20M repeated unit rows plus one nearly collinear row; paired Gram has rounded binary32 products. No full inference, coverage or indefinite certificate.'}
 assert lanes['paired_Gram']['weak_direction_energy']<0
 assert abs(lanes['paired_Gram']['repetition'][-1]['relative_error'])<1e-6
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--mixed',required=True);p.add_argument('--gram',required=True);p.add_argument('--out',required=True);a=p.parse_args();run(a.mixed,a.gram,a.out)
