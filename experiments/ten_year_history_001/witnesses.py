"""Finite checks of the written foundation; no battery fit or aging calibration."""
import json
import math
from pathlib import Path
import subprocess
import sys
import numpy as np
from experiments.region_compression_001 import compare as base

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def oscillation(p,q):
    r=np.log(p)-np.log(q)
    return float(r.max()-r.min())


def main():
    out=HERE/'attempt001';out.mkdir(exist_ok=False)
    plan=json.loads((HERE/'plan.json').read_text())
    sources=[Path(__file__),HERE/'plan.json',* (ROOT/'proofs/ten_year_history_001').glob('*'),
             ROOT/'experiments/physical_rc_scale_001/summary.json',ROOT/'proofs/indefinite_stability_004/contract.json',
             ROOT/'specifications/minimal_health_model_001/model.json',ROOT/'plans/estimation_targets_001.json']
    bindings={str(p.relative_to(ROOT)):base.identity(p) for p in sources if p.is_file()}
    base.write(out/'reservation.json',dict(plan=plan,identities=bindings,
        revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        branch=subprocess.check_output(['git','branch','--show-current'],text=True).strip(),python=sys.version,numpy=np.__version__))
    checks=[];evidence={}
    def check(name,ok):
        checks.append(dict(name=name,passed=bool(ok)))
        if not ok:raise AssertionError(name)
    # Exact integer sufficient statistics; only final likelihood evaluation floats.
    codes=np.array([101,103,99,104,100,98,102],dtype=np.int64)
    n,S,T=len(codes),int(codes.sum()),int(codes@codes)
    for prediction in [98.,100.25,104.]:
        raw=np.sum((codes-prediction)**2)/8
        compact=(n*prediction**2-2*S*prediction+T)/8
        check('L1 exact scalar quadratic '+str(prediction),raw==compact)
    check('L1 sufficient-statistic merge', (3,int(codes[:3].sum()),int(codes[:3]@codes[:3]))[1]+int(codes[3:].sum())==S)
    precision_once=1+n/4;precision_duplicated=2*(1+n/4)
    check('L2 duplicate posterior changes precision',precision_duplicated!=precision_once)
    A=np.array([[.5,.5],[0,1.]]);B=np.array([[.5,-.5],[0,1.]])
    check('L3 chronological noncommutation',(B@A)[0,1]==-.25 and (A@B)[0,1]==.25)
    check('L3 associative composition',np.array_equal((A@B)@A,A@(B@A)))
    # Independent batch Gaussian elimination versus sequential moment recursion.
    process=np.array([.01,.02,.005]);noise=np.array([.04,.03,.02]);obs=np.array([.1,.15,.2]);drift=np.array([.01,-.005,.003])
    J=np.zeros((4,4));h=np.zeros(4);J[0,0]=1.
    mean,var=0.,1.
    for i in range(3):
        vector=np.zeros(4);vector[i]=-1;vector[i+1]=1
        J+=np.outer(vector,vector)/process[i];h+=drift[i]*vector/process[i]
        J[i+1,i+1]+=1/noise[i];h[i+1]+=obs[i]/noise[i]
        prior_mean=mean+drift[i];prior_var=var+process[i]
        gain=prior_var/(prior_var+noise[i])
        mean=prior_mean+gain*(obs[i]-prior_mean);var=prior_var*noise[i]/(prior_var+noise[i])
    batch_mean=np.linalg.solve(J,h)[-1];batch_var=np.linalg.solve(J,np.eye(4))[-1,-1]
    check('L4 forward/batch mean',abs(mean-batch_mean)<2e-15)
    check('L4 forward/batch variance',abs(var-batch_var)<2e-15)
    evidence['gaussian_elimination']=dict(forward_mean=mean,batch_mean=float(batch_mean),forward_variance=var,batch_variance=float(batch_var))
    P,Aage=.01,.03
    check('L5 physical uncertainty reduces old precision',1/(P+Aage)<1/P)
    check('L5 identity aging preserves information',1/(P+0)==1/P)
    # Bound properties use strictly positive finite distributions.
    rng=np.random.default_rng(103100)
    for i in range(plan['bounds']['randomized_metric_cases']):
        p=rng.uniform(.01,1,7);p/=p.sum();q=rng.uniform(.01,1,7);q/=q.sum()
        K=rng.uniform(.01,1,(7,7));K/=K.sum(1)[:,None]
        L=rng.uniform(.01,1,7)
        d=oscillation(p,q)
        check(f'L8 nonexpansivity {i}',oscillation(p@K,q@K)<=d+2e-14)
        check(f'L8 observation isometry {i}',abs(oscillation(p*L/(p@L),q*L/(q@L))-d)<2e-14)
        tv=float(abs(p-q).sum()/2)
        check(f'L10 TV bound {i}',tv<=math.tanh(d/4)+2e-14)
        g=rng.uniform(-.2,.8,7);width=g.max()-g.min()
        check(f'L10 query bound {i}',abs((p-q)@g)<=width*math.tanh(d/4)+2e-14)
    L=rng.uniform(.8,1.2,20);defect=rng.uniform(0,.001,20);e0=.01
    recursive=e0
    for ll,dd in zip(L,defect):recursive=ll*recursive+dd
    expanded=np.prod(L)*e0+sum(defect[i]*np.prod(L[i+1:]) for i in range(len(L)))
    check('L9 error ledger expansion',abs(recursive-expanded)<1e-15)
    # Actual contraction in a two-state mixing operator, not chosen battery decay.
    mixing=.01;rho=1-2*mixing;epsilon=1e-6;logodds=0.
    for _ in range(plan['bounds']['maximum_explicit_recurrence_steps']):
        x=math.exp(logodds)
        logodds=math.log(((1-mixing)*x+mixing)/(mixing*x+1-mixing))+epsilon
    bound=epsilon/(1-rho)
    check('L9 true mixing toy bound',abs(logodds)<=bound+1e-12)
    evidence['mixing_toy']=dict(mixing_probability=mixing,derived_rho=rho,local_logodds_error=epsilon,observed_error=logodds,uniform_bound=bound,
        interpretation='Illustrative two-state kernel; no battery contraction or forgetting rate inferred')
    # No mixing: repeated compaction changes odds without receiving new evidence.
    repetitions=10000;delta=1e-6
    check('L11 no-contraction accumulation',abs(repetitions*delta-.01)<1e-15)
    evidence['compaction_counterexample']=dict(repetitions=repetitions,per_compaction_logodds_bias=delta,total_log_distance=repetitions*delta)
    values=[.7 if i%2==0 else 1.3 for i in range(101)]
    total_variation=sum(abs(y-x) for x,y in zip(values,values[1:]))
    check('L6 bounded range not bounded path variation',max(values)-min(values)<.61 and total_variation>59.9)
    a,b=1.,1.3
    check('L6 indistinguishability lower bound',min(max(abs(m-a),abs(m-b)) for m in np.linspace(a,b,101))>=.15-1e-15)
    # A deliberately specified illustrative30percent linear drift.
    t=np.linspace(0,10,1001);current=1+.3*t/10
    pooled=1+.15*t/10
    check('stale stationary pooling bias',abs(current[-1]-pooled[-1]-.15)<1e-15)
    evidence['stale_aging_pool']=dict(current_relative_value=float(current[-1]),stationary_pooled_mean=float(pooled[-1]),error=float(pooled[-1]-current[-1]),
        interpretation='Analytic counterexample, not a calibrated cell trajectory')
    check('L7 broad tau envelope',.5*.5==.25 and 1.5*1.5==2.25)
    check('L7 directional tau envelope',1*.5==.5 and 1.5*1==1.5)
    H=np.geomspace(1e-4,100,240);response=-np.expm1(-H)
    check('L12 bounded horizon response',np.all((response>=0)&(response<=1)))
    N=int(10*365.25*86400*35)
    sums=dict(n=N,S_max=4095*N,T_max=4095**2*N)
    check('L13 count needs34bits',N.bit_length()==34)
    check('L13 scalar accumulators fit64bits',max(sums.values())<2**64)
    check('L13 uint32 insufficient',N>2**32-1)
    evidence['nominal_ten_year_ranges']=dict(**sums,count_bits=N.bit_length(),S_bits=sums['S_max'].bit_length(),T_bits=sums['T_max'].bit_length(),
        scope='Nominal-rate planning count only; maximum delivered count remains an operational premise')
    evidence['storage_B']=dict(scalar_n_S_T=24,Gaussian_mean_covariance_dimension16=(16+136)*8,quadratic_information_with_constant_and_count=(136+16+1)*8+8,
        current_research_message=2544,complete_subsystem=None)
    # Standalone analytic illustration. No billions-of-record simulation.
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.size':10})
    fig,axes=plt.subplots(2,2,figsize=(12,8),constrained_layout=True)
    n=np.geomspace(1,N,240)
    axes[0,0].loglog(n,n,color='#b34b32');axes[0,0].set(title='Repeated approximation without contraction',xlabel='Compaction count m',ylabel='Log-density error / per-step bias = m')
    axes[0,1].loglog(n,n/np.sqrt(n+1),color='#8b5ba6');axes[0,1].set(title='Fixed response bias, growing confidence',xlabel='Independent observation count n',ylabel='Standardized bias / (bias / noise SD)')
    axes[1,0].plot(t,current,label='Current health',color='#235b82');axes[1,0].plot(t,pooled,label='Incorrect stationary pooling',color='#b34b32',linestyle='--')
    axes[1,0].set(title='Illustrative 30% linear aging; no fitted cell rates',xlabel='Years (specified example)',ylabel='Relative parameter');axes[1,0].legend()
    axes[1,1].semilogx(H,response,color='#24856c');axes[1,1].set(title='Forecast horizon can expose a fixed error',xlabel='Prediction horizon / RC time constant',ylabel='Carried response gain (normalized)')
    for ax in axes.flat:ax.grid(alpha=.25)
    fig.suptitle('Distinct error mechanisms — analytic witnesses, not a ten-year battery forecast',fontsize=13)
    fig.savefig(out/'error_mechanisms.png',dpi=170);fig.savefig(out/'error_mechanisms.pdf');plt.close(fig)
    base.write(out/'result.json',dict(status='finite_mathematical_controls_passed',checks=checks,evidence=evidence,
        new_battery_fits=0,new_particle_steps=0,ten_year_simulation=False,ten_year_battery_certificate=False,
        qualification='Written proofs supply conditional quantifiers; these finite controls only check examples and arithmetic correspondences'))
    print(json.dumps(dict(checks=len(checks),nominal_records=N,certificate=False)))


if __name__=='__main__':main()
