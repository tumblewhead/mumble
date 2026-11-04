"""Opt-in projected likelihood with full bank physical transport retained."""
import numpy as np
from specifications.evidence_feedback_001.protocol import digest
from experiments.foster_campaign_001.bank_tangent_backend import BankTangentBackend,Projection
from experiments.foster_campaign_001.distinct_backend import prepare_distinct
from experiments.distinct_bank_integration_001.field import Compressed
from .field import SmallField,Packed

class LeanProjection(Projection):
    @property
    def J(self):return self.o.field.features_jacobian(self.o.mean+self.o.prior_root@self.anchor)@self.o.prior_root
    @property
    def factor(self):return self.packed.dense()
    @factor.setter
    def factor(self,a):self.packed.values[:]=a[np.triu_indices(17)]
    def initialize(self,w):
        o=self.o
        if not hasattr(self,'packed'):self.packed=Packed(17,o.kernel_directory,'float64')
        self.anchor=w.copy();self.phi=o.field.features(o.mean+o.prior_root@w)
        J=self.J;self.factor=np.linalg.qr(np.vstack((np.c_[np.eye(16),w],np.c_[o.field.root@J,o.field.root@self.phi])),mode='r')
    def update(self,rows):self.packed.update(np.c_[rows@self.J,rows@self.phi])

class SmallBackend(BankTangentBackend):
    def __init__(self,campaign,config,source,model_id,rate,settings):
        super().__init__(campaign,config,source,model_id,rate,settings)
        rc,h,m=prepare_distinct(campaign);self.kernel_directory=campaign/'backend_small'
        self.field=SmallField(config,self.field.center,rc.resolve(),h.resolve(),m,source,self.kernel_directory,settings.bank_rank,settings.bank_precision,self.mean if settings.bank_center else None)
        self.objective=Compressed(self.field,self.mean,self.prior_root);self.native=LeanProjection(self)
        self.configuration_id=digest(dict(parent=self.configuration_id,rank=settings.bank_rank,precision=settings.bank_precision,center=settings.bank_center,projection=digest(dict(V=self.field.V.tolist(),P=self.field.P.tolist()))))
        self._publish(self.native.query(),0,0,0)
    def storage(self):
        import ctypes as C
        objects=[self,self.field,self.field.base,self.field.base.legacy,self.field.base.map,self.field.packed,self.native,self.native.packed,self.objective]
        arrays={}
        for obj in objects:
            for v in vars(obj).values():
                if isinstance(v,np.ndarray) and not np.shares_memory(v,self._message_view):
                    while isinstance(v.base,np.ndarray):v=v.base
                    arrays[id(v)]=v
        return dict(actual_retained_numpy_B=sum(v.nbytes for v in arrays.values()),
            actual_resident_numeric_B=sum(v.nbytes for v in arrays.values())+C.sizeof(self.context),
            resident_scope='Includes host projection/map arrays and carrier; excludes Python/library objects and transient query/solver workspace',
            C_context_B=C.sizeof(self.context),prior_mean_and_root_B=self.mean.nbytes+self.prior_root.nbytes,
            experimental_field=self.field.storage(),tangent_packed_factor_B=self.native.packed.values.nbytes,
            tangent_derivative_cache_B=0,anchor_B=self.native.anchor.nbytes,features_B=self.native.phi.nbytes,
            scope='Reduced history reference; dense query/solver/prior remain host allocations, not a complete10KiB estimator')
