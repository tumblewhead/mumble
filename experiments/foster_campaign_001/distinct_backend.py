"""Opt-in stationary N13e history refreshes of the existing C rolling estimator.

Only public calibration and ordered V/I/T observations enter this backend.
Same-prefix joint replacements use the original prior once. This is the W94
desktop comparator, with TaylorH2 and provisional local uncertainty, not firmware.
"""
import copy
import ctypes as C
import json
import math
import shutil
import numpy as np
from specifications.evidence_feedback_001.protocol import digest
from .backend import CBackend, ROOT, identity
from .field_backend import FieldBackend, BUFFER_RECORDS
from experiments.distinct_bank_integration_001.field import DistinctBankField, Compressed
from experiments.foster_uncertainty_audit_001.conditional_packet import partition
from experiments.rc_sensitivity_basis_001.basis import build as build_rc
from experiments.hysteresis_sensitivity_basis_001.basis import build as build_h

MAP = 'experiments/distinct_bank_integration_001/map_n13e.json'
DEPENDENCIES = [
    'experiments/foster_campaign_001/bank_tangent_backend.py',
    'experiments/foster_campaign_001/tangent_backend.py',
    'experiments/foster_campaign_001/distinct_backend.py',
    'experiments/distinct_bank_integration_001/field.py', MAP,
    'experiments/rc_sensitivity_basis_001/basis.py',
    'experiments/rc_sensitivity_basis_001/response.c',
    'experiments/hysteresis_sensitivity_basis_001/basis.py',
    'experiments/hysteresis_sensitivity_basis_001/response.c',
    'experiments/response_basis_attribution_001/basis.py',
    'experiments/hysteresis_refinement_001/field.py',
    'experiments/joint_rate_history_001/field.py',
    'experiments/slow_likelihood_diagnostic_001/numerics.py',
    'experiments/foster_uncertainty_audit_001/conditional_packet.py',
    'experiments/foster_feedback_001/estimator.py',
    'experiments/foster_c_baseline_001/reference.py',
]


def prepare_distinct(campaign):
    directory = campaign/'backend_distinct'
    receipt = directory/'build.json'
    paths = (directory/'rc/response.so', directory/'h/response.so', directory/'map_n13e.json')
    sources = {name: identity(ROOT/name) for name in DEPENDENCIES}
    if receipt.exists():
        info = json.loads(receipt.read_text())
        if info['sources'] != sources or info['artifacts'] != {str(p.relative_to(directory)): identity(p) for p in paths}:
            raise ValueError('distinct-bank source/map/binary mismatch')
        return paths
    directory.mkdir(exist_ok=False)
    for name in DEPENDENCIES:
        target = directory/'source_snapshot'/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT/name, target)
        if identity(target) != sources[name]:raise ValueError('source changed while snapshotting')
    shutil.copy2(ROOT/MAP, paths[2])
    build_rc(directory/'rc', 'taylor2')
    build_h(directory/'h', 'derivative')
    if sources != {name: identity(ROOT/name) for name in DEPENDENCIES}:
        raise ValueError('source changed during bank build')
    receipt.write_text(json.dumps(dict(schema='distinct_campaign_build_v1', sources=sources,
        artifacts={str(p.relative_to(directory)): identity(p) for p in paths},
        scope='Stationary25C; N13e supplied NUM; TaylorH2; no coverage or M23 qualification'), indent=2)+'\n')
    return paths


