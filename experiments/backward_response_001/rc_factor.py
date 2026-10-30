"""Adaptive follow-up: exact RC response products, no new model or fit."""
import json
from pathlib import Path
import numpy as np
from experiments.backward_response_001 import algebra as a
from experiments.region_compression_001 import compare as base
from experiments.natural_hysteresis_001.message import Message

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def factors(x, frame):
    scale = a.c.rc.attenuation(x, frame)
    F = scale*x[:, 12:15]
    r = -np.expm1(-20/np.exp(x[:, :3]))/scale
    return F, r


def split(x, frame, anchors):
    F, r = factors(x, frame)
    mf, mr = anchors
    amplitude = (F-mf)*mr
    rate = (r-mr)*mf
    interaction = (F-mf)*(r-mr)
    carried = (r*F).sum(1)
    constant = float((mf*mr).sum())
    voltage = a.reversal_closed(x, .05, 10.)
    values = np.column_stack([amplitude, rate, interaction, voltage-carried])
    np.testing.assert_allclose(values.sum(1)+constant, voltage, atol=2e-12, rtol=0)
    return values, F, r


def main():
    out = HERE/'rc_factor001'
    out.mkdir(exist_ok=False)
    plan = json.loads((HERE/'rc_factor_plan.json').read_text())
    parent = json.loads((ROOT/plan['parent']).read_text())
    old_path = ROOT/'experiments/natural_hysteresis_001/attempt001/result.json'
    old = json.loads(old_path.read_text())
    bindings = json.loads((HERE/'attempt001/reservation.json').read_text())['identities']
    for path, expected in bindings.items():
        assert base.identity(ROOT/path) == expected, path
    for path in [HERE/'rc_factor_plan.json', Path(__file__), ROOT/plan['parent']]:
        bindings[str(path.relative_to(ROOT))] = base.identity(path)
    base.write(out/'reservation.json',dict(plan=plan,identities=bindings))
    work = {k:0 for k in plan['work_caps']}

    def charge(key, n):
        assert work[key]+n <= plan['work_caps'][key], key
        work[key] += n

    groups = {'RC_frame_amplitudes': [0,1,2], 'RC_rate_gains': [3,4,5], 'RC_amplitude_gain_interactions': [6,7,8], 'remaining_voltage': [9]}
    transform = np.zeros((4,10))
    for j,indices in enumerate(groups.values()):
        transform[j,indices]=1

    def contrast(model, ref):
        dm = model['mean']-ref['mean']
        dc = model['covariance']-ref['covariance']
        return dict(mean_difference_V=float(dm.sum()), variance_difference_V2=float(dc.sum()),
                    group_mean_difference_V=dict(zip(groups,transform@dm)),
                    group_variance_contribution_V2=dict(zip(groups,(transform@dc@transform.T).sum(1))),
                    term_variance_contribution_V2=dc.sum(1), group_covariance_difference_V2=transform@dc@transform.T)

    cases=[]
    for p in [8,32]:
        ref=old['references'][str(p)]['inherited']
        def load(path):
            with np.load(ROOT/path,allow_pickle=False) as f:
                x=f['projected'][:,:16].copy()
            charge('source_rows',len(x))
            return x
        train=[load(path) for path in ref['train']]
        held=[load(path) for path in ref['heldout']]
        msg=Message.restore(json.loads((old_path.parent/f'prefix{p}_natural_refit_message.json').read_text())['posterior'])
        F,r=factors(np.concatenate(train),msg.frame)
        anchors=(F.mean(0),r.mean(0))
        diagnostics={}
        def assess(x):
            charge('closed_reversal_rows',len(x))
            values,F,r=split(x,msg.frame,anchors)
            return dict(parts=a.moments(values),F=a.moments(F),r=a.moments(r))
        diagnostics['train']=[assess(x) for x in train]
        diagnostics['heldout']=[assess(x) for x in held]
        batches=next(row for row in old['cases'] if row['prefix']==p and row['arm']=='natural_refit')['batches']
        diagnostics['generated']=[]
        for batch in batches:
            charge('generated_rows',batch['draws'])
            charge('inverse_OCV_sample_iterations',batch['draws']*52)
            x,_=msg.draw(batch['draws'],batch['seed'])
            diagnostics['generated'].append(assess(x))
        pooled={kind:{what:a.pool([row[what] for row in rows]) for what in ['parts','F','r']} for kind,rows in diagnostics.items()}
        contrasts={name:contrast(pooled[left]['parts'],pooled[right]['parts']) for name,left,right in
                   [('model_minus_reference','generated','heldout'),('model_minus_construction','generated','train'),('construction_minus_reference','train','heldout')]}
        previous=next(c for c in parent['cases'] if c['prefix']==p)['probes']['reversal_10s']['model_minus_reference']
        assert abs(contrasts['model_minus_reference']['mean_difference_V']-previous['mean_difference_V'])<2e-12
        assert abs(contrasts['model_minus_reference']['variance_difference_V2']-previous['variance_difference_V2'])<2e-15
        cases.append(dict(prefix=p,anchors=dict(F_mean=anchors[0],r_mean=anchors[1]),pooled=pooled,contrasts=contrasts,
            batch_model_minus_construction=[contrast(row['parts'],pooled['train']['parts']) for row in diagnostics['generated']]))
        print(p, base.plain(contrasts['model_minus_construction']),flush=True)
    base.write(out/'result.json',base.plain(dict(status='exact_factor_decomposition_completed',cases=cases,work=work,groups=groups,
        qualification='No fit; all response sums and mean/variance changes agree with parent decomposition; attribution depends on construction anchors and chosen coordinates')))


if __name__=='__main__':
    main()
