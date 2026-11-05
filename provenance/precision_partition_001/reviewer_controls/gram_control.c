#include "/home/easy/proj/mumble/.worktrees/qr-sharing/experiments/precision_partition_001/paired_gram.h"
#include <stdio.h>
int main(void){history_store h[3]={0};float x[2]={1,1+0x1p-12f};if(history_insert(h,2,x))return 1;double b=x[1],e=b*b*history_get(h,0)-2*b*history_get(h,1)+history_get(h,2);printf("%.17g\n",e);return e!=-0x1p-24;}
