"""Run targeted controls, sanitizer harness and target build without long replays."""
import hashlib,json,os,subprocess,sys
from pathlib import Path
from .build import build,FLAGS
from .reference import HERE,ROOT,config
import numpy as np

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    report={'checks':{},'commands':[]};env={**os.environ,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'}
    def command(name,cmd,extra=None):
        result=subprocess.run(cmd,env={**env,**(extra or {})},text=True,capture_output=True)
        report['commands'].append(cmd);report['checks'][name]={'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr}
        return result
    build(HERE/'build')
    command('targeted_tests',[sys.executable,'-B','-m','unittest','experiments.foster_c_baseline_001.test_baseline','-v'])
    out=HERE/'build_clang_sanitize';build(out,sanitize=True,compiler='clang')
    cmd=['clang',*FLAGS,'-g','-DFB_PROFILE','-D_POSIX_C_SOURCE=200809L','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(HERE/'host_cli.c'),*[str(out/(n+'.o')) for n in ('baseline','history','numeric','model')],'-lm','-o',str(out/'host_cli')]
    command('sanitizer_link',cmd)
    cfg,c,m=config();fixture=HERE/'sanitizer_fixture.bin';obs=np.load(ROOT/'experiments/foster_cccv_stimulus_001/cycle001/case_0000/observations.npy',mmap_mode='r')[:4097]
    with fixture.open('wb') as f:np.r_[list(c.cal),list(m.mean),list(m.root),m.logZ].tofile(f);obs.tofile(f)
    command('address_undefined_sanitizers',[str(out/'host_cli'),str(fixture)],{'ASAN_OPTIONS':'detect_leaks=0'})
    report['sanitizer_limits']='LeakSanitizer disabled: tracing environment unsupported. Core has no heap allocation. GCC16 sanitizer compile diagnosed stringop-overread in unchanged parent model; Clang sanitizer build used without modifying it.'
    target=HERE/'build_m23';build(target,arm=True)
    cmd=['arm-none-eabi-gcc',*FLAGS,'-mcpu=cortex-m23','-mthumb','-mfloat-abi=soft','-nostartfiles','--specs=nosys.specs',f'-Wl,--gc-sections,-e,probe_entry,-Map,{target}/probe.map',str(HERE/'link_probe.c'),*[str(target/(n+'.o')) for n in ('baseline','history','numeric','model')],'-lm','-o',str(target/'probe.elf')]
    command('M23_link_probe',cmd)
    command('M23_size',['arm-none-eabi-size',str(target/'probe.elf')])
    command('M23_symbols',['arm-none-eabi-nm','-S','--size-sort',str(target/'probe.elf')])
    expected=json.loads((ROOT/'experiments/foster_feedback_001/verification.json').read_text())['artifacts']
    changed=[name for name,v in expected.items() if sha(ROOT/name)!=v['sha256']]
    report['parent_preservation']={'artifacts':len(expected),'changed':changed}
    report['status']='passed' if not changed and all(v['returncode']==0 for v in report['checks'].values()) else 'failed'
    (HERE/'qualification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'parent_artifacts':len(expected),'checks':{k:v['returncode'] for k,v in report['checks'].items()}}))
    if report['status']!='passed':raise SystemExit(1)
if __name__=='__main__':main()
