"""Semantic state identities for old/new tangent comparisons (scratch excluded)."""
import ctypes as C
import hashlib
import json
import numpy as np


def identity(path):
    b=path.read_bytes();return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())


def save(path,value):
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def capture(bank):
    return dict(context=np.frombuffer(bytes(bank.context),dtype=np.uint8).copy(),
                **{k:v.copy() for k,v in bank.checkpoint_arrays().items()})


def restore(bank,saved):
    if len(saved['context'])!=C.sizeof(bank.context):raise ValueError('carrier ABI changed')
    C.memmove(bank.context,saved['context'].tobytes(),len(saved['context']))
    bank.restore_arrays({k:v.copy() for k,v in saved.items() if k!='context'})
    bank.failed=False


def digest(bank):
    h=hashlib.sha256()
    for key,value in sorted(capture(bank).items()):
        h.update(json.dumps([key,value.dtype.str,value.shape]).encode());h.update(value.tobytes())
    return h.hexdigest()


def exported(prefix):
    metadata=json.loads((prefix/'initial_estimator_state.json').read_text())
    if identity(prefix/'initial_estimator_state.npz')!=metadata['payload']:
        raise ValueError('derived state export checksum mismatch')
    with np.load(prefix/'initial_estimator_state.npz',allow_pickle=False) as data:
        saved={k.split('__',1)[1]:data[k].copy() for k in data.files
               if k.startswith('tangent64__') and '__public_prior_' not in k}
        mean=data['tangent64__public_prior_mean'].copy();root=data['tangent64__public_prior_root'].copy()
    binding=json.loads((prefix/'binding_parity.json').read_text())
    if identity(prefix/'observations.npy')!=binding['observation_identity']:
        raise ValueError('owned observations changed')
    return metadata,saved,mean,root


def stats(values):
    a=np.asarray(values)
    return dict(count=len(a),total_s=float(a.sum()),mean_us=float(a.mean()*1e6),
                median_us=float(np.median(a)*1e6),p95_us=float(np.quantile(a,.95)*1e6),
                p99_us=float(np.quantile(a,.99)*1e6),maximum_ms=float(a.max()*1e3))
