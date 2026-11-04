"""Native rowwise solver/scalar readout with a host covariance adapter for plots."""
import ctypes as C
import numpy as np
from experiments.bank_memory_001.backend import SmallBackend
from specifications.evidence_feedback_001.protocol import digest
from .native import Native
class RowwiseBackend(SmallBackend):
 def __init__(self,*args):
  super().__init__(*args)
  settings=args[-1]
  if getattr(settings,'rowwise_implementation','baseline')=='sram':
   from experiments.sram_size_001.native import Native as SRAM
   self.native=SRAM(self.field,self.mean,self.prior_root,args[0]/'backend_sram',settings.sram_math,settings.sram_map,True,settings.sram_history_bits)
   self.configuration_id=digest(dict(parent=self.configuration_id,kind='sram_stream_rank3_v1',math=settings.sram_math,map=settings.sram_map,history_bits=settings.sram_history_bits,sources=self.native.build_identity['configuration']['sources'],binary=self.native.build_identity['binary_sha256']))
  else:
   self.native=Native(self.field,self.mean,self.prior_root,args[0]/'backend_rowwise')
   self.configuration_id=digest(dict(parent=self.configuration_id,kind='native_rowwise_rank3_v1'))
  self.native.initialize(np.zeros(16))
  self._publish(self.native.query(),0,0,0)
 def _advance_admitted(self,first,rows):
  if hasattr(self.native,'advance'):self.native.advance(first,rows)
  else:
   lifted=self.field.update(first,rows,return_rows=True);self.native.update(lifted)
  self.live_count=self.field.count;self.noise=self.field.noise;stop='rowwise_bank'
  if self.live_count%self.interval==0:
   self.audit['attempts']+=1;self.audit['last_attempt_record']=self.live_count
   try:
    fit=self.native.fit(self.w)
    if fit['diagnostic']['stop'] not in ('gradient','GN_decrement_at_cost_roundoff'):raise ValueError(fit['diagnostic']['stop'])
    # Validate readout before changing committed tangent anchor. A failed refresh
    # rebuilds old-anchor likelihood from history; no duplicate factor retained.
    candidate=fit['w'];old=self.native.anchor.copy()
    self.native.initialize(candidate)
    try:self.native.query()
    except Exception:
     self.native.anchor[:]=old
     raise
    self.audit['accepted']+=1;self.audit['last_accepted_record']=self.live_count;stop='rowwise_bank_refresh'
   except (ValueError,np.linalg.LinAlgError,OverflowError) as e:
    self.native.initialize(self.native.anchor.copy());self.audit['rejected']+=1
    self.audit['last_rejection']=dict(record=self.live_count,reason=str(e));stop='rowwise_bank_refresh_unresolved'
  result=self.native.query();self._publish(result,self.live_count,self.carrier.ticks+int(np.rint(rows[:,0]*self.hz).sum()),self.carrier.tokens+1)
  r,d=self.readout(rows);d['stop']=stop;return r,d
 def storage(self):
  return dict(native_inference_context_B=C.sizeof(self.native.context),packed_history_B=self.field.packed.values.nbytes,
   native_context_plus_history_B=C.sizeof(self.native.context)+self.field.packed.values.nbytes,
   response_B=744 if hasattr(self.native,'advance') else self.field.storage()['response_B'],prior_mean_scale_B=256,
   host_carrier_B=C.sizeof(self.context),host_covariance_adapter=True,
   scope=('Native stationary sample/QR/solver/scalar path; host owns normalization, ownership, scheduling, full covariance plots and checkpoints. Not complete firmware SRAM.' if hasattr(self.native,'advance') else 'Native solver/scalar interface integrated; host owns response generation and full covariance plots/checkpoints. Not complete firmware SRAM.'))
