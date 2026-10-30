"""One short benchmark, then two fixed prospective four-hour streams.

Native C generator/scoring truth is separated from the estimator input object.
All arms receive the same observations once. A failing codec stops only its arm.
"""
import ctypes as C
import hashlib
import json
import math
from pathlib import Path
import resource
import shutil
import subprocess
import sys
import time
import numpy as np
from .history import Operator,History
from experiments.joint_mass_codebook_001.model import Frame
from experiments.structured_joint_001.qualify import ident,write

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]


def reserve(out):
    out.mkdir(parents=True,exist_ok=False)
    earlier=json.loads((HERE/'qualification002/reservation.json').read_text())['preserved_artifacts']
    for folder in ['qualification001','qualification002']:
        for p in (HERE/folder).rglob('*'):
            if p.is_file():earlier[str(p.relative_to(ROOT))]=ident(p)
    for p,e in earlier.items():
        if ident(ROOT/p)!=e:raise ValueError('earlier evidence changed: '+p)
    files=list(HERE.glob('*.py'))+[HERE/'generate.c',HERE/'plan.json',HERE/'analysis.md',ROOT/'src/scm_model.c',ROOT/'include/scm_model.h',
          ROOT/'experiments/joint_mass_codebook_001/model.py']
    identities={str(p.relative_to(ROOT)):ident(p) for p in files}
    for p in files:
        target=out/'source_snapshot'/p.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
    write(out/'reservation.json',dict(source_identities=identities,preserved_artifacts=earlier,command=sys.argv,
          source_revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
          branch=subprocess.check_output(['git','branch','--show-current'],text=True).strip()))


def build_inputs(out):
    command=['cc','-std=c99','-O2','-Wall','-Wextra','-Werror','-shared','-fPIC','-I',str(ROOT/'include'),
             str(HERE/'generate.c'),str(ROOT/'src/scm_model.c'),'-lm','-o',str(out/'generator.so')]
    r=subprocess.run(command,capture_output=True,text=True)
    write(out/'build.json',dict(command=command,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr,
          compiler=subprocess.check_output(['cc','--version'],text=True).splitlines()[0]))
    if r.returncode:raise RuntimeError(r.stderr)
    lib=C.CDLL(str((out/'generator.so').resolve()))
    lib.generate_case.argtypes=[C.c_int,C.c_int,C.POINTER(C.c_double),C.POINTER(C.c_double)];lib.generate_case.restype=C.c_int
    inputdir=out/'inputs';inputdir.mkdir()
    metadata={}
    for case in ['stationary','monotone_stress']:
        observations=np.empty((504000,5),dtype=float);truth=np.empty((504000,4),dtype=float)
        status=lib.generate_case(int(case=='monotone_stress'),len(observations),observations.ctypes.data_as(C.POINTER(C.c_double)),truth.ctypes.data_as(C.POINTER(C.c_double)))
        if status:raise ValueError('physical generator failure at '+str(status))
        np.save(inputdir/(case+'_observations.npy'),observations);np.save(inputdir/(case+'_truth.npy'),truth)
        metadata[case]=dict(records=len(observations),duration_s=14400,nominal_rate_Hz=35,
              observation_identity=ident(inputdir/(case+'_observations.npy')),scoring_truth_identity=ident(inputdir/(case+'_truth.npy')))
    write(inputdir/'manifest.json',metadata)


def benchmark(out):
    obs=np.load(out/'inputs/stationary_observations.npy',mmap_mode='r')
    opbuilder=Operator('benchmark',.01)
    banks={kind:History('benchmark',kind,initial_sd=.03) for kind in ['float64','log16','float32']}
    per_arm={k:0. for k in banks};failures={};ops=0.;started=time.perf_counter()
    for index,row in enumerate(obs[:2100]):
        frame=Frame(index,*map(float,row))
        t=time.perf_counter();op=opbuilder.prepare(frame,'benchmark');ops+=time.perf_counter()-t
        for key,bank in banks.items():
            if key in failures:continue
            t=time.perf_counter()
            try:bank.step(op)
            except ValueError as e:failures[key]=dict(index=index,reason=str(e))
            per_arm[key]+=time.perf_counter()-t
    report=dict(records=2100,simulated_s=60,wall_s=time.perf_counter()-started,operator_s=ops,arms_s=per_arm,failures=failures,
                estimated_wall_s_per_4h=(time.perf_counter()-started)*240,
                interpretation='Short instrumented benchmark, a planning extrapolation, not a runtime promise')
    write(out/'benchmark.json',report);print(json.dumps(dict(benchmark=report)),flush=True)


def score_error(readout,truth):
    return 100*(readout['Q']-truth[0])/truth[0],100*(readout['SOC']-truth[2])