class DistinctBackend(FieldBackend):
    def _make_field(self, campaign, config, source):
        rc, h, bank_map = prepare_distinct(campaign)
        return DistinctBankField(config, partition(self.mean)[1], rc.resolve(), h.resolve(), bank_map, source)

    def _make_objective(self):
        return Compressed(self.field, self.mean, self.prior_root)

    def _transport(self, x):
        return self.field.transported(x)

    def _flush_field(self):
        # The native response kernel accepts at most1024 rows. Keep its original
        # bound, and retire the pending stream in chronological chunks.
        for begin in range(0, self.buffered, 1024):
            self.field.update(self.field.count, self.pending_rows[begin:min(begin+1024,self.buffered)])
        self.buffered = 0

    def advance(self, first, rows):
        rows = np.ascontiguousarray(rows, dtype=float)
        if (isinstance(first, (bool, np.bool_)) or not isinstance(first, (int,np.integer)) or
                first != self.field.count+self.buffered or rows.ndim != 2 or
                rows.shape[1] != 5 or not 1 <= len(rows) <= 16 or
                not np.isfinite(rows).all() or np.any(rows[:,0] < 0) or
                np.any(rows[:,2] != 25.) or np.any(rows[:,4] <= 0)):
            raise ValueError('distinct-bank requires ordered finite rows, dt>=0, sigma>0 and T=25C')
        # C may fail partway through a window, or a later QR may fail. Restore
        # both owners on failure. Full field backup is needed only on flushes.
        context = bytes(self.context)
        buffered = self.buffered
        boundary = buffered+len(rows)>=BUFFER_RECORDS or (first+len(rows))%self.interval==0
        saved = self.checkpoint_arrays() if boundary else None
        try:
            return super().advance(first, rows)
        except Exception:
            C.memmove(self.context, context, len(context))
            if saved is not None:self.restore_arrays(saved)
            else:self.buffered=buffered
            raise

    def _binding(self):
        return dict(schema='distinct_campaign_checkpoint_v1', source=self.field.source,
                    map_sha256=self.field.map.sha256, config=digest(self.config),
                    center=self.field.center.tolist(), interval=self.interval, width=self.field.width)

    def checkpoint_arrays(self):
        return dict(root=self.field.root.copy(), state=self.field.state.copy(),
                    rc_free=self.field.rc_free.copy(), rc_forced=self.field.rc_forced.copy(),
                    w=self.w.copy(), pending=self.pending_rows[:self.buffered].copy(),
                    metadata=np.frombuffer(json.dumps(dict(binding=self._binding(),
                        count=self.field.count, noise=self.field.noise, audit=self.audit),
                        allow_nan=False).encode(),dtype=np.uint8).copy())

    def restore_arrays(self, arrays):
        meta=json.loads(arrays['metadata'].tobytes())
        if meta['binding']!=self._binding():raise ValueError('bank checkpoint identity/configuration mismatch')
        shapes=dict(root=self.field.root.shape, state=self.field.state.shape,
                    rc_free=(3,13), rc_forced=(3,13), w=(16,))
        staged={}
        for name,shape in shapes.items():
            value=np.array(arrays[name],dtype=float,copy=True)
            if value.shape!=shape or not np.isfinite(value).all():raise ValueError('bank checkpoint shape/values')
            staged[name]=value
        pending=np.array(arrays['pending'],dtype=float,copy=True)
        count=meta['count'];noise=meta['noise']
        if (type(count) is not int or count<0 or not math.isfinite(noise) or
                pending.ndim!=2 or pending.shape[1]!=5 or len(pending)>BUFFER_RECORDS or
                not np.isfinite(pending).all() or np.any(pending[:,0]<0) or
                np.any(pending[:,2]!=25.) or np.any(pending[:,4]<=0) or
                count+len(pending)!=CBackend.counts(self)['retired_records']):
            raise ValueError('bank checkpoint chronology/rows')
        audit=copy.deepcopy(meta['audit'])
        self.field.root=staged['root']
        self.field._commit(staged['state'],staged['rc_free'],staged['rc_forced'],count,noise)
        self.w=staged['w'];self.buffered=len(pending)
        self.pending_rows[:self.buffered]=pending;self.audit=audit

    def counts(self):
        result=super().counts()
        result['field_history'].update(representation='N13e_RC_TaylorH2',
            uncertainty='provisional local Gaussian; deterministic bias floor not implemented',
            stationary_temperature_C=25, lifetime_qualified=False)
        return result

    def storage(self):
        result=super().storage()
        result['bank_transaction_backup_max_B']=C.sizeof(self.context)+self.field.root.nbytes+self.field.storage()['live_response_B']+self.w.nbytes+self.pending_rows.nbytes
        result['scope']='Overbudget Python/C desktop comparator; includes C rolling carrier and bank; no M23 size or timing qualification'
        return result
