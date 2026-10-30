"""Independent finite oracles and lifecycle checks; no battery inference."""
import argparse
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import platform
import resource
import shutil
import subprocess
import time
import traceback
from unittest.mock import patch
import numpy as np
from .token import Boundary, Context, ContractError, RollingReference, Token, identity, observation

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def file_identity(path):
    data = path.read_bytes()
    return dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def write(path, obj):
    with path.open('x') as out:
        json.dump(obj, out, indent=2, allow_nan=False)
        out.write('\n')


def batch(rows, m, P):
    """Build the entire joint Gaussian from independent driving blocks.

    This oracle does not call token algebra or sequential conditioning. It
    supports singular W/P because only observation covariance is inverted.
    """
    d = len(m)
    sizes = [d]+[d+len(r['y']) for r in rows]
    total = sum(sizes)
    V = np.zeros((total, total)); V[:d, :d] = P
    X = np.zeros((d, total)); X[:, :d] = np.eye(d)
    mu = np.array(m, copy=True)
    Ys, ys, ym = [], [], []
    pos = d
    for r in rows:
        k = len(r['y'])
        V[pos:pos+d, pos:pos+d] = r['W']
        V[pos+d:pos+d+k, pos+d:pos+d+k] = r['R']
        X = r['F']@X
        X[:, pos:pos+d] += np.eye(d)
        mu = r['F']@mu+r['offset']
        Y = r['H']@X
        Y[:, pos+d:pos+d+k] += np.eye(k)
        Ys.append(Y); ys.append(r['y']); ym.append(r['H']@mu)
        pos += d+k
    if not rows:
        return mu, P.copy(), 0.
    Y = np.concatenate(Ys)
    residual = np.concatenate(ys)-np.concatenate(ym)
    CY = Y@V@Y.T; CXY = X@V@Y.T
    mean = mu+CXY@np.linalg.solve(CY, residual)
    cov = X@V@X.T-CXY@np.linalg.solve(CY, CXY.T)
    sign, ld = np.linalg.slogdet(CY)
    assert sign > 0
    log_z = -.5*(residual@np.linalg.solve(CY, residual)+ld+len(residual)*math.log(2*math.pi))
    return mean, cov, float(log_z)


def sequential(rows, m, P):
    m, P, log_z = m.copy(), P.copy(), 0.
    for r in rows:
        m = r['F']@m+r['offset']; P = r['F']@P@r['F'].T+r['W']
        S = r['H']@P@r['H'].T+r['R']; residual = r['y']-r['H']@m
        K = np.linalg.solve(S, r['H']@P).T
        m = m+K@residual
        D = np.eye(len(m))-K@r['H']
        P = D@P@D.T+K@r['R']@K.T
        log_z -= .5*(residual@np.linalg.solve(S, residual)+np.linalg.slogdet(S)[1]
                      +len(residual)*math.log(2*math.pi))
    return m, P, float(log_z)


class Census:
    def __init__(self, plan):
        self.checks = []
        self.rtol = plan['comparison']['rtol']; self.atol = plan['comparison']['atol']

    def check(self, name, passed, **detail):
        self.checks.append(dict(name=name, passed=bool(passed), **detail))

    def close(self, name, actual, expected):
        a, b = np.asarray(actual), np.asarray(expected)
        delta = np.abs(a-b)
        allowance = self.atol+self.rtol*np.abs(b)
        self.check(name, np.all(np.isfinite(a)) and np.all(delta <= allowance),
                   maximum_absolute_error=float(np.max(delta, initial=0.)),
                   maximum_allowance_ratio=float(np.max(delta/allowance, initial=0.)))

    def reject(self, name, function):
        try:
            function()
        except (ContractError, np.linalg.LinAlgError):
            self.check(name, True)
        else:
            self.check(name, False)

    def view(self, name, view, expected):
        for key, value, ref in zip(('mean', 'covariance', 'log_evidence'),
                                  (view.mean, view.covariance, view.log_evidence), expected):
            self.close(name+'/'+key, value, ref)

    def case(self, name, function):
        try:
            return function()
        except Exception:
            self.check(name+'/exception', False, traceback=traceback.format_exc())


def context(d):
    return Context('fabricated-stream-290103', 'linear-Gaussian-v1',
                   'independent-known-covariances-v1', 'fixture-SI-v1', d, 1000000)


