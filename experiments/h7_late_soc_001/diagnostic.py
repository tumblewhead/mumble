"""Checkpoint-local read-only SOC diagnostic. Fitting receives no truth."""
import copy
import json
from pathlib import Path
import numpy as np
from experiments.foster_campaign_001.compact import restore_checkpoint, CHUNK
from experiments.foster_campaign_001.backend import identity
from experiments.hysteresis_refinement_001.field import Compressed, transported
from experiments.slow_likelihood_diagnostic_001.numerics import solve

RUN=Path('experiments/foster_campaign_001/run_20261101_071802_121297')
OUT=Path('experiments/h7_late_soc_001/attempt002')
COLUMNS=['record','hours','I_A','T_C','SOC_error_pp','SOC_sd_pp','SOC_zscore','Q_error_percent','Q_sd_percent','h_error','refresh','seconds_since_refresh','V_fit_error_uV']

def write(path,obj):
    path.write_text(json.dumps(obj,indent=2,allow_nan=False,default=lambda x:x.tolist() if isinstance(x,np.ndarray) else x.item())+'\n')

def soc_gaussian_moments(mu,C,A):
    e=np.exp(-mu[5]+.5*C[5,5])
    return mu[0]-A*e, C[0,0]+A*A*e*e*np.expm1(C[5,5])+2*A*C[0,5]*e

def unpack(context):
    values=np.frombuffer(context.tobytes(),dtype=np.float64,count=169)
    R=np.zeros((17,17));R[np.triu_indices(17)]=values[:153]
    return R,values[153:169].copy()

def capture(bank):
    field=copy.copy(bank.field);field.root=field.root.copy();field.state=field.state.copy()
    if bank.buffered:field.update(field.count,bank.pending_rows[:bank.buffered])
    assert np.array_equal(field.state,bank.live_state)
    native=bank.native.snapshot();R,anchor=unpack(native)
    return dict(field=field,mean=bank.mean.copy(),L=bank.prior_root.copy(),w=bank.w.copy(),
                R=R,anchor=anchor,message=bank.full_message(),count=bank.live_count)

def probe(s):
    f,mean,L=s['field'],s['mean'],s['L'];obj=Compressed(f,mean,L)
    native=s['message'];native_sd=np.linalg.norm(native[16:272].reshape(16,16)[0])
    cost,g,P,_,_=obj(s['anchor']);wd=s['anchor']-np.linalg.solve(P,g)
    xd=mean+L@wd;ed,Dd=transported(f,xd)
    dense_origin=L@np.linalg.solve(np.linalg.cholesky(P).T,np.eye(16));dense_sd=np.linalg.norm((Dd@dense_origin)[0])
    origin=L@np.linalg.solve(s['R'][:16,:16],np.eye(16));C=origin@origin.T
    mu=mean+L@s['w'];A=f.state[-3];a=A*np.exp(-mu[5]);j=np.zeros(16);j[0]=1;j[5]=a
    analytic=mu[0]-a;sd=np.linalg.norm(j@origin)
    gm,gv=soc_gaussian_moments(mu,C,A)
    fit=solve(obj,start=s['w']);end,D=transported(f,fit['x']);fr=D@fit['root']
    return dict(record=s['count'],hours=s['count']/50/3600,
        native_SOC=native[0],native_SOC_sd=native_sd,
        dense_same_anchor_SOC_difference_local_SD=(ed[0]-native[0])/native_sd,
        dense_same_anchor_SOC_width_ratio=dense_sd/native_sd,
        analytic_SOC_difference_local_SD=(analytic-native[0])/native_sd,
        analytic_SOC_width_ratio=sd/native_sd,
        SOC_variance_terms=[C[0,0],a*a*C[5,5],2*a*C[0,5]],
        origin_SOC_logQ_correlation=C[0,5]/np.sqrt(C[0,0]*C[5,5]),
        nonlinear_Gaussian_SOC_mean_shift_local_SD=(gm-analytic)/native_sd,
        nonlinear_Gaussian_SOC_width_ratio=np.sqrt(gv)/native_sd,
        full_refit_stop=fit['diagnostic']['stop'],
        full_refit_SOC_difference_local_SD=(end[0]-native[0])/native_sd,
        full_refit_SOC_width_ratio=np.linalg.norm(fr[0])/native_sd,
        full_refit_Q_difference_percent=100*np.expm1(end[5]-native[5]))

