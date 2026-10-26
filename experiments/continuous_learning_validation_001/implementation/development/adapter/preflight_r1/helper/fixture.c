
#include "scm_hypothesis_checkpoint.h"
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
static scm_hypothesis b,saved;
static scm_hypothesis_workspace w;
static scm_hypothesis_query_result q;
static scm_hypothesis_config c;
static unsigned char buf[SCM_HYPOTHESIS_CHECKPOINT_BUFFER_BYTES];
static char path[512];
static int save(const char*dir,const char*name){
 int n=snprintf(path,sizeof path,"%s/%s.bin",dir,name);
 return n<0||(size_t)n>=sizeof path?-1:scm_hypothesis_checkpoint_save(&b,path,buf);
}
static int init(void){scm_hypothesis_config_default(&c);memset(c.source_id,0x11,sizeof c.source_id);return scm_hypothesis_init(&b,&c,SCM_HYPOTHESIS_PUBLIC_LOGQ_SPLIT);}
int main(int argc,char **argv){
 int j;unsigned char bad[32];scm_sample x={1./35.,.03,3.8};
 if(argc!=2||init())return 1;
 saved=b;
 for(j=-1;j<2;j++)if(scm_hypothesis_query(&b,j,&q)||memcmp(&saved,&b,sizeof b))return 2;
 memset(bad,0x22,sizeof bad);
 if(scm_hypothesis_ingest(&b,bad,0,&x,1,&w)!=SCM_ONLINE_ERR_SOURCE||memcmp(&saved,&b,sizeof b))return 3;
 if(scm_hypothesis_ingest(&b,c.source_id,1,&x,1,&w)!=SCM_ONLINE_ERR_ORDER||memcmp(&saved,&b,sizeof b))return 4;
 if(init())return 5;
 b.component[1].factor[SCM_HYPOTHESIS_FACTOR_INDEX(11,0)]=1e200;
 if(scm_hypothesis_validate(&b)||save(argv[1],"rejection"))return 6;
 if(init())return 7;
 b.component[1].mean[11]=0.;
 if(scm_hypothesis_validate(&b)||save(argv[1],"recovery"))return 8;
 if(init())return 9;
 memset(b.component[0].factor,0,sizeof b.component[0].factor);
 if(scm_hypothesis_ingest(&b,c.source_id,0,&x,1,&w)||scm_hypothesis_validate(&b))return 10;
 if(b.component[0].evidence_next_index!=0||b.component[1].evidence_next_index!=1||b.header.bank_evidence_next_index!=1)return 11;
 if(save(argv[1],"lag"))return 12;
 puts("{\"checks\":8,\"input_deliveries\":3,\"query_byte_purity\":true,\"source_order_atomicity\":true,\"fixtures_created\":3}");
 return 0;
}
