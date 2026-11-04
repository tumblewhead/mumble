"""Experimental fixed-origin likelihood refresh of the C rolling estimator.

Only ordered observations and public calibration enter this adapter. The original
prior is used once in each full-history fit. The resulting joint distribution
REPLACES the same-prefix rolling distribution; it is never multiplied into it.
Stationary parameters only. No aging, field recentering or support clipping.
"""
import ctypes as C
import json
import math
from pathlib import Path
import numpy as np
from .backend import CBackend,identity,ROOT
from .coordinates import prior
from experiments.foster_c_baseline_001.reference import DP,ptr
from experiments.foster_feedback_001.estimator import Model
from experiments.foster_uncertainty_audit_001.conditional_packet import partition
from experiments.joint_rate_history_001.field import Field,build
from experiments.slow_likelihood_diagnostic_001.numerics import Compressed,features_jacobian,solve

DEPENDENCIES=['experiments/joint_rate_history_001/field.py',
              'experiments/joint_rate_history_001/probe.c',
              'experiments/slow_likelihood_diagnostic_001/numerics.py',
              'experiments/foster_uncertainty_audit_001/conditional_packet.py',
              'experiments/foster_feedback_001/estimator.py']
BUFFER_RECORDS=4096


def prepare_field(campaign):
    directory=campaign/'backend_field';receipt=directory/'build.json'
    if receipt.exists():
        info=json.loads(receipt.read_text())
        if identity(directory/'response.so')!=info['binary']:raise ValueError('field binary changed')
        return directory/'response.so'
    binary=build(directory)
    receipt.write_text(json.dumps({'binary':identity(binary),'sources':{n:identity(ROOT/n) for n in DEPENDENCIES}},indent=2)+'\n')
    return binary


def transported(field,x):
    """Analytic joint endpoint transport; static parameter coordinates stay exact."""
    features=field.features(x);J=features_jacobian(field,x)
    W=np.zeros((5,field.width));W[0,0]=1;W[0,1]=-field.state[-3]
    n=field.n;b=field.b;state=field.state
    for i in range(3):
        W[1+i,3+2*i*n:3+(2*i+1)*n]=field.p1@state[i*n:(i+1)*n]
        W[1+i,3+(2*i+1)*n:3+(2*i+2)*n]=field.p1@state[(3+i)*n:(4+i)*n]
    start=3+6*n;hstart=6*n
    W[4,start:start+b]=field.p2@state[hstart+n*n:hstart+2*n*n]
    W[4,start+b:start+2*b]=field.p2@state[hstart:hstart+n*n]
    physical=W@features;D=np.eye(16);D[:5]=W@J
    H=math.exp(x[13]);h=physical[4]/H
    if not -1<h<1 or not 0<=physical[0]<=1:raise ValueError('native field endpoint outside physical chart support')
    D[4]/=H;D[4,13]-=h;D[4]/=(1-h*h)
    end=x.copy();end[:4]=physical[:4];end[4]=np.arctanh(h)
    return end,D


