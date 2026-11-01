"""Harness-only replay from sample zero; estimator checkpoints are fit starts, not data."""
import argparse
import json
from pathlib import Path
import sys
import time


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--source-root',type=Path,required=True)
    p.add_argument('--case',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--hours',nargs='+',type=float,default=[24,72])
    a=p.parse_args()
    sys.path.insert(0,str(a.source_root.resolve()))
    import numpy as np
    from experiments.foster_campaign_001.compact import CHUNK,restore_checkpoint,atomic_json
    from experiments.foster_campaign_001.backend import identity
    case=a.case.resolve();out=a.out.resolve();run=case.parent
    settings=json.loads((run/'campaign_plan.json').read_text())['configuration']
    cfg=json.loads((run/'calibration.json').read_text())
    sc=json.loads((case/'scenario.json').read_text())
    scenario={k:sc[k] for k in ('cell','load','noise_v','seed','load_seed') if k in sc}
    entries=json.loads((case/'checkpoints/index.json').read_text())['checkpoints']
    stream,_,meta=restore_checkpoint(case,entries[0],cfg,sc['cell_definition'],scenario,settings)
    assert stream.index==0
    selected=[min(entries,key=lambda e:abs(e['sequence']-h*3600*stream.rate)) for h in a.hours]
    if any(e['sequence']<=0 for e in selected):raise ValueError('positive prefix required')
    stop=max(e['sequence'] for e in selected)
    out.mkdir(parents=True,exist_ok=False)
    atomic_json(out/'registration.json',dict(command=sys.argv,source_case=str(case),source_binding=meta['binding'],
        requested_hours=a.hours,selected=selected,calibration=identity(run/'calibration.json'),
        selection='nearest saved checkpoint by sample count, before observing diagnostics',
        semantics='full observations regenerated from origin; no estimator replay; exact stimulus checkpoints required'))
    atomic_json(out/'calibration.json',cfg)
    obs=np.lib.format.open_memmap(out/'observations.npy',mode='w+',dtype='float64',shape=(stop,5))
    checks=[];targets={e['sequence'] for e in selected};began=time.perf_counter()
    for entry in entries[1:]:
        n=entry['sequence']
        if n>stop:break
        while stream.index<n:
            first=stream.index
            rows,truth,_=stream.read(min(CHUNK,n-first))
            if stream.failure or not len(rows):raise RuntimeError(stream.failure)
            obs[first:stream.index]=rows
        saved,banks,binding=restore_checkpoint(case,entry,cfg,sc['cell_definition'],scenario,settings)
        if stream.snapshot()!=saved.snapshot():raise RuntimeError('stimulus checkpoint mismatch')
        checks.append(dict(sequence=n,stimulus_exact=True,checkpoint=entry))
        if n in targets:
            field=banks['field64'];field._flush_field()
            arrays=field.checkpoint_arrays()
            np.savez(out/f'field_{n}.npz',**arrays)
            atomic_json(out/f'prefix_{n}.json',dict(sequence=n,hours=n/stream.rate/3600,
                field=identity(out/f'field_{n}.npz'),checkpoint=entry,counts=field.counts(),
                model_binary=str(run/'backend_c/estimator.so'),model_identity=identity(run/'backend_c/estimator.so'),
                field_binary=str(run/'backend_field/response.so'),field_binary_identity=identity(run/'backend_field/response.so')))
            atomic_json(out/f'scoring_only_{n}.json',dict(endpoint=truth[-1].tolist(),parameters=sc['cell_definition']['parameters']))
        print(json.dumps(dict(sequence=n,hours=n/stream.rate/3600,wall_s=time.perf_counter()-began)),flush=True)
    obs.flush()
    atomic_json(out/'validated.json',dict(status='validated',observations=identity(out/'observations.npy'),
        calibration=identity(out/'calibration.json'),checks=checks,selected=selected,wall_s=time.perf_counter()-began))

if __name__=='__main__':main()
