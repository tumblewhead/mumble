"""Targeted controls, host sanitizer and target resource build for optimized C."""
import hashlib,json,os,subprocess,sys
from experiments.foster_c_baseline_001.build import FLAGS
from .build import build,HERE,BASE
ROOT=HERE.parents[1]
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def main():
    report={'checks':{},'commands':[]};env={**os.environ,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'}
    def run(name,cmd,extra=None):
        r=subprocess.run(cmd,text=True,capture_output=True,env={**env,**(extra or {})})
        report['commands'].append(cmd);report['checks'][name]={'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr};return r
    for stage in range(4):build(stage)
    run('targeted_tests',[sys.executable,'-B','-m','unittest','experiments.foster_c_cpu_001.test_cpu','-v'])
    out=build(3,sanitize=True)
    objects=[str(out/(n+'.o')) for n in ['rolling','numeric','history','model']]
    run('sanitizer_link',['clang',*FLAGS,'-g','-DFB_PROFILE','-D_POSIX_C_SOURCE=200809L','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(BASE/'host_cli.c'),*objects,'-lm','-o',str(out/'host_cli')])
    run('sanitizer_run',[str(out/'host_cli'),str(BASE/'sanitizer_fixture.bin')],{'ASAN_OPTIONS':'detect_leaks=0'})
    target=build(3,arm=True);objects=[str(target/(n+'.o')) for n in ['rolling','numeric','history','model']]
    run('M23_link',['arm-none-eabi-gcc',*FLAGS,'-mcpu=cortex-m23','-mthumb','-mfloat-abi=soft','-nostartfiles','--specs=nosys.specs',f'-Wl,--gc-sections,-e,probe_entry,-Map,{target}/probe.map',str(BASE/'link_probe.c'),*objects,'-lm','-o',str(target/'probe.elf')])
    run('M23_size',['arm-none-eabi-size',str(target/'probe.elf')])
    frozen=json.loads((BASE/'verification.json').read_text())['artifacts']
    changed=[p for p,v in frozen.items() if sha(ROOT/p)!=v['sha256']]
    older=json.loads((ROOT/'experiments/foster_feedback_001/verification.json').read_text())['artifacts']
    old_changed=[p for p,v in older.items() if sha(ROOT/p)!=v['sha256']]
    report['preserved']={'C_baseline_artifacts':len(frozen),'C_baseline_changed':changed,'original_Foster_artifacts':len(older),'original_Foster_changed':old_changed}
    report['limits']='LeakSanitizer disabled in traced environment; no heap in core. Link probe lacks target startup/memory map and is not executed RTL evidence.'
    report['status']='passed' if not changed and not old_changed and all(v['returncode']==0 for v in report['checks'].values()) else 'failed'
    (HERE/'qualification.json').write_text(json.dumps(report,indent=2)+'\n');print(report['status'],{k:v['returncode'] for k,v in report['checks'].items()})
    if report['status']!='passed':raise SystemExit(1)
if __name__=='__main__':main()
