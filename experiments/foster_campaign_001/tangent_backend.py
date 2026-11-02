"""Opt-in original-origin tangent updates with periodic full-field relinearization.

Only public prior/calibration and ordered observations enter this backend. The
outgoing Gaussian is a readout, never a new prior. Stationary-parameter experiment.
"""
import ctypes as C
import copy
import hashlib
import json
import math
import numpy as np
from .backend import CBackend,identity,ROOT
from .coordinates import prior
from .rate import clock_hz
from .field_backend import prepare_field,BUFFER_RECORDS
from experiments.field_tangent_native_001.native import Native,build,ptr
from experiments.foster_uncertainty_audit_001.conditional_packet import partition
from experiments.joint_rate_history_001.field import Field
from experiments.slow_likelihood_diagnostic_001.numerics import Compressed,solve

DEPENDENCIES=['experiments/field_tangent_native_001/'+name for name in ('kernel.c','kernel.h','native.py')]+['experiments/joint_rate_history_001/probe.c']

class Carrier(C.Structure):
    _fields_=[('message',C.c_double*273),('sequence',C.c_uint64),('ticks',C.c_uint64),('tokens',C.c_uint64)]

def prepare_tangent(campaign):
    directory=campaign/'backend_tangent';receipt=directory/'build.json'
    if receipt.exists():
        info=json.loads(receipt.read_text())
        if identity(directory/'tangent.so')!=info['binary']:raise ValueError('tangent binary changed')
        return directory/'tangent.so'
    binary=build(directory)
    receipt.write_text(json.dumps(dict(binary=identity(binary),sources={n:identity(ROOT/n) for n in DEPENDENCIES}),indent=2)+'\n')
    return binary

