from pathlib import Path
import subprocess,hashlib,json
root=Path(__file__).resolve().parents[3]/'experiments/integer_qr_001'
out=Path('/tmp/integer_qr_review');out.mkdir(parents=True,exist_ok=True)
body=r'''
#include <stdio.h>
#include <assert.h>
#include <math.h>
#include <string.h>
static uint64_t seed=713;
static uint32_t rng(void){seed=seed*UINT64_C(6364136223846793005)+1;return seed>>32;}
int main(void){
 int32_t R[595],x[34],old[595];
 for(unsigned z=0;z<3000;z++){
  unsigned n=1+rng()%34,nn=n*(n+1)/2,p=0;
  int32_t bound=(z%3==0)?IQ_LIMIT:((z%3==1)?65536:8);
  for(unsigned i=0;i<nn;i++)R[i]=(int32_t)(rng()%(2u*bound+1))-bound;
  for(unsigned i=0;i<n;i++){R[p]=R[p]<0?-R[p]:R[p];p+=n-i;x[i]=(int32_t)(rng()%(2u*bound+1))-bound;}
  int rc=iq_insert(R,n,x);assert(rc==0||rc==-1);
  if(!rc)for(unsigned i=0;i<nn;i++)assert(iq_bound(R[i]));
 }
 memset(R,0,sizeof R);memcpy(old,R,sizeof R);memset(x,0,sizeof x);x[33]=IQ_LIMIT+1;
 assert(iq_insert(R,34,x)==-1);assert(memcmp(old,R,sizeof R)==0);
 assert(iq_insert(R,0,x)==-1);assert(iq_insert(R,35,x)==-1);
 R[0]=1;R[1]=1000000;R[2]=0;x[0]=1;x[1]=-1000000;
 assert(iq_insert(R,2,x)==0);printf("small_pivot %d %d %d\n",R[0],R[1],R[2]);
 int32_t edges[]={0,1,-1,IQ_LIMIT,-IQ_LIMIT,IQ_LIMIT-1,-IQ_LIMIT+1};
 for(unsigned a=0;a<7;a++)for(unsigned b=0;b<7;b++)for(unsigned c=0;c<7;c++)for(unsigned d=0;d<7;d++){
  R[0]=edges[a]<0?-edges[a]:edges[a];R[1]=edges[b];R[2]=0;x[0]=edges[c];x[1]=edges[d];
  iq_insert(R,2,x);
 }
 R[0]=1;R[1]=1000000;R[2]=0;x[0]=0;x[1]=0;assert(iq_insert(R,2,x)==0);assert(R[0]==1&&R[1]==1000000&&R[2]==0);printf("controls_passed\n");return 0;
}
'''
results={}
for kind in (0,1):
 src=out/f'check{kind}.c';src.write_text(f'#define CORDIC_KIND {kind}\n#include "{root}/kernel.h"\n'+body)
 cmd=['cc','-std=c11','-O2','-fsanitize=undefined','-fno-sanitize-recover=all',str(src),'-lm','-o',str(out/f'check{kind}')]
 subprocess.run(cmd,check=True)
 p=subprocess.run([str(out/f'check{kind}')],capture_output=True,text=True)
 results[kind]={'compile':cmd,'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
 assert p.returncode==0,results
results['source_sha256']=hashlib.sha256((root/'kernel.h').read_bytes()).hexdigest()
(out/'corrected_result.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results,indent=2))
