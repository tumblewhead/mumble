"""Cross-compile the actual core, link a bare-metal probe, measure stack in QEMU.
M23 code executes on M33 emulation: stack witness, not M23 cycles/WCET proof.
"""
import argparse,json,subprocess,hashlib
from pathlib import Path
import numpy as np
from experiments.bank_memory_001.test_memory import Tests as Fixture
HERE=Path(__file__).resolve().parent

def run(out):
 out.mkdir(parents=True,exist_ok=False);Fixture.setUpClass()
 try:
  f=Fixture();field=f.make(rank=3);field.update(0,f.obs)
  arrays=dict(history=field.packed.values,mean=f.mean,scale=np.diag(f.L),center=field.center,A=field.map.A,knots=field.map.um,PA=field.P@field.map.A,state=np.r_[field.state,field.rc_free.ravel(),field.rc_forced.ravel()])
  text='\n'.join('static const double fixture_'+n+'['+str(a.size)+']={'+','.join(float(v).hex() for v in a.flat)+'};' for n,a in arrays.items())
  text+='\nstatic const double fixture_hu='+float(field.map.hu).hex()+';\n'
  (out/'fixture.h').write_text(text)
 finally:Fixture.tearDownClass()
 # Fixed allocation deliberately includes future streaming row/input/metadata,
 # though this probe drives retained history, not the entire streaming pipeline.
 # Public mean/scale/center/calibration are fixed ROM configuration, not working history.
 probe='''#include "CORE"
#include "fixture.h"
extern unsigned long _data_load,_data_start,_data_end,_bss_start,_bss_end,_stack_top;
typedef struct { core solver; double history[595],response[117],stream_row[34],input[5]; unsigned char identities[160]; double result[2]; } allocation;
allocation bank;
volatile unsigned long measured, own_bytes, status;
static void write0(const char *p){register unsigned r0 __asm__("r0")=4;register const char *r1 __asm__("r1")=p;__asm__ volatile("bkpt 0xab" : "+r"(r0) : "r"(r1) : "memory");}
static void number(unsigned n){char b[16];unsigned k=15;b[k--]=0;b[k--]='\\n';do{b[k--]='0'+n%10;n/=10;}while(n);write0(b+k+1);}
__attribute__((noinline)) static int setup_model(void){
 model m={fixture_mean,fixture_scale,fixture_center,fixture_A,fixture_knots,fixture_PA,fixture_hu,bank.response,bank.response+39,bank.response+78};
 return bind(&bank.solver,&m);
}
__attribute__((noinline)) static int exercise(void){
 for(unsigned i=0;i<16;i++)bank.solver.trial[i]=0;
 if(initialize(&bank.solver,bank.history,bank.solver.trial))return 2;
 /* Zero evidence row exercises incremental tangent code without changing data. */
 if(append(&bank.solver,bank.stream_row,1))return 11;
 for(unsigned run=0;run<4;run++){
  if(fit(&bank.solver,bank.history,bank.solver.anchor))return 3;
  if(bank.solver.stop!=1&&bank.solver.stop!=2)return 4;
  if(initialize(&bank.solver,bank.history,bank.solver.point))return 5;
  if(estimate(&bank.solver))return 6;
  for(unsigned i=0;i<16;i++)if(scalar(&bank.solver,i,bank.result,bank.result+1))return 7;
 }
 /* Exercise malformed candidate and refusal, then recover explicitly. */
 bank.solver.trial[0]=1e20;
 if(initialize(&bank.solver,bank.history,bank.solver.trial)==0)return 8;
 if(estimate(&bank.solver)==0)return 9;
 if(initialize(&bank.solver,bank.history,bank.solver.anchor))return 10;
 return 0;
}
static void main_probe(void){
 memcpy(bank.history,fixture_history,sizeof(bank.history));memcpy(bank.response,fixture_state,sizeof(bank.response));
 /* Original public prior and calibration are immutable configuration inROM. */
 if(setup_model()){write0("BIND_FAILURE\\n");return;}
 unsigned long sp;__asm__ volatile("mov %0,sp":"=r"(sp));
 volatile unsigned char *bottom=(volatile unsigned char *)((unsigned long)&_stack_top-16384),*top=(volatile unsigned char *)(sp-64);
 for(volatile unsigned char *p=bottom;p<top;p++)*p=0xa5;
 status=exercise();volatile unsigned char *p=bottom;while(p<top&&*p==0xa5)p++;
 measured=(unsigned long)&_stack_top-(unsigned long)p;own_bytes=sizeof(bank);
 write0("status=");number(status);write0("allocation_B=");number(own_bytes);write0("stack_watermark_B=");number(measured);
 register unsigned r0 __asm__("r0")=0x18;register unsigned r1 __asm__("r1")=0x20026;__asm__ volatile("bkpt 0xab" : "+r"(r0) : "r"(r1) : "memory");for(;;){}
}
void reset(void){unsigned long *src=&_data_load;for(unsigned long *p=&_data_start;p<&_data_end;)*p++=*src++;for(unsigned long *p=&_bss_start;p<&_bss_end;)*p++=0;main_probe();}
void fault(void){write0("FAULT\\n");for(;;){}}
__attribute__((section(".vectors"),used)) const void *vectors[]={&_stack_top,reset,fault,fault,fault,fault,fault};
'''.replace('CORE',str(HERE/'core.c'))
 (out/'probe.c').write_text(probe)
 (out/'link.ld').write_text('''ENTRY(reset)
MEMORY { FLASH (rx) : ORIGIN = 0x10000000, LENGTH = 1M
 RAM (rwx) : ORIGIN = 0x30000000, LENGTH = 32K }
SECTIONS {
 .vectors : { KEEP(*(.vectors)) } > FLASH
 .text : { *(.text*) *(.rodata*) } > FLASH
 .ARM.exidx : { *(.ARM.exidx*) } > FLASH
 _data_load = LOADADDR(.data);
 .data : { _data_start = .; *(.data*) _data_end = .; } > RAM AT>FLASH
 .bss (NOLOAD) : { _bss_start = .; *(.bss*) *(COMMON) _bss_end = .; } > RAM
 _end = .; end = .; _stack_top = ORIGIN(RAM)+LENGTH(RAM);
}
''')
 flags=['-mcpu=cortex-m23','-mthumb','-mfloat-abi=soft','-std=c11','-Os','-fno-fast-math','-ffp-contract=off','-ffunction-sections','-fdata-sections','-fstack-usage']
 command=['arm-none-eabi-gcc',*flags,'-nostartfiles',str(out/'probe.c'),'-T',str(out/'link.ld'),'-Wl,--gc-sections,-Map='+str(out/'probe.map'),'-lm','-lc','-lgcc','-lnosys','-o',str(out/'probe.elf')]
 subprocess.run(command,check=True)
 q=['qemu-system-arm','-M','mps2-an505','-nographic','-semihosting-config','enable=on,target=native','-kernel',str(out/'probe.elf')]
 p=subprocess.run(q,capture_output=True,text=True,timeout=60)
 result=dict(command=command,emulator_command=q,compiler=subprocess.check_output(['arm-none-eabi-gcc','--version'],text=True).splitlines()[0],output=p.stdout+p.stderr,returncode=p.returncode,size=subprocess.check_output(['arm-none-eabi-size',str(out/'probe.elf')],text=True),nm=subprocess.check_output(['arm-none-eabi-nm','-S','--size-sort',str(out/'probe.elf')],text=True),scope='M23 soft-float compile executed on M33 QEMU. Observed exercised-path stack watermark, not WCET, ISR stack or universal bound. Link includes actual newlib/libgcc; retained-history inference probe excludes response generator and complete device runtime.')
 (out/'measurement.json').write_text(json.dumps(result,indent=2)+'\n');print(result['output']);print(result['size'])
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.out.resolve())