def make_row(ctx, boundary, F, offset, W, H, y, R, ticks=28571, current=0.):
    values = dict(F=np.array(F, dtype=float), offset=np.array(offset, dtype=float),
                  W=np.array(W, dtype=float), H=np.array(H, dtype=float),
                  y=np.array(y, dtype=float), R=np.array(R, dtype=float))
    tok = observation(ctx, boundary, boundary.ticks+ticks, current, **values)
    return values, tok


def fold(tokens):
    out = identity(tokens[0].context, tokens[0].entry)
    for t in tokens:
        out = out.then(t)
    return out


def vector_case(c, rng, index):
    d, n = 3, 3+index % 10
    ctx = context(d); boundary = Boundary(0, 0)
    prior_m = rng.normal(size=d)
    Z = rng.normal(size=(d, d)); prior_P = Z@Z.T+.3*np.eye(d)
    rows, tokens = [], []
    for k in range(n):
        F = .85*np.eye(d)+.06*rng.normal(size=(d, d))
        G = rng.normal(size=(d, 1 if index % 3 == 1 else d))*.1
        W = np.zeros((d, d)) if index % 3 == 0 else G@G.T
        H = rng.normal(size=(2, d)); N = rng.normal(size=(2, 2))*.1
        row, t = make_row(ctx, boundary, F, rng.normal(size=d)*.1, W, H,
                          rng.normal(size=2), N@N.T+.2*np.eye(2),
                          ticks=[0, 26000, 31000][k % 3], current=[1., -2., 0.][k % 3])
        rows.append(row); tokens.append(t); boundary = t.exit
    name = f'vector/{index}'
    agg = fold(tokens); expected = batch(rows, prior_m, prior_P)
    c.view(name+'/operator_vs_batch', agg.query(prior_m, prior_P), expected)
    for key, a, b in zip(('mean', 'covariance', 'log_evidence'), sequential(rows, prior_m, prior_P), expected):
        c.close(name+'/sequential_vs_batch/'+key, a, b)
    groups = [fold(tokens[:1]), fold(tokens[1:2]), fold(tokens[2:])]
    left = groups[0].then(groups[1]).then(groups[2])
    right = groups[0].then(groups[1].then(groups[2]))
    for key in ('J', 'h', 'c', 'A', 'b', 'Q'):
        c.close(name+'/associativity/'+key, getattr(left, key), getattr(right, key))
    c.view(name+'/grouped_vs_batch', right.query(prior_m, prior_P), expected)
    # Off-anchor conditional likelihood and exit distribution, with no entry uncertainty.
    x = rng.normal(size=d)
    c.view(name+'/conditional_entry', agg.query(x, np.zeros((d, d))), batch(rows, x, np.zeros((d, d))))
    c.check(name+'/identity', identity(ctx, tokens[0].entry).then(agg) is agg
            and agg.then(identity(ctx, agg.exit)) is agg)
    roll = RollingReference(ctx, Boundary(0, 0), capacity=4)
    for k, t in enumerate(tokens):
        if k and k % 3 == 0:
            roll.retire(2 if k == 3 else 3)
        roll.offer(t)
        before = roll.fingerprint()
        v = roll.query(prior_m, prior_P)
        c.view(name+f'/rolling/{k}', v, batch(rows[:k+1], prior_m, prior_P))
        repeat = roll.query(prior_m, prior_P)
        c.check(name+f'/immutable_query/{k}', before == roll.fingerprint()
                and np.array_equal(v.mean, repeat.mean) and v.records == k+1)
    c.close(name+'/actual_duration', agg.duration_s, sum([0, 26000, 31000][k % 3] for k in range(n))/ctx.tick_hz)
    c.close(name+'/signed_charge', agg.signed_Ah, sum(t.signed_Ah for t in tokens))
    c.close(name+'/throughput', agg.throughput_Ah, sum(t.throughput_Ah for t in tokens))


