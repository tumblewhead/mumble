"""Portable qualified four-hour runner; plant/truth stay in this harness."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import numpy as np
from .estimator import Rolling
from .history import numeric_storage
from .plant import generate
from .qualify import qualify
from specifications.evidence_feedback_001.protocol import digest
from experiments.structured_joint_001.qualify import ident,write

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]


def read(p):return json.loads(p.read_text())


def prepare(out,args):
    out.mkdir(parents=True,exist_ok=False)
    previous=ROOT/'specifications/evidence_feedback_001'
    preserved=read(previous/'qualification001/reservation.json')['preserved_artifacts']
    preserved.update(read(previous/'verification.json')['artifacts'])
    preserved[str((previous/'verification.json').relative_to(ROOT))]=ident(previous/'verification.json')
    for p,expected in preserved.items():
        if ident(ROOT/p)!=expected:raise ValueError('earlier evidence changed: '+p)
    files=list(HERE.glob('*.py'))+list(HERE.glob('*.c'))+list(HERE.glob('*.json'))
    files+=[previous/'protocol.py',previous/'model.json',previous/'contract.json',ROOT/'experiments/structured_joint_001/qualify.py']
    sources={str(p.relative_to(ROOT)):ident(p) for p in files}
    for p in files:
        target=out/'source_snapshot'/p.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
    write(out/'reservation.json',dict(source_identities=sources,preserved_artifacts=preserved,
        source_revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        branch=subprocess.check_output(['git','branch','--show-current'],text=True).strip(),
        command=sys.argv,configuration=vars(args)))
    command=['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-pedantic','-fno-fast-math','-ffp-contract=off',
             '-shared','-fPIC',str(HERE/'model.c'),'-lm','-o',str(out/'model.so')]
    build=subprocess.run(command,capture_output=True,text=True)
    write(out/'build.json',dict(command=command,returncode=build.returncode,stdout=build.stdout,stderr=build.stderr))
    if build.returncode:raise RuntimeError(build.stderr)
    config=read(HERE/'calibration.json');write(out/'calibration.json',config)
    model_id=digest(dict(model=read(previous/'model.json'),source=sources[str((HERE/'model.c').relative_to(ROOT))],calibration=config))
    report=qualify((out/'model.so').resolve(),config,model_id);write(out/'qualification.json',report)
    print(json.dumps(dict(qualification=report['status'],passing_checks=report['passing_checks'],failures=report['failed_checks'])),flush=True)
    if report['status']!='passed':raise ValueError('targeted qualification failed; preserved run directory')
    return config,model_id


def bucket():
    return dict(outputs=0,max_Q_percent=0.,max_SOC_pp=0.,sum_Q2=0.,sum_SOC2=0.,joint_preferred=0,Q_3sd_misses=0,SOC_3sd_misses=0)


def score(stats,r,truth,t):
    qe=100*(r['Q']/truth[0]-1);ze=100*(r['SOC']-truth[2]);inside=abs(qe)<=.5 and abs(ze)<=.5
    phase='learning' if t<=5400 else ('weak' if t<=10800 else 'renewed')
    for b in [stats['all'],stats['phase'][phase]]:
        b['outputs']+=1;b['max_Q_percent']=max(b['max_Q_percent'],abs(qe));b['max_SOC_pp']=max(b['max_SOC_pp'],abs(ze))
        b['sum_Q2']+=qe*qe;b['sum_SOC2']+=ze*ze;b['joint_preferred']+=int(inside)
        b['Q_3sd_misses']+=int(not r['Q_interval_3sd'][0]<=truth[0]<=r['Q_interval_3sd'][1])
        b['SOC_3sd_misses']+=int(abs(r['SOC']-truth[2])>3*r['SOC_sd'])
    if not inside:stats['last_outside_s']=t
    if inside and stats['first_inside_s'] is None:stats['first_inside_s']=t
    stats['final']=dict(time_s=t,Q_error_percent=qe,SOC_error_pp=ze,estimate=r)


def finish(stats):
    for b in [stats['all'],*stats['phase'].values()]:
        n=b['outputs'];b['Q_RMSE_percent']=float(np.sqrt(b.pop('sum_Q2')/n)) if n else None
        b['SOC_RMSE_pp']=float(np.sqrt(b.pop('sum_SOC2')/n)) if n else None
        b['joint_preferred_fraction']=b['joint_preferred']/n if n else None


def plot(out,result,truth):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,1,figsize=(10,7),sharex=True,layout='constrained')
    for kind,color in [('float64','#222222'),('float32','#17806e')]:
        path=out/(kind+'_trace.npy')
        if not path.exists():continue
        rows=np.load(path)
        if not len(rows):continue
        ix=rows[:,0].astype(int)-1;t=rows[:,1]/3600
        axes[0].plot(t,100*(rows[:,2]/truth[ix,0]-1),color=color,label=kind,lw=.9)
        axes[1].plot(t,100*(rows[:,3]-truth[ix,2]),color=color,label=kind,lw=.9)
    for ax in axes:
        ax.axhspan(-.5,.5,color='#d9edd9',alpha=.5);ax.axvspan(1.5,3,color='#999999',alpha=.15)
        ax.grid(alpha=.2);ax.set_yscale('symlog',linthresh=.5)
    axes[0].set_ylabel('Q error (% relative)');axes[1].set_ylabel('SOC error (percentage points)')
    axes[1].set_xlabel('Simulated hours');axes[0].legend()
    fig.suptitle('Continuous Foster rolling estimator + coefficient-compressed history')
    fig.savefig(out/'errors.png',dpi=160);fig.savefig(out/'errors.pdf');plt.close(fig)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hours',type=float,default=4.)
    parser.add_argument('--cell',choices=['A','B'],default='B')
    parser.add_argument('--noise-v',type=float,default=.004)
    parser.add_argument('--seed',type=int,default=314159)
    parser.add_argument('--temperature',choices=['cycle','constant'],default='cycle')
    parser.add_argument('--encoding',choices=['both','float64','float32'],default='both')
    parser.add_argument('--out',default=None)
    args=parser.parse_args()
    if not np.isfinite(args.hours) or args.hours<=0 or args.noise_v<=0:parser.error('positive duration/noise required')
    n=round(args.hours*126000)
    if n<16:parser.error('duration must contain at least16 samples')
    out=Path(args.out) if args.out else HERE/('run_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f'))
    out=out.resolve();started=time.perf_counter();config,model_id=prepare(out,args)
    obs,truth=generate(config,n,args.cell,args.noise_v,args.seed,args.temperature)
    np.save(out/'observations.npy',obs);np.save(out/'truth.npy',truth)
    source=digest(dict(observations=ident(out/'observations.npy'),model_id=model_id))
    write(out/'inputs.json',dict(source_id=source,model_id=model_id,observations=ident(out/'observations.npy'),truth=ident(out/'truth.npy'),
         columns=['dt_s','current_A','temperature_C','voltage_V','sigma_V'],truth_columns=['Q_Ah','R0_ohm','SOC','noiseless_voltage_V'],
         records=n,simulated_s=n/35,plant='separate scalar implementation; constant reference parameters',calibration_status='known synthetic characterization, not learned'))
    kinds=['float64','float32'] if args.encoding=='both' else [args.encoding]
    # One short benchmark on an independent source; main arms start fresh.
    begin=time.perf_counter()
    for kind in kinds:
        short=Rolling((out/'model.so').resolve(),config,digest('benchmark'+source),model_id,kind)
        for i,row in enumerate(obs[:min(2100,n)]):short.offer(i,*map(float,row))
        short.retire()
    seconds=time.perf_counter()-begin
    write(out/'benchmark.json',dict(records=min(2100,n),arms=kinds,wall_s=seconds,planning_run_wall_s=seconds*n/min(2100,n)))
    print(json.dumps(dict(benchmark_wall_s=seconds,estimated_run_wall_s=seconds*n/min(2100,n))),flush=True)
    banks={kind:Rolling((out/'model.so').resolve(),config,source,model_id,kind) for kind in kinds}
    stats={kind:dict(status='running',all=bucket(),phase={p:bucket() for p in ['learning','weak','renewed']},
          first_inside_s=None,last_outside_s=None,stops={},model_evaluations=0,max_encoding_Q_percent=0.,max_encoding_SOC_pp=0.,
          sum_predictive_RMS=0.,sum_fitted_RMS=0.,storage=numeric_storage(kind)) for kind in kinds}
    traces={kind:[] for kind in kinds};checkpoints=[];last_checkpoint=-1;last_print=time.perf_counter();run_start=last_print;cpu=time.process_time()
    for i,row in enumerate(obs):
        reads={}
        for kind,bank in banks.items():
            stat=stats[kind]
            if stat['status']!='running':continue
            try:
                result=bank.offer(i,*map(float,row))
                if i==n-1 and result is None:result=bank.retire()
            except (ValueError,RuntimeError,np.linalg.LinAlgError) as e:
                stat.update(status='unresolved',failure=dict(index=i,time_s=i/35,reason=str(e)))
                print(json.dumps(dict(arm=kind,failure=stat['failure'])),flush=True);continue
            if result is None:continue
            r,d=result;reads[kind]=r;t=(i+1)/35;score(stat,r,truth[i],t)
            stat['stops'][d['stop']]=stat['stops'].get(d['stop'],0)+1;stat['model_evaluations']+=d['evaluations']
            stat['sum_predictive_RMS']+=d['initial_predictive_RMS'];stat['sum_fitted_RMS']+=d['fitted_RMS']
            traces[kind].append([i+1,t,r['Q'],r['SOC'],r['Q_log_sd'],r['SOC_sd'],r['Q_ref'],r['log_evidence']])
            if kind=='float32' and 'float64' in reads:
                ref=reads['float64'];stat['max_encoding_Q_percent']=max(stat['max_encoding_Q_percent'],abs(100*(r['Q']/ref['Q']-1)))
                stat['max_encoding_SOC_pp']=max(stat['max_encoding_SOC_pp'],abs(100*(r['SOC']-ref['SOC'])))
        if reads and (int((i+1)/2100)>last_checkpoint or i==n-1):
            checkpoints.append(dict(index=i,time_s=(i+1)/35,truth_Q=float(truth[i,0]),truth_SOC=float(truth[i,2]),arms=reads))
            last_checkpoint=int((i+1)/2100)
        if time.perf_counter()-last_print>25:
            print(json.dumps(dict(records=i+1,simulated_hours=(i+1)/126000,wall_s=time.perf_counter()-run_start)),flush=True)
            last_print=time.perf_counter()
        if all(s['status']!='running' for s in stats.values()):break
    for kind,bank in banks.items():
        stat=stats[kind]
        if stat['status']=='running':stat['status']='completed'
        stat['received_records']=bank.next_index;stat['retired_records']=bank.history.read().boundary.sequence
        stat['generation']=bank.history.read().generation;stat['pending_records']=len(bank.rows);finish(stat)
        count=stat['all']['outputs'];stat['mean_block_predictive_RMS']=stat.pop('sum_predictive_RMS')/count if count else None
        stat['mean_block_fitted_RMS']=stat.pop('sum_fitted_RMS')/count if count else None
        np.save(out/(kind+'_trace.npy'),np.array(traces[kind],dtype=float).reshape(-1,8))
    report=dict(status='completed_with_explicit_arm_statuses',arms=stats,checkpoints=checkpoints,
        records_requested=n,simulated_s=n/35,source_id=source,model_id=model_id,configuration=vars(args),
        run_wall_s=time.perf_counter()-run_start,run_cpu_s=time.process_time()-cpu,total_wall_s=time.perf_counter()-started,
        qualification_checks=read(out/'qualification.json')['passing_checks'],
        scoring_cadence='Each retired16-record block; all35Hz observations processed. Final partial block also retired.',
        approximation='Local Gaussian likelihood and deterministic transport linearization; coefficient encoding only, no physical parameter lattice',
        coverage_validated=False,aging_implemented=False,complete_SRAM_B=None)
    write(out/'result.json',report);plot(out,report,truth)
    artifacts={str(p.relative_to(out)):ident(p) for p in sorted(out.rglob('*')) if p.is_file() and '__pycache__' not in p.parts}
    write(out/'manifest.json',dict(artifacts=artifacts,scope='Immutable run evidence and source snapshots'))
    print(json.dumps(dict(result=str(out/'result.json'),arms={k:dict(status=s['status'],retired_records=s['retired_records'],
         final_Q_percent=s.get('final',{}).get('Q_error_percent'),final_SOC_pp=s.get('final',{}).get('SOC_error_pp')) for k,s in stats.items()})),flush=True)


if __name__=='__main__':main()
