"""Finite fabricated adapter qualification; no optimizer or canonical replay."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
os.environ['OMP_NUM_THREADS']='1'
import ctypes as C
from datetime import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
SOURCES=[HERE/'provider.c',HERE.parent/'desktop_history_001/replay.c',
         *[HERE.parent/'live_anchor_integration_001'/n for n in
           ('rolling_engine.c','rolling_model.c','public_contract.c','host_input.c')],
         *[HERE.parent/'live_anchor_bootstrap_001'/n for n in
           ('adc12.c','history_translation.c','support_step.c')],ROOT/'src/scm_model.c']
DP=C.POINTER(C.c_double)

class Result(C.Structure):
    _fields_=[('likelihood',C.c_double),('gradient',C.c_double*16),
              ('gn_packed',C.c_double*136),('endpoint',C.c_double*5),
              ('represented_rows',C.c_uint64),('retained_rows',C.c_uint64),
              ('status',C.c_int),('provider_kind',C.c_uint),('legacy_flags',C.c_uint)]

def ptr(a):return a.ctypes.data_as(DP)
def identity(p):
    raw=p.read_bytes();return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
def save(p,v):
    with p.open('x') as f:json.dump(v,f,indent=2,allow_nan=False);f.write('\n')

class Harness:
    def __init__(self,binary):
        self.lib=C.CDLL(str(binary));lib=self.lib
        lib.hp_context_bytes.restype=C.c_size_t
        lib.hp_context_init.argtypes=[C.c_void_p,C.c_char_p]
        lib.hp_append.argtypes=[C.c_void_p,C.c_char_p,C.c_uint64,C.c_uint64,C.c_uint,C.c_uint,C.c_uint]
        lib.hp_decode.argtypes=[C.c_uint64,C.c_uint,C.c_uint,C.c_uint,DP]
        lib.hp_commit_at.argtypes=[C.c_void_p,DP]
        lib.hp_compact_query.argtypes=[C.c_void_p,DP,C.POINTER(Result)]
        lib.hp_exact_query.argtypes=[DP,C.c_size_t,DP,C.POINTER(Result)]
        lib.desktop_eval.argtypes=[DP,C.c_size_t,DP,C.c_int,DP,DP,DP,DP]
        lib.re_query.argtypes=[C.c_void_p,C.c_int,C.c_int]
        self.mean=np.array((C.c_double*16).in_dll(lib,'ch_public_mean'))
        self.sd=np.array((C.c_double*16).in_dll(lib,'ch_public_sd'))
        self.calls=0;self.steps=0;self.checks=0
    def check(self,value,label):
        self.checks+=1
        if not value:raise AssertionError(label)
    def context(self):
        n=self.lib.hp_context_bytes();self.check(n%8==0,'context alignment')
        c=(C.c_double*(n//8))()
        self.check(self.lib.hp_context_init(c,b'H'*32)==0,'initialize')
        return c
    def query(self,c,rows,x):
        self.calls+=1
        n=len(rows);self.steps+=n
        if self.steps>100_000:raise RuntimeError('qualification model-step upper cap')
        r=Result()
        status=(self.lib.hp_exact_query(ptr(rows),n,ptr(x),C.byref(r)) if c is None else
                self.lib.hp_compact_query(c,ptr(x),C.byref(r)))
        self.check(status==r.status,'consistent error status')
        return r
    def close(self,a,b,label):
        self.check(np.allclose(a,b,rtol=2e-11,atol=2e-9),label)

def qualification(out):
    out.mkdir(parents=True,exist_ok=False)
    tracked=list(SOURCES)+[HERE/'provider.h',HERE/'contract.json',HERE/'qualify.py',
        ROOT/'include/scm_model.h',HERE.parent/'live_anchor_integration_001/rolling_engine.h',
        HERE.parent/'live_anchor_integration_001/rolling_model.h',
        HERE.parent/'live_anchor_integration_001/host_input.h',
        HERE.parent/'live_anchor_bootstrap_001/live_layout.h',
        HERE.parent/'live_anchor_bootstrap_001/adc12.h',
        HERE.parent/'live_anchor_bootstrap_001/support_step.h',
        HERE.parent/'live_anchor_bootstrap_001/history_translation.h',
        HERE.parent/'compact_nonlinear_history_001/compact_history.h']
    sources={str(p.relative_to(ROOT)):identity(p) for p in tracked}
    save(out/'reservation.json',dict(sources=sources,max_model_steps_upper=100_000,
        canonical_reads=0,optimizer_calls=0,truth_reads=0,
        source_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        status='registered_before_build_and_fabricated_evaluation'))
    command=['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-pedantic',
        '-fno-fast-math','-ffp-contract=off','-shared','-fPIC','-I'+str(ROOT/'include'),
        *map(str,SOURCES),'-lm','-o',str(out/'provider.so')]
    started=time.monotonic();build=subprocess.run(command,capture_output=True,text=True)
    save(out/'build.json',dict(command=command,returncode=build.returncode,
                              stdout=build.stdout,stderr=build.stderr))
    if build.returncode:raise RuntimeError(build.stderr)
    h=Harness(out/'provider.so');lib=h.lib;result=dict(status='failed')
    try:
        # Fabricated measurements: not plant truth or a fitted anchor.
        raw=[(200000+[0,10000,-10000,20000][i%4],2400+i%7,
              [2368,2048,1808,2688][(i//4)%4],1040) for i in range(64)]
        rows=[]
        for record in raw:
            d=np.zeros(3);h.check(lib.hp_decode(*record,ptr(d))==0,'decode');rows.append(d)
        rows=np.asarray(rows)
        nodes=[h.mean.copy()]
        for j in range(16):
            for sign in [-1,1]:
                x=h.mean.copy();x[j]+=sign*.1*h.sd[j];nodes.append(x)
        save(out/'frozen_queries.json',dict(raw=raw,nodes=[x.tolist() for x in nodes],
             reason='public-centered coordinate perturbations, fixed before any query outcome'))
        empty=rows[:0];c=h.context()
        a=h.query(None,empty,h.mean);b=h.query(c,empty,h.mean)
        h.check(a.status==b.status==0,'empty status');h.close(a.likelihood,0,'prior absent')
        h.close(b.likelihood,0,'compact prior absent');h.close(a.endpoint,b.endpoint,'empty endpoint')
        h.check(a.retained_rows==b.represented_rows==b.retained_rows==0,'empty ownership')
        for index,record in enumerate(raw[:16]):
            h.check(lib.hp_append(c,b'H'*32,index,*record)==0,'append')
        before=bytes(c)
        a=h.query(None,rows[:16],h.mean);b=h.query(c,rows[:16],h.mean)
        h.check(a.status==b.status==0,'raw query available')
        for field in ['likelihood','gradient','gn_packed','endpoint']:
            h.close(getattr(a,field),getattr(b,field),'raw parity '+field)
        h.check(bytes(c)==before,'query does not mutate any context byte')
        # Check exact-adapter packing and values against original C entry point.
        cost=np.zeros(1);g=np.zeros(16);metric=np.zeros((16,16));endpoint=np.zeros(5)
        h.check(lib.desktop_eval(ptr(rows[:16]),16,ptr(h.mean),1,ptr(cost),ptr(g),ptr(metric),ptr(endpoint))==0,'native replay')
        h.steps+=16
        h.check(a.likelihood==cost[0] and np.array_equal(a.gradient,g) and
                np.array_equal(a.gn_packed,metric[np.tril_indices(16)]) and
                np.array_equal(a.endpoint,endpoint),'exact adapter bitwise native parity')
        h.check(lib.hp_append(c,b'H'*32,16,*raw[16])!=0 and bytes(c)==before,'full block atomic')
        bad=h.mean.copy();bad[5]=-100
        h.check(h.query(c,rows[:16],bad).status!=0 and bytes(c)==before,'invalid query immutable')
        h.check(lib.hp_commit_at(c,ptr(bad))!=0 and bytes(c)==before,'invalid commit atomic')
        h.check(lib.hp_commit_at(c,ptr(h.mean))==0,'commit')
        post=bytes(c);b=h.query(c,rows[:16],h.mean)
        h.close(a.likelihood,b.likelihood,'at-anchor commit likelihood')
        h.close(a.gradient,b.gradient,'at-anchor commit gradient')
        h.close(a.gn_packed,b.gn_packed,'at-anchor commit GN')
        h.close(a.endpoint,b.endpoint,'at-anchor commit boundary')
        h.check(b.represented_rows==16 and b.retained_rows==0,'retire raw exactly once')
        h.check(bytes(c)==post,'committed query immutable')
        for source,index,record in [(b'X'*32,16,raw[16]),(b'H'*32,17,raw[16]),
                                    (b'H'*32,16,(200000,4096,2048,1040))]:
            h.check(lib.hp_append(c,source,index,*record)!=0 and bytes(c)==post,'invalid append atomic')
        # Finite difference on uncompressed likelihood, in public-scaled coordinates.
        for j in range(16):
            xp=h.mean.copy();xm=h.mean.copy();delta=1e-5*h.sd[j];xp[j]+=delta;xm[j]-=delta
            derivative=(h.query(None,rows[:16],xp).likelihood-h.query(None,rows[:16],xm).likelihood)/(2*delta)
            h.check(abs(derivative-a.gradient[j])*h.sd[j] <= 1e-5*max(1,abs(a.gradient[j])*h.sd[j]),'gradient finite difference')
        # Representation-only comparisons; fixed anchors are not solver outputs.
        arms=[]
        for block,move in [(8,False),(16,False),(16,True)]:
            c=h.context()
            for index,record in enumerate(raw):
                h.check(lib.hp_append(c,b'H'*32,index,*record)==0,'arm append')
                if (index+1)%block==0:
                    anchor=h.mean.copy()
                    if move:anchor[:5]+=.5*h.sd[:5]*np.sin((index+1)/16)
                    h.check(lib.hp_commit_at(c,ptr(anchor))==0,'arm commit')
            gaps=[];grad=[];end=[];compact_values=[]
            before=bytes(c)
            for x in nodes:
                exact=h.query(None,rows,x);compact=h.query(c,rows,x)
                h.check(exact.status==compact.status==0,'arm query status')
                h.check(compact.represented_rows==64 and compact.retained_rows==0,'arm ownership')
                gaps.append(compact.likelihood-exact.likelihood)
                grad.append(float(np.max(abs(np.array(compact.gradient)-exact.gradient)*h.sd)))
                end.append(float(np.max(abs(np.array(compact.endpoint)-exact.endpoint))))
                compact_values.append(compact.likelihood)
            h.check(before==bytes(c),'all node queries immutable')
            arms.append(dict(block=block,moving_anchor=move,centered_error_oscillation_NLL=max(gaps)-min(gaps),
                max_scaled_gradient_error=max(grad),max_endpoint_gap=max(end),likelihoods=compact_values,
                numerical_queries_available=True,physical_fidelity_claim=False))
        h.check(all(identity(ROOT/name)==value for name,value in sources.items()),'sources unchanged')
        result.update(status='passed',checks=h.checks,queries=h.calls,model_steps_upper=h.steps,
            arms=arms,legacy_context_bytes=lib.hp_context_bytes(),query_result_bytes=C.sizeof(Result),
            desktop_scratch='compact adapter clones8680B context; exact adapter owns256double metric scratch. Not an M23 layout.',
            optimizer_calls=0,canonical_reads=0,truth_reads=0,
            new_compressor_qualified=False,uncertainty_qualified=False,solver_modified=False,
            interpretation='Adapter and ownership qualification passed. Differences are measured legacy representation errors, not adapter tolerance passes or new compression results.')
    except Exception:
        import traceback
        result.update(error=traceback.format_exc(),checks=h.checks,model_steps_upper=h.steps)
    result['wall_s_including_build']=time.monotonic()-started
    save(out/'receipt.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='arms'},indent=2),flush=True)
    return 0 if result['status']=='passed' else 1

if __name__=='__main__':
    output=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else HERE/('qualification_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    raise SystemExit(qualification(output))
