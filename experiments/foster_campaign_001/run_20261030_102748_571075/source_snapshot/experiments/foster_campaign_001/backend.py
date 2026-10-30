"""Campaign estimator adapters. Inputs are indexed observations and public config only."""
import ctypes as C
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import numpy as np
from experiments.foster_feedback_001.estimator import Rolling,prior
from experiments.foster_feedback_001.history import GaussianBackend
from specifications.evidence_feedback_001.protocol import History,WindowOwnership
from experiments.foster_c_baseline_001.reference import Config,Message,DP,message,ptr,library
from .rate import clock_hz
ROOT=Path(__file__).resolve().parents[2]
ADAPTER=ROOT/'experiments/foster_campaign_c_001'
CORE=ROOT/'experiments/foster_c_history_001'
BASE=ROOT/'experiments/foster_c_baseline_001'
MODEL=ROOT/'experiments/foster_c_model_001/model.c'
STOPS=['round_limit','gradient','step','no_descent']

def identity(path):
    return {'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}

def prepare_c(campaign,rate):
    hz=clock_hz(rate);out=campaign/'backend_c';binary=out/'estimator.so';receipt=out/'build.json'
    if binary.exists() and receipt.exists():
        info=json.loads(receipt.read_text())
        if info['tick_hz']!=hz or info['binary']!=identity(binary):raise ValueError('C backend clock/binary mismatch')
        return binary,info
    out.mkdir(exist_ok=False)
    sources=[ADAPTER/'rolling.c',ADAPTER/'bridge.c',CORE/'history.c',BASE/'numeric.c',MODEL]
    recorded=sources+[CORE/'baseline.h']
    # Verify the frozen core files actually used, without rebuilding old evidence.
    expected=json.loads((CORE/'verification.json').read_text())['artifacts']
    for src in [CORE/'history.c',CORE/'baseline.h']:
        if identity(src)!=expected[str(src.relative_to(ROOT))]:raise ValueError('frozen history source changed')
    for folder,src in [('foster_c_baseline_001',BASE/'numeric.c'),('foster_c_model_001',MODEL)]:
        expected_src=json.loads((ROOT/'experiments'/folder/'verification.json').read_text())['artifacts'][str(src.relative_to(ROOT))]
        if identity(src)!=expected_src:raise ValueError('frozen model/numeric source changed')
    snapshots=[]
    for src in recorded:
        dst=out/'source_snapshot'/src.relative_to(ROOT);dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst);snapshots.append(dst)
    flags=['-std=c11','-O2','-fno-fast-math','-ffp-contract=off','-Wall','-Wextra','-Werror','-pedantic','-fPIC','-DFB_PROFILE','-D_POSIX_C_SOURCE=200809L',f'-DFB_CLOCK_HZ={hz}','-DFB_MODEL_STAGE=2','-DFB_OPT_STAGE=3','-DFB_HISTORY_STAGE=2','-include',str(snapshots[-1]),'-I',str(snapshots[-1].parent)]
    commands=[];objects=[]
    for src in snapshots[:-1]:
        obj=out/(src.stem+'.o');cmd=['cc',*flags,'-c',str(src),'-o',str(obj)];subprocess.run(cmd,check=True);commands.append(cmd);objects.append(str(obj))
    cmd=['cc','-shared',*objects,'-lm','-o',str(binary)];subprocess.run(cmd,check=True);commands.append(cmd)
    info={'backend':'c','core':'foster_c_history_001 stage2','tick_hz':hz,'sample_rate_hz':rate,'commands':commands,'sources':{str(src.relative_to(ROOT)):identity(src) for src in recorded},'binary':identity(binary),'compiler':subprocess.check_output(['cc','--version'],text=True).splitlines()[0]}
    receipt.write_text(json.dumps(info,indent=2)+'\n');return binary,info

class ClockRolling(Rolling):
    """Same Python fitter/history; only observation clock binding is generalized."""
    def __init__(self,binary,config,source,model_id,encoding,hz):
        super().__init__(binary,config,source,model_id,encoding);head=self.history.read()
        self.binding=replace(self.binding,tick_hz=hz)
        self.history=History(self.binding,head.root_prior_id,head.payload,self.backend,2184)
        self.window=WindowOwnership(self.history.read());self.clock=hz
    def offer(self,index,dt,current,temperature,voltage,sigma):
        if index!=self.next_index:raise ValueError('source order')
        values=np.asarray([dt,current,temperature,voltage,sigma],dtype=float)
        if not np.isfinite(values).all() or sigma<=0 or dt<0:raise ValueError('invalid observation')
        ticks=round(dt*self.clock)
        if abs(ticks/self.clock-dt)>1e-12:raise ValueError('interval not represented by declared clock')
        if len(self.rows)>=self.block:raise ValueError('unretired full window')
        self.window.offer(index);self.rows.append(values);self.next_index+=1;self.ticks+=ticks
        if len(self.rows)==self.block:return self.retire()
        return None