class TangentBackend:
    def _make_field(self,campaign,config,source):
        return Field(config,partition(self.mean)[1],1.,5,prepare_field(campaign),source)
    def _make_native(self,campaign):
        return Native(prepare_tangent(campaign),self.field,self.mean,self.prior_root)
    def _make_objective(self):
        return Compressed(self.field,self.mean,self.prior_root)
    def __init__(self,campaign,config,source,model_id,rate,settings):
        if config.get('hysteresis_chart')!='bounded' or config['numerical']['block_records']!=16:
            raise ValueError('native tangent requires bounded chart and16-record windows')
        self.config=config;self.hz=clock_hz(rate);self.failure_index=0;self.failed=False
        self.model_id=str(model_id)
        self.failure=None;self._consumed_count=0
        self.mean,self.prior_root=prior(config)
        self.field=self._make_field(campaign,config,source)
        self.live_state=self.field.state.copy();self.live_count=0;self.noise=0.
        self.native=self._make_native(campaign)
        self.native.prepare_step()
        self.objective=self._make_objective()
        self.interval=max(16,math.ceil(settings.field_refresh_seconds*rate/16)*16)
        binding=dict(schema='tangent_configuration_v1',calibration=config,clock_hz=self.hz,
                     refresh_interval_records=self.interval,rc_degree=self.field.n-1,
                     hysteresis_degree=getattr(self.field,'hdegree',self.field.n-1),width=self.field.width)
        self.configuration_id=hashlib.sha256(json.dumps(binding,sort_keys=True,allow_nan=False).encode()).hexdigest()
        self.pending_rows=np.empty((BUFFER_RECORDS,5));self.buffered=0;self.w=np.zeros(16)
        self.context=C.create_string_buffer(C.sizeof(Carrier));self.carrier=Carrier.from_buffer(self.context)
        self._message_view=np.ctypeslib.as_array(self.carrier.message)
        self.diag=np.zeros(7);self.diag[6]=1376
        self.audit=dict(refresh_interval_records=self.interval,attempts=0,accepted=0,rejected=0,
                        emergency_attempts=0,last_attempt_record=0,last_accepted_record=0,last_rejection=None,
                        max_abs_Q_replacement_percent=0.,max_abs_SOC_replacement_pp=0.)
        self.native.initialize(self.w);self._publish(self.native.query(),0,0)

    def _flush_field(self):
        if self.buffered:
            # rows/update replace mutable fields; calibration/projection arrays
            # are borrowed immutable data. Commit only after live-state parity.
            trial=copy.copy(self.field)
            trial.update(trial.count,self.pending_rows[:self.buffered])
            if trial.count!=self.live_count or not np.array_equal(trial.state,self.live_state):
                raise ValueError('live/batched state transport mismatch')
            if not np.isfinite(trial.root).all() or not math.isfinite(trial.noise):
                raise ValueError('nonfinite field flush')
            self.field.root,self.field.state,self.field.count,self.field.noise=trial.root,trial.state,trial.count,trial.noise
            self.buffered=0

    def _refresh(self,reason):
        self._flush_field();self.audit['attempts']+=1;self.audit['last_attempt_record']=self.live_count
        if reason!='scheduled':self.audit['emergency_attempts']+=1
        saved=self.native.snapshot()
        try:
            fit=solve(self.objective,start=self.w)
            if fit['diagnostic']['stop'] not in ('GN_decrement_at_cost_roundoff','gradient'):
                raise ValueError('field solve unresolved: '+fit['diagnostic']['stop'])
            self.native.initialize(fit['w']);result=self.native.query()
            self.audit['accepted']+=1;self.audit['last_accepted_record']=self.live_count
            return result
        except (ValueError,np.linalg.LinAlgError,OverflowError,FloatingPointError) as e:
            self.native.restore(saved,self.live_count)
            self.audit['rejected']+=1;self.audit['last_rejection']=dict(record=self.live_count,trigger=reason,reason=str(e))
            return None

    @staticmethod
    def _publication_payload(result,sequence,ticks,tokens,noise):
        for value in (sequence,ticks,tokens):
            if not isinstance(value,(int,np.integer)) or isinstance(value,(bool,np.bool_)) or not 0<=value<=2**64-1:
                raise ValueError('publication counter range')
        end=np.asarray(result['end'],dtype=float);root=np.asarray(result['endpoint_root'],dtype=float)
        w=np.asarray(result['w'],dtype=float)
        logZ=-result['linearized_cost']-noise-.5*result['logdet_precision']
        if end.shape!=(16,) or root.shape!=(16,16) or w.shape!=(16,) or not all(np.isfinite(a).all() for a in (end,root,w)) or not math.isfinite(logZ):
            raise ValueError('nonfinite tangent readout')
        payload=Carrier();message=np.ctypeslib.as_array(payload.message)
        message[:16]=end;message[16:272]=root.ravel()
        message[272]=logZ
        payload.sequence=sequence;payload.ticks=ticks;payload.tokens=tokens
        return payload,w.copy()

    def _publish(self,result,sequence,ticks,tokens=None):
        if sequence!=self.live_count or sequence!=self.native.count:raise ValueError('publication chronology')
        payload,w=self._publication_payload(result,sequence,ticks,self.carrier.tokens if tokens is None else tokens,self.noise)
        C.memmove(self.context,C.byref(payload),C.sizeof(payload));self.w=w

    def _quarantine(self,error,operation):
        # Disable reads first, even if collecting diagnostic details fails.
        self.failed=True;self._consumed_count=None
        try:
            self._consumed_count=self.native.count
            self.failure=dict(type=type(error).__name__,reason=str(error),operation=operation,
                              input_first=self.failure_index if operation=='advance' else None)
        except Exception:
            self.failure=None

    def _require_current(self):
        if self.failed or self.carrier.sequence!=self.live_count:
            raise ValueError('tangent readout unavailable; last_message is diagnostic only')

    def publication_status(self):
        current=not self.failed and self.carrier.sequence==self.live_count
        return dict(schema='tangent_publication_v1',execution='quarantined' if self.failed else 'tracking' if self.carrier.tokens else 'acquiring',
                    readout='current' if current else 'unavailable',consumed_records=self._consumed_count if self.failed else self.live_count,
                    published_records=int(self.carrier.sequence),source_id=self.field.source,model_id=self.model_id,configuration_id=self.configuration_id,
                    guarantee='provisional_local_precision',authorization='unresolved',authorization_reason='no_validated_query_enclosure',failure=copy.deepcopy(self.failure))

    def publication(self):
        # A copied last readout is always explicitly labeled, including failure.
        return dict(status=self.publication_status(),message=self.last_message())

    def advance(self,first,rows):
        if self.failed:raise ValueError('tangent arm already unresolved')
        if not isinstance(first,(int,np.integer)) or isinstance(first,(bool,np.bool_)):
            raise ValueError('tangent source/order mismatch')
        first=int(first);self.failure_index=first
        if first!=self.carrier.sequence or first!=self.field.count+self.buffered:
            raise ValueError('tangent source/order mismatch')
        rows=np.ascontiguousarray(rows,dtype=float)
        if rows.ndim!=2 or rows.shape[1]!=5 or not 1<=len(rows)<=16:raise ValueError('finite observation block required')
        if not np.isfinite(rows).all() or np.any(rows[:,0]<0) or np.any(rows[:,0]>1) or np.any(abs(rows[:,1])>.25) or np.any(rows[:,2]<15) or np.any(rows[:,2]>35) or np.any(rows[:,4]<=0):
            raise ValueError('observation support')
        ticks=np.rint(rows[:,0]*self.hz)
        if np.any(abs(ticks/self.hz-rows[:,0])>1e-12):raise ValueError('interval not represented by declared clock')
        if first>2**64-1-len(rows) or self.carrier.tokens==2**64-1 or self.carrier.ticks>2**64-1-int(ticks.sum()):
            raise ValueError('tangent counter range')
        try:return self._advance_admitted(first,rows)
        except Exception as error:
            self._quarantine(error,'advance')
            raise

    def _advance_admitted(self,first,rows):
        if self.buffered+len(rows)>BUFFER_RECORDS:
            # Irregular partial windows crossing the raw batch boundary retain
            # the previous response -> flush -> update transaction ordering.
            if first!=self.native.count or not np.isfinite(rows).all():raise ValueError('invalid observation/source')
            ticks=np.rint(rows[:,0]*self.hz)
            if np.any(abs(ticks/self.hz-rows[:,0])>1e-12):raise ValueError('interval not represented by declared clock')
            state=self.live_state.copy();lifted=np.empty((len(rows),self.field.width));f=self.field
            shape=(f.n,f.m,f.b) if hasattr(f,'m') else (f.n,f.b)
            if f.fn(ptr(rows),len(rows),ptr(f.cal),*shape,ptr(f.rates),ptr(f.p1),ptr(f.p2),ptr(state),ptr(lifted)):
                raise ValueError('response recurrence failed')
            self._flush_field();self.native.update(first,lifted);self.live_state=state
            tick_sum=int(ticks.sum())
        else:
            tick_sum=self.native.step(first,rows,self.live_state,self.hz,
                                      query=(first+len(rows))%self.interval!=0)
        self.pending_rows[self.buffered:self.buffered+len(rows)]=rows;self.buffered+=len(rows)
        self.live_count=first+len(rows)
        self.noise+=float(np.log(rows[:,4]).sum()+len(rows)*.5*math.log(2*math.pi))
        if self.buffered==BUFFER_RECORDS:self._flush_field()
        stop='native_tangent';result=None
        if self.live_count%self.interval==0:
            result=self._refresh('scheduled');stop='tangent_field_refresh' if result is not None else 'tangent_refresh_unresolved'
        if result is None:
            try:result=self.native.query(state=self.live_state,count=self.live_count,reuse=True)
            except ValueError as error:
                result=self._refresh('readout_domain: '+str(error));stop='tangent_domain_refresh'
                if result is None:
                    self.failed=True;raise ValueError('tangent readout and full-field recovery unresolved: '+str(error))
        before_Q=float(self._message_view[5]);before_SOC=float(self._message_view[0])
        self._publish(result,self.live_count,self.carrier.ticks+tick_sum,self.carrier.tokens+1)
        if 'refresh' in stop and stop!='tangent_refresh_unresolved':
            self.audit['max_abs_Q_replacement_percent']=max(self.audit['max_abs_Q_replacement_percent'],abs(100*np.expm1(result['end'][5]-before_Q)))
            self.audit['max_abs_SOC_replacement_pp']=max(self.audit['max_abs_SOC_replacement_pp'],abs(100*(result['end'][0]-before_SOC)))
        read,diagnostic=self.readout(rows);diagnostic['stop']=stop;diagnostic['cost']=result['linearized_cost']
        return read,diagnostic

    def last_message(self):
        """Diagnostic only; may describe an older prefix. Inspect publication_status."""
        return self._message_view.copy()
    def full_message(self):
        self._require_current()
        return self.last_message()
    def readout(self,rows):
        self._require_current()
        self.state=[self.carrier.sequence,self.carrier.sequence,0,self.carrier.tokens,self.carrier.ticks]
        # Shared formatting only; no rolling fitter or Gaussian history is invoked.
        read,diagnostic=CBackend.readout(self,rows)
        read['estimate_status']=self.publication_status()
        return read,diagnostic
    def counts(self):
        consumed=self._consumed_count if self.failed else self.live_count
        return dict(received_records=consumed,retired_records=self.carrier.sequence,
                    pending_records=None if consumed is None else consumed-self.carrier.sequence,tokens=self.carrier.tokens,
                    publication=self.publication_status(),
                    field_history={**self.audit,'accumulated_records':self.field.count,'buffered_records':self.buffered,
                                   'status':'unresolved' if self.failed else 'some_refreshes_unresolved' if self.audit['rejected'] else 'all_refreshes_accepted' if self.audit['accepted'] else 'no_refresh_yet'})
    def storage(self):
        return dict(self.native.storage(),C_context_B=C.sizeof(self.context),experimental_field=self.field.storage(),
                    field_pending_buffer_B=self.pending_rows.nbytes,field_actual_dense_root_B=self.field.root.nbytes,
                    live_transport_copy_B=self.live_state.nbytes,
                    scope='Desktop C/Python integration; Python, QR/solver and caller workspace excluded; not M23-ready')
    def checkpoint_arrays(self):
        self._require_current()
        return dict(root=self.field.root.copy(),state=self.field.state.copy(),live_state=self.live_state.copy(),w=self.w.copy(),
                    pending=self.pending_rows[:self.buffered].copy(),native=self.native.snapshot(),
                    metadata=np.frombuffer(json.dumps(dict(schema='tangent_checkpoint_v2',source_id=self.field.source,model_id=self.model_id,
                        configuration_id=self.configuration_id,hz=self.hz,count=self.field.count,noise=self.field.noise,live_count=self.live_count,
                        ticks=int(self.carrier.ticks),tokens=int(self.carrier.tokens),live_noise=self.noise,audit=self.audit,interval=self.interval,failed=self.failed),allow_nan=False).encode(),dtype=np.uint8))
    def restore_arrays(self,arrays):
        # Restoring private arrays is not a license to reuse a stale publication.
        # Any invalid/partial restore quarantines the backend until a valid restore.
        try:self._restore_arrays(arrays)
        except Exception as error:
            self._quarantine(error,'restore')
            raise

    def _restore_arrays(self,arrays):
        meta=json.loads(arrays['metadata'].tobytes())
        if meta.get('schema')!='tangent_checkpoint_v2' or meta.get('source_id')!=self.field.source or meta.get('model_id')!=self.model_id or meta.get('configuration_id')!=self.configuration_id or meta.get('hz')!=self.hz:
            raise ValueError('tangent checkpoint identity/configuration')
        if meta['interval']!=self.interval or meta['failed']:raise ValueError('tangent checkpoint cadence/status')
        for name in ('count','live_count','ticks','tokens'):
            if type(meta[name]) is not int or not 0<=meta[name]<=2**64-1:raise ValueError('checkpoint counter range')
        if not all(math.isfinite(meta[k]) for k in ('noise','live_noise')):raise ValueError('checkpoint normalizer')
        staged={}
        for name,shape in [('root',self.field.root.shape),('state',self.field.state.shape),('live_state',self.live_state.shape),('w',(16,))]:
            if arrays[name].shape!=shape or not np.isfinite(arrays[name]).all():raise ValueError('tangent checkpoint shape/values')
            staged[name]=np.ascontiguousarray(arrays[name],dtype=float).copy()
        pending=arrays['pending'];buffered=len(pending)
        if pending.shape!=(buffered,5) or buffered>BUFFER_RECORDS or not np.isfinite(pending).all():raise ValueError('tangent pending checkpoint')
        pending=pending.copy()
        if meta['count']+buffered!=meta['live_count'] or meta['live_count']!=self.carrier.sequence:raise ValueError('tangent checkpoint chronology')
        if meta['ticks']!=self.carrier.ticks or meta['tokens']!=self.carrier.tokens:raise ValueError('tangent checkpoint publication counters')
        self.native.restore(arrays['native'],meta['live_count'])
        result=self.native.query(state=staged['live_state'],count=meta['live_count'])
        payload,w=self._publication_payload(result,meta['live_count'],meta['ticks'],meta['tokens'],meta['live_noise'])
        if bytes(payload)!=bytes(self.context) or not np.array_equal(w,staged['w']):raise ValueError('checkpoint readout/native mismatch')
        self.field.root=staged['root'];self.field.state=staged['state'];self.live_state=staged['live_state'];self.w=staged['w']
        self.pending_rows[:buffered]=pending;self.buffered=buffered
        self.field.count=meta['count'];self.field.noise=meta['noise'];self.noise=meta['live_noise'];self.live_count=meta['live_count'];self.audit=meta['audit']
        self._consumed_count=self.live_count;self.failure=None;self.failed=False
