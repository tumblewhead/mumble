"""Reproducible baseline builds; all old sources remain untouched."""
import argparse,json,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
MODEL=ROOT/'experiments/foster_feedback_001/model.c'
SOURCES=[HERE/n for n in ('baseline.c','numeric.c','history.c')]+[MODEL]
FLAGS=['-std=c11','-O2','-fno-fast-math','-ffp-contract=off','-Wall','-Wextra','-Werror','-pedantic','-fstack-usage']
def build(out,arm=False,sanitize=False,compiler=None):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=True);commands=[]
    cc=compiler or ('arm-none-eabi-gcc' if arm else 'cc')
    extra=['-mcpu=cortex-m23','-mthumb','-mfloat-abi=soft'] if arm else ['-fPIC','-D_POSIX_C_SOURCE=200809L','-DFB_PROFILE']
    if sanitize:extra+=['-fsanitize=address,undefined','-fno-omit-frame-pointer','-g']
    objects=[]
    for source in SOURCES:
        obj=out/(source.stem+'.o');cmd=[cc,*FLAGS,*extra,'-c',str(source),'-o',str(obj)]
        subprocess.run(cmd,check=True);commands.append(cmd);objects.append(str(obj))
    if not arm:
        cmd=[cc,'-shared',*extra,*objects,'-lm','-o',str(out/'baseline.so')]
        subprocess.run(cmd,check=True);commands.append(cmd)
    (out/'build.json').write_text(json.dumps(dict(commands=commands,compiler=subprocess.check_output([cc,'--version'],text=True).splitlines()[0]),indent=2)+'\n')
    return out/'baseline.so'
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=HERE/'build');p.add_argument('--arm',action='store_true');p.add_argument('--sanitize',action='store_true');p.add_argument('--cc');a=p.parse_args();build(a.out,a.arm,a.sanitize,a.cc)