def main():
    OUT.mkdir(parents=True,exist_ok=False)
    config=json.loads((RUN/'calibration.json').read_text());settings=json.loads((RUN/'campaign_plan.json').read_text())['configuration']
    prior=json.loads(Path('provenance/h7_campaign_720h_001/comparison.json').read_text());summaries=[]
    for name in ('case_0007','case_0006'):
        case=RUN/name;cellfile=json.loads((case/'scenario.json').read_text());cell=cellfile['cell_definition']
        scenario={k:cellfile[k] for k in ('cell','load','noise_v','seed')}
        record=next(c for c in prior['cases'] if c['case']==name)
        bounds=record['arms']['tangent_h7']['first_miss_checkpoint_interval_hours']['SOC']
        entries=json.loads((case/'checkpoints/index.json').read_text())['checkpoints']
        start=min(entries,key=lambda e:abs(e['sequence']/50/3600-bounds[0]));stop=min(entries,key=lambda e:abs(e['sequence']/50/3600-bounds[1]))
        stream,banks,meta=restore_checkpoint(case,start,config,cell,scenario,settings)
        destination=OUT/name;destination.mkdir();traces={k:[] for k in banks};probes={'start':capture(banks['tangent_h7'])};events=[];maxratio=0;firstmiss=False
        previous_current=None
        while stream.index<stop['sequence']:
            first=stream.index;obs,truth,new_events=stream.read(min(CHUNK,stop['sequence']-first));events.extend(new_events)
            for offset in range(0,len(obs),16):
                block=obs[offset:offset+16];true=truth[offset+len(block)-1];I=block[-1,1];T=block[-1,2]
                for kind,bank in banks.items():
                    read,diag=bank.advance(first+offset,block)
                    err=read['SOC']-true[0];z=err/read['SOC_sd'];msg=bank.full_message();p=np.exp(msg[5:16]);p[5]+=p[3];p[7]+=p[5]
                    temp=np.exp(np.asarray(config['arrhenius_A_K'])*(1/(T+273.15)-1/config['reference_temperature_K']));p*=temp
                    v=config['ocv_intercept_V']+config['ocv_slope_V_per_SOC']*msg[0]+p[8]*np.tanh(msg[4])-I*p[1]-sum(msg[1:4])
                    traces[kind].append([read['records'],read['records']/50/3600,I,T,100*err,100*read['SOC_sd'],z,100*(read['Q_ref']/cell['parameters']['Q_Ah']-1),100*read['Q_log_sd'],np.tanh(msg[4])-true[4],int(diag['stop']=='tangent_field_refresh'),(read['records']-bank.audit['last_accepted_record'])/50,1e6*(v-true[-1])])
                    if kind=='tangent_h7':
                        if abs(z)>3 and not firstmiss:probes['first_miss']=capture(bank);firstmiss=True
                        if abs(z)>maxratio:probes['peak']=capture(bank);maxratio=abs(z)
                previous_current=I
        probes['end']=capture(banks['tangent_h7'])
        finalpath=case/'checkpoints'/stop['file'];assert identity(finalpath)=={k:stop[k] for k in ('bytes','sha256')}
        with np.load(finalpath) as saved:
            target=json.loads(saved['metadata'].tobytes());parity={'stimulus':json.loads(json.dumps(stream.snapshot()))==target['stimulus']}
            for kind,b in banks.items():
                parity[kind+'_carrier']=np.array_equal(np.frombuffer(bytes(b.context),dtype=np.uint8),saved[kind])
                for k,v in b.checkpoint_arrays().items():
                    if k=='metadata':parity[kind+'__'+k]=json.loads(v.tobytes())==json.loads(saved[kind+'__'+k].tobytes())
                    else:parity[kind+'__'+k]=np.array_equal(v,saved[kind+'__'+k])
        assert all(parity.values()),parity
        arrays={k:np.asarray(v) for k,v in traces.items()};np.savez_compressed(destination/'traces.npz',**arrays)
        arms={}
        for k,a in arrays.items():
            miss=abs(a[:,6])>3
            arms[k]=dict(outputs=len(a),SOC_misses=int(miss.sum()),max_abs_SOC_local_SD=float(max(abs(a[:,6]))),
                max_abs_SOC_error_pp=float(max(abs(a[:,4]))),SOC_misses_at_refresh=int(np.sum(miss & (a[:,10]>0))),
                miss_current_A_range=[float(a[miss,2].min()),float(a[miss,2].max())] if miss.any() else None,
                miss_temperature_C_range=[float(a[miss,3].min()),float(a[miss,3].max())] if miss.any() else None,
                first_miss_hours=float(a[np.flatnonzero(miss)[0],1]) if miss.any() else None,
                miss_refresh_age_s_range=[float(a[miss,11].min()),float(a[miss,11].max())] if miss.any() else None)
        results={k:probe(v) for k,v in probes.items()}
        for k,s in probes.items():np.savez_compressed(destination/(k+'_probe.npz'),root=s['field'].root,state=s['field'].state,mean=s['mean'],L=s['L'],w=s['w'],R=s['R'],anchor=s['anchor'],message=s['message'])
        result=dict(case=name,start=start,stop=stop,parity=parity,arms=arms,probes=results,events=events,trace_columns=COLUMNS)
        write(destination/'result.json',result);summaries.append(result)
        print(json.dumps(dict(case=name,arms=arms,probes=results)),flush=True)
    write(OUT/'summary.json',dict(status='completed',registration=identity(Path(__file__).with_name('registration.json')),cases=summaries,scope='Selected diagnostic witnesses, not coverage validation; no truth in fits.'))
if __name__=='__main__':main()
