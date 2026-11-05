#include <stdio.h>
#include "/home/easy/proj/mumble/.worktrees/qr-sharing/experiments/constant_codebook_001/word/tiny_cardinal/core.c"
#include "/home/easy/proj/mumble/.worktrees/qr-sharing/experiments/constant_codebook_001/word/tiny_cardinal/config.h"
int main(void){for(unsigned i=0;i<16;i++){double x=cb_scale(config_scale,i);fwrite(&x,8,1,stdout);}return 0;}
