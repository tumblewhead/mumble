"""Build previous optimized control, sparse derivatives, and sparse+thermal cache."""
import argparse,json,subprocess
from pathlib import Path
from experiments.foster_c_baseline_001.build import FLAGS,MODEL
HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'foster_c_baseline_001'
PREVIOUS=HERE.parent/'foster_c_cpu_001'
def build(stage=2,arm=False,sanitize=False):
    out=HERE/f'build_{"m23" if arm else "sanitize" if sanitize else "host"}_{stage}';out.mkdir(exist_ok=True)
    cc='arm-none-eabi-gcc' if arm else 'clang' if sanitize else 'cc'
    extra=['-mcpu=cortex-m23','-mthumb','-mfloat-abi=soft'] if arm else ['-fPIC','-DFB_PROFILE','-D_POSIX_C_SOURCE=200809L']
    if sanitize:extra+=['-fsanitize=address,undefined','-fno-omit-frame-pointer','-g']
    extra += ['-DFB_OPT_STAGE=3',f'-DFB_MODEL_STAGE={stage}','-include',str(HERE/'baseline.h')]
    sources=[HERE/'rolling.c' if stage else PREVIOUS/'rolling.c',BASE/'numeric.c',BASE/'history.c',HERE/'model.c' if stage else MODEL]
    commands=[];objects=[]
    for source in sources:
        obj=out/(source.stem+'.o');compile_extra=extra[:-2] if source==MODEL else extra
        cmd=[cc,*FLAGS,*compile_extra,'-c',str(source),'-o',str(obj)]
        subprocess.run(cmd,check=True);commands.append(cmd);objects.append(str(obj))
    if not arm:
        cmd=[cc,'-shared',*extra,*objects,'-lm','-o',str(out/'baseline.so')];subprocess.run(cmd,check=True);commands.append(cmd)
    (out/'build.json').write_text(json.dumps({'stage':stage,'compiler':subprocess.check_output([cc,'--version'],text=True).splitlines()[0],'commands':commands},indent=2)+'\n')
    return out
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',type=int,choices=range(3),default=2);p.add_argument('--arm',action='store_true');p.add_argument('--sanitize',action='store_true');a=p.parse_args();print(build(a.stage,a.arm,a.sanitize))