class PythonBackend:
    def __init__(self,campaign,config,source,model_id,encoding,rate):
        self.hz=clock_hz(rate);args=((campaign/'model.so').resolve(),config,source,model_id,encoding)
        self.bank=Rolling(*args) if self.hz==1050 else ClockRolling(*args,self.hz)
        self.failure_index=0
    def advance(self,first,rows):
        value=None
        for offset,row in enumerate(rows):
            self.failure_index=first+offset;value=self.bank.offer(first+offset,*map(float,row))
        if value is None:value=self.bank.retire()
        r,d=value;r['time_s']=self.bank.history.read().boundary.ticks/self.hz;return r,d
    def counts(self):
        h=self.bank.history.read()
        return dict(received_records=self.bank.next_index,retired_records=h.boundary.sequence,pending_records=len(self.bank.rows),tokens=h.generation)
    def full_message(self):return np.frombuffer(self.bank.history.read().payload,dtype='<f8').copy()
    def storage(self):return {}

class CBackend:
    def __init__(self,campaign,config,source,model_id,encoding,rate):
        if config['numerical']['block_records']!=16:raise ValueError('C backend requires16-record windows')
        binary,self.build=prepare_c(campaign,rate);self.hz=clock_hz(rate);self.config=config
        self.lib=library(binary.resolve());self.context=C.create_string_buffer(self.lib.fb_context_bytes())
        num=config['numerical'];self.c=Config((C.c_double*14)(config['reference_temperature_K'],config['ocv_intercept_V'],config['ocv_slope_V_per_SOC'],*config['arrhenius_A_K']),num['max_rounds'],num['fractions'],8 if encoding=='float64' else 4,num['gradient_inf_tolerance'],num['latent_step_tolerance'])
        initial=message(*prior(config))
        if self.lib.fb_init(self.context,C.byref(self.c),C.byref(initial),int(source[:16],16)):raise ValueError('C initialization failed')
        self.lib.campaign_block.argtypes=[C.c_void_p,C.c_uint64,DP,C.c_int,C.POINTER(C.c_uint64)]
        self.lib.campaign_state.argtypes=[C.c_void_p,C.POINTER(C.c_uint64),DP]
        self.state=(C.c_uint64*5)();self.diag=np.empty(7);self.failure_index=0
    def refresh(self):self.lib.campaign_state(self.context,self.state,ptr(self.diag))
    def advance(self,first,rows):
        rows=np.ascontiguousarray(rows,dtype=float)
        if rows.ndim!=2 or rows.shape[1]!=5 or not 1<=len(rows)<=16:raise ValueError('C observation block shape')
        failure=C.c_uint64(first);status=self.lib.campaign_block(self.context,first,ptr(rows),len(rows),C.byref(failure))
        self.failure_index=failure.value;self.refresh()
        if status<0:raise ValueError('C estimator status '+str(status))
        a=self.full_message();m=a[:16];L=a[16:272].reshape(16,16);sd=np.sqrt(np.sum(L*L,axis=1))
        factor=math.exp(self.config['arrhenius_A_K'][0]*(1/(float(rows[-1,2])+273.15)-1/self.config['reference_temperature_K']))
        q=math.exp(m[5])*factor
        r=dict(Q=q,Q_ref=math.exp(m[5]),SOC=float(m[0]),Q_log_sd=float(sd[5]),SOC_sd=float(sd[0]),Q_SOC_chart_covariance=float(L[5]@L[0]),Q_interval_3sd=[q*math.exp(-3*sd[5]),q*math.exp(3*sd[5])],chart_mean=m.tolist(),chart_sd=sd.tolist(),log_evidence=float(a[272]),records=int(self.state[1]),time_s=int(self.state[4])/self.hz)
        d=dict(stop=STOPS[int(self.diag[0])],rounds=int(self.diag[1]),evaluations=int(self.diag[2]),cost=float(self.diag[3]),initial_predictive_RMS=float(self.diag[4]),fitted_RMS=float(self.diag[5]),token_bytes=int(self.diag[6]))
        return r,d
    def counts(self):
        self.refresh();return dict(received_records=int(self.state[0]),retired_records=int(self.state[1]),pending_records=int(self.state[2]),tokens=int(self.state[3]))
    def full_message(self):
        a=np.empty(273);self.lib.fb_get_message(self.context,ptr(a));return a
    def storage(self):return dict(C_context_B=self.lib.fb_context_bytes(),C_stack_excluded=True)
