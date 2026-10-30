"""Frozen system comparison, no estimator adaptation or automatic retries."""
import ctypes as C
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import time
import numpy as np
from experiments.continuous_soc_001.history import Operator, History, lse
from experiments.joint_mass_codebook_001.model import Frame
from experiments.structured_joint_001.qualify import ident, write

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CASES = ['matched', 'between_nodes', 'gradual', 'combined']
DP = C.POINTER(C.c_double)
SOURCES = [HERE/'native.c', ROOT/'src/scm_model.c'] + [
    ROOT/'experiments/live_anchor_integration_001'/name for name in
    ['rolling_engine.c', 'rolling_model.c', 'public_contract.c']] + [
    ROOT/'experiments/live_anchor_bootstrap_001'/name for name in
    ['adc12.c', 'history_translation.c', 'support_step.c']]


def read(p): return json.loads(p.read_text())
def ptr(a): return a.ctypes.data_as(DP)


def library(out):
    lib = C.CDLL(str((out/'native.so').resolve()))
    lib.generate.argtypes = [C.c_int, C.c_int, DP, DP]
    lib.generate.restype = C.c_int
    lib.run_legacy.argtypes = [DP, C.c_int, C.c_char_p, DP, DP]
    lib.run_legacy.restype = C.c_int
    return lib


def prepare(out):
    out.mkdir(parents=True, exist_ok=False)
    previous = ROOT/'experiments/continuous_soc_001'
    preserved = read(previous/'campaign001/reservation.json')['preserved_artifacts']
    preserved.update(read(previous/'verification.json')['artifacts'])
    preserved[str((previous/'verification.json').relative_to(ROOT))] = ident(previous/'verification.json')
    for p, expected in preserved.items():
        if ident(ROOT/p) != expected: raise ValueError('earlier evidence changed: '+p)
    files = set(SOURCES + list(HERE.glob('*.py')) + [HERE/'plan.json'])
    for folder in ['live_anchor_integration_001', 'live_anchor_bootstrap_001']:
        files.update((ROOT/'experiments'/folder).glob('*.h'))
    files.update([ROOT/'include/scm_model.h', ROOT/'experiments/continuous_soc_001/history.py',
                  ROOT/'experiments/joint_mass_codebook_001/model.py',
                  ROOT/'experiments/structured_joint_001/qualify.py'])
    sources = {str(p.relative_to(ROOT)): ident(p) for p in sorted(files)}
    for p in files:
        target = out/'source_snapshot'/p.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(p, target)
    write(out/'reservation.json', dict(source_identities=sources, preserved_artifacts=preserved,
          source_revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
          branch=subprocess.check_output(['git','branch','--show-current'],text=True).strip(), command=sys.argv))
    cmd = ['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-pedantic',
           '-fno-fast-math','-ffp-contract=off','-shared','-fPIC','-I'+str(ROOT/'include'),
           *map(str,SOURCES),'-lm','-o',str(out/'native.so')]
    build = subprocess.run(cmd,capture_output=True,text=True)
    write(out/'build.json',dict(command=cmd,returncode=build.returncode,stdout=build.stdout,stderr=build.stderr))
    if build.returncode: raise RuntimeError(build.stderr)
    lib = library(out); inp = out/'inputs'; inp.mkdir(); manifest = {}
    for k, name in enumerate(CASES):
        obs = np.empty((504000,5)); truth = np.empty((504000,6))
        status = lib.generate(k,len(obs),ptr(obs),ptr(truth))
        if status: raise RuntimeError('generator failed: '+str((name,status)))
        np.save(inp/(name+'_observations.npy'),obs); np.save(inp/(name+'_truth.npy'),truth)
        manifest[name] = dict(observations=ident(inp/(name+'_observations.npy')),
                              truth=ident(inp/(name+'_truth.npy')), records=len(obs))
        source_material = dict(observations=manifest[name]['observations'], sources=sources)
        manifest[name]['source_id'] = hashlib.sha256(json.dumps(source_material,sort_keys=True).encode()).hexdigest()
    write(inp/'manifest.json',manifest)
    print(json.dumps(dict(prepared=str(out),cases=CASES,preserved_artifacts=len(preserved))),flush=True)


