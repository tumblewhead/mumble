"""Small deterministic controls; writes a fresh immutable attempt directory."""
import hashlib
import json
import math
from pathlib import Path
import platform
import resource
import shutil
import subprocess
import sys
import time
import numpy as np
from . import joint
from experiments.partitioned_battery_closure_001 import conditional

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def ident(path):
    raw = path.read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def write(path, value):
    with path.open('x') as f:
        json.dump(value, f, indent=2, allow_nan=False); f.write('\n')


class Checks:
    def __init__(self): self.items = []
    def check(self, name, passed, **detail):
        self.items.append(dict(name=name, passed=bool(passed), **detail))
    def close(self, name, got, expected, atol=3e-11, rtol=3e-11):
        a, b = np.asarray(got), np.asarray(expected)
        error = float(np.max(np.abs(a-b), initial=0))
        self.check(name, np.all(np.isfinite(a)) and np.all(np.abs(a-b) <= atol+rtol*np.abs(b)), max_absolute_error=error)
    def reject(self, name, fn):
        try: fn()
        except ValueError: self.check(name, True)
        else: self.check(name, False)


def gaussian_controls(c, rng):
    evidence = []
    for p, k in [(3, 1), (8, 3), (16, 5), (40, 8), (64, 8)]:
        # Independent synthetic standardized residual fixtures, not battery fits.
        rows = rng.normal(size=(2*p+7, p+1))
        rows[:p, :p] += 2*np.eye(p)
        const = 1.234
        b = joint.split(rows, k, const)
        h = rows[:, :p].T@rows[:, :p]; g = rows[:, :p].T@rows[:, p]
        inv = np.linalg.inv(h); mean = np.linalg.solve(h, -g)
        schur = h[k:, k:]-h[k:, :k]@np.linalg.solve(h[:k, :k], h[:k, k:])
        cov_s = np.linalg.inv(schur)
        beta = -np.linalg.solve(b.eliminated_root, b.cross)
        cond0, cond_cov = b.conditional(mean[k:])
        c.close(f'p{p}/conditional mean', cond0, mean[:k])
        c.close(f'p{p}/retained covariance', cov_s, inv[k:, k:])
        c.close(f'p{p}/cross covariance', beta@cov_s, inv[:k, k:])
        c.close(f'p{p}/retired covariance', cond_cov+beta@cov_s@beta.T, inv[:k, :k])
        c.close(f'p{p}/Schur root', b.retained_root[:-1, :-1].T@b.retained_root[:-1, :-1], schur)
        for j in range(6):
            x = rng.normal(size=p); s = x[k:]
            residual = rows@np.r_[x, 1.]
            c.close(f'p{p}/joint{j}', b.log_joint(x[:k], s), -.5*residual@residual-const)
            rhs = g[:k]+h[:k, k:]@s
            # Independent completion of the square, retaining determinant/constant.
            a = .5*(s@h[k:, k:]@s+2*g[k:]@s+rows[:, p]@rows[:, p])
            a -= .5*rhs@np.linalg.solve(h[:k, :k], rhs)
            logint = -a-const+.5*k*math.log(2*math.pi)-.5*np.linalg.slogdet(h[:k, :k])[1]
            c.close(f'p{p}/marginal{j}', b.log_marginal_unbounded(s), logint)
        # No storage saving merely by exposing conditional cross blocks.
        doubles = k*(k+1)//2+k*(p-k)+k+(p-k+1)*(p-k+2)//2
        c.check(f'p{p}/partition bytes identity', 8*doubles == joint.packed_factor_bytes(p))
        evidence.append(dict(p=p, retired=k, full_packed_B=8*doubles,
                             cross_covariance_max=float(np.max(np.abs(inv[:k, k:])))))
    c.reject('flat retired direction rejects', lambda: joint.split(np.array([[0., 1., 2.]]), 1))
    c.reject('duplicate retired columns rejects', lambda: joint.split(np.array([[1., 1., 0.], [2., 2., 1.]]), 2))
    # A flat retained direction is legitimate; do not regularize it.
    flat = joint.split(np.array([[2., 0., 1.], [1., 0., 0.]]), 1)
    c.close('flat retained direction remains flat', flat.log_marginal_unbounded([0.]), flat.log_marginal_unbounded([123.]))
    c.reject('nonfinite rows reject', lambda: joint.split([[1., float('nan'), 0.]], 1))
    c.reject('unsupported multidimensional support rejects', lambda: joint.split(np.eye(4), 2).log_marginal_scalar_interval([0.], 0., 1.))
    return evidence


