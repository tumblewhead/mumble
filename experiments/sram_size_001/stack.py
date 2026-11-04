"""Target execution witness for final candidate. Fixtures are test-only;
use measure.py's separate clean image for size. M23 code on M33 QEMU, not timing.
"""
from pathlib import Path
import ast,json,subprocess,argparse
import numpy as np
from experiments.bank_memory_001.test_memory import Tests as Fixture
from .generate import generate
from .native import projected_coefficients
HERE=Path(__file__).resolve().parent

def run(out,bits):
 out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False);src=generate(out,'tiny','cardinal',True,bits)
 Fixture.setUpClass()
 try:
  f=Fixture();field=f.make(rank=3);field.update(0,f.obs)
  arrays=dict(history=field.packed.values,mean=f.mean,scale=np.diag(f.L),center=field.center,P=projected_coefficients(field),V=field.V,ocv=np.array([field.base.config['ocv_intercept_V'],field.base.config['ocv_slope_V_per_SOC']]),state=np.r_[field.state[18:24],field.state[27:33],field.state[36:39],field.rc_free.ravel(),field.rc_forced.ravel()])
  text='\n'.join('static const double fixture_'+n+'['+str(a.size)+']={'+','.join(float(v).hex() for v in a.flat)+'};' for n,a in arrays.items())
  (out/'fixture.h').write_text(text+'\n')
 finally:Fixture.tearDownClass()
 tree=ast.parse((HERE.parent/'bank_rowwise_001/measure.py').read_text())
 assign=next(n for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='probe' for t in n.targets))
 probe=assign.value.func.value.value.replace('CORE',str(src))
 probe=probe.replace('core solver; double history[595],response[117],stream_row[34],input[5]','core solver; history_store history[595]; double response[93],input[5]')
 probe=probe.replace('fixture_A,fixture_knots,fixture_PA,fixture_hu,bank.response,bank.response+39,bank.response+78','fixture_P,fixture_P,fixture_P,1.,bank.response,bank.response+15,bank.response+54')
 probe=probe.replace('if(append(&bank.solver,bank.stream_row,1))return 11;', '''bank.input[0]=.02;bank.input[1]=.03;bank.input[2]=25;bank.input[3]=3.8;bank.input[4]=.002;
 if(stream_ingest(&bank.solver,bank.history,fixture_V,fixture_ocv,bank.input))return 11;''')
 copy='for(unsigned i=0;i<595;i++)history_put(bank.history,i,fixture_history[i]);' if bits==48 else 'memcpy(bank.history,fixture_history,sizeof(bank.history));'
 probe=probe.replace('memcpy(bank.history,fixture_history,sizeof(bank.history));',copy)
 # Exercise a real sample after the successful retained-data fits, then query.
 a=probe.index(' bank.input[0]=');b=probe.index(' for(unsigned run=0;',a)
 ingest=probe[a:b];probe=probe[:a]+probe[b:]
 a=probe.index(' /* Exercise malformed candidate')
 probe=probe[:a]+ingest+' if(estimate(&bank.solver))return 12;\n for(unsigned j=0;j<16;j++)if(scalar(&bank.solver,j,bank.result,bank.result+1))return 13;\n if(fit(&bank.solver,bank.history,bank.solver.anchor))return 14;\n if(initialize(&bank.solver,bank.history,(bank.solver.stop==1||bank.solver.stop==2)?bank.solver.point:bank.solver.anchor))return 15;\n if(estimate(&bank.solver))return 16;\n for(unsigned j=0;j<16;j++)if(scalar(&bank.solver,j,bank.result,bank.result+1))return 17;\n'+probe[a:]
 (out/'probe.c').write_text(probe)
 link='''ENTRY(reset)
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
'''
 (out/'link.ld').write_text(link)
 flags=['-mcpu=cortex-m23','-mthumb','-mfloat-abi=soft','-std=c11','-Os','-flto','-fno-fast-math','-ffp-contract=off','-ffunction-sections','-fdata-sections','-fstack-usage']
 command=['arm-none-eabi-gcc',*flags,'-nostartfiles',str(out/'probe.c'),str(HERE/'soft_sub.c'),'-Wl,--wrap=__aeabi_dsub','-T',str(out/'link.ld'),'-Wl,--gc-sections,-Map='+str(out/'probe.map'),'-lm','-lc','-lgcc','-lnosys','-o',str(out/'probe.elf')]
 subprocess.run(command,check=True)
 q=['qemu-system-arm','-M','mps2-an505','-nographic','-semihosting-config','enable=on,target=native','-kernel',str(out/'probe.elf')]
 p=subprocess.run(q,capture_output=True,text=True,timeout=60)
 result=dict(command=command,emulator=q,output=p.stdout+p.stderr,returncode=p.returncode,scope=__doc__)
 (out/'measurement.json').write_text(json.dumps(result,indent=2)+'\n');print(result['output'])
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--history-bits',type=int,choices=[48,64],default=48);a=p.parse_args();run(a.out,a.history_bits)
