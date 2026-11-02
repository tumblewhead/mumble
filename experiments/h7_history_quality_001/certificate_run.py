"""Bounded-sensor stationary pilot; all truth stays in this harness/scoring file."""
import argparse
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path
import time
from types import SimpleNamespace

import numpy as np
from experiments.foster_campaign_001.backend import ROOT
from experiments.foster_campaign_001.h7_backend import H7Backend
from experiments.foster_feedback_001.plant import scalar_step
from .certificate import Certificate,Response,DEFAULT_SHAPE
from .interval import Interval as IV
from .history import write,source_receipt,verify_sources


def hidden_fixture(seed):
    # Deliberately not a population model. These draws never enter public support,
    # rate boxes, initial guesses, centering, or constraint construction.
    rng=np.random.default_rng(seed)
    Q=F(int(rng.integers(590,631)),10000)
    amplitude=[F('.72'),F('.001'),F('-.002'),F('.001'),1/Q,
               F(int(rng.integers(90,121)),1000),F('.037'),F('.075'),F('.11'),F('.014'),F('.0021')]
    tau1,tau2,tau3,kp,km=map(F,DEFAULT_SHAPE)
    params=[Q,amplitude[5],amplitude[6],tau1,amplitude[7],tau2,amplitude[8],tau3,amplitude[9],kp*Q,km*Q]
    state=[float(v) for v in amplitude[:4]]+[float(amplitude[10]/amplitude[9])]
    return amplitude,list(map(float,params)),state


def current_at(index,rate,kind):
    if kind=='rest':return 0.
    phase=index%(2040*rate)
    if phase<900*rate:return .12
    if phase<1020*rate:return 0.
    if phase<1920*rate:return -.12
    return 0.


def run_case(out,campaign,config,kind,prefixes,rate,seed,noise_seed,radii,stride):
    out.mkdir();a,params,state=hidden_fixture(seed);rng=np.random.default_rng(noise_seed)
    public=dict(kind=kind,prefixes=prefixes,rate_Hz=rate,cell_seed=seed,noise_seed=noise_seed,
                declared_voltage_error_V='.001',generated_uniform_noise_V=.0004,
                ADC_step_V=1/1024,shape=DEFAULT_SHAPE,rate_radii=radii,stride=stride)
    source=hashlib.sha256(json.dumps(public,sort_keys=True).encode()).hexdigest()
    certs=[Certificate(source,rate_radius=r,stride=stride) for r in radii]
    bank=H7Backend(campaign,config,source,'bounded-certificate-fixture-v1',rate,SimpleNamespace(field_refresh_seconds=60))
    # Independent real-model consistency check, used solely to score assumptions.
    physical=Response();A=F(0);measurement_valid=True;hashobs=hashlib.sha256()
    results=[];started=time.perf_counter();index=0;bank_failure=None
    def snapshot():
        point=bank.last_message() if bank_failure is None else None
        samples=[]
        for radius,certificate in zip(radii,certs):
            result=certificate.query(soc_point=float(point[0]) if point is not None else None,
                                     q_point=math.exp(point[5]) if point is not None else None)
            actual_z=a[0]-A*a[4];actual_Q=1/a[4]
            score=dict(selected_measurement_envelope_verified=measurement_valid,
                       true_SOC=float(actual_z),true_Q_Ah=float(actual_Q))
            if result['execution']=='verified_outer_enclosure':
                for name,truth in [('SOC',actual_z),('Q',actual_Q)]:
                    lo,hi=[F(*v) for v in result['enclosures'][name]['exact']]
                    score[name+'_contained']=lo<=truth<=hi
            result.update(rate_radius=radius,scoring_only=score)
            samples.append(result)
        entry=dict(records=index,hours=index/rate/3600,certificates=samples,
            H7_status=bank.publication_status(),H7_point=None if point is None else dict(SOC=float(point[0]),Q_Ah=float(math.exp(point[5]))),
            observation_sha256=hashobs.hexdigest(),wall_s=time.perf_counter()-started)
        results.append(entry)
        write(out/'result.json',dict(status='running',public=public,prefixes=results))
        print(json.dumps(dict(case=kind,records=index,wall_s=entry['wall_s'],
            authorizations=[dict(radius=s['rate_radius'],SOC_midpoint=s.get('SOC',{}).get('midpoint_authorized'),
                SOC_H7=s.get('SOC',{}).get('H7_point_authorized'),Q_midpoint=s.get('Q',{}).get('midpoint_authorized'),
                Q_H7=s.get('Q',{}).get('H7_point_authorized')) for s in samples])),flush=True)
    snapshot()
    for target in sorted({max(16,math.ceil(s*rate/16)*16) for s in prefixes}):
        while index<target:
            n=min(16,target-index);rows=[]
            for i in range(index,index+n):
                I=current_at(i,rate,kind);dt=1/rate
                state,V=scalar_step(state,params,dt,I,config['ocv_intercept_V'],config['ocv_slope_V_per_SOC'])
                error=rng.uniform(-.0004,.0004);code=math.floor((V+error-1.5)*1024+.5)
                if not 0<=code<=4095:raise ValueError('fixture ADC support')
                measured=1.5+code/1024;rows.append([dt,I,25.,measured,math.sqrt(.0004**2/3+(1/1024)**2/12)])
                beta=physical.advance(dt,I);A+=F(I)*F(dt)/3600
                if (i+1)%stride==0:
                    enclosure=IV.bounds(3)+sum((b*value for b,value in zip(beta,a)),IV.bounds(0))
                    # Both endpoints within the fixed envelope: simulator rounding
                    # cannot silently consume an undeclared part of sensor error.
                    measurement_valid &= max(abs(F(measured)-F(enclosure.lo,1<<80)),abs(F(measured)-F(enclosure.hi,1<<80)))<=F('.001')
            rows=np.asarray(rows);hashobs.update(rows.astype('<f8',copy=False).tobytes())
            for certificate in certs:certificate.advance(index,rows)
            if bank_failure is None:
                try:bank.advance(index,rows)
                except Exception as error:bank_failure=dict(type=type(error).__name__,reason=str(error))
            index+=n
        snapshot()
    valid=measurement_valid and all(c['scoring_only'].get('SOC_contained',True) and c['scoring_only'].get('Q_contained',True) for r in results for c in r['certificates'])
    answer=dict(status='completed' if valid else 'assumption_or_containment_failure',public=public,prefixes=results,
                H7_failure=bank_failure,scoring_only=dict(amplitudes=[str(x) for x in a]),
                limits='Selected observations satisfy declared real-model bounded-error premise by outward interval check. Shared recurrence creates common-cause risk; independent model/interval tests and proof review required. No population or Gaussian coverage claim.')
    write(out/'result.json',answer);return answer


