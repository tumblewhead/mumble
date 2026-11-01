"""Opt-in original-origin tangent updates with periodic full-field relinearization.

Only public prior/calibration and ordered observations enter this backend. The
outgoing Gaussian is a readout, never a new prior. Stationary-parameter experiment.
"""
import ctypes as C
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
        self.mean,self.prior_root=prior(config)
        self.field=self._make_field(campaign,config,source)
        self.live_state=self.field.state.copy();self.live_count=0;self.noise=0.
        self.native=self._make_native(campaign)
        self.native.prepare_step()
        self.objective=self._make_objective()
        self.interval=max(16,math.ceil(settings.field_refresh_seconds*rate/16)*16)
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
            self.field.update(self.field.count,self.pending_rows[:self.buffered]);self.buffered=0
            if not np.array_equal(self.field.state,self.live_state):raise ValueError('live/batched state transport mismatch')

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

    def _publish(self,result,sequence,ticks):
        logZ=-result['linearized_cost']-self.noise-.5*result['logdet_precision']
        if not np.isfinite(result['end']).all() or not np.isfinite(result['endpoint_root']).all() or not math.isfinite(logZ):
            raise ValueError('nonfinite tangent readout')
        message=self._message_view
        message[:16]=result['end'];message[16:272]=result['endpoint_root'].ravel()
        message[272]=logZ
        self.carrier.sequence=sequence;self.carrier.ticks=ticks
        self.w[:]=result['w']

    def advance(self,first,rows):
        self.failure_index=first
        if self.failed:raise ValueError('tangent arm already unresolved')
        if first!=self.carrier.sequence or first!=self.field.count+self.buffered:
            raise ValueError('tangent source/order mismatch')
        rows=np.ascontiguousarray(rows,dtype=float)
        if rows.ndim!=2 or rows.shape[1]!=5 or not 1<=len(rows)<=16:raise ValueError('finite observation block required')
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
        self._publish(result,self.live_count,self.carrier.ticks+tick_sum);self.carrier.tokens+=1
        if 'refresh' in stop and stop!='tangent_refresh_unresolved':
            self.audit['max_abs_Q_replacement_percent']=max(self.audit['max_abs_Q_replacement_percent'],abs(100*np.expm1(result['end'][5]-before_Q)))
            self.audit['max_abs_SOC_replacement_pp']=max(self.audit['max_abs_SOC_replacement_pp'],abs(100*(result['end'][0]-before_SOC)))
        read,diagnostic=self.readout(rows);diagnostic['stop']=stop;diagnostic['cost']=result['linearized_cost']
        return read,diagnostic

    def full_message(self):return self._message_view.copy()
    def readout(self,rows):
        self.state=[self.carrier.sequence,self.carrier.sequence,0,self.carrier.tokens,self.carrier.ticks]
        # Shared formatting only; no rolling fitter or Gaussian history is invoked.
        return CBackend.readout(self,rows)
    def counts(self):
        return dict(received_records=self.live_count,retired_records=self.carrier.sequence,
                    pending_records=self.live_count-self.carrier.sequence,tokens=self.carrier.tokens,
                    field_history={**self.audit,'accumulated_records':self.field.count,'buffered_records':self.buffered,
                                   'status':'unresolved' if self.failed else 'some_refreshes_unresolved' if self.audit['rejected'] else 'all_refreshes_accepted' if self.audit['accepted'] else 'no_refresh_yet'})
    def storage(self):
        return dict(self.native.storage(),C_context_B=C.sizeof(self.context),experimental_field=self.field.storage(),
                    field_pending_buffer_B=self.pending_rows.nbytes,field_actual_dense_root_B=self.field.root.nbytes,
                    live_transport_copy_B=self.live_state.nbytes,
                    scope='Desktop C/Python integration; Python, QR/solver and caller workspace excluded; not M23-ready')
    def checkpoint_arrays(self):
        return dict(root=self.field.root,state=self.field.state,live_state=self.live_state,w=self.w,
                    pending=self.pending_rows[:self.buffered].copy(),native=self.native.snapshot(),
                    metadata=np.frombuffer(json.dumps(dict(count=self.field.count,noise=self.field.noise,live_count=self.live_count,
                        live_noise=self.noise,audit=self.audit,interval=self.interval,failed=self.failed)).encode(),dtype=np.uint8))
    def restore_arrays(self,arrays):
        meta=json.loads(arrays['metadata'].tobytes())
        if meta['interval']!=self.interval or meta['failed']:raise ValueError('tangent checkpoint cadence/status')
        for name,shape in [('root',self.field.root.shape),('state',self.field.state.shape),('live_state',self.live_state.shape),('w',(16,))]:
            if arrays[name].shape!=shape or not np.isfinite(arrays[name]).all():raise ValueError('tangent checkpoint shape/values')
        pending=arrays['pending'];buffered=len(pending)
        if pending.shape!=(buffered,5) or buffered>BUFFER_RECORDS or not np.isfinite(pending).all():raise ValueError('tangent pending checkpoint')
        if meta['count']+buffered!=meta['live_count'] or meta['live_count']!=self.carrier.sequence:raise ValueError('tangent checkpoint chronology')
        self.native.restore(arrays['native'],meta['live_count'])
        self.field.root=arrays['root'].copy();self.field.state=arrays['state'].copy();self.live_state=arrays['live_state'].copy();self.w=arrays['w'].copy()
        self.pending_rows[:buffered]=pending;self.buffered=buffered
        self.field.count=meta['count'];self.field.noise=meta['noise'];self.noise=meta['live_noise'];self.live_count=meta['live_count'];self.audit=meta['audit']
        if not np.isfinite(self.full_message()).all():raise ValueError('nonfinite checkpoint readout')
