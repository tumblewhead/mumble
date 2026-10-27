#!/usr/bin/env python3
"""Retained-observation desktop baseline; no 10 KiB deployment claim."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
os.environ['OMP_NUM_THREADS']='1'
import ctypes as C
import json
from pathlib import Path
import sys
import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE.parent/'fixed_prefix_shape_001'))
import runner
import shape

def load(p):return json.loads(Path(p).read_text())
def sources():
    out=runner.bound_sources()
    for n in ('replay.c','desktop.py','qualify.py','run.py','plan.json'):
        out[str((HERE/n).relative_to(ROOT))]=runner.identity(HERE/n)
    out['experiments/live_anchor_integration_001/qualification/independent_oracle.py']=runner.identity(HERE.parent/'live_anchor_integration_001/qualification/independent_oracle.py')
    return out

def build(out):
    return ['cc',*runner.FLAGS,'-shared','-fPIC',str(HERE/'replay.c'),
        'src/scm_model.c','experiments/live_anchor_integration_001/public_contract.c',
        'experiments/live_anchor_integration_001/host_input.c',
        'experiments/live_anchor_bootstrap_001/adc12.c','-lm','-o',str(out)]

class Replay:
    def __init__(self,binary):
        self.lib=C.CDLL(str(binary));d=C.POINTER(C.c_double)
        self.lib.desktop_eval.argtypes=[d,C.c_size_t,d,C.c_int,d,d,d,d]
        self.lib.desktop_decode.argtypes=[C.c_char_p,C.c_uint64,C.c_size_t,d]
        self.mean=np.array((C.c_double*16).in_dll(self.lib,'ch_public_mean'))
        self.sd=np.array((C.c_double*16).in_dll(self.lib,'ch_public_sd'))
        self.lower=np.array((C.c_double*16).in_dll(self.lib,'ch_lower'))
        self.upper=np.array((C.c_double*16).in_dll(self.lib,'ch_upper'))
        self.steps=0;self.calls=0;self.derivative_calls=0
    @staticmethod
    def ptr(a):return a.ctypes.data_as(C.POINTER(C.c_double))
    def decode(self,raw,first):
        if len(raw)%32:raise ValueError('partial record')
        a=np.empty((len(raw)//32,3));s=self.lib.desktop_decode(raw,first,len(a),self.ptr(a))
        if s:raise ValueError('source order/codec '+str(s))
        return a
    def evaluate(self,a,x,derivatives=True):
        a=np.ascontiguousarray(a,dtype=float);x=np.ascontiguousarray(x,dtype=float)
        if a.ndim!=2 or a.shape[1]!=3 or x.shape!=(16,):raise ValueError('shape')
        if self.steps+len(a)>2_000_000_000:raise RuntimeError('model-step cap')
        c=C.c_double();g=np.zeros(16);h=np.zeros((16,16));e=np.zeros(5)
        s=self.lib.desktop_eval(self.ptr(a),len(a),self.ptr(x),int(derivatives),C.byref(c),self.ptr(g),self.ptr(h),self.ptr(e))
        self.steps+=len(a);self.calls+=1;self.derivative_calls+=int(derivatives)
        if s:return None
        return c.value,g,h,e
    def prior(self,x):
        sd=self.sd.copy();sd[5]=.20951093757861336
        q=x-self.mean;t=(x[5]-np.array([-3.0907210901048416,-2.536100343415231]))/sd[5]
        logp=-.5*t*t;m=max(logp);ls=m+np.log(np.exp(logp-m).sum());w=np.exp(logp-ls)
        v=q/sd;v[5]=0
        cost=.5*(v@v)+np.log(sd).sum()+8*np.log(2*np.pi)+np.log(2)-ls
        g=q/sd**2;g[5]=(w@t)/sd[5]
        return float(cost),g,np.diag(1/sd**2)

def fit(r,a,start,limit):
    """Damped GN with box projection and exact-objective backtracking.
    Original mixture prior once; its positive majorizer is a solver metric,
    not a reported posterior precision. SOC-invalid trials are rejected.
    """
    x=start.copy();damping=1e-3;trace=[];status='iteration_limit'
    lo=(r.lower-r.mean)/r.sd;hi=(r.upper-r.mean)/r.sd
    for iteration in range(limit):
        ev=r.evaluate(a,x)
        if ev is None:raise RuntimeError('invalid accepted point')
        lc,g,h,end=ev;pc,pg,ph=r.prior(x);f=lc+pc
        g=(g+pg)*r.sd;h=(h+ph)*r.sd[:,None]*r.sd[None,:]
        u=(x-r.mean)/r.sd
        pgvec=u-np.clip(u-g,lo,hi);station=float(np.max(np.abs(pgvec)))
        record={'iteration':iteration,'likelihood':lc,'prior':pc,'total':f,
                'projected_gradient_inf':station,'damping':damping,'accepted':False}
        trace.append(record)
        if station<1e-4:status='projected_gradient_tolerance';break
        active=((u<=lo+1e-12)&(g>0))|((u>=hi-1e-12)&(g<0))
        free=np.flatnonzero(~active);step=np.zeros(16)
        hh=h[np.ix_(free,free)];diag=np.maximum(np.diag(hh),1.)
        step[free]=np.linalg.solve(hh+damping*np.diag(diag),-g[free])
        step=np.clip(u+step,lo,hi)-u
        slope=float(g@step)
        if slope>=0:
            step=np.clip(u-g/np.maximum(np.diag(h),1.),lo,hi)-u;slope=float(g@step)
        for backtrack in range(12):
            fraction=2.**(-backtrack)
            trial=np.clip(r.mean+r.sd*(u+fraction*step),r.lower,r.upper)
            candidate=r.evaluate(a,trial,False)
            if candidate is None:continue
            tc=candidate[0]+r.prior(trial)[0]
            if tc<=f+1e-4*fraction*slope and tc<f:
                record.update(accepted=True,after_total=tc,fraction=fraction)
                x=trial;damping=max(1e-9,damping/3);break
        if not record['accepted']:
            damping*=10
            if damping>1e12:status='no_accepted_step';break
    final=r.evaluate(a,x);pc,_,_=r.prior(x)
    assert final is not None
    return {'x':x.tolist(),'status':status,'iterations':trace,
        'likelihood':final[0],'prior':pc,'total':final[0]+pc,'endpoint':final[3].tolist(),
        'all_parameter_convergence':False,'coverage_validated':False}

def worker(mode,binary,out):
    plan=load(HERE/'plan.json');r=Replay(binary);obs=ROOT/plan['inputs']['observations']['path']
    if mode=='fidelity':
        with obs.open('rb') as f:a=r.decode(f.read(plan['prefix']*32),0)
        nodes=load(ROOT/plan['inputs']['nodes']['path']);refs=load(ROOT/plan['inputs']['evaluations']['path'])
        rows=[];endpoint_gaps=[]
        for node,ref in zip(nodes['nodes'],refs['rows'],strict=True):
            ev=r.evaluate(a,np.array(node['x']),False)
            row={'id':node['id'],'x':node['x'],'status':'unavailable'}
            if ev is not None and ref['status']=='available':
                # Same numerical recurrence as frozen reference; explicit
                # conservative summation allowance, not forward-error proof.
                nu=(8*len(a)+32)*2**-53
                row.update(status='available',represented_likelihood_cost=ev[0],
                    represented_cost_allowance=nu/(1-nu)*abs(ev[0])+1e-8,
                    reference_likelihood_cost=ref['reference_likelihood_cost'],
                    reference_cost_allowance=ref['reference_cost_allowance'])
                endpoint_gaps.append(float(np.max(np.abs(ev[3]-ref['reference_endpoint']))))
            rows.append(row)
        analysis=shape.compare(nodes,rows)
        runner.save(out/'analysis.json',analysis)
        result={'status':'completed','available_nodes':analysis['available_nodes'],
            'decision':analysis['decision'],'oscillation_NLL':analysis['centered_error_oscillation_NLL'],
            'interval_NLL':analysis['oscillation_computed_arithmetic_interval_NLL'],
            'max_endpoint_difference':max(endpoint_gaps),'optimizer_calls':0}
    elif mode=='causal':
        # This path never loads frozen nodes, reference results, old anchors or truth.
        a=np.empty((plan['prefix'],3));received=0;x=r.mean.copy();checkpoints=[]
        with obs.open('rb') as f:
            for n in plan['checkpoints']:
                raw=f.read((n-received)*32)
                if len(raw)!=(n-received)*32:raise ValueError('short source')
                a[received:n]=r.decode(raw,received);del raw;received=n
                fit_result=fit(r,a[:received],x,plan['iterations_per_checkpoint'])
                x=np.array(fit_result['x']);fit_result.update(prefix=n,elapsed_s=float(a[:n,0].sum()))
                runner.save(out/('checkpoint_'+str(n)+'.json'),fit_result);checkpoints.append(fit_result)
                print(json.dumps({'prefix':n,'status':fit_result['status'],'total':fit_result['total']}),flush=True)
        result={'status':'completed','checkpoints':[{'prefix':c['prefix'],'status':c['status'],
            'total':c['total'],'Q_Ah':float(np.exp(c['x'][5])),'SOC':c['endpoint'][0]} for c in checkpoints],
            'observation_bytes':a.nbytes,'received':received,'initialization':'public mean',
            'saved_anchor_reads':0,'reference_reads':0,'truth_reads':0,
            'likelihood_ownership':'All received observations once per objective; original prior once; no posterior carried as additional evidence',
            'optimizer_calls':len(checkpoints)}
    else:raise ValueError(mode)
    result.update(model_steps_upper_bound=r.steps,evaluations=r.calls,derivative_evaluations=r.derivative_calls,
                  firmware_ready=False,source_revision=plan['base_revision'])
    runner.save(out/'result.json',result);print(json.dumps(result),flush=True)

if __name__=='__main__':worker(sys.argv[1],Path(sys.argv[2]).resolve(),Path(sys.argv[3]).resolve())
