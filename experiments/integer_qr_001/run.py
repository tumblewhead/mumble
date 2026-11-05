"""Compare bounded integer QR kernels. No complete collector claim."""
import argparse,ctypes,hashlib,json,subprocess,time
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent

def run(out,fraction_bits=16):
 out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False);records={}
 for name,kind in [('digit',0),('cordic',1)]:
  d=out/name;d.mkdir();header=ROOT/'kernel.h'
  s=f'#define CORDIC_KIND {kind}\n#include "{header}"\n'
  api=s+'''int insert(int32_t*R,unsigned n,int32_t*x){return iq_insert(R,n,x);}
int repeated(unsigned n,int32_t value,int32_t*out){int32_t R=0;for(unsigned i=0;i<n;i++){int32_t x=value;if(iq_insert(&R,1,&x))return -1;}*out=R;return 0;}
'''
  (d/'host.c').write_text(api);lib=d/'host.so'
  subprocess.run(['cc','-std=c11','-O2','-fno-fast-math','-ffp-contract=off','-shared','-fPIC',str(d/'host.c'),'-o',str(lib)],check=True)
  dll=ctypes.CDLL(str(lib));ptr=ctypes.POINTER(ctypes.c_int32);dll.insert.argtypes=[ptr,ctypes.c_uint,ptr];dll.repeated.argtypes=[ctypes.c_uint,ctypes.c_int32,ptr]
  Q=1<<fraction_bits;cases={};rng=np.random.default_rng(713)
  for label,rows in [('varied',rng.normal(size=(4096,8))*.2),('weak',np.tile([1,1+2**-12],(4096,1))),('rest',np.zeros((16,8)))]:
   rows=np.rint(rows*Q).astype(np.int32);n=rows.shape[1];R=np.zeros(n*(n+1)//2,dtype=np.int32);start=time.perf_counter()
   for row in rows:
    x=row.copy();assert dll.insert(R.ctypes.data_as(ptr),n,x.ctypes.data_as(ptr))==0
   secs=time.perf_counter()-start;tri=np.zeros((n,n));tri[np.triu_indices(n)]=R/Q;G=rows.astype(float).T@rows.astype(float)/Q**2
   cases[label]={'relative_Gram_error':float(np.linalg.norm(tri.T@tri-G)/max(1,np.linalg.norm(G))),'host_seconds_including_ctypes':secs,'min_diagonal':float(np.diag(tri).min())}
  repeated=[]
  for count in (100000,1000000,20000000):
   val=ctypes.c_int32();t=time.perf_counter();rc=dll.repeated(count,Q,ctypes.byref(val));elapsed=time.perf_counter()-t
   repeated.append({'updates':count,'status':rc,'factor_raw':val.value,'relative_information_error':(val.value/Q)**2/count-1,'host_seconds':elapsed})
  R=np.array([1,1000000,0],dtype=np.int32);x=np.array([1,-1000000],dtype=np.int32)
  assert dll.insert(R.ctypes.data_as(ptr),2,x.ctypes.data_as(ptr))==0
  small_pivot={'factor_raw':R.tolist(),'trailing_energy_relative_error':float((int(R[1])**2+int(R[2])**2)/2e12-1)}
  assert abs(small_pivot['trailing_energy_relative_error'])<1e-4
  before=R.copy();x=np.zeros(2,dtype=np.int32)
  assert dll.insert(R.ctypes.data_as(ptr),2,x.ctypes.data_as(ptr))==0 and np.array_equal(R,before)
  # Range rejection before mutation and zero/rank-deficient controls.
  R=np.array([0],dtype=np.int32);x=np.array([2**29+1],dtype=np.int32);assert dll.insert(R.ctypes.data_as(ptr),1,x.ctypes.data_as(ptr))==-1 and R[0]==0
  # Standalone SRAM kernel image, inputs volatile and outputs visible.
  probe=s+'''extern unsigned long _bss_start,_bss_end,_stack_top;
static int32_t R[595],x[34];volatile int32_t input[34];volatile int status;
void reset(void){for(unsigned long*p=&_bss_start;p<&_bss_end;)*p++=0;for(;;){for(unsigned j=0;j<34;j++)x[j]=input[j];status=iq_insert(R,34,x);}}
void fault(void){for(;;){}}
__attribute__((section(".vectors"),used))const void*vectors[]={&_stack_top,reset,fault,fault,fault,fault,fault};
'''
  (d/'probe.c').write_text(probe)
  link='''ENTRY(reset)
MEMORY { SRAM(rwx): ORIGIN=0x10000000,LENGTH=128K }
SECTIONS { .vectors : { KEEP(*(.vectors)) } > SRAM
.text : { *(.text*) } > SRAM
.rodata : { *(.rodata*) } > SRAM
.bss (NOLOAD) : { _bss_start = .; *(.bss*) *(COMMON) _bss_end = .; } > SRAM
_stack_top = ORIGIN(SRAM)+LENGTH(SRAM); }
'''.replace('SRAM(rwx): ORIGIN=0x10000000,LENGTH=128K','SRAM (rwx) : ORIGIN = 0x10000000, LENGTH = 128K')
  (d/'link.ld').write_text(link)
  cmd=['arm-none-eabi-gcc','-mcpu=cortex-m23','-mthumb','-mfloat-abi=soft','-Os','-flto','-ffunction-sections','-fdata-sections','-fstack-usage','-nostartfiles',str(d/'probe.c'),'-T',str(d/'link.ld'),'-Wl,--gc-sections','-lgcc','-o',str(d/'probe.elf')];subprocess.run(cmd,check=True)
  sizes=subprocess.check_output(['arm-none-eabi-size','-A',str(d/'probe.elf')],text=True);sections={a[0]:int(a[1]) for l in sizes.splitlines() if len(a:=l.split())==3 and a[0].startswith('.') and a[1].isdigit()}
  symbols=subprocess.check_output(['arm-none-eabi-nm','-S','--size-sort',str(d/'probe.elf')],text=True);(d/'symbols.txt').write_text(symbols)
  records[name]={'small_pivot':small_pivot,'cases':cases,'repeated':repeated,'sections':sections,'command':cmd,'elf_sha256':hashlib.sha256((d/'probe.elf').read_bytes()).hexdigest(),'stack_reports':{p.name:p.read_text() for p in d.glob('*.su')}}
 (out/'result.json').write_text(json.dumps({'fraction_bits':fraction_bits,'records':records,'scope':'Fixed-scale bounded kernel only; no rescaling, complete collector, M23 timing, lifetime guarantee or trig API','source_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.iterdir() if p.suffix in ('.py','.h')}},indent=2)+'\n')
 print(json.dumps(records))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--fraction-bits',type=int,choices=(12,16),default=16);a=p.parse_args();run(a.out,a.fraction_bits)