def ownership(c):
    ctx = context(1); start = Boundary(0, 0)
    def one(boundary=start, **kw):
        return make_row(ctx, boundary, [[1]], [0], [[0]], [[1]], [1], [[1]], **kw)[1]
    a = one(); b = one(a.exit); z = one(b.exit)
    r = RollingReference(ctx, start, 2); r.offer(a); r.offer(b)
    before = r.fingerprint()
    for label, fun in [
        ('overlap', lambda: a.then(a)), ('gap', lambda: a.then(z)),
        ('wrong_source', lambda: a.then(replace(b, context=replace(ctx, source='different')))),
        ('wrong_model', lambda: a.then(replace(b, context=replace(ctx, model='different')))),
        ('wrong_noise', lambda: a.then(replace(b, context=replace(ctx, noise='different')))),
        ('wrong_calibration', lambda: a.then(replace(b, context=replace(ctx, calibration='different')))),
        ('wrong_ticks', lambda: a.then(replace(b, entry=Boundary(1, a.exit.ticks+1)))),
        ('queue_full', lambda: r.offer(z)), ('duplicate_offer', lambda: r.offer(a)),
        ('posterior_not_evidence', lambda: r.offer(r.query([0], [[1]]))),
        ('aggregate_not_one_record', lambda: r.offer(a.then(b))),
        ('invalid_retire', lambda: r.retire(3)),
        ('negative_retire', lambda: r.retire(-1)),
        ('nonfinite_query', lambda: r.query([float('nan')], [[1]])),
        ('negative_covariance', lambda: r.query([0], [[-1]])),
        ('nonidentity_empty', lambda: replace(identity(ctx, start), c=1.)),
        ('invented_certificate', lambda: replace(a, arithmetic_bound=0.)),
        ('counter_overflow', lambda: one(Boundary(2**64-1, 0))),
        ('nonfinite_current', lambda: one(current=float('inf'))),
        ('negative_duration', lambda: one(ticks=-1)),
        ('zero_observation_variance', lambda: observation(ctx, start, 0, 0., [[1]], [0], [[0]], [[1]], [0], [[0]])),
    ]:
        c.reject('ownership/'+label, fun)
        c.check('ownership/'+label+'/atomic', r.fingerprint() == before)
    c.reject('ownership/backwards_order', lambda: b.then(a))
    native_then = Token.then
    calls = 0
    def fail_second(left, right):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ContractError('injected arithmetic failure after partial local work')
        return native_then(left, right)
    with patch.object(Token, 'then', fail_second):
        c.reject('ownership/retirement_mid_computation_failure', lambda: r.retire(2))
    c.check('ownership/retirement_mid_computation_atomic', r.fingerprint() == before and calls == 2)
    r.retire(1)
    c.check('ownership/retire_prefix', r.retired_boundary == a.exit and r.accepted_boundary == b.exit)
    r.offer(z); r.retire(2)
    c.check('ownership/all_retired', r.retired_boundary == z.exit and r.query([0], [[1]]).records == 3)
    snapshot = r.fingerprint(); r.retire(0)
    c.check('ownership/empty_retirement', snapshot == r.fingerprint())
    c.reject('ownership/replayed_after_retirement', lambda: r.offer(a))
    try:
        a.J.setflags(write=True)
    except ValueError:
        c.check('ownership/immutable_arrays', True)
    else:
        c.check('ownership/immutable_arrays', False)
    c.check('ledger/explicit_unresolved', a.representation_defect_real_arithmetic == 0
            and a.arithmetic_bound is None and a.physical_model_bound is None)


def physical_controls(c):
    ctx = context(2); m = np.array([0., 0.]); P = np.diag([1., 4.])
    # Quiet elapsed step: no informative observation, independent explicit aging.
    _, t = make_row(ctx, Boundary(0, 0), np.eye(2), [0, 0], np.diag([.2, .3]),
                    [[0, 0]], [0], [[1]], ticks=1000000)
    quiet = t.query(m, P)
    c.close('aging/quiet_adds_supplied_covariance', quiet.covariance, P+np.diag([.2, .3]))
    c.close('aging/quiet_does_not_correct_mean', quiet.mean, m)
    _, obs = make_row(ctx, t.exit, np.eye(2), [0, 0], np.zeros((2, 2)), [[1, 0]], [1], [[.1]])
    v = t.then(obs).query(m, P)
    c.close('excitation/unobserved_direction_unchanged', v.covariance[1, 1], 4.3)
    c.close('excitation/unobserved_mean_unchanged', v.mean[1], 0.)
    c.check('excitation/observed_direction_tightens', v.covariance[0, 0] < quiet.covariance[0, 0])
    correlated = np.array([[1., .6], [.6, 1.]])
    cv = obs.query(m, correlated)
    c.check('excitation/correlation_indirect_correction', cv.mean[1] > 0 and cv.covariance[1, 1] < 1.)
    # Same stimulus objects reordered at matching new source positions change evidence.
    def order(ys):
        rows = []; toks = []; boundary = Boundary(0, 0)
        for y in ys:
            row, tok = make_row(context(1), boundary, [[1]], [0], [[1]], [[1]], [y], [[.1]])
            rows.append(row); toks.append(tok); boundary = tok.exit
        return fold(toks).query([0], [[1]])
    c.check('chronology/reordering_changes_current_estimate', abs(order([0., 2.]).mean[0]-order([2., 0.]).mean[0]) > 1.)
    _, fixed = make_row(context(1), Boundary(0, 0), [[1]], [0], [[0]], [[1]], [1], [[1]])
    c.close('ownership/prior_counted_once', fixed.query([0], [[1]]).covariance, [[.5]])
    c.close('ownership/requery_with_different_prior', fixed.query([0], [[4]]).covariance, [[.8]])


