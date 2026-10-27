#!/usr/bin/env python3
"""Bounded read-only audit; reuse qualified replay, never fit a new estimate."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
import json
from pathlib import Path
import resource
import struct
import sys
import time
import numpy as np
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE.parent/'desktop_history_001'))
import desktop as d

def main():
    plan=d.load(HERE/'analysis_plan.json');out=HERE/'attempt001';out.mkdir()
    q=d.load(d.HERE/'qualification/development001/receipt.json')
    binary=d.HERE/'qualification/development001/replay.so'
    assert d.sources()==q['sources'] and d.runner.identity(binary)==q['binary']
    parent=d.load(d.HERE/'attempt001/receipt.json')
    for name,h in parent['files'].items():assert d.runner.identity(d.HERE/'attempt001'/name)==h
    inputs={n:ROOT/v['path'] for n,v in d.load(d.HERE/'plan.json')['inputs'].items()}
    expected=HERE.parent/'fixed_prefix_shape_001/attempt001/expected.bin'
    oldplan=d.load(HERE.parent/'structured_history_repair_001/plan.json')
    for name,path in inputs.items():assert d.runner.identity(path)=={k:oldplan['inputs'][name][k] for k in ('bytes','sha256')}
    assert d.runner.identity(expected)=={k:oldplan['inputs']['expected'][k] for k in ('bytes','sha256')}
    bindings={'analyzer':d.runner.identity(Path(__file__)),'plan':d.runner.identity(HERE/'analysis_plan.json'),
        'desktop_receipt':d.runner.identity(d.HERE/'attempt001/receipt.json'),'qualification':d.runner.identity(d.HERE/'qualification/development001/receipt.json'),
        'binary':d.runner.identity(binary),'observations':d.runner.identity(inputs['observations']),'old_estimates':d.runner.identity(expected)}
    d.runner.save(out/'reservation.json',bindings)
    started=time.monotonic();cpu=time.process_time();result={'status':'unresolved','bindings':bindings,'rows':[]}
    try:
        r=d.Replay(binary)
        with inputs['observations'].open('rb') as f:raw=f.read(plan['checkpoints'][-1]*32)
        a=r.decode(raw,0);del raw
        previous=r.mean.copy()
        with expected.open('rb') as f:
            for n in plan['checkpoints']:
                saved=d.load(d.HERE/'attempt001/causal'/('checkpoint_'+str(n)+'.json'));x=np.array(saved['x'])
                ev=r.evaluate(a[:n],x);assert ev is not None
                assert ev[0]==saved['likelihood'] and ev[3].tolist()==saved['endpoint']
                prior,pg,ph=r.prior(x);assert prior==saved['prior']
                f.seek((n//16)*236);row=f.read(236);assert struct.unpack_from('<Q',row)[0]==n
                old=np.array(struct.unpack_from('<16d',row,8));old_ev=r.evaluate(a[:n],old,False);assert old_ev is not None
                H=ev[2]*r.sd[:,None]*r.sd[None,:]
                eigen=np.linalg.eigvalsh(H);tol=16*np.finfo(float).eps*max(abs(eigen))
                change=(x-previous)/r.sd
                result['rows'].append({'prefix':n,'cost_reproduced_exactly':True,
                    'likelihood_GN_eigenvalues_public_SD_scaled':eigen.tolist(),
                    'roundoff_rank_threshold':float(tol),'eigenvalues_above_roundoff_threshold':int(sum(eigen>tol)),
                    'GN_condition_ratio_if_positive':float(eigen[-1]/eigen[0]) if eigen[0]>tol else None,
                    'original_coordinate_gradient':ev[1].tolist(),
                    'total_gradient_public_SD_scaled':((ev[1]+pg)*r.sd).tolist(),
                    'step_from_previous_checkpoint_in_public_SD':change.tolist(),
                    'max_absolute_step_public_SD':float(max(abs(change))),
                    'desktop_total_NLL':ev[0]+prior,'old_rolling_point_exact_total_NLL':old_ev[0]+r.prior(old)[0],
                    'old_minus_desktop_total_NLL':old_ev[0]+r.prior(old)[0]-ev[0]-prior,
                    'last_recorded_solver_stop':saved['status']})
                previous=x
        assert r.steps==plan['model_steps'] and r.calls==10 and r.derivative_calls==5
        result.update(status='completed',model_steps=r.steps,optimizer_calls=0,truth_reads=0,
            CPU_s=time.process_time()-cpu,wall_s=time.monotonic()-started,
            peak_RSS_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
            memory_arithmetic={'current_other_planned_bytes':10216-5624,
                'triangular_binary64_factor_bytes':{str(m):8*m*(m+1)//2 for m in (10,17,37,55,76)},
                'binary32_37feature_factor_bytes':4*37*38//2,
                'current_raw_record_bytes':16,'two_hour_raw_records_bytes':252000*16,
                'remaining_after_replacing_37factor_with_17factor_bytes':10240-(10216-5624+8*17*18//2),
                'maximum_raw_seconds_even_if_entire10KiB_used':10240/(16*35)},
            limits=plan['interpretation'])
        assert result['CPU_s']<60 and result['wall_s']<90 and result['peak_RSS_bytes']<268435456
    except BaseException as exc:result['error']=type(exc).__name__+': '+str(exc)
    finally:d.runner.save(out/'analysis.json',result)
    print(json.dumps({'status':result['status'],'rows':[{k:v for k,v in row.items() if k in ('prefix','max_absolute_step_public_SD','old_minus_desktop_total_NLL','GN_condition_ratio_if_positive','eigenvalues_above_roundoff_threshold')} for row in result['rows']],'CPU_s':result.get('CPU_s'),'error':result.get('error')}))
    if result['status']!='completed':raise SystemExit(1)

if __name__=='__main__':main()