def verify_inputs(out, name):
    reservation = read(out/'reservation.json')
    for p, expected in reservation['source_identities'].items():
        if ident(ROOT/p) != expected: raise ValueError('reserved source changed: '+p)
    entry = read(out/'inputs/manifest.json')[name]
    for suffix, key in [('observations','observations'),('truth','truth')]:
        if ident(out/'inputs'/(name+'_'+suffix+'.npy')) != entry[key]: raise ValueError('input changed')
    return entry


def qualification(out):
    dest = out/'qualification'; dest.mkdir(exist_ok=False)
    checks = []
    def check(name, ok): checks.append(dict(name=name,passed=bool(ok)))
    lib = library(out)
    for k, name in enumerate(CASES):
        verify_inputs(out,name)
        obs = np.load(out/'inputs'/(name+'_observations.npy'),mmap_mode='r')
        truth = np.load(out/'inputs'/(name+'_truth.npy'),mmap_mode='r')
        check(name+'/finite',np.isfinite(obs).all() and np.isfinite(truth).all())
        check(name+'/actual_intervals',np.all(obs[:,0]==1/35))
        check(name+'/physical_SOC',np.all((truth[:,2]>0)&(truth[:,2]<1)))
        check(name+'/monotone_reference_Q',np.all(np.diff(truth[:,4])<=0))
        for col, offset, step in [(1,-.256,.000125),(2,-40,.0625),(3,1.5,1/1024)]:
            codes=np.floor((obs[:,col]-offset)/step+.5)
            check(name+'/ADC_'+str(col),np.array_equal(offset+codes*step,obs[:,col]))
        small=np.empty((128,5)); tr=np.empty((128,6))
        check(name+'/repeat_generation',lib.generate(k,128,ptr(small),ptr(tr))==0 and
              np.array_equal(small,obs[:128]) and np.array_equal(tr,truth[:128]))
        operator=Operator(name,.01); histories=[History(name,t,initial_sd=.03) for t in ['float64','float32']]
        for i,row in enumerate(small):
            op=operator.prepare(Frame(i,*map(float,row)),name)
            for history in histories: history.step(op)
        a,b=[h.readout(op) for h in histories]
        check(name+'/short_encoding',abs(100*(a['Q']-b['Q'])/a['Q'])<.5 and abs(100*(a['SOC']-b['SOC']))<.5)
        check(name+'/source_consumption',all(h.next_index==128 for h in histories))
    # Independent stationary physical recurrence on the first generated control.
    tr=np.load(out/'inputs/matched_truth.npy'); obs=np.load(out/'inputs/matched_observations.npy')
    z=.61;v=np.zeros(3);h=0.;max_error=0.
    for i,row in enumerate(obs[:128]):
        dt,I=row[:2];z-=I*dt/3600/.06
        d=np.exp(-dt/np.array([.05,.5,5.]));v=d*v+(1-d)*np.array([.04,.08,.12])*I
        d=math.exp(-(100 if I>0 else 150)*abs(I)*dt/3600)
        h=d*h+(1-d)*np.sign(I)
        voltage=3+1.15*z+.08*math.tanh(8*(z-.5))-I*.1-sum(v)-.015*h
        max_error=max(max_error,abs(voltage-tr[i,3]),abs(z-tr[i,2]))
    check('independent_physical_recurrence',max_error<1e-12)
    # Native wrapper is causal and deterministic; only future inputs differ.
    a=obs[:128].copy();b=a.copy();b[64:,3]+=1/1024
    oa=np.zeros((8,6));ob=np.zeros((8,6));ca=np.zeros(5);cb=np.zeros(5)
    sa=lib.run_legacy(ptr(a),128,b'Q'*32,ptr(oa),ptr(ca))
    sb=lib.run_legacy(ptr(b),128,b'Q'*32,ptr(ob),ptr(cb))
    check('legacy_short_completes',sa==0 and sb==0 and ca[1]==128 and cb[1]==128)
    check('legacy_prefix_causal',np.array_equal(oa[:4],ob[:4]))
    check('legacy_owned_records',np.array_equal(oa[:,0],np.arange(16,129,16)))
    a[0,0]=.1
    check('legacy_invalid_interval_rejected',lib.run_legacy(ptr(a),128,b'Q'*32,ptr(oa),ptr(ca))==-300 and ca[1]==0)
    report=dict(status='passed' if all(c['passed'] for c in checks) else 'failed', checks=checks,
                passing_checks=sum(c['passed'] for c in checks),physical_max_abs_error=max_error,
                native_identity=ident(out/'native.so'))
    write(dest/'result.json',report);print(json.dumps({k:report[k] for k in ['status','passing_checks','physical_max_abs_error']}),flush=True)
    if report['status']!='passed':raise RuntimeError('qualification failed')


