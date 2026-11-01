"""Bitwise comparison and alternating matched timing from fully owned exports."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
from experiments.foster_campaign_001.tangent_backend import TangentBackend
from checks import identity,save,capture,restore,digest,exported,stats


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def compare(prefix,dest,frozen,repetitions):
    meta,saved,mean,root=exported(prefix)
    expected=json.loads((dest/'reference.json').read_text())
    if expected['initial_export']!=identity(prefix/'initial_estimator_state.npz') or expected['observations']!=identity(prefix/'observations.npy'):
        raise ValueError('reference/export mismatch')
    # Original adapter and original kernel binary, not a reimplementation of the
    # reference. Every owned state below must also match the isolated frozen run.
    native=load('experiments.field_tangent_native_001._frozen_native',frozen/'experiments/field_tangent_native_001/native.py')
    module=load('experiments.foster_campaign_001._frozen_tangent',frozen/'experiments/foster_campaign_001/tangent_backend.py')
    module.Native=native.Native
    job=json.loads((prefix/'job.json').read_text());campaign=Path(job['campaign'])
    candidate_dir=dest/'candidate_build';candidate_dir.mkdir()
    args=(meta['config'],meta['source_id'],meta['model_id'],meta['sample_rate_Hz'],SimpleNamespace(**meta['settings']))
    banks={'reference':module.TangentBackend(campaign,*args),'fused':TangentBackend(candidate_dir,*args)}
    for bank in banks.values():
        np.testing.assert_array_equal(bank.mean,mean);np.testing.assert_array_equal(bank.prior_root,root)
        restore(bank,saved)
    obs=np.load(prefix/'observations.npy',allow_pickle=False);first=meta['sequence'];failures=[]
    parity=0;refreshes={'reference':0,'fused':0};phase_snapshots={}
    interval=banks['reference'].interval;boundary=(first//interval+1)*interval
    anchors=(boundary-16,boundary,boundary+(interval//32)*16)
    for offset in range(0,len(obs),16):
        for key,bank in banks.items():
            bank.advance(first+offset,obs[offset:offset+16])
            actual=digest(bank)
            if actual!=expected['committed_window_hashes'][offset//16]:
                failures.append(dict(arm=key,sequence=first+offset+16,expected=expected['committed_window_hashes'][offset//16],actual=actual))
        a=banks['reference'].full_message();b=banks['fused'].full_message()
        if not np.array_equal(a,b):raise ValueError('joint message changed: '+str(first+offset+16))
        if first+offset+16 in anchors:
            phase_snapshots[str(first+offset+16)]={key:digest(bank) for key,bank in banks.items()}
        parity+=1
    if failures:
        save(dest/'parity_failures.json',failures);raise ValueError('owned state differs from frozen suffix')
    # Retained full state/mean/root and actual intervals are bitwise equal, so
    # deterministic frozen forecast outputs are identical at all three anchors.
    timings={k:[] for k in banks};by_repeat=[]
    final={k:digest(b) for k,b in banks.items()}
    for repeat in range(repetitions):
        for bank in banks.values():restore(bank,saved)
        repeat_times={k:[] for k in banks}
        for offset in range(0,len(obs),16):
            order=('reference','fused') if (repeat+offset//16)%2==0 else ('fused','reference')
            for key in order:
                bank=banks[key];t=time.perf_counter();bank.advance(first+offset,obs[offset:offset+16]);elapsed=time.perf_counter()-t
                timings[key].append(elapsed);repeat_times[key].append(elapsed)
        for key,bank in banks.items():
            if digest(bank)!=final[key]:raise ValueError('timed repeat changed final state')
        by_repeat.append({k:stats(v) for k,v in repeat_times.items()})
    result=dict(status='bitwise_parity_pass',records=len(obs),windows_checked=parity,
        reference_certificate=identity(dest/'reference.json'),all_owned_state_exact=True,
        anchors=phase_snapshots,timing={k:stats(v) for k,v in timings.items()},per_repeat=by_repeat,
        speedup=sum(timings['reference'])/sum(timings['fused']),
        final_counts={k:b.counts() for k,b in banks.items()},storage={k:b.storage() for k,b in banks.items()},
        scope='Same fresh starting state each repeat; alternate arm order per window/repeat. Hashing, IO, restore and forecast scoring excluded from timed advance. Host only.',
        memory_note='Fused scratch reserves3360B and removes ordinary16x82 lifted rows10496B plus live-state copy888B; refresh and rare irregular-batch fallback retain their workspace. Not whole-system SRAM.')
    save(dest/'result.json',result)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('study',type=Path);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--prefixes',nargs='+');p.add_argument('--repetitions',type=int,default=5)
    p.add_argument('--frozen',type=Path,default=Path('/home/easy/proj/mumble/.worktrees/uncertainty-weak-stimulus'))
    a=p.parse_args()
    if a.repetitions<1:p.error('positive repetitions required')
    a.study=a.study.resolve();a.out=a.out.resolve();a.frozen=a.frozen.resolve()
    a.out.mkdir(parents=True,exist_ok=False)
    directories=sorted(a.study.glob('case_*'))
    if a.prefixes:
        if set(a.prefixes)-{d.name for d in directories}:p.error('unknown prefix')
        directories=[d for d in directories if d.name in a.prefixes]
    source_files=[HERE/n for n in ('checks.py','compare.py','reference.py')]+[ROOT/'experiments/field_tangent_native_001'/n for n in ('kernel.c','kernel.h','native.py')]+[ROOT/'experiments/foster_campaign_001/tangent_backend.py',ROOT/'experiments/joint_rate_history_001/probe.c']
    save(a.out/'manifest.json',dict(study=str(a.study),study_summary=identity(a.study/'summary.json'),
        source_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        sources={str(f.relative_to(ROOT)):identity(f) for f in source_files},repetitions=a.repetitions,
        prefixes=[d.name for d in directories],thread_environment={k:os.environ.get(k) for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS')}))
    results=[]
    for prefix in directories:
        dest=a.out/prefix.name;dest.mkdir()
        subprocess.run([sys.executable,'-B',str(HERE/'reference.py'),str(a.frozen),str(prefix),str(dest/'reference.json')],cwd=a.frozen,check=True)
        result=compare(prefix,dest,a.frozen,a.repetitions)
        results.append(dict(prefix=prefix.name,**result))
        save(a.out/'summary.json',dict(status='completed' if len(results)==len(directories) else 'running',results=results))
        print(prefix.name+': bitwise parity; speedup '+format(result['speedup'],'.3f')+'x',flush=True)
    # Ensure live source did not drift during the comparison.
    manifest=json.loads((a.out/'manifest.json').read_text())
    for name,value in manifest['sources'].items():
        if identity(ROOT/name)!=value:raise ValueError('source changed during qualification')
    print('Results: '+str(a.out/'summary.json'),flush=True)


if __name__=='__main__':main()