def constrained_controls(c):
    # x is retired health, s is retained health. x in [0,s] is monotone support.
    # The Gaussian conditional x|s has mean .15+.4s and sd .25.
    rows = np.array([[4., -1.6, -.6], [0., 1.2, -.1], [0., 0., .2]])
    b = joint.split(rows, 1)
    points, weights = np.polynomial.legendre.leggauss(128)
    records = []
    for i, s in enumerate([.02, .05, .1, .2, .4, .6, .8, 1.]):
        x = .5*s*(points+1)
        direct = .5*s*float(weights@np.array([math.exp(b.log_joint([v], [s])) for v in x]))
        actual = b.log_marginal_scalar_interval([s], 0., s)
        c.close(f'monotone bounded integral{i}', actual, math.log(direct))
        correction = actual-b.log_marginal_unbounded([s])
        c.check(f'monotone mass negative{i}', correction < 0)
        records.append(dict(retained=s, log_mass=correction, log_marginal=actual))
    # A quadratic's third forward difference is zero. Support correction is not quadratic.
    values = np.array([b.log_marginal_scalar_interval([s], 0., s) for s in [.1, .3, .5, .7]])
    third = float(np.diff(values, n=3)[0])
    c.check('monotone marginal nonquadratic witness', abs(third) > .01, third_difference=third)
    c.reject('empty scalar support rejects explicitly', lambda: b.log_marginal_scalar_interval([.2], .2, .2))
    c.reject('extreme mass underflow remains unresolved', lambda: joint.normal_log_mass(100., 101.))
    c.close('whole real line mass', joint.normal_log_mass(-math.inf, math.inf), 0.)
    c.close('positive negative tail symmetry', joint.normal_log_mass(2., 3.), joint.normal_log_mass(-3., -2.))
    # Different nonlinear conditioning nodes need their elimination determinants.
    # exp(-a^2*x^2/2) has zero profile cost for every a, but marginal sqrt(2pi)/a.
    a1, a2 = joint.split([[1., 0.]], 1), joint.split([[4., 0.]], 1)
    c.close('conditional determinant ratio', a1.log_marginal_unbounded([])-a2.log_marginal_unbounded([]), math.log(4.))
    return dict(monotone=records, third_difference=third, determinant_mass_ratio=4.)


def adversaries(c):
    h = np.eye(2)+100*np.ones((2, 2)); cov = np.linalg.inv(h)
    diag_cov = np.diag(np.diag(cov)); diag_precision_cov = np.diag(1/np.diag(h))
    sums, differences = np.ones(2), np.array([1., -1.])
    plus = float(sums@cov@sums); minus = float(differences@cov@differences)
    independent_plus = float(sums@diag_cov@sums); independent_minus = float(differences@diag_cov@differences)
    c.close('joint sum variance', plus, 2/201)
    c.close('unexcited difference variance', minus, 2.)
    c.check('discarded covariance worsens sum', independent_plus/plus > 100)
    c.check('discarded covariance falsely tightens difference', independent_minus < minus)
    ratio = float(cov[0, 0]/diag_precision_cov[0, 0])
    c.check('discarded precision cross term gives false precision', ratio > 50)
    # One candidate must hold all coordinates; coordinatewise union is not enough.
    boxes = [np.array([[0., .9], [.1, 1.]]), np.array([[.9, 0.], [1., .1]])]
    point = np.array([.5, .5]); hull_lo = np.min([b[0] for b in boxes], axis=0); hull_hi = np.max([b[1] for b in boxes], axis=0)
    in_hull = bool(np.all(point >= hull_lo) and np.all(point <= hull_hi))
    coherent = any(np.all(point >= b[0]) and np.all(point <= b[1]) for b in boxes)
    c.check('marginal hull does not certify common candidate', in_hull and not coherent)
    return dict(joint_sum_variance=plus, independent_sum_variance=independent_plus,
                joint_difference_variance=minus, independent_difference_variance=independent_minus,
                false_precision_ratio=ratio, marginal_midpoint_is_coherent=coherent)


def physical_graph(c):
    # Actual conditional battery algebra, arbitrary observations; no fitted/truth center.
    eta = np.r_[np.log([.05, .5, 5., 100., 150.]), .6, math.log(.06)]
    rows = np.zeros((128, 3)); rows[:, 0] = 1/35
    rows[:, 1] = .1+.03*np.sin(np.arange(128)*.3); rows[:, 2] = 3.7
    block = conditional.build(eta, rows)
    gram = block.S.T@block.S
    # All amplitude columns have common-sign nonzero sensitivities in this drive.
    c.check('physical conditional amplitude clique', bool(np.all(gram[:9, :9] > 0)))
    g = joint.graph_from_scopes(list(range(9)), [list(range(9))])
    _, fill, peak = joint.eliminate_graph(g, list(range(9)))
    c.check('amplitude clique has no independent blocks', peak == 9 and len(fill) == 0)
    # x0--x1--x2 with a common thermal variable t. Retiring x1 induces x0--x2.
    g = joint.graph_from_scopes(['x0', 'x1', 'x2', 't'], [['x0', 'x1', 't'], ['x1', 'x2', 't']])
    remaining, fill, peak = joint.eliminate_graph(g, ['x1'])
    c.check('retirement fill preserved', ['x0', 'x2'] in fill and 'x2' in remaining['x0'])
    # Long temporal chain: two-dimensional boundary plus two globals.
    # Generic local scopes include both endpoints and shared thermal coefficients.
    sizes = []
    for length in [4, 16, 64]:
        static = ['g0', 'g1']; states = [[f'x{i}_{j}' for j in range(2)] for i in range(length)]
        nodes = static+sum(states, [])
        scopes = [states[i]+states[i+1]+static for i in range(length-1)]
        graph = joint.graph_from_scopes(nodes, scopes)
        retained, fill, peak = joint.eliminate_graph(graph, sum(states[:-1], []))
        c.check(f'separator chain{length}', len(retained) == 4 and peak == 6)
        sizes.append(dict(segments=length, retained_variables=len(retained), elimination_clique=peak))
    return dict(conditional_amplitude_variables=9, conditional_augmented_factor_B=440,
                minimum_amplitude_cross_Gram=float(np.min(gram[:9, :9])), temporal_chain=sizes,
                warning='Generic graph closure does not imply Gaussian closure under nonlinear or monotone factors')


