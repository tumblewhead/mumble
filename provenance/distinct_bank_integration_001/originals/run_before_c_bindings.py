"""Short stationary distinct-bank integration diagnostic; no campaign promotion."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.distinct_bank_integration_001.field import DistinctBankField, Compressed, features_jacobian, transported
from experiments.foster_campaign_001.backend import ROOT, identity, prepare_c
from experiments.foster_feedback_001.estimator import Model
from experiments.foster_uncertainty_audit_001.conditional_packet import chart_from, partition
from experiments.h7_history_quality_001.history import source_receipt, verify_sources, write
from experiments.hysteresis_mixed_completion_001.run import CommonDomain, choose_fit
from experiments.hysteresis_sensitivity_basis_001.basis import HField, build as build_h
from experiments.rc_sensitivity_basis_001.basis import build as build_rc
from experiments.shared_operator_budget_001.field import Compressed as TaylorCompressed
from experiments.shared_operator_budget_001.field import features_jacobian as taylor_jacobian
from experiments.shared_operator_budget_001.field import transported as taylor_transport
from experiments.slow_likelihood_diagnostic_001.numerics import Exact


REGISTRATION = ROOT/'provenance/rc_sensitivity_basis_001/full001_registration.json'
MAP = ROOT/'experiments/distinct_bank_integration_001/map_n13e.json'


def public_registration():
    """Consume only public calibration/prior/centre, never historical fitted queries."""
    reg = json.loads(REGISTRATION.read_text())
    return {key: reg[key] for key in ('config', 'prior_mean', 'prior_root', 'center')}


def build_kernels(directory, config):
    """Every invocation starts from source, including the direct native comparator."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    direct, receipt = prepare_c(directory, 35, config)
    rc = build_rc(directory/'rc', 'taylor2')
    h = build_h(directory/'h', 'derivative')
    return dict(direct=direct.resolve(), rc=rc.resolve(), h=h.resolve()), receipt