def bucket():
    return dict(count=0,max_Q_percent=0.,max_SOC_pp=0.,sum_Q2=0.,sum_SOC2=0.,joint_preferred=0,
                Q_3sd_misses=0,SOC_3sd_misses=0)


def score(stat,q,z,truth,time_s,sd=None):
    qe=100*(q-truth[0])/truth[0];ze=100*(z-truth[2]);inside=abs(qe)<=.5 and abs(ze)<=.5
    phase='learning' if time_s<=5400 else ('weak' if time_s<=10800 else 'renewed')
    for b in [stat['all'],stat['phase'][phase]]:
        b['count']+=1;b['max_Q_percent']=max(b['max_Q_percent'],abs(qe));b['max_SOC_pp']=max(b['max_SOC_pp'],abs(ze))
        b['sum_Q2']+=qe*qe;b['sum_SOC2']+=ze*ze;b['joint_preferred']+=int(inside)
        if sd:
            b['Q_3sd_misses']+=int(abs(q-truth[0])>3*sd[0]);b['SOC_3sd_misses']+=int(abs(z-truth[2])>3*sd[1])
    if not inside:stat['last_outside_s']=time_s
    stat['final']=dict(time_s=time_s,Q=q,SOC=z,Q_error_percent=qe,SOC_error_pp=ze)


def statistics():
    return dict(status='running',all=bucket(),phase={p:bucket() for p in ['learning','weak','renewed']},last_outside_s=None)


def finish(stat,uncertainty):
    for b in [stat['all'],*stat['phase'].values()]:
        n=b['count'];b['Q_RMSE_percent']=math.sqrt(b.pop('sum_Q2')/n) if n else None
        b['SOC_RMSE_pp']=math.sqrt(b.pop('sum_SOC2')/n) if n else None
        b['joint_preferred_fraction']=b['joint_preferred']/n if n else None
        if not uncertainty:b['Q_3sd_misses']=b['SOC_3sd_misses']=None


def predictive(history,op):
    joint=history.logw[None]+op['logP'].T[:,:,None,None,None,None]
    lw=lse(joint,axis=1);w=np.exp(joint-lw[:,None]);m=np.sum(w*history.mean[None],axis=1)
    var=np.sum(w*(history.variance[None]+(history.mean[None]-m[:,None])**2),axis=1)
    m-=op['decrement'][:,None,:,None,None];t=np.tanh(8*(m-.5))
    v=3+1.15*m+.08*t-op['current']*op['R'][:,None,None,:,None]-op['nuisance'][None,None,None,None,:]
    weights=np.exp(lw-lse(lw));mean=float(np.sum(weights*v))
    variance=float(np.sum(weights*((v-mean)**2+(1.15+.64*(1-t*t))**2*var)))+op['sigma']**2
    return dict(voltage_mean=mean,voltage_sd=math.sqrt(variance),standardized_innovation=(op['observation']-mean)/math.sqrt(variance))


