"""Refine the finite-difference step in registered local Q-curvature checks."""
import argparse
import json
from pathlib import Path
import numpy as np
from experiments.foster_feedback_001.estimator import Model
from experiments.foster_campaign_001.coordinates import prior
from experiments.slow_likelihood_diagnostic_001.numerics import Exact
from .diagnostics import write,identity


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--inputs',type=Path,required=True)
    p.add_argument('--diagnostics',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();args.out.mkdir(parents=True,exist_ok=False)
    steps=[.01,.003,.001,.0003,.0001]
    write(args.out/'registration.json',dict(trigger='initial0.1/0.03SD directional checks not step-stable, especially weak case',
          steps_in_original_GN_direction=steps,anchor='frozen retained-data optimum',source=identity(Path(__file__)),
          inference_truth_reads=0,no_refitting=True))
    index=json.loads((args.diagnostics/'index.json').read_text());rows=[]
    for entry in index['cases']:
        case=args.inputs/entry['label'];path=args.diagnostics/entry['label']/'result.json'
        if identity(path)!=entry['result']:raise ValueError('changed fit')
        r=json.loads(path.read_text());reg=json.loads((case/'regeneration.json').read_text())
        if identity(case/'observations.npy')!=reg['observations']:raise ValueError('changed data')
        cfg=json.loads((case/'calibration.json').read_text());mean,L=prior(cfg)
        model=Model(Path(reg['source_case']).parent/'backend_c/estimator.so',cfg)
        obs=np.load(case/'observations.npy',mmap_mode='r')[:reg['fit_records']]
        exact=Exact(model,obs,mean,L);w=np.array(r['exact']['selected']['w'])
        d=np.array(r['observed_directions']['exact'][0]['direction_w'])
        c,g,P,_,_=exact(w);evaluated=[]
        for h in steps:
            plus=exact(w+h*d);minus=exact(w-h*d)
            evaluated.append(dict(step_GN_SD=h,observed_curvature=float(d@(plus[1]-minus[1])/(2*h)),
                GN_curvature=float(d@P@d),cost_second_difference=float((plus[0]-2*c+minus[0])/h**2)))
        rows.append(dict(label=entry['label'],fit=entry['result'],direction_w=d,checks=evaluated))
        write(args.out/'result.json',dict(cases=rows,inference_truth_reads=0,status='running'))
    write(args.out/'result.json',dict(cases=rows,inference_truth_reads=0,status='complete',
        scope='Directional derivatives only; small cost differences may reach floating-point cancellation. Not full Hessian or validated covariance.'))


if __name__=='__main__':main()
