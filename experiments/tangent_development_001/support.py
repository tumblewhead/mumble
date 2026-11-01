"""Study ownership, profiling and memory accounting; imported after replay binding."""
import copy
import ctypes as C
import hashlib
import json
import sys
import time
from collections import defaultdict
from contextlib import ExitStack
from unittest.mock import patch
import numpy as np


ARMS = ('field64', 'tangent64')


def identity(path):
    return dict(bytes=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')


def capture(bank):
    return dict(context=np.frombuffer(bytes(bank.context), dtype=np.uint8).copy(),
                **{k: v.copy() for k, v in bank.checkpoint_arrays().items()})


def restore(bank, saved):
    if len(saved['context']) != C.sizeof(bank.context):
        raise ValueError('derived export context size mismatch')
    C.memmove(bank.context, saved['context'].tobytes(), len(saved['context']))
    bank.restore_arrays({k: v.copy() for k, v in saved.items() if k != 'context'})
    if hasattr(bank, 'failed'):
        bank.failed = False  # restore_arrays accepts only a nonfailed checkpoint
    bank.failure_index = bank.counts()['retired_records']
    bank.objective.calls = 0


def same_arrays(a, b):
    return a.keys() == b.keys() and all(np.array_equal(a[k], b[k]) for k in a)


def geometry(bank):
    """Decode the bound native ABI; verify against native readout before use."""
    from experiments.foster_campaign_001.field_backend import transported
    class Context(C.Structure):
        _fields_ = [('factor', C.c_double*153), ('anchor', C.c_double*16),
                    ('source', C.c_uint64), ('count', C.c_uint64), ('magic', C.c_uint64)]
    raw = bank.native.snapshot()
    if len(raw) != C.sizeof(Context):
        raise ValueError('unrecognized tangent context ABI')
    context = Context.from_buffer_copy(raw)
    factor = np.zeros((17, 17))
    factor[np.triu_indices(17)] = np.array(context.factor)
    w = np.array(context.anchor)-np.linalg.solve(factor[:16, :16], factor[:16, 16])
    mean = bank.mean+bank.prior_root@w
    root = bank.prior_root@np.linalg.solve(factor[:16, :16], np.eye(16))
    field = copy.copy(bank.field)
    field.state = bank.live_state.copy()
    end, D = transported(field, mean)
    published = bank.full_message()
    # Registered arithmetic-order tolerance; no fitting or tolerance adaptation.
    if not np.allclose(end, published[:16], atol=2e-11, rtol=2e-11):
        raise ValueError('original-coordinate mean differs from native readout')
    native_root = published[16:272].reshape(16, 16)
    if not np.allclose(D@root@(D@root).T, native_root@native_root.T, atol=2e-11, rtol=2e-9):
        raise ValueError('original-coordinate covariance differs from native readout')
    return mean, root, lambda x: transported(field, x)


def distribution(values):
    a = np.asarray(values, dtype=float)
    if not len(a):
        return dict(count=0)
    return dict(count=len(a), total=float(a.sum()), mean=float(a.mean()),
                median=float(np.median(a)), p95=float(np.quantile(a, .95)),
                p99=float(np.quantile(a, .99)), maximum=float(a.max()))


class Phases:
    """Nested inclusive/exclusive wall timings. Patches exist only in this worker."""
    def __init__(self):
        self.times = defaultdict(list)
        self.exclusive = defaultdict(list)
        self.stack = []
        self.solves = []
        self.qr_shapes = defaultdict(int)

    def wrap(self, fn, label):
        def wrapped(*args, **kwargs):
            if label == 'field_qr':
                self.qr_shapes[str(np.shape(args[0]))] += 1
            self.stack.append(0.)
            begin = time.perf_counter()
            try:
                result = fn(*args, **kwargs)
                if label == 'full_solve':
                    self.solves.append(result['diagnostic'])
                return result
            finally:
                elapsed = time.perf_counter()-begin
                child = self.stack.pop()
                self.times[label].append(elapsed)
                self.exclusive[label].append(elapsed-child)
                if self.stack:
                    self.stack[-1] += elapsed
        return wrapped

    def instrument(self, bank):
        from experiments.foster_campaign_001 import field_backend, tangent_backend
        stack = ExitStack()
        def bind(obj, attr, label):
            stack.enter_context(patch.object(obj, attr, self.wrap(getattr(obj, attr), label)))
        bind(bank, 'advance', 'advance')
        bind(bank, 'readout', 'formatted_readout')
        bind(bank, '_flush_field', 'field_flush')
        bind(bank.field, 'update', 'field_update')
        bind(bank.field, 'fn', 'response_recurrence')
        bind(np.linalg, 'qr', 'field_qr')
        bind(field_backend, 'solve', 'full_solve')
        bind(tangent_backend, 'solve', 'full_solve')
        if hasattr(bank, 'native'):
            for name in ('update', 'query', 'initialize'):
                bind(bank.native, name, 'native_'+name)
            bind(bank, '_refresh', 'refresh')
        else:
            bind(bank, '_replace', 'refresh')
            bind(bank.lib, 'campaign_block', 'rolling_C_block')
            bind(field_backend, 'transported', 'mean_joint_transport')
        return stack

    def report(self):
        return dict(inclusive_seconds={k: distribution(v) for k, v in self.times.items()},
                    exclusive_seconds={k: distribution(v) for k, v in self.exclusive.items()},
                    qr_shapes_and_calls=dict(self.qr_shapes), full_solve_diagnostics=self.solves,
                    scope='Inclusive times overlap; exclusive times partition wrapped calls including wrapper overhead. Native query combines transport/covariance; no invented split.')


def c_profile(bank):
    if hasattr(bank, 'native'):
        return {}
    from experiments.foster_c_baseline_001.reference import Profile
    p = Profile()
    bank.lib.fb_get_profile(bank.context, C.byref(p))
    return {k: list(getattr(p, k)) if k == 'stops' else getattr(p, k) for k, _ in p._fields_}


def profile_delta(a, b):
    return {k: ([x-y for x, y in zip(b[k], a[k])] if isinstance(b[k], list) else b[k]-a[k]) for k in b}


def memory(bank):
    """Reachable Python/NumPy/ctypes census, deduplicating shared allocations.

    Unknown native transient/stack storage remains explicit, not reported as 0.
    Raw views follow their owner to avoid counting an aliased carrier twice.
    """
    seen, items = set(), []
    def walk(value, name):
        if id(value) in seen:
            return
        seen.add(id(value))
        if isinstance(value, np.ndarray):
            if value.base is not None:
                walk(value.base, name+'.base')
            items.append(dict(path=name, kind='numpy_owned' if value.base is None else 'numpy_view',
                              bytes=sys.getsizeof(value), numeric_payload_B=value.nbytes if value.base is None else 0))
        elif isinstance(value, (C.Array, C.Structure)):
            if getattr(value, '_b_base_', None) is not None:
                walk(value._b_base_, name+'.owner')
            # ctypes from_buffer exposes owner through _objects, not _b_base_.
            if getattr(value, '_objects', None):
                walk(value._objects, name+'._objects')
            items.append(dict(path=name, kind='ctypes', bytes=sys.getsizeof(value),
                              numeric_payload_B=C.sizeof(value) if getattr(value, '_b_needsfree_', False) else 0))
        elif isinstance(value, memoryview):
            walk(value.obj, name+'.owner')
        elif isinstance(value, dict):
            items.append(dict(path=name, kind='dict', bytes=sys.getsizeof(value), numeric_payload_B=0))
            for k, v in value.items():
                walk(v, name+'.'+str(k))
        elif isinstance(value, (tuple, list)):
            items.append(dict(path=name, kind='sequence', bytes=sys.getsizeof(value), numeric_payload_B=0))
            for j, v in enumerate(value):
                walk(v, name+'.'+str(j))
        elif hasattr(value, '__dict__') and type(value).__module__.startswith('experiments.'):
            items.append(dict(path=name, kind='object', bytes=sys.getsizeof(value), numeric_payload_B=0))
            walk(vars(value), name)
        elif isinstance(value, (str, int, float, bool, bytes, type(None))):
            items.append(dict(path=name, kind='scalar', bytes=sys.getsizeof(value), numeric_payload_B=0))
    walk(bank, 'bank')
    return dict(items=items, reported_backend_storage=bank.storage(),
                reachable_python_getsizeof_sum_B=sum(i['bytes'] for i in items),
                owned_numeric_payload_B=sum(i['numeric_payload_B'] for i in items),
                target_factor_only_B=dict(float64=27224, float32=13612),
                unknown=['native LAPACK allocations', 'nested C and libm stack', 'allocator overhead and shared libraries',
                         'complete target solver workspace and scheduling', 'ARM instruction cycles'],
                scope='Host reachable object census, not whole-process RSS or a whole-system SRAM bound. Numeric payload overlaps getsizeof for owned NumPy arrays; do not add totals.')