def run(out,name):
    entry=verify_inputs(out,name)
    if read(out/'qualification/result.json')['status']!='passed':raise ValueError('qualification required')
    dest=out/name;dest.mkdir(exist_ok=False)
    obs=np.load(out/'inputs'/(name+'_observations.npy'),mmap_mode='r')
    truth=np.load(out/'inputs'/(name+'_truth.npy'),mmap_mode='r')
    source=entry['source_id'];started=time.perf_counter();cpu=time.process_time()
    lib=library(out);legacy=np.zeros((len(obs)//16,6));counters=np.zeros(5);t=time.perf_counter()
    legacy_status=lib.run_legacy(ptr(obs),len(obs),bytes.fromhex(source),ptr(legacy),ptr(counters))
    legacy_wall=time.perf_counter()-t;legacy=legacy[:int(counters[2])];np.save(dest/'legacy_blocks.npy',legacy)
    ls=statistics();ls.update(status='completed' if legacy_status==0 else 'unresolved',native_status=legacy_status,
         records=int(counters[1]),model_steps=int(counters[3]),context_B=int(counters[4]),wall_s=legacy_wall,
         uncertainty='unvalidated; optimizer curvature is not posterior variance',history='unchanged legacy approximation; no new feedback')
    for row in legacy:
        i=int(row[0])-1;score(ls,row[1],row[3],truth[i],(i+1)/35)
    ls['search_stop_counts']={str(int(k)):int(n) for k,n in zip(*np.unique(legacy[:,4],return_counts=True))}
    ls['accepted_steps']=int(legacy[-1,5]) if len(legacy) else 0
    finish(ls,False)
    banks={k:History(source,k,initial_sd=.03) for k in ['float64','float32']}
    stats={k:statistics() for k in banks};operator=Operator(source,.01);checkpoints=[];last_print=time.perf_counter()
    for i,row in enumerate(obs):
        op=operator.prepare(Frame(i,*map(float,row)),source)
        checkpoint=i%2100==2099 or i in [0,3600*35-1,5400*35-1,10800*35-1]
        pred=predictive(banks['float64'],op) if checkpoint and stats['float64']['status']=='running' else None
        reads={}
        for kind,bank in banks.items():
            stat=stats[kind]
            if stat['status']!='running':continue
            try:bank.step(op);r=bank.readout(op)
            except (ValueError,FloatingPointError) as e:
                stat.update(status='unresolved',failure=dict(index=i,time_s=i/35,reason=str(e)))
                print(json.dumps(dict(case=name,arm=kind,failure=stat['failure'])),flush=True);continue
            reads[kind]=r;score(stat,r['Q'],r['SOC'],truth[i],(i+1)/35,(r['Q_sd'],r['SOC_sd']))
            if kind=='float32' and 'float64' in reads:
                ref=reads['float64'];dq=abs(100*(r['Q']-ref['Q'])/ref['Q']);dz=abs(100*(r['SOC']-ref['SOC']))
                stat['max_history_Q_percent']=max(stat.get('max_history_Q_percent',0),dq)
                stat['max_history_SOC_pp']=max(stat.get('max_history_SOC_pp',0),dz)
        if checkpoint:
            checkpoints.append(dict(index=i,time_s=(i+1)/35,truth_Q=float(truth[i,0]),truth_SOC=float(truth[i,2]),
                                    current=float(row[1]),temperature=float(row[2]),arms=reads,predictive=pred))
        if time.perf_counter()-last_print>25:
            print(json.dumps(dict(case=name,records=i+1,simulated_hours=(i+1)/126000,wall_s=time.perf_counter()-started)),flush=True)
            last_print=time.perf_counter()
        if all(s['status']!='running' for s in stats.values()):break
    for k,s in stats.items():
        if s['status']=='running':s['status']='completed'
        s['records']=banks[k].next_index;s['storage']=banks[k].bytes();finish(s,True)
    result=dict(case=name,source_id=source,arms={**stats,'legacy':ls},checkpoints=checkpoints,
                wall_s=time.perf_counter()-started,cpu_s=time.process_time()-cpu,
                ownership='Independent source-once estimators; no cross-arm feedback',coverage_validated=False)
    write(dest/'result.json',result)
    print(json.dumps(dict(case=name,done=True,wall_s=result['wall_s'],arms={k:dict(status=s['status'],records=s['records'],final=s.get('final')) for k,s in result['arms'].items()})),flush=True)


if __name__=='__main__':
    mode=sys.argv[1];out=Path(sys.argv[2]) if len(sys.argv)>2 else HERE/'campaign001'
    if mode=='prepare':prepare(out)
    elif mode=='qualify':qualification(out)
    elif mode=='run':run(out,sys.argv[3])
    else:raise ValueError('prepare, qualify or run required')
