"""Bitwise state/history controls plus ARM software-subtraction qualification."""
import json,subprocess,hashlib,argparse
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def run(out):
 out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False);transcripts={}
 for name in ('baseline','sub','scratch','combined','lazy002'):
  d=ROOT/name;lazy=name=='lazy002';count=54 if lazy else 93
  src='''#include "CORE"
#include "config.h"
#include <stdio.h>
static collector c;static history_store H[595];static float state[COUNT];
static const fixed_config cfg={config_mean,config_scale,config_center,config_P};
int main(void){c.m=(model){&cfg,state};c.valid=1;state[0]=1;INIT
 for(unsigned i=0;i<4096;i++){
 float o[5]={i%13?.02f:0,((int)((i/31)%9)-4)*.005f,25,3.7f,.002f};int rc=collect(&c,H,config_V,config_ocv,o);if(rc)return 1;
 if(i%128==127){fwrite(H,sizeof H,1,stdout);fwrite(state,sizeof state,1,stdout);}
 }
 history_store saved[595];float before[COUNT];memcpy(saved,H,sizeof H);memcpy(before,state,sizeof state);
 float bad[5]={-1,0,25,3.7f,.002f};if(collect(&c,H,config_V,config_ocv,bad)!=-1)return 2;
 bad[0]=.02f;if(collect(&c,H,config_V,config_ocv,bad)!=-1)return 3;
 if(memcmp(saved,H,sizeof H)||memcmp(before,state,sizeof state))return 4;return 0;}
'''.replace('CORE',str(d/'core.c')).replace('COUNT',str(count)).replace('INIT','' if lazy else 'for(unsigned j=15;j<54;j++)state[j]=1;')
  p=out/(name+'.c');p.write_text(src);exe=out/name
  subprocess.run(['cc','-std=c11','-O3','-fstrict-aliasing','-fsanitize=undefined','-fno-fast-math','-ffp-contract=off','-I'+str(d),str(p),'-lm','-o',str(exe)],check=True)
  r=subprocess.run([str(exe)],capture_output=True,check=True);assert not r.stderr,r.stderr
  transcripts[name]={'bytes':len(r.stdout),'sha256':hashlib.sha256(r.stdout).hexdigest()}
 assert all(transcripts[n]==transcripts['baseline'] for n in ('sub','scratch','combined'))
 # ARM actual libgcc subtraction vs wrapped addition, including special values.
 src=r'''
#include <stdint.h>
#include <string.h>
extern float __aeabi_fsub(float,float),__real___aeabi_fsub(float,float);
static float (*volatile wrapped)(float,float)=__aeabi_fsub;
static float (*volatile reference)(float,float)=__real___aeabi_fsub;
static int one(uint32_t a,uint32_t b){float x,y;memcpy(&x,&a,4);memcpy(&y,&b,4);float z=wrapped(x,y),w=reference(x,y);uint32_t u,v;memcpy(&u,&z,4);memcpy(&v,&w,4);if((u&0x7fffffff)>0x7f800000)return (v&0x7fffffff)>0x7f800000?0:1;return u!=v;}
static void say(const char*p){register unsigned r0 __asm__("r0")=4;register const char*r1 __asm__("r1")=p;__asm__ volatile("bkpt 0xab":"+r"(r0):"r"(r1):"memory");}
extern unsigned long _stack_top;
void reset(void){uint32_t v[]={0,0x80000000,1,0x80000001,0x007fffff,0x00800000,0x3f800000,0xbf800000,0x7f7fffff,0xff7fffff,0x7f800000,0xff800000,0x7fc00001,0xffc00001,0x7f800001,0xff800001};int bad=0;for(unsigned j=0;j<16;j++)for(unsigned k=0;k<16;k++)bad|=one(v[j],v[k]);uint32_t s=9;for(unsigned j=0;j<32768;j++){s=s*1664525u+1013904223u;uint32_t a=s;s=s*1664525u+1013904223u;bad|=one(a,s);}say(bad?"FAIL\n":"PASS 33024 pairs\n");register unsigned r0 __asm__("r0")=0x18;register unsigned r1 __asm__("r1")=0x20026;__asm__ volatile("bkpt 0xab":"+r"(r0):"r"(r1):"memory");for(;;){} }
void fault(void){say("FAULT\n");for(;;){}}
__attribute__((section(".vectors"),used))const void*vectors[]={&_stack_top,reset,fault,fault,fault,fault,fault};
'''
 # Data pointers need to reside in loadable SRAM for this test, using RAM region
 # as the ELF loader destination; no flash copy startup is assumed.
 link=(ROOT/'stack_sub/link.ld').read_text().replace('.data : { *(.data*) } > RAM','.data : { *(.data*) } > RAM')
 (out/'arm.c').write_text(src);(out/'link.ld').write_text(link)
 cmd=['arm-none-eabi-gcc','-mcpu=cortex-m23','-mthumb','-mfloat-abi=soft','-Os','-fno-fast-math','-ffp-contract=off','-nostartfiles',str(out/'arm.c'),str(ROOT/'soft_sub32.c'),'-Wl,--wrap=__aeabi_fsub','-T',str(out/'link.ld'),'-lc','-lgcc','-lnosys','-o',str(out/'arm.elf')];subprocess.run(cmd,check=True)
 q=['qemu-system-arm','-M','mps2-an505','-nographic','-semihosting-config','enable=on,target=native','-kernel',str(out/'arm.elf')];r=subprocess.run(q,capture_output=True,text=True,timeout=60);assert r.returncode==0 and 'PASS 33024 pairs' in r.stdout+r.stderr,r.stdout+r.stderr
 result={'transcripts':transcripts,'arm_subtraction':{'command':cmd,'output':r.stdout+r.stderr,'scope':'bit identity except NaN payload/sign; finite signed zeros, subnormals, infinity and NaN classification'},'lazy':'different approximation/layout, not parity-qualified','scope':'4096 samples, actual intervals incl zero dt; failure latch; no Q12 stall repair'}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',required=True);run(p.parse_args().out)