def repetitions(c, count):
    ctx = context(2); start = Boundary(0, 0); agg = identity(ctx, start)
    H = np.array([[1., 2.]])
    S = T = 0
    for i in range(count):
        y = i % 5-2
        _, row = make_row(ctx, agg.exit, np.eye(2), [0, 0], np.zeros((2, 2)), H, [y], [[1]], ticks=0)
        agg = agg.then(row); S += y; T += y*y
    c.close('repetition/exact_information_coefficient', agg.J, count*(H.T@H))
    c.close('repetition/exact_linear_coefficient', agg.h, H[0]*S)
    c.close('repetition/evidence_constant', agg.c, .5*T+.5*count*math.log(2*math.pi))
    c.close('repetition/deterministic_state_map', agg.A, np.eye(2))
    c.check('repetition/no_injected_process_noise', not np.any(agg.Q) and agg.duration_s == 0 and agg.records == count)
    c.check('repetition/constant_token_numeric_storage', agg.numeric_bytes == row.numeric_bytes == 136)
    return dict(records=count, integer_sum=S, integer_squared_sum=T,
                retained_token_numeric_B=agg.numeric_bytes, duration_s=agg.duration_s,
                meaning='Algebraic repetition/zero-interval control; not a battery trajectory or realistic delivery-rate premise')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    dest = args.destination.resolve(); dest.mkdir(parents=True, exist_ok=False)
    plan = json.loads((HERE/'plan.json').read_text())
    parent = ROOT/'experiments/ten_year_history_001/verification.json'
    old = json.loads(parent.read_text())['artifacts']
    sources = [HERE/'plan.json', HERE/'derivation.md', HERE/'token.py', HERE/'qualify.py',
               parent, ROOT/'experiments/history_provider_001/contract.json',
               ROOT/'experiments/live_anchor_integration_001/rolling_engine.h',
               ROOT/'experiments/live_anchor_integration_001/rolling_engine.c']
    identities = {str(p.relative_to(ROOT)): file_identity(p) for p in sources}
    reservation = dict(schema='incremental_history_reservation_v1',
                       git_revision=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
                       branch=subprocess.check_output(['git', 'branch', '--show-current'], text=True).strip(),
                       command=['python3', '-B', '-m', 'experiments.incremental_history_001.qualify', str(args.destination)],
                       python=platform.python_version(), numpy=np.__version__, source_identities=identities,
                       prior_artifacts=old, status='reserved_before_evaluation')
    write(dest/'reservation.json', reservation)
    for path in identities:
        target = dest/'source_snapshot'/path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT/path, target)
    started = time.perf_counter(); cpu = time.process_time()
    c = Census(plan); rng = np.random.default_rng(plan['fixtures']['seed'])
    for index in range(plan['fixtures']['vector_cases']):
        c.case(f'vector/{index}', lambda index=index: vector_case(c, rng, index))
    c.case('ownership', lambda: ownership(c))
    c.case('physical_controls', lambda: physical_controls(c))
    repetition = c.case('repetition', lambda: repetitions(c, plan['fixtures']['repetition_records']))
    for path, expected in {**old, **identities}.items():
        c.check('preservation/'+path, file_identity(ROOT/path) == expected)
    failures = [q for q in c.checks if not q['passed']]
    result = dict(schema='incremental_history_result_v1', status='passed' if not failures else 'failed',
                  checks=c.checks, checks_passed=len(c.checks)-len(failures), checks_failed=len(failures),
                  repetition=repetition, wall_seconds=time.perf_counter()-started,
                  cpu_seconds=time.process_time()-cpu, maximum_RSS_B=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
                  new_battery_fits=0, rolling_solver_changed=False, ten_year_certificate=False,
                  arithmetic_error_bound=None, coverage_validated=False, firmware_qualified=False)
    write(dest/'result.json', result)
    print(json.dumps({key: value for key, value in result.items() if key not in ('checks', 'repetition')}, indent=2))
    if failures:
        print(json.dumps(failures, indent=2))
    return bool(failures)


if __name__ == '__main__':
    raise SystemExit(main())
