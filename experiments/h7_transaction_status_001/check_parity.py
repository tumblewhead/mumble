"""Short deterministic normal-path comparison against preserved pre-repair code.

Run from the repository root with OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
MKL_NUM_THREADS=1 python3 -B experiments/h7_transaction_status_001/check_parity.py.
Plant truth is never supplied to either backend. This is finite numerical
evidence, not fault coverage, calibrated uncertainty or peer review.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import numpy as np
from experiments.foster_campaign_001.h7_backend import H7Backend, prepare_h7, DEPENDENCIES
from experiments.field_tangent_native_001.native import Native
from experiments.hysteresis_refinement_001.field import Compressed
from experiments.foster_uncertainty_audit_001.conditional_packet import partition
from experiments.foster_campaign_001.stimulus import generate, cells


def identity(path):
    data = path.read_bytes()
    return dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def archived_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def baseline_modules(baseline, archive=None):
    """Load verified originals, reconstructing the ignored archive when absent."""
    archive = ROOT/baseline['local_snapshot'] if archive is None else Path(archive)
    with tempfile.TemporaryDirectory(prefix='mumble-h7-baseline-') as temporary:
        materialized = archive if archive.exists() else Path(temporary)
        origin = 'local_archive' if archive.exists() else 'git_show_pinned_revision'
        for name, expected in baseline['source_identities'].items():
            path = materialized/name
            if origin == 'git_show_pinned_revision':
                data = subprocess.check_output(
                    ['git', 'show', baseline['source_revision'] + ':' + name], cwd=ROOT)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            if identity(path) != expected:
                raise ValueError('baseline source identity mismatch: ' + name)
        backend = archived_module('experiments.foster_campaign_001._h7_parity_baseline',
                                  materialized/'experiments/foster_campaign_001/tangent_backend.py')
        field = archived_module('experiments.hysteresis_refinement_001._h7_parity_baseline',
                                materialized/'experiments/hysteresis_refinement_001/field.py')
        # Only loaded class/function objects are used below. Archived build()
        # (which would need siblings beside __file__) is never called.
        return backend, field, origin


def run():
    for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
        if os.environ.get(name) != '1':
            raise ValueError(name + '=1 required for this registered comparison')
    baseline_path = ROOT/'provenance/h7_transaction_status_001/baseline.json'
    baseline = json.loads(baseline_path.read_text())
    old_backend, old_field, baseline_origin = baseline_modules(baseline)

    class BaselineH7(old_backend.TangentBackend):
        def _make_field(self, campaign, config, source):
            response, _ = prepare_h7(campaign)
            return old_field.MixedField(config, partition(self.mean)[1], 1., 7, response, source)

        def _make_native(self, campaign):
            return Native(prepare_h7(campaign)[1], self.field, self.mean, self.prior_root)

        def _make_objective(self):
            return Compressed(self.field, self.mean, self.prior_root)

    config_path = ROOT/'experiments/foster_feedback_001/calibration.json'
    config = json.loads(config_path.read_text())
    config['hysteresis_chart'] = 'bounded'
    cases = [dict(name='multiscale_reversal', load='multiscale', amplitude=.03,
                  n=6304, cadence_s=17, partial=False),
             dict(name='rest', load='rest', amplitude=0., n=2112,
                  cadence_s=17, partial=False),
             dict(name='weak_partial_overflow', load='multiscale', amplitude=.0005,
                  n=6304, cadence_s=1000, partial=True)]
    dependencies = sorted(set(DEPENDENCIES + [
        'experiments/foster_campaign_001/tangent_backend.py',
        'experiments/foster_campaign_001/backend.py',
        'experiments/foster_campaign_001/coordinates.py',
        'experiments/foster_campaign_001/rate.py',
        'experiments/foster_campaign_001/stimulus.py',
        'experiments/foster_campaign_001/telemetry.py',
        'experiments/foster_feedback_001/plant.py',
        'experiments/foster_feedback_001/estimator.py',
        'experiments/foster_feedback_001/calibration.json',
        'experiments/foster_uncertainty_audit_001/conditional_packet.py',
        'experiments/joint_rate_history_001/field.py',
        'experiments/slow_likelihood_diagnostic_001/numerics.py',
        str(Path(__file__).resolve().relative_to(ROOT))]))
    sources = {name: identity(ROOT/name) for name in dependencies}
    results = []
    with tempfile.TemporaryDirectory(prefix='mumble-h7-parity-') as temporary:
        campaign = Path(temporary)
        binaries = prepare_h7(campaign)
        for specification in cases:
            directory = campaign/specification['name']
            directory.mkdir()
            obs, truth, generated = generate(directory, config, specification['n'], cells()['B'],
                specification['load'], specification['amplitude'], .002, 1103, 'cycle',
                sample_rate_hz=35)
            del truth  # Harness state is not a backend input or an error target.
            if generated['status'] != 'generated':
                raise AssertionError(generated)
            settings = SimpleNamespace(field_refresh_seconds=specification['cadence_s'])
            source = 'parity/' + specification['name']
            banks = [kind(campaign, config, source, 'h7-parity', 35, settings)
                     for kind in (BaselineH7, H7Backend)]
            checked = set()
            boundaries = dict(initial=0, advance=0, scheduled_refresh=0,
                              partial_buffer_overflow=0, explicit_flush=0, explicit_refresh=0)

            def check(boundary):
                a, b = banks
                arrays = dict(carrier=(bytes(a.context), bytes(b.context)),
                    native=(a.native.snapshot(), b.native.snapshot()),
                    root=(a.field.root, b.field.root), state=(a.field.state, b.field.state),
                    live_state=(a.live_state, b.live_state), w=(a.w, b.w),
                    pending=(a.pending_rows[:a.buffered], b.pending_rows[:b.buffered]),
                    mean=(a.mean, b.mean), prior_root=(a.prior_root, b.prior_root))
                for name, (left, right) in arrays.items():
                    if isinstance(left, np.ndarray):
                        equal = left.dtype == right.dtype and left.shape == right.shape and left.tobytes() == right.tobytes()
                    else:
                        equal = left == right
                    if not equal:
                        raise AssertionError((specification['name'], boundary, a.live_count, name))
                    checked.add(name)
                for name, left, right in [
                    ('field_count', a.field.count, b.field.count),
                    ('native_count', a.native.count, b.native.count),
                    ('live_count', a.live_count, b.live_count),
                    ('buffered', a.buffered, b.buffered),
                    ('field_noise', a.field.noise, b.field.noise),
                    ('live_noise', a.noise, b.noise),
                    ('audit', a.audit, b.audit)]:
                    if left != right:
                        raise AssertionError((specification['name'], boundary, a.live_count, name))
                    checked.add(name)
                boundaries[boundary] += 1

            check('initial')
            first = 0
            while first < len(obs):
                length = min(8 if specification['partial'] and first == 0 else 16, len(obs)-first)
                overflow = banks[0].buffered + length > 4096
                outcomes = [bank.advance(first, obs[first:first+length]) for bank in banks]
                # Status labels are deliberately new; existing numerical readouts
                # and solver diagnostics must remain equal.
                read_before, diagnostic_before = outcomes[0]
                read_after, diagnostic_after = outcomes[1]
                read_after = {k: v for k, v in read_after.items() if k != 'estimate_status'}
                for label, left, right in [('readout', read_before, read_after),
                                            ('diagnostic', diagnostic_before, diagnostic_after)]:
                    if json.dumps(left, sort_keys=True) != json.dumps(right, sort_keys=True):
                        raise AssertionError((specification['name'], first, label))
                    checked.add(label)
                first += length
                check('advance')
                if overflow:
                    check('partial_buffer_overflow')
                if first % banks[0].interval == 0:
                    check('scheduled_refresh')
            for bank in banks:
                bank._flush_field()
            check('explicit_flush')
            refresh = [bank._refresh('scheduled') for bank in banks]
            if (refresh[0] is None) != (refresh[1] is None):
                raise AssertionError('refresh decision mismatch')
            check('explicit_refresh')
            if banks[1].audit['accepted'] == 0:
                raise AssertionError('no accepted refresh in case')
            if specification['partial'] and not boundaries['partial_buffer_overflow']:
                raise AssertionError('overflow boundary not exercised')
            results.append(dict(**specification, rate_Hz=35, cell='B', noise_seed=1103,
                noise_V=.002, observation_sha256=hashlib.sha256(obs.tobytes()).hexdigest(),
                duration_s=float(obs[:,0].sum()), observation_count=len(obs),
                boundaries=boundaries, checked=sorted(checked), bitwise_equal=True,
                refresh_audit=banks[1].audit,
                current_publication_status=banks[1].publication_status()))
        binary_identities = dict(zip(('response', 'tangent'), map(identity, binaries)))
    if sources != {name: identity(ROOT/name) for name in dependencies}:
        raise RuntimeError('source changed during comparison; rerun after edits settle')
    return dict(schema='h7_transaction_normal_path_parity_v1', status='passed',
        source_revision=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        source_identities=sources, baseline_receipt=identity(baseline_path),
        baseline_origin=baseline_origin,
        baseline_source_revision=baseline['source_revision'],
        baseline_source_identities=baseline['source_identities'],
        binary_identities=binary_identities, cases=results,
        numpy_version=np.__version__, python_version=sys.version,
        command='OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 python3 -B experiments/h7_transaction_status_001/check_parity.py',
        comparison='Archived backend and MixedField; shared unchanged H7 Native and Compressed; identical observations and public prior.',
        limits=['Three short synthetic stationary-cell controls; no fault injection in this receipt.',
                'Finite byte parity at checked boundaries does not prove universal equivalence.',
                'New publication/status metadata excluded from baseline equality by design.',
                'No coverage, aging, lifetime, resource or firmware readiness claim.',
                'No timing or optimization claim; this numerical evidence is not peer review.'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT/'provenance/h7_transaction_status_001/parity.json')
    args = parser.parse_args()
    if args.out.exists():
        raise SystemExit('Refusing to overwrite existing evidence; select a new --out path.')
    receipt = run()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2, allow_nan=False)+'\n')
    print(json.dumps(dict(status=receipt['status'], cases=len(receipt['cases']), receipt=str(args.out))))
