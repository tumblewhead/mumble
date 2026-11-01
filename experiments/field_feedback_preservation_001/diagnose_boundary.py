"""Resolve prior stalled Gaussian-boundary fits without changing evidence."""
import argparse
import json
from pathlib import Path
import numpy as np
from experiments.foster_feedback_001.estimator import Model
from experiments.slow_likelihood_diagnostic_001.numerics import Exact
from experiments.uncertainty_weak_stimulus_001.diagnostics import write,identity,endpoint
from .numerics import polish_stationary,observed_hessian


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    base=Path(__file__).resolve().parents[1]/'uncertainty_weak_stimulus_001'
    case=base/'weak_boundary_regeneration002';reg=json.loads((case/'regeneration.json').read_text())
    for name,key in [('observations.npy','observations'),('last_refresh.npz','last_refresh')]:
        if identity(case/name)!=reg[key]:raise ValueError('changed source artifact')
    cfg=json.loads((case/'calibration.json').read_text())
    obs=np.load(case/'observations.npy',mmap_mode='r')[reg['last_refresh_records']:reg['fit_records']]
    m=np.load(case/'last_refresh.npz')['after'];L=m[16:272].reshape(16,16)
    obj=Exact(Model(Path(reg['source_case']).parent/'backend_c/estimator.so',cfg),obs,m[:16],L)
    previous=base/'weak_boundary002/result.json';old=json.loads(previous.read_text())
    args.out.mkdir(parents=True,exist_ok=False)
    write(args.out/'registration.json',dict(source=identity(Path(__file__)),numerics=identity(Path(__file__).with_name('numerics.py')),
        previous=identity(previous),observations=reg['observations'],starts='three preserved stalled states',truth_reads=0,
        rule='Observed-Newton stationarity; report every mode and observed/GN widths separately; no global posterior claim.'))
    records=[]
    for s in old['joint_suffix']['continuations']:
        fit=polish_stationary(obj,s['w']);fit['start']=s['start']
        fit['endpoint']=endpoint(fit['end'],fit['F']@fit['root'])
        H,_=observed_hessian(obj,fit['w'],step=3e-5)
        if np.linalg.eigvalsh(H)[0]>0:
            observed_root=L@np.linalg.solve(np.linalg.cholesky(H).T,np.eye(16))
            fit['observed_curvature_Q_log_SD']=float(np.linalg.norm(observed_root[5]))
        records.append(fit)
    write(args.out/'result.json',dict(fits=records,truth_reads=0,
        scope='Local stationary modes for Gaussian-boundary approximation; multiple modes retained, not exact marginal posterior uncertainty.'))


if __name__=='__main__':main()
