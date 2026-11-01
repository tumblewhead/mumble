"""Fixed-grid omitted-mode diagnostic, never reads truth.

Dropping columns uses QR on the existing joint factor; no observation is added
and no diagonal approximation is made. Live collocation is deliberately kept
unchanged so polynomial degree and collocation-grid aliasing are separable.
"""
import argparse
import copy
import json
from pathlib import Path
import numpy as np
from experiments.shared_uncertainty_growth_001.audit import load_inputs
from experiments.slow_likelihood_diagnostic_001.numerics import solve
from experiments.uncertainty_weak_stimulus_001.diagnostics import write,fit_record,identity,CONVERGED
from .field import MixedField,Compressed,features_jacobian,transported
from experiments.foster_uncertainty_audit_001.conditional_packet import partition


def restricted(field,degree):
    chosen=[i for i,pair in enumerate(field.pairs) if sum(pair)<=degree]
    start=3+6*field.n
    keep=np.r_[np.arange(start),start+np.array(chosen),start+field.b+np.array(chosen),field.width-1].astype(int)
    f=copy.copy(field)
    f.pairs=[field.pairs[i] for i in chosen];f.p2=np.ascontiguousarray(field.p2[chosen]);f.b=len(chosen)
    f.hdegree=degree;f.width=len(keep);f.state=field.state.copy()
    f.root=np.linalg.qr(field.root[:,keep],mode='r')
    f.root*=np.where(np.diag(f.root)<0,-1.,1.)[:,None]
    return f


def omitted_modes(field,x,L):
    phi=field.features(x);D=features_jacobian(field,x)@L;start=3+6*field.n
    B=field.root@D;full=field.root@phi;lowphi=phi.copy();lowD=D.copy()
    omitted=[]
    for k,(i,j) in enumerate(field.pairs):
        if i+j>5:
            cols=[start+k,start+field.b+k];omitted.append((i,j,cols));lowphi[cols]=0;lowD[cols]=0
    low=field.root@lowphi;lowB=field.root@lowD;P=np.eye(16)+B.T@B
    terms=[];total=np.zeros(16)
    for i,j,cols in omitted:
        dr=-field.root[:,cols]@phi[cols];dB=-field.root[:,cols]@D[cols]
        g=B.T@dr+dB.T@low;total+=g
        terms.append(dict(mode=[i,j],kind='mixed' if i and j else 'pure',
            predicted_low_minus_full_Q_percent=float(-100*L[5]@np.linalg.solve(P,g))))
    direct=lowB.T@low-B.T@full
    return dict(terms=terms,gradient_identity_max_abs_error=float(np.max(abs(total-direct))),
        projected_identity_Q_error=float(100*L[5]@np.linalg.solve(P,total-direct)),
        summed_predicted_Q_percent=sum(t['predicted_low_minus_full_Q_percent'] for t in terms),
        semantics='Additive joint gradient convention at full fit, reference residual is all omitted modes removed; signed contributions may cancel, not independent variances')


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--run',type=Path,required=True)
    p.add_argument('--seed',type=int,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    rows=[]
    for n in (4325376,12976128):
        inputs=Path(f'experiments/shared_uncertainty_growth_001/inputs{a.seed}')
        cfg,mean,L,old,w,obs,entry=load_inputs(inputs,n)
        path=a.run/f'n{n}_h7';r=json.loads((path/'result.json').read_text())
        if r['status']!='complete_local_diagnostic':raise ValueError('full fit unresolved')
        if identity(path/'field.npz')!=r['field_identity']:raise ValueError('changed full field')
        f=MixedField(cfg,partition(mean)[1],1.,7,(a.run/'build/response.so').resolve())
        with np.load(path/'field.npz') as d:f.root=d['root'].copy();f.state=d['state'].copy()
        f.count=n
        x=np.array(r['fit']['x']);w=np.array(r['fit']['w']);ref=json.loads(Path(f'experiments/shared_uncertainty_growth_001/audit{a.seed}_{n}/result.json').read_text())['selected_exact']
        sd=np.linalg.norm(np.asarray(ref['root'])[5]);record=dict(records=n,modes=omitted_modes(f,x,L),variants=[])
        for degree in (5,6):
            sub=restricted(f,degree);fit=solve(Compressed(sub,mean,L),start=w)
            v=dict(degree=degree,collocation_order=8,fit=fit_record(fit),
                Q_reference_shift_SD=float((fit['x'][5]-ref['x'][5])/sd),storage=sub.storage())
            try:transported(sub,fit['x']);v['transport_status']='supported'
            except ValueError as e:v['transport_status']='unresolved';v['reason']=str(e)
            record['variants'].append(v)
        rows.append(record)
    write(a.out/'result.json',dict(seed=a.seed,cases=rows,original_run=str(a.run.resolve()),inference_truth_reads=0))

if __name__=='__main__':main()