class FieldBackend(CBackend):
    def __init__(self,campaign,config,source,model_id,rate,settings):
        if config.get('hysteresis_chart')!='bounded':raise ValueError('field requires bounded chart')
        super().__init__(campaign,config,source,model_id,'float64',rate)
        self.mean,self.prior_root=prior(config)
        self.field=self._make_field(campaign,config,source)
        self.model=Model((campaign/'backend_c/estimator.so').resolve(),config)
        self.objective=self._make_objective()
        self.interval=max(16,math.ceil(settings.field_refresh_seconds*rate/16)*16)
        self.pending_rows=np.empty((BUFFER_RECORDS,5));self.buffered=0
        self.w=np.zeros(16)
        self.audit=dict(refresh_interval_records=self.interval,attempts=0,accepted=0,rejected=0,
                        last_attempt_record=0,last_accepted_record=0,last_rejection=None,
                        max_abs_Q_replacement_percent=0.,max_abs_SOC_replacement_pp=0.)
        self.lib.campaign_replace_message.argtypes=[C.c_void_p,C.c_uint64,DP]
        self.lib.campaign_replace_message.restype=C.c_int

    def _make_field(self,campaign,config,source):
        return Field(config,partition(self.mean)[1],1.,5,prepare_field(campaign),source)

    def _make_objective(self):
        return Compressed(self.field,self.mean,self.prior_root)

    def _transport(self,x):
        return transported(self.field,x)

    def _flush_field(self):
        if self.buffered:
            self.field.update(self.field.count,self.pending_rows[:self.buffered])
            self.buffered=0

    def _replace(self,sequence):
        self.audit['attempts']+=1;self.audit['last_attempt_record']=sequence
        try:
            fit=solve(self.objective,start=self.w)
            diag=fit['diagnostic']
            if diag['stop'] not in ('GN_decrement_at_cost_roundoff','gradient'):
                raise ValueError('field solve unresolved: '+diag['stop'])
            end,D=self._transport(fit['x']);root=D@fit['root']
            self.model.evaluate(end,np.empty((0,5)))
            _,_,P,_,_=self.objective(fit['w'])
            sign,logdet=np.linalg.slogdet(P)
            if sign<=0:raise ValueError('nonpositive GN precision')
            # Laplace/GN evidence estimate in original prior-whitened coordinates.
            logZ=-diag['cost']-self.field.noise-.5*logdet
            replacement=np.ascontiguousarray(np.r_[end,root.ravel(),logZ])
            before=self.full_message()
            if self.lib.campaign_replace_message(self.context,sequence,ptr(replacement)):
                raise ValueError('same-boundary message replacement rejected')
            self.w=fit['w'];self.audit['accepted']+=1;self.audit['last_accepted_record']=sequence
            self.audit['max_abs_Q_replacement_percent']=max(self.audit['max_abs_Q_replacement_percent'],abs(100*np.expm1(end[5]-before[5])))
            self.audit['max_abs_SOC_replacement_pp']=max(self.audit['max_abs_SOC_replacement_pp'],abs(100*(end[0]-before[0])))
            return True
        except (ValueError,np.linalg.LinAlgError,OverflowError,FloatingPointError) as e:
            self.audit['rejected']+=1
            self.audit['last_rejection']={'record':sequence,'reason':str(e)}
            return False

    def advance(self,first,rows):
        # C rejects reordered input before the field sees any of it.
        result=super().advance(first,rows)
        if first!=self.field.count+self.buffered:raise ValueError('field/rolling chronology mismatch')
        if self.buffered+len(rows)>BUFFER_RECORDS:self._flush_field()
        self.pending_rows[self.buffered:self.buffered+len(rows)]=rows;self.buffered+=len(rows)
        sequence=first+len(rows)
        if self.buffered==BUFFER_RECORDS:self._flush_field()
        if sequence%self.interval==0:
            self._flush_field()
            if self._replace(sequence):
                result=self.readout(rows);result[1]['stop']='field_refresh'
            else:result[1]['stop']='field_refresh_unresolved'
        return result

    def counts(self):
        counts=super().counts()
        counts['field_history']={**self.audit,'accumulated_records':self.field.count,
                                 'buffered_records':self.buffered,
                                 'status':('no_refresh_yet' if not self.audit['attempts'] else
                                           'refreshes_unresolved' if not self.audit['accepted'] else
                                           'some_refreshes_unresolved' if self.audit['rejected'] else 'all_refreshes_accepted')}
        return counts

    def storage(self):
        return {**super().storage(),'experimental_field':self.field.storage(),
                'field_pending_buffer_B':self.pending_rows.nbytes,
                'field_actual_dense_root_B':self.field.root.nbytes,
                'scope':'Desktop Python/C experiment; other Python/QR workspace excluded, not M23-ready'}

    def checkpoint_arrays(self):
        return {'root':self.field.root,'state':self.field.state,'w':self.w,
                'pending':self.pending_rows[:self.buffered].copy(),
                'metadata':np.frombuffer(json.dumps({'count':self.field.count,'noise':self.field.noise,
                                                    'audit':self.audit,'interval':self.interval}).encode(),dtype=np.uint8)}

    def restore_arrays(self,arrays):
        meta=json.loads(arrays['metadata'].tobytes())
        if meta['interval']!=self.interval:raise ValueError('field cadence mismatch')
        for name,shape in [('root',self.field.root.shape),('state',self.field.state.shape),('w',(16,))]:
            if arrays[name].shape!=shape or not np.isfinite(arrays[name]).all():raise ValueError('field checkpoint shape/values')
        self.field.root=arrays['root'].copy();self.field.state=arrays['state'].copy();self.w=arrays['w'].copy()
        pending=arrays['pending'];self.buffered=len(pending)
        if pending.shape!=(self.buffered,5) or self.buffered>BUFFER_RECORDS:raise ValueError('field pending buffer shape')
        self.pending_rows[:self.buffered]=pending
        self.field.count=meta['count'];self.field.noise=meta['noise'];self.audit=meta['audit']
        if self.field.count+self.buffered!=super().counts()['retired_records']:raise ValueError('field checkpoint chronology')