def run_case(out,case):
    obs=np.load(out/'inputs'/(case+'_observations.npy'),mmap_mode='r')
    # Scoring truth stays in this harness; it is never passed to Operator/History.
    truth=np.load(out/'inputs'/(case+'_truth.npy'),mmap_mode='r')
    directory=out/case;directory.mkdir(exist_ok=False)
    operator=Operator(case,.01);arms={kind:History(case,kind,initial_sd=.03) for kind in ['float64','log16','float32']}
    stats={k:dict(status='running',records=0,maximum_Q_error_percent=0.,maximum_SOC_error_pp=0.,
                  sum_squared_Q_error=0.,sum_squared_SOC_error=0.,preferred_Q_count=0,preferred_SOC_count=0,
                  maximum_history_Q_difference_percent=0.,maximum_history_SOC_difference_pp=0.,
                  maximum_log_span=0.,first_joint_preferred_s=None,last_joint_outside_s=None,
                  phase={str(j):dict(records=0,max_Q_error_percent=0.,max_SOC_error_pp=0.,joint_preferred_count=0) for j in range(3)}) for k in arms}
    checkpoints=[];started=time.perf_counter();cpu=time.process_time();last_print=started
    for index,row in enumerate(obs):
        op=operator.prepare(Frame(index,*map(float,row)),case)
        reference=None;reads={}
        for kind,bank in arms.items():
            stat=stats[kind]
            if stat['status']!='running':continue
            try:bank.step(op);read=bank.readout(op)
            except (ValueError,FloatingPointError) as e:
                stat.update(status='unresolved',failure=dict(index=index,time_s=index/35,reason=str(e)),retained_source_next_index=bank.next_index)
                print(json.dumps(dict(case=case,arm=kind,failure=stat['failure'])),flush=True);continue
            reads[kind]=read
            if kind=='float64':reference=read
            qe,ze=score_error(read,truth[index]);stat['records']+=1
            stat['maximum_Q_error_percent']=max(stat['maximum_Q_error_percent'],abs(qe))
            stat['maximum_SOC_error_pp']=max(stat['maximum_SOC_error_pp'],abs(ze))
            stat['sum_squared_Q_error']+=qe*qe;stat['sum_squared_SOC_error']+=ze*ze
            stat['preferred_Q_count']+=int(abs(qe)<=.5);stat['preferred_SOC_count']+=int(abs(ze)<=.5)
            stat['maximum_log_span']=max(stat['maximum_log_span'],read['log_weight_span'])
            inside=abs(qe)<=.5 and abs(ze)<=.5
            if inside and stat['first_joint_preferred_s'] is None:stat['first_joint_preferred_s']=(index+1)/35
            if not inside:stat['last_joint_outside_s']=(index+1)/35
            phase=0 if index<5400*35 else (1 if index<10800*35 else 2)
            ph=stat['phase'][str(phase)];ph['records']+=1;ph['joint_preferred_count']+=int(inside)
            ph['max_Q_error_percent']=max(ph['max_Q_error_percent'],abs(qe));ph['max_SOC_error_pp']=max(ph['max_SOC_error_pp'],abs(ze))
            if reference is not None:
                dq=100*(read['Q']-reference['Q'])/reference['Q'];dz=100*(read['SOC']-reference['SOC'])
                stat['maximum_history_Q_difference_percent']=max(stat['maximum_history_Q_difference_percent'],abs(dq))
                stat['maximum_history_SOC_difference_pp']=max(stat['maximum_history_SOC_difference_pp'],abs(dz))
            stat['final']=dict(time_s=(index+1)/35,readout=read,Q_error_percent=qe,SOC_error_pp=ze)
        if index%2100==2099 or index in [0,3600*35-1,3600*35,5400*35-1,10800*35-1]:
            checkpoints.append(dict(index=index,time_s=(index+1)/35,truth_Q=float(truth[index,0]),truth_SOC=float(truth[index,2]),
                                    current=float(row[1]),temperature=float(row[2]),arms=reads))
        now=time.perf_counter()
        if now-last_print>20:
            print(json.dumps(dict(case=case,records=index+1,simulated_hours=(index+1)/126000,wall_s=now-started,
                                 active=[k for k,s in stats.items() if s['status']=='running'])),flush=True);last_print=now
        if not any(s['status']=='running' for s in stats.values()):break
    for kind,stat in stats.items():
        if stat['status']=='running':stat['status']='completed'
        n=stat['records']
        if n:
            stat['Q_RMSE_percent']=math.sqrt(stat.pop('sum_squared_Q_error')/n);stat['SOC_RMSE_pp']=math.sqrt(stat.pop('sum_squared_SOC_error')/n)
        stat['storage']=arms[kind].bytes()
    result=dict(case=case,status='completed_with_explicit_arm_statuses',arms=stats,checkpoints=checkpoints,
                cpu_seconds=time.process_time()-cpu,wall_seconds=time.perf_counter()-started,
                maximum_RSS_B=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
                truth_scope='Finite in-support C-generated model controls; no general-cell, continuous-prior or calibrated-aging qualification',
                original_rolling_optimizer_integrated=False)
    write(directory/'result.json',result)
    print(json.dumps(dict(case=case,done=True,wall_seconds=result['wall_seconds'],arms={k:dict(status=s['status'],records=s['records']) for k,s in stats.items()})),flush=True)
    return result


def main():
    mode=sys.argv[1]
    out=Path(sys.argv[2]) if len(sys.argv)>2 else HERE/'campaign001'
    if mode=='prepare':reserve(out);build_inputs(out);benchmark(out)
    elif mode=='run':
        reservation=json.loads((out/'reservation.json').read_text())
        for p,e in reservation['source_identities'].items():
            if ident(ROOT/p)!=e:raise ValueError('source changed: '+p)
        manifest=json.loads((out/'inputs/manifest.json').read_text())
        for case,entry in manifest.items():
            assert ident(out/'inputs'/(case+'_observations.npy'))==entry['observation_identity']
            assert ident(out/'inputs'/(case+'_truth.npy'))==entry['scoring_truth_identity']
        results=[run_case(out,case) for case in ['stationary','monotone_stress']]
        write(out/'summary.json',dict(status='completed',cases=[dict(case=r['case'],arms={k:s['status'] for k,s in r['arms'].items()},wall_seconds=r['wall_seconds']) for r in results]))
    else:raise ValueError('mode must be prepare or run')


if __name__=='__main__':main()
