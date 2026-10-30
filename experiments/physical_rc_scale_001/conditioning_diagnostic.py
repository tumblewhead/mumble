"""Construction-only conditional/prefix decomposition, registered before use."""
import json
from pathlib import Path
import numpy as np
from experiments.physical_rc_scale_001.combined_message import Message as Combined
from experiments.physical_rc_scale_001.message import Message,c,log_mass
from experiments.region_compression_001 import compare as base

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def evaluate(x,labels,msg):
    y,a,_=c.encode(x,msg.chart,msg.frame)
    response=-np.expm1(-20/np.exp(x[:,:3]))
    carried=(response*x[:,12:15]).sum(1)
    previous=(response[:,:2]*x[:,12:14]).sum(1)
    ratio=response[:,2]/a[:,2]
    m1,m2=np.empty(len(x)),np.empty(len(x))
    gradient=[]
    nodes,weights=np.polynomial.legendre.leggauss(512)
    for r,reg in enumerate(msg.regions):
        take=labels==r;local=y[take];aa=a[take]
        beta=c.coefficients(reg,11)
        mu=beta[0]+local[:,:11]@beta[1:]
        sd=np.full(len(mu),np.exp(reg['shape'][11]))
        if 'mix' in reg:
            sd/=np.sqrt(1+reg['mix'][2]*(((-np.expm1(-1))/aa[:,2])**2-1))
        left,right=(-.25*aa[:,2]-mu)/sd,(.25*aa[:,2]-mu)/sd
        z=log_mass(left,right)
        pa=np.exp(-.5*left**2-.5*c.old.LOG2PI-z);pb=np.exp(-.5*right**2-.5*c.old.LOG2PI-z)
        delta=pa-pb
        mean=mu+sd*delta
        second=mu*mu+2*mu*sd*delta+sd*sd*(1+left*pa-right*pb)
        # Check the analytic moments independently on16 rows per component.
        yy=.25*aa[:16,2,None]*nodes
        mass=np.exp(-.5*((yy-mu[:16,None])/sd[:16,None])**2)*weights
        mass/=mass.sum(1)[:,None]
        np.testing.assert_allclose(mean[:16],(mass*yy).sum(1),atol=2e-12,rtol=0)
        np.testing.assert_allclose(second[:16],(mass*yy**2).sum(1),atol=2e-12,rtol=0)
        m1[take]=previous[take]+ratio[take]*mean
        m2[take]=previous[take]**2+2*previous[take]*ratio[take]*mean+ratio[take]**2*second
        # Candidate physical compensation directions, measured only on the
        # construction rows in the returned diagnostic; no new fit here.
        extra=local[:,9:11]*(aa[:,2,None]/aa[:,:2]-1)
        gmean=(mean-local[:,11])/sd**2
        gradient.append((extra.T@gmean/len(local)).tolist())
    return dict(empirical_mean=float(carried.mean()),empirical_variance=float(carried.var()),
                conditional_mean=float(m1.mean()),conditional_second_moment=float(m2.mean()),
                conditional_variance=float(m2.mean()-m1.mean()**2),
                compensation_score_by_component=gradient)


def main():
    out=HERE/'conditioning001';out.mkdir(exist_ok=False)
    source=ROOT/'experiments/natural_hysteresis_001/attempt001/result.json'
    old=json.loads(source.read_text())
    paths=[Path(__file__),HERE/'attempt001/result.json',HERE/'combined001/result.json',source]
    base.write(out/'reservation.json',dict(
        purpose='After partial scale repair, isolate slow conditional error from generated-prefix error using construction only; no fits or heldout scoring.',
        formula='S=previous_carried+r3*F3; integrate the last conditional analytically for E[S] and E[S²]',
        limits=dict(source_rows=32768,generated_rows=262144,new_fits=0),
        identities={str(p.relative_to(ROOT)):base.identity(p) for p in paths}))
    rows=[]
    for prefix in [8,32]:
        ref=old['references'][str(prefix)]['inherited']
        train=np.concatenate([np.load(ROOT/path,allow_pickle=False)['projected'][:,:16] for path in ref['train']])
        trainlabels=np.searchsorted([.5],c.old.to_unit(train)[:,5],side='right')
        seeds=next(case for case in old['cases'] if case['prefix']==prefix and case['arm']=='natural_refit')['batches']
        for arm,folder,cls in [('baseline','attempt001',Message),('combined_information','combined001',Combined)]:
            path=HERE/folder/f'prefix{prefix}_{arm}_message.json'
            msg=cls.restore(json.loads(path.read_text())['posterior'])
            construction=evaluate(train,trainlabels,msg)
            arrays,labels=[],[]
            for batch in seeds:
                x,_=msg.draw(batch['draws'],batch['seed']);arrays.append(x)
                rng=np.random.default_rng(batch['seed'])
                labels.append(rng.choice(2,len(x),p=np.exp([r['logweight'] for r in msg.regions])))
            generated=evaluate(np.concatenate(arrays),np.concatenate(labels),msg)
            decomposition=dict(
                conditional_fit_mV2=1e6*(construction['conditional_variance']-construction['empirical_variance']),
                prefix_distribution_mV2=1e6*(generated['conditional_variance']-construction['conditional_variance']),
                draw_noise_mV2=1e6*(generated['empirical_variance']-generated['conditional_variance']))
            total=1e6*(generated['empirical_variance']-construction['empirical_variance'])
            assert abs(sum(decomposition.values())-total)<1e-9
            row=dict(prefix=prefix,arm=arm,construction=construction,generated=generated,variance_decomposition=decomposition,
                scope='Augmented component labels: fixed construction memberships versus model latent labels; isolates carried sum only, not full voltage')
            rows.append(row);print(prefix,arm,decomposition,'construction score',construction['compensation_score_by_component'],flush=True)
    base.write(out/'result.json',dict(status='conditional_prefix_decomposition_completed',cases=rows,new_fits=0))


if __name__=='__main__':main()
