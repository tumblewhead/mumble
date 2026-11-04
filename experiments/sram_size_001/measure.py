"""Clean numerical stream/inference image: code, constants, in-place data and BSS all SRAM.
Native stationary VIT stream/QR/refit/scalar path; platform scheduling, normalization, identity/transaction code remain external. No saved observations or history in image.
"""
from pathlib import Path
import json,subprocess,hashlib,argparse
import numpy as np
from experiments.bank_memory_001.test_memory import Tests as Fixture
from .generate import generate
from .native import projected_coefficients
HERE=Path(__file__).resolve().parent

def run(out,history_bits=64):
 out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
 Fixture.setUpClass()
 try:
  f=Fixture();field=f.make(rank=3)
  arrays=dict(mean=f.mean,scale=np.diag(f.L),center=field.center,A=field.map.A,knots=field.map.um,PA=field.P@field.map.A,P=projected_coefficients(field),V=field.V,ocv=np.array([field.base.config['ocv_intercept_V'],field.base.config['ocv_slope_V_per_SOC']]))
  hu=field.map.hu
 finally:Fixture.tearDownClass()
 results=[]
 for math_kind,map_kind in [('tiny','cardinal')]:
  d=out/(math_kind+'_'+map_kind);src=generate(d,math_kind,map_kind,True,history_bits)
  names=['mean','scale','center','V','ocv']+(['A','knots','PA'] if map_kind=='spline' else ['P'])
  config='\n'.join('static const double config_'+n+'['+str(arrays[n].size)+']={'+','.join(float(v).hex() for v in arrays[n].flat)+'};' for n in names)
  (d/'config.h').write_text(config+'\n')
  mapargs='config_A,config_knots,config_PA,'+float(hu).hex() if map_kind=='spline' else 'config_P,config_P,config_P,1.'
  probe='''#include "core.c"
#include "config.h"
extern unsigned long _bss_start,_bss_end,_stack_top;
typedef struct { core solver; history_store history[595]; double response[93],input[5]; unsigned char identities[160]; double result[2]; } allocation;
allocation bank;
volatile unsigned status;
/* Volatile external sample slot prevents constant folding of runtime evidence. */
volatile double sample;
void reset(void){
 for(unsigned long*p=&_bss_start;p<&_bss_end;)*p++=0;
 model m={config_mean,config_scale,config_center,MAPARGS,bank.response,bank.response+15,bank.response+54};
 bank.response[0]=1;for(unsigned j=15;j<54;j++)bank.response[j]=1;
 status=bind(&bank.solver,&m);
 status|=initialize(&bank.solver,bank.history,bank.solver.anchor);
 for(;;){
  bank.input[0]=.02;bank.input[1]=sample;bank.input[2]=25;bank.input[3]=3.8;bank.input[4]=.002;
  status=stream_ingest(&bank.solver,bank.history,config_V,config_ocv,bank.input);
  status|=fit(&bank.solver,bank.history,bank.solver.anchor);
  status|=initialize(&bank.solver,bank.history,bank.solver.point);
  status|=estimate(&bank.solver);
  for(unsigned j=0;j<16;j++)status|=scalar(&bank.solver,j,bank.result,bank.result+1);
 }
}
void fault(void){for(;;){}}
__attribute__((section(".vectors"),used)) const void*vectors[]={&_stack_top,reset,fault,fault,fault,fault,fault};
'''.replace('MAPARGS',mapargs)
  (d/'probe.c').write_text(probe)
  (d/'link.ld').write_text('''ENTRY(reset)
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
''')
  command=['arm-none-eabi-gcc','-mcpu=cortex-m23','-mthumb','-mfloat-abi=soft','-std=c11','-Os','-flto','-fno-fast-math','-ffp-contract=off','-ffunction-sections','-fdata-sections','-fstack-usage','-nostartfiles',str(d/'probe.c'),str(HERE/'soft_sub.c'),'-Wl,--wrap=__aeabi_dsub','-T',str(d/'link.ld'),'-Wl,--gc-sections,-Map='+str(d/'probe.map'),'-lm','-lc','-lgcc','-lnosys','-o',str(d/'probe.elf')]
  subprocess.run(command,check=True)
  sizes=subprocess.check_output(['arm-none-eabi-size','-A',str(d/'probe.elf')],text=True)
  sections={a[0]:int(a[1]) for line in sizes.splitlines() if len(a:=line.split())==3 and a[0].startswith('.') and a[1].isdigit()}
  nm=subprocess.check_output(['arm-none-eabi-nm','-S','--size-sort',str(d/'probe.elf')],text=True);(d/'symbols.txt').write_text(nm)
  allocated=[dict(name=a[0],bytes=int(a[1]),address=int(a[2])) for line in sizes.splitlines() if len(a:=line.split())==3 and a[1].isdigit() and a[2].isdigit() and 0x10000000<=int(a[2])<0x10020000 and int(a[1])>0]
  occupied=max(x['address']+x['bytes'] for x in allocated)-0x10000000
  gap=occupied-sum(x['bytes'] for x in allocated)
  record=dict(math=math_kind,map=map_kind,history_bits=history_bits,allocated=allocated,alignment_gaps_B=gap,sections=sections,allocated_sections_B=occupied,with_1024_stack_B=occupied+1024,stack='1024B reservation, not bound; final linked stack qualification pending',command=command,sha256=hashlib.sha256((d/'probe.elf').read_bytes()).hexdigest())
  results.append(record);print(math_kind,map_kind,occupied,occupied+1024,flush=True)
 (out/'measurement.json').write_text(json.dumps(dict(results=results,scope=__doc__),indent=2)+'\n')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--history-bits',type=int,choices=[48,64],default=64);a=p.parse_args();run(a.out,a.history_bits)