def plot(out,results):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(len(results),2,figsize=(12,4*len(results)),squeeze=False,layout='constrained')
    for row,result in enumerate(results):
        for col,name in enumerate(('SOC','Q')):
            ax=axes[row,col]
            for j,radius in enumerate(result['public']['rate_radii']):
                data=[(p,p['certificates'][j]) for p in result['prefixes'] if p['certificates'][j]['execution']=='verified_outer_enclosure']
                x=[p['hours'] for p,_ in data];scale=100 if name=='SOC' else 1000
                low=[c['enclosures'][name]['outer_float'][0]*scale for _,c in data];high=[c['enclosures'][name]['outer_float'][1]*scale for _,c in data]
                ax.fill_between(x,low,high,alpha=.22,label=f'rate radius {radius}')
                ax.plot(x,low,linewidth=.8);ax.plot(x,high,linewidth=.8)
            x=[p['hours'] for p in result['prefixes']]
            truthkey='true_SOC' if name=='SOC' else 'true_Q_Ah'
            ax.plot(x,[p['certificates'][0]['scoring_only'][truthkey]*scale for p in result['prefixes']],'k--',label='truth (scoring only)')
            valid=[p for p in result['prefixes'] if p['H7_point'] is not None]
            key='SOC' if name=='SOC' else 'Q_Ah'
            ax.plot([p['hours'] for p in valid],[p['H7_point'][key]*scale for p in valid],'o:',label='H7 point')
            ax.set_title(result['public']['kind']+' / '+name);ax.set_xlabel('Simulated hours');ax.set_ylabel('SOC %' if name=='SOC' else 'Capacity mAh');ax.legend(fontsize=8);ax.grid(alpha=.3)
    fig.savefig(out/'certificate_enclosures.png',dpi=150);plt.close(fig)


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--prefix-seconds',type=float,nargs='+',default=[60,600,3600]);p.add_argument('--sample-rate-hz',type=int,default=35)
    p.add_argument('--kinds',nargs='+',choices=['rest','informative'],default=['rest','informative'])
    p.add_argument('--rate-radii',nargs='+',default=['0','.01']);p.add_argument('--stride',type=int,default=175)
    p.add_argument('--cell-seed',type=int,default=121);p.add_argument('--noise-seed',type=int,default=710);args=p.parse_args()
    if args.sample_rate_hz<1 or args.stride<1 or any(not math.isfinite(x) or x<=0 for x in args.prefix_seconds):p.error('positive finite durations/rate/stride required')
    args.out.mkdir(parents=True,exist_ok=False)
    config=json.loads((ROOT/'experiments/foster_feedback_001/calibration.json').read_text());config['hysteresis_chart']='bounded'
    import scipy
    sources=source_receipt();sources['scipy']=scipy.__version__
    write(args.out/'registration.json',dict(arguments={**vars(args),'out':str(args.out)},source=sources,calibration=config,
        scope='Restricted stationary family, exact I/dt/temperature/calibration, bounded voltage error, all11 amplitudes uncertain. H7 inference unchanged. Five response rates fixed or enclosed by specified public box.'))
    results=[]
    for kind in args.kinds:
        results.append(run_case(args.out/kind,args.out,config,kind,args.prefix_seconds,args.sample_rate_hz,args.cell_seed,args.noise_seed,args.rate_radii,args.stride))
        write(args.out/'summary.json',dict(status='running',cases=results,requested_cases=len(args.kinds)))
    try:
        verify_sources(sources);plot(args.out,results)
    except Exception as error:
        write(args.out/'summary.json',dict(status='unresolved',cases=results,finalization_error=str(error)));return 1
    from experiments.foster_campaign_001.backend import identity
    write(args.out/'summary.json',dict(status='completed' if all(r['status']=='completed' for r in results) else 'unresolved',
        cases=results,source_verified=True,build_receipts={str(p.relative_to(args.out)):identity(p) for p in args.out.glob('backend_*/build.json')}))
    return 0 if all(r['status']=='completed' for r in results) else 1


if __name__=='__main__':raise SystemExit(main())