def layouts(c):
    results = []
    for name, p in [('full_trajectory_example', 64), ('boundary_health_thermal_fast_nuisance', 40),
                    ('boundary_plus_uncertain_temperature_segment', 44),
                    ('active_linear_age_segment', 48), ('active_age_and_temperature_segments', 52)]:
        factor = joint.packed_factor_bytes(p); centers = (12*p+7)//8; scratch = 8*(p+1)
        results.append(dict(name=name, p=p, factor_B=factor, center_codes_B=centers,
                            one_row_scratch_B=scratch, partial_total_B=factor+centers+scratch,
                            complete_SRAM_B=None))
    c.check('64 dense payload preserved', results[0]['factor_B'] == 17160)
    c.check('40 boundary payload arithmetic', results[1]['factor_B'] == 6888)
    c.check('48 active payload exceeds target with one row', results[3]['partial_total_B'] > 10240)
    return dict(layouts=results, invalid_eight_independent_p8_blocks_B=8*joint.packed_factor_bytes(8),
                scope='Packed numeric proposals only. Python uses dense arrays. Support factors, priors not representable by this root, nonlinear functions, descriptors, stacks and solver workspace are additional.')


def main():
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE/'attempt001'
    output.mkdir(parents=True, exist_ok=False)
    old = json.loads((ROOT/'experiments/monotone_codebook_001/verification.json').read_text())
    older = json.loads((ROOT/'experiments/monotone_codebook_001/attempt001/reservation.json').read_text())['preserved_artifacts']
    preserved = {**older, **old['artifacts'], 'experiments/monotone_codebook_001/verification.json': ident(ROOT/'experiments/monotone_codebook_001/verification.json')}
    for p, expected in preserved.items():
        if ident(ROOT/p) != expected: raise ValueError('earlier evidence changed: '+p)
    sources = list(HERE.glob('*.py'))+[HERE/'plan.json', HERE/'derivation.md', HERE/'sources.json',
              ROOT/'experiments/partitioned_battery_closure_001/conditional.py']
    sources += [p for p in (HERE/'sources').rglob('*') if p.is_file()]
    identities = {str(p.relative_to(ROOT)): ident(p) for p in sources}
    for p in sources:
        target = output/'source_snapshot'/p.relative_to(ROOT); target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, target)
    write(output/'reservation.json', dict(source_revision=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
          branch=subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip(),
          source_identities=identities, preserved_artifacts=preserved,
          python=platform.python_version(), numpy=np.__version__, command=sys.argv,
          scope='Synthetic algebra controls; no SCM code execution or estimator trajectories'))
    c = Checks(); t = time.perf_counter(); cpu = time.process_time(); rng = np.random.default_rng(291029)
    evidence = {}
    for name, fn in [('gaussian', lambda: gaussian_controls(c, rng)), ('constrained', lambda: constrained_controls(c)),
                     ('adversaries', lambda: adversaries(c)), ('physical_graph', lambda: physical_graph(c)), ('storage', lambda: layouts(c))]:
        try: evidence[name] = fn()
        except Exception as e:
            import traceback
            c.check(name+'/unexpected exception', False, detail=traceback.format_exc())
    for p, expected in identities.items(): c.check('source preserved/'+p, ident(ROOT/p) == expected)
    for p, expected in preserved.items():
        if ident(ROOT/p) != expected: c.check('old evidence modified/'+p, False)
    result = dict(status='passed' if all(v['passed'] for v in c.items) else 'failed',
                  passing_checks=sum(v['passed'] for v in c.items), failed_checks=[v for v in c.items if not v['passed']],
                  checks=c.items, evidence=evidence, wall_seconds=time.perf_counter()-t, cpu_seconds=time.process_time()-cpu,
                  maximum_RSS_B=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
                  preserved_artifacts=len(preserved), full_posterior_qualified=False, lifetime_qualified=False, target_qualified=False)
    write(output/'result.json', result)
    print(json.dumps({k: result[k] for k in ['status', 'passing_checks', 'failed_checks', 'cpu_seconds', 'preserved_artifacts']}))
    if result['failed_checks']: raise SystemExit(1)


if __name__ == '__main__': main()
