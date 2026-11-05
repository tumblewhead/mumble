from pathlib import Path
import argparse,json,subprocess,hashlib
from .build import generate,VARIANTS,configuration,convert_float
ROOT=Path(__file__).resolve().parents[2]


def run(out,variant,execute=False, arithmetic="double", history="local"):
 if arithmetic == "float" and variant == "predictor": raise ValueError("float predictor not qualified or implemented")
 out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False);generate(out,variant,arithmetic)
 configuration(out)
 count=16 if variant=='predictor' else 2 if variant=='soc' else 0
 extra='double outputs[16],gradient[16];' if variant=='predictor' else 'double outputs[1];' if variant=='soc' else ''
 params='volatile double host_parameters['+str(count)+'];' if count else ''
 cfg='config_mean,config_scale,config_center,0' if variant=='predictor' else '0,0,config_center,0'
 prediction=''
 if variant=='soc':prediction='double parameters[2];for(unsigned j=0;j<2;j++)parameters[j]=host_parameters[j];status|=predict_soc(&bank.state,parameters,bank.outputs);readout=bank.outputs[0];'
 if variant=='predictor':prediction='for(unsigned j=0;j<16;j++)bank.state.point[j]=host_parameters[j];status|=predict(&bank.state,bank.outputs,bank.gradient);for(unsigned j=0;j<16;j++)readout=bank.outputs[j];'
 begin='''#include "core.c"
#include "config.h"
static const fixed_config configuration={CONFIG};
typedef struct {collector state;history_store history[595];double response[93],input[5];unsigned char identities[160];EXTRA} allocation;
allocation bank;
volatile unsigned status;
volatile double samples[5],readout;
PARAMS
static void setup(void){bank.state.m.config=&configuration;bank.state.m.response=bank.response;bank.state.valid=1;bank.response[0]=1;for(unsigned j=15;j<54;j++)bank.response[j]=1;}
'''.replace('CONFIG',cfg).replace('EXTRA',extra).replace('PARAMS',params)
 step='for(unsigned j=0;j<5;j++)bank.input[j]=samples[j];status=collect(&bank.state,bank.history,config_V,config_ocv,bank.input);'+prediction
 if not execute:
  body='''extern unsigned long _bss_start,_bss_end,_stack_top;
void reset(void){for(unsigned long*p=&_bss_start;p<&_bss_end;)*p++=0;setup();for(;;){STEP}}
void fault(void){for(;;){}}
__attribute__((section(".vectors"),used)) const void*vectors[]={&_stack_top,reset,fault,fault,fault,fault,fault};
'''.replace('STEP',step)
  link="""ENTRY(reset)
MEMORY { SRAM (rwx) : ORIGIN = 0x10000000, LENGTH = 128K }
SECTIONS {
 .vectors : { KEEP(*(.vectors)) } > SRAM
 .text : { *(.text*) } > SRAM
 .rodata : { *(.rodata*) } > SRAM
 .ARM.exidx : { *(.ARM.exidx*) } > SRAM
 .data : { *(.data*) } > SRAM
 .bss (NOLOAD) : { _bss_start = .; *(.bss*) *(COMMON) _bss_end = .; } > SRAM
 _end = .; end = .; _stack_top = ORIGIN(SRAM)+LENGTH(SRAM);
}
"""
 else:
  body='''extern unsigned long _bss_start,_bss_end,_stack_top;
static void write0(const char*p){register unsigned r0 __asm__("r0")=4;register const char*r1 __asm__("r1")=p;__asm__ volatile("bkpt 0xab":"+r"(r0):"r"(r1):"memory");}
static void number(unsigned n){char b[16];unsigned k=15;b[k--]=0;b[k--]='\\n';do{b[k--]='0'+n%10;n/=10;}while(n);write0(b+k+1);}
static __attribute__((noinline)) int exercise(void){
 setup();
 for(unsigned i=0;i<512;i++){samples[0]=.02;samples[1]=((int)(i%17)-8)*.005;samples[2]=25;samples[3]=3.7;samples[4]=.002;STEP if(status)return status;}
 samples[0]=-1;STEP if(status!=-1)return 9;
 return 0;
}
static void main_probe(void){
 PARAM_INIT
 unsigned long sp;__asm__ volatile("mov %0,sp":"=r"(sp));
 volatile unsigned char*bottom=(volatile unsigned char*)((unsigned long)&_stack_top-16384),*top=(volatile unsigned char*)(sp-64);
 for(volatile unsigned char*p=bottom;p<top;p++)*p=0xa5;
 status=exercise();volatile unsigned char*p=bottom;while(p<top&&*p==0xa5)p++;
 unsigned used=(unsigned long)&_stack_top-(unsigned long)p;
 write0("status=");number(status);write0("allocation_B=");number(sizeof(bank));write0("stack_watermark_B=");number(used);
 register unsigned r0 __asm__("r0")=0x18;register unsigned r1 __asm__("r1")=0x20026;__asm__ volatile("bkpt 0xab":"+r"(r0):"r"(r1):"memory");for(;;){}
}
void reset(void){for(unsigned long*p=&_bss_start;p<&_bss_end;)*p++=0;main_probe();}
void fault(void){write0("FAULT\\n");for(;;){}}
__attribute__((section(".vectors"),used)) const void*vectors[]={&_stack_top,reset,fault,fault,fault,fault,fault};
'''.replace('STEP',step).replace('PARAM_INIT','host_parameters[0]=.6;host_parameters[1]=20;' if variant=='soc' else '')
  link='''ENTRY(reset)
MEMORY { FLASH (rx) : ORIGIN = 0x10000000, LENGTH = 1M
 RAM (rwx) : ORIGIN = 0x30000000, LENGTH = 32K }
SECTIONS {
 .vectors : { KEEP(*(.vectors)) } > FLASH
 .text : { *(.text*) } > FLASH
 .rodata : { *(.rodata*) } > FLASH
 .ARM.exidx : { *(.ARM.exidx*) } > FLASH
 .data : { *(.data*) } > RAM
 .bss (NOLOAD) : { _bss_start = .; *(.bss*) *(COMMON) _bss_end = .; } > RAM
 _end = .; end = .; _stack_top = ORIGIN(RAM)+LENGTH(RAM);
}
'''
 probe=begin+body
 if history == "shared":
  probe=probe.replace('history_store history[595];','').replace('bank.history','shared_history')
  probe=probe.replace('allocation bank;', 'allocation bank;\n__attribute__((section(".shared_history"),aligned(8))) history_store shared_history[595];')
  # Explicit startup initialization: NOLOAD shared SRAM cannot be assumed zeroed.
  probe=probe.replace('static void setup(void){','static void setup(void){memset(shared_history,0,sizeof shared_history);')
  link=link.replace('MEMORY {', 'MEMORY { SHARED (rw) : ORIGIN = 0x31000000, LENGTH = 8K\n')
  link=link.replace('SECTIONS {','SECTIONS {\n .shared_history (NOLOAD) : { *(.shared_history) } > SHARED')
 if arithmetic == "float":
  probe=convert_float(probe)
  (out/'config.h').write_text(convert_float((out/'config.h').read_text()))
 (out/'probe.c').write_text(probe);(out/'link.ld').write_text(link)
 flags=['-mcpu=cortex-m23','-mthumb','-mfloat-abi=soft','-std=c11','-Os','-flto','-fno-fast-math','-ffp-contract=off','-ffunction-sections','-fdata-sections','-fstack-usage']
 cmd=['arm-none-eabi-gcc',*flags,'-nostartfiles',str(out/'probe.c'),str(ROOT/'experiments/sram_size_001/soft_sub.c'),'-Wl,--wrap=__aeabi_dsub','-T',str(out/'link.ld'),'-Wl,--gc-sections,-Map='+str(out/'probe.map'),'-lm','-lc','-lgcc','-lnosys','-o',str(out/'probe.elf')]
 if arithmetic == 'float':
  cmd=[x for x in cmd if not x.endswith('/soft_sub.c') and x!='-Wl,--wrap=__aeabi_dsub']
 subprocess.run(cmd,check=True)
 sizes=subprocess.check_output(['arm-none-eabi-size','-A',str(out/'probe.elf')],text=True)
 sections={x[0]:int(x[1]) for line in sizes.splitlines() if len(x:=line.split())==3 and x[0].startswith('.') and x[1].isdigit()}
 (out/'symbols.txt').write_text(subprocess.check_output(['arm-none-eabi-nm','-S','--size-sort',str(out/'probe.elf')],text=True))
 rec={'variant':variant,'command':cmd,'execute':execute,'arithmetic':arithmetic,'history_placement':history,'external_history_B':sections.get('.shared_history',0),'sections':sections,'elf_sha256':hashlib.sha256((out/'probe.elf').read_bytes()).hexdigest()}
 if execute:
  q=['qemu-system-arm','-M','mps2-an505','-nographic','-semihosting-config','enable=on,target=native','-kernel',str(out/'probe.elf')];r=subprocess.run(q,capture_output=True,text=True,timeout=60);rec.update(emulator=q,returncode=r.returncode,output=r.stdout+r.stderr);assert r.returncode==0 and 'status=0\n' in rec['output'],rec['output']
 else:
  alloc=[{'name':x[0],'bytes':int(x[1]),'address':int(x[2])} for line in sizes.splitlines() if len(x:=line.split())==3 and x[1].isdigit() and x[2].isdigit() and 0x10000000<=int(x[2])<0x10020000 and int(x[1])>0]
  occupied=max(x['address']+x['bytes'] for x in alloc)-0x10000000;rec.update(allocated=alloc,static_B=occupied,alignment_gaps_B=occupied-sum(x['bytes'] for x in alloc),with_1024_stack_B=occupied+1024)
 (out/'measurement.json').write_text(json.dumps(rec,indent=2)+'\n');print(rec.get('static_B',rec.get('output')))