def observation_inputs(records):
    """Public deterministic load, actual intervals and declared Gaussian sigmas."""
    k = np.arange(records)
    dt = np.array([1/35, 1/35, 2/35, 0., 1/70])[k % 5]
    current = np.array([.12, -.08, 0., .04, -.12])[(k//17) % 5]
    sigma = np.array([.001, .0012, .0008])[k % 3]
    return np.c_[dt, current, np.full(records, 25.), np.zeros(records), sigma]


def fixture(model, mean, root, records):
    """Synthetic observations only: the generator never sets fit/prior/centre."""
    obs = observation_inputs(records)
    generator = np.asarray(mean) + np.asarray(root) @ np.array(
        [.15, .2, -.1, .1, .2, -.15, .1, -.1, .1, .1, -.1, -.1, .1, .1, -.1, .1])
    voltage = model.evaluate(generator, obs)[0]
    seed = 20261104
    obs[:, 3] = voltage + obs[:, 4]*np.random.default_rng(seed).standard_normal(records)
    return obs, dict(scope='synthetic integration fixture, not performance or coverage evidence',
                     generator_chart=generator, noise_seed=seed,
                     generator_use='observation synthesis only; prior, starts and basis centres remain public')


def finite_probe(fields, rows, model, obs, mean, root):
    """Full joint, same-anchor diagnostics. Finite samples are no global certificate."""
    a, s = partition(mean)
    offsets = [np.zeros(5)]
    for j in range(5):
        for sign in (-1., 1.):
            value = np.zeros(5); value[j] = .8*sign; offsets.append(value)
    report = []
    for offset in offsets:
        x = chart_from(a, s*np.exp(offset))
        v, J, end, F = model.evaluate(x, obs)
        direct_B = J@root/obs[:, 4, None]
        direct_qr = np.linalg.qr(np.vstack((np.eye(16), direct_B)), mode='reduced')[1]
        entry = dict(log_shape_offsets=offset, arms={})
        for name, field in fields.items():
            jac = features_jacobian if name == 'distinct_bank' else taylor_jacobian
            transport = transported if name == 'distinct_bank' else taylor_transport
            feature = field.features(x)
            prediction = rows[name]@feature*obs[:, 4]+obs[:, 3]
            B = rows[name]@jac(field, x)@root
            E = np.linalg.solve(direct_qr.T, (B-direct_B).T).T
            ce, cF = transport(field, x)
            entry['arms'][name] = dict(voltage_max_abs_uV=float(1e6*np.max(abs(prediction-v))),
                jacobian_prior_scaled_max_abs=float(np.max(abs(B-direct_B))),
                joint_relative_jacobian_norm=float(np.linalg.norm(E, 2)),
                endpoint_chart_max_abs=float(np.max(abs(ce-end))),
                endpoint_joint_jacobian_max_abs=float(np.max(abs((cF-F)@root))))
        report.append(entry)
    return dict(status='finite_same_anchor_diagnostic_not_uniform_certificate', samples=report)


def refits(fields, model, obs, mean, root):
    direct = CommonDomain(Exact(model, obs, mean, root, chunk=4096), fields['distinct_bank'])
    objectives = dict(direct=direct,
        distinct_bank=Compressed(fields['distinct_bank'], mean, root),
        TaylorRC_TaylorH2=TaylorCompressed(fields['TaylorRC_TaylorH2'], mean, root))
    report = {}
    for name, objective in objectives.items():
        fit, report[name] = choose_fit(objective)
        if fit is not None:
            if name == 'direct':
                _, _, endpoint, F = model.evaluate(fit['x'], obs)
            elif name == 'distinct_bank':
                endpoint, F = transported(fields[name], fit['x'])
            else:
                endpoint, F = taylor_transport(fields[name], fit['x'])
            endpoint_root = F@fit['root']
            report[name]['local_readout'] = dict(Q_mAh=float(1000*np.exp(fit['x'][5])),
                Q_log_SD=float(np.linalg.norm(fit['root'][5])), SOC=float(endpoint[0]),
                SOC_SD=float(np.linalg.norm(endpoint_root[0])),
                Q_SOC_chart_covariance=float(fit['root'][5]@endpoint_root[0]),
                qualification='provisional local curvature; short fixture does not establish identification or coverage')
        print(json.dumps(dict(stage='refit', arm=name, status=report[name]['status'])), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--records', type=int, default=512)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--refit', action='store_true')
    args = parser.parse_args()
    if args.records < 1: parser.error('--records must be positive')
    args.out = args.out.resolve(); args.out.mkdir(parents=True, exist_ok=False)
    reg = public_registration()
    mean, root, center = map(np.asarray, (reg['prior_mean'], reg['prior_root'], reg['center']))
    bins, build = build_kernels(args.out/'build', reg['config'])
    model = Model(bins['direct'], reg['config'])
    obs, generator = fixture(model, mean, root, args.records)
    source = 'distinct_bank_integration_fixture_v1'
    fields = dict(distinct_bank=DistinctBankField(reg['config'], center, bins['rc'], bins['h'], MAP, source),
        TaylorRC_TaylorH2=HField(reg['config'], center, bins['rc'], bins['h'], 'TaylorH2', source))
    sources = source_receipt()
    # Include untracked study source too; bind map/public input independently of
    # the repository module collector and recheck all identities before success.
    for path in Path(__file__).resolve().parent.glob('*.py'):
        sources['sources'][str(path.relative_to(ROOT))] = identity(path)
    input_bindings = {str(path.relative_to(ROOT)): identity(path) for path in (MAP, REGISTRATION)}
    write(args.out/'registration.json', dict(source=sources, command=sys.argv,
        public_registration=dict(path=str(REGISTRATION.relative_to(ROOT)), identity=identity(REGISTRATION)),
        map=dict(path=str(MAP.relative_to(ROOT)), identity=identity(MAP)), public=reg,
        nominal_rate_Hz=35, temperature_C=25, interval_policy='actual dt and original sample order',
        objective='one original prior plus full joint Gaussian voltage likelihood; unchanged choose_fit/Exact',
        fit_starts='public mean and alternating +/-0.05 whitened coordinates',
        fit_rounds=60, refit_requested=args.refit, direct_build=build,
        binaries={key: identity(path) for key, path in bins.items()}))
    rows = {name: [] for name in fields}
    for start in range(0, len(obs), 128):
        for name, field in fields.items():
            rows[name].append(field.update(start, obs[start:start+128], source, return_rows=True))
    rows = {name: np.vstack(value) for name, value in rows.items()}
    result = dict(status='completed_experimental_integration_no_promotion', records=len(obs),
        observation_sha256=hashlib.sha256(obs.astype('<f8').tobytes()).hexdigest(),
        elapsed_s=float(obs[:, 0].sum()), fixture=generator,
        probes=finite_probe(fields, rows, model, obs, mean, root),
        storage={name: field.storage() for name, field in fields.items()},
        limitations=['stationary 25 C only', 'incoming map not globally certified',
            'finite diagnostics do not establish accuracy or uncertainty coverage',
            'separate three-branch banks exceed W34 and M23 resource budgets',
            'desktop Python dense QR; no bounded target implementation or campaign promotion'])
    if args.refit: result['fits'] = refits(fields, model, obs, mean, root)
    snapshot = dict(observations=obs)
    for name, field in fields.items(): snapshot[name+'_root'] = field.root
    np.savez_compressed(args.out/'snapshot.npz', **snapshot)
    result['snapshot'] = identity(args.out/'snapshot.npz')
    verify_sources(sources)
    for name, expected in input_bindings.items():
        if identity(ROOT/name) != expected: raise ValueError('input changed during run: '+name)
    write(args.out/'result.json', result)
    print(json.dumps(dict(status=result['status'], records=len(obs), result=str(args.out/'result.json'))))


if __name__ == '__main__': main()
