#include "/home/easy/proj/mumble/.worktrees/qr-sharing/experiments/collector_structure_001/lazy002/core.c"
#include "/home/easy/proj/mumble/.worktrees/qr-sharing/experiments/collector_structure_001/lazy002/config.h"
#include <stdio.h>
static collector c;static float s[54];static history_store H[595];
static const fixed_config cfg={config_mean,config_scale,config_center,config_P};
static void init(uint64_t t){memset(&c,0,sizeof c);memset(s,0,sizeof s);memset(H,0,sizeof H);c.m=(model){&cfg,s};c.valid=1;c.ticks=t;s[0]=1;}
static int one(float dt,uint64_t before,int want,uint64_t after){init(before);float o[5]={dt,0,25,3.7f,.002f};int rc=collect(&c,H,config_V,config_ocv,o);return rc!=want||c.ticks!=after||(want==-1&&c.valid!=0);}
int main(void){int bad=0;bad|=one(0,0,0,0);bad|=one(-0.f,0,0,0);bad|=one(0x1p-32f,0,0,1);bad|=one(0x1p-33f,0,-1,0);bad|=one(0x1p-149f,0,-1,0);bad|=one(1,0,0,UINT64_C(4294967296));bad|=one(0x1p-32f,UINT64_MAX-1,0,UINT64_MAX);bad|=one(0x1p-32f,UINT64_MAX,-1,UINT64_MAX);bad|=one(1,UINT64_MAX-UINT64_C(4294967296)+1,-1,UINT64_MAX-UINT64_C(4294967296)+1);bad|=one(NAN,0,-1,0);bad|=one(INFINITY,0,-1,0);printf("cases=11 status=%s\n",bad?"FAIL":"PASS");return bad;}
