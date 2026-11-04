"""Desktop original-origin tangent for N13e; dense reference, no rolling feedback."""
import ctypes as C
import json
import math
import numpy as np
from .tangent_backend import TangentBackend,Carrier
from .distinct_backend import prepare_distinct
from .coordinates import prior
from .rate import clock_hz
from .backend import CBackend
from specifications.evidence_feedback_001.protocol import digest
from experiments.distinct_bank_integration_001.field import DistinctBankField,Compressed
from experiments.foster_uncertainty_audit_001.conditional_packet import partition
from experiments.slow_likelihood_diagnostic_001.numerics import solve

class Projection:
    def __init__(self,owner):self.o=owner;self.initialize(np.zeros(16))
    @property
    def count(self):return self.o.field.count
    def initialize(self,w):
        o=self.o;self.anchor=w.copy();x=o.mean+o.prior_root@w
        self.phi=o.field.features(x);self.J=o.field.features_jacobian(x)@o.prior_root
        self.factor=np.linalg.qr(np.vstack((np.c_[np.eye(16),w],np.c_[o.field.root@self.J,o.field.root@self.phi])),mode='r')
    def update(self,rows):self.factor=np.linalg.qr(np.vstack((self.factor,np.c_[rows@self.J,rows@self.phi])),mode='r')
    def query(self):
        o=self.o;R=self.factor[:16,:16];step=-np.linalg.solve(R,self.factor[:16,16]);w=self.anchor+step
        x=o.mean+o.prior_root@w;end,D=o.field.transported(x)
        return dict(w=w,end=end,endpoint_root=D@o.prior_root@np.linalg.solve(R,np.eye(16)),linearized_cost=float(.5*self.factor[16,16]**2),logdet_precision=float(2*np.log(abs(np.diag(R))).sum()))
    def snapshot(self):return np.r_[self.anchor,self.factor.ravel()]
    def restore(self,a):
        self.initialize(a[:16]);self.factor=a[16:].reshape(17,17).copy()

class BankTangentBackend(TangentBackend):
    def __init__(self,campaign,config,source,model_id,rate,settings):
        self.config=config;self.hz=clock_hz(rate);self.failure_index=0;self.failed=False;self.failure=None;self._consumed_count=0
        self.model_id=str(model_id);self.mean,self.prior_root=prior(config)
        rc,h,m=prepare_distinct(campaign)
        self.field=DistinctBankField(config,partition(self.mean)[1],rc.resolve(),h.resolve(),m,source)
        self.objective=Compressed(self.field,self.mean,self.prior_root)
        self.interval=max(16,math.ceil(settings.field_refresh_seconds*rate/16)*16)
        self.configuration_id=digest(dict(config=config,hz=self.hz,interval=self.interval,map=self.field.map.sha256,kind='bank_tangent_v1'))
        self.context=C.create_string_buffer(C.sizeof(Carrier));self.carrier=Carrier.from_buffer(self.context)
        self._message_view=np.ctypeslib.as_array(self.carrier.message);self.diag=np.zeros(7)
        self.buffered=0;self.live_count=0;self.noise=0.;self.w=np.zeros(16)
        self.audit=dict(attempts=0,accepted=0,rejected=0,last_rejection=None,last_attempt_record=0,last_accepted_record=0)
        self.native=Projection(self);self._publish(self.native.query(),0,0,0)
    def advance(self,first,rows):
        if np.asarray(rows).ndim==2 and np.any(np.asarray(rows)[:,2]!=25.):raise ValueError('bank tangent requires25C')
        return super().advance(first,rows)
    def _advance_admitted(self,first,rows):
        lifted=self.field.update(first,rows,return_rows=True);self.native.update(lifted)
        self.live_count=self.field.count;self.noise=self.field.noise;stop='bank_tangent'
        if self.live_count%self.interval==0:
            self.audit['attempts']+=1;self.audit['last_attempt_record']=self.live_count;saved=self.native.snapshot()
            try:
                fit=solve(self.objective,start=self.w)
                if fit['diagnostic']['stop'] not in ('gradient','GN_decrement_at_cost_roundoff'):raise ValueError(fit['diagnostic']['stop'])
                self.native.initialize(fit['w']);self.native.query();self.audit['accepted']+=1;self.audit['last_accepted_record']=self.live_count;stop='bank_tangent_refresh'
            except (ValueError,np.linalg.LinAlgError,OverflowError) as e:
                self.native.restore(saved);self.audit['rejected']+=1;self.audit['last_rejection']=dict(record=self.live_count,reason=str(e));stop='bank_tangent_refresh_unresolved'
        result=self.native.query();self._publish(result,self.live_count,self.carrier.ticks+int(np.rint(rows[:,0]*self.hz).sum()),self.carrier.tokens+1)
        r,d=self.readout(rows);d['stop']=stop;return r,d
    def storage(self):return dict(C_context_B=C.sizeof(self.context),experimental_field=self.field.storage(),tangent_dense_factor_B=17*17*8,tangent_derivative_cache_B=self.native.J.nbytes,scope='Dense desktop reference; QR every block; not speed or M23 qualified')
    def checkpoint_arrays(self):
        self._require_current()
        return dict(root=self.field.root.copy(),state=self.field.state.copy(),free=self.field.rc_free.copy(),forced=self.field.rc_forced.copy(),projection=self.native.snapshot(),metadata=np.frombuffer(json.dumps(dict(configuration=self.configuration_id,source=self.field.source,model=self.model_id,count=self.live_count,noise=self.noise,audit=self.audit)).encode(),dtype=np.uint8))
    def restore_arrays(self,a):
        try:
            m=json.loads(a['metadata'].tobytes())
            if (m['configuration'],m['source'],m['model'],m['count'])!=(self.configuration_id,self.field.source,self.model_id,self.carrier.sequence):raise ValueError('bank tangent checkpoint identity')
            for k,shape in dict(root=(94,94),state=self.field.state.shape,free=(3,13),forced=(3,13),projection=(305,)).items():
                if a[k].shape!=shape or not np.isfinite(a[k]).all():raise ValueError('bank tangent checkpoint arrays')
            if not math.isfinite(m['noise']):raise ValueError('normalizer')
            self.field.root=a['root'].copy();self.field._commit(a['state'].copy(),a['free'].copy(),a['forced'].copy(),m['count'],m['noise'])
            self.live_count=m['count'];self.noise=m['noise'];self.audit=m['audit'];self.native.restore(a['projection'])
            result=self.native.query();payload,w=self._publication_payload(result,self.live_count,self.carrier.ticks,self.carrier.tokens,self.noise)
            if bytes(payload)!=bytes(self.context):raise ValueError('checkpoint readout mismatch')
            self.w=w;self.failed=False;self.failure=None
        except Exception as e:self._quarantine(e,'restore');raise
