"""Matched H response representations at frozen anchors; never refit."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from experiments.joint_precision_attribution_001 import metrics as m
from .basis import HField, build
from .reference import envelope as h_envelope
from experiments.rc_sensitivity_basis_001.basis import SensitivityField
from experiments.response_basis_attribution_001.basis import BasisField
from experiments.hysteresis_refinement_001.field import MixedField, features_jacobian, transported
from experiments.foster_campaign_001.backend import ROOT, identity
from experiments.foster_campaign_001.compact import StimulusStream
from experiments.foster_feedback_001.estimator import Model
from experiments.h7_history_quality_001.history import source_receipt, verify_sources, write


ARMS = ['TaylorRC_H2','TaylorRC_c22','TaylorRC_tensor','TaylorRC_TaylorH2','TaylorRC_H7','R5_H7']


def field(name, reg, directory, source, binaries):
    if name == 'R5_H7':
        return MixedField(reg['config'], reg['center'], 1., 7, directory/'response/response.so', source)
    kind = name.removeprefix('TaylorRC_')
    mode = 'derivative' if kind == 'TaylorH2' else 'collocation'
    return HField(reg['config'], reg['center'], directory/'response_taylor2/response.so',
                  binaries[mode], kind, source)


def verify(path, expected, bindings):
    actual = identity(path)
    if actual != expected:
        raise ValueError('input identity changed: '+str(path))
    bindings[str(path)] = actual


def measure(directory, only_loads, binaries):
    bindings = {}
    # Committed compact registration/manifest anchor the local dependency chain.
    for suffix, filename in [('registration', 'registration.json'), ('summary', 'summary.json')]:
        frozen = ROOT/'provenance/rc_sensitivity_basis_001'/f'{directory.name}_{suffix}.json'
        verify(directory/filename, identity(frozen), bindings)
        bindings[str(frozen)] = identity(frozen)
    reg = json.loads((directory/'registration.json').read_text())
    verify_sources(reg['source'])
    for path, expected in reg['new_artifacts'].items():
        verify(ROOT/path, expected, bindings)
    verify(directory/'response/response.so', reg['response_binary'], bindings)
    verify(directory/'response_taylor2/response.so', reg['sensitivity_binaries']['taylor2'], bindings)
    cbinary = directory/'backend_c/estimator.so'
    verify(cbinary, reg['direct_binary'], bindings)
    mean, L = np.array(reg['prior_mean']), np.array(reg['prior_root'])
    model = Model(cbinary, reg['config'])
    manifest = json.loads((directory/'summary.json').read_text())
    results = []
    for case in manifest['cases']:
        path = directory/case['file'];verify(path, case['identity'], bindings)
        data = json.loads(path.read_text())
        if data['load'] not in only_loads:
            continue
        baseline = Path(data['baseline_result']['path'])
        verify(baseline, data['baseline_result']['identity'], bindings)
        old = json.loads(baseline.read_text());recipe = old['recipe'];source = old['source_id']
        if len(data['prefixes']) != 1:
            raise ValueError('registered study expects one prefix per saved run')
        prefix = data['prefixes'][0]
        sp = Path(prefix['snapshot']['path']);verify(sp, prefix['snapshot']['identity'], bindings)
        with np.load(sp, allow_pickle=False) as snap:
            saved = {k:snap[k].copy() for k in snap.files}
        generators = {name:field(name,reg,directory,source,binaries) for name in ARMS}
        final = generators
        anchors = {}
        for name in ['direct', 'Taylor2_H2']:
            fit = prefix['fits']['arms'][name]
            if 'selected' not in fit:
                raise ValueError('registered anchor has no selected fit')
            x = np.array(fit['selected']['x']);w = np.array(fit['selected']['w'])
            if not np.allclose(x, mean+L@w, atol=1e-12, rtol=0):
                raise ValueError('anchor coordinate identity')
            a, shape, B, K = m.coordinates(x, L)
            anchors[name] = dict(x=x, a=a, shape=shape, B=B, K=K, end=x.copy(), F=np.eye(16),
                fit_status=fit['status'], roots={arm:np.zeros((51,51)) for arm in ARMS},
                feature={arm:final[arm].features(x) for arm in ARMS},
                Dfeature={arm:features_jacobian(final[arm], x)@B for arm in ARMS},
                other_error={arm:0. for arm in ARMS}, residual_split_error={arm:0. for arm in ARMS})
        stream = StimulusStream(reg['config'], recipe['cell'], recipe['case'], recipe['settings'])
        digest = hashlib.sha256();imax = 0.;sigma_sum = 0.
        while stream.index < prefix['records']:
            first = stream.index;obs, _, _ = stream.read(min(1024,prefix['records']-first))
            if stream.failure or not len(obs):
                raise ValueError('frozen input regeneration failed')
            digest.update(obs.astype('<f8',copy=False).tobytes())
            imax = max(imax, float(max(abs(obs[:,1]))));sigma_sum += float(sum(obs[:,4]**-2))
            rows = {name:g.update(first,obs,source,return_rows=True) for name,g in generators.items()}
            for a in anchors.values():
                v, J, end, F = model.evaluate(a['end'],obs)
                Jx = (J@a['F'])/obs[:,4,None]
                Jc = Jx@a['B'];Jw = Jx@L;r = (v-obs[:,3])/obs[:,4]
                for name in ARMS:
                    delta = rows[name]@a['Dfeature'][name]-Jc
                    dr, dh = m.separate(delta)
                    er = dr[:,:11]@a['a'];eh = dh[:,:11]@a['a']
                    a['other_error'][name] = max(a['other_error'][name],float(np.max(abs(delta[:,m.OTHER]))))
                    control = rows[name]@a['feature'][name]-r-er-eh
                    a['residual_split_error'][name] = max(a['residual_split_error'][name],float(max(abs(control))))
                    a['roots'][name] = m.append(a['roots'][name],np.column_stack((Jw,dr,dh,r,er,eh)))
                a['end'], a['F'] = end,F@a['F']
        if digest.hexdigest() != prefix['observation_sha256']:
            raise ValueError('frozen observation hash changed')
        for name, oldname in [('TaylorRC_H2','Taylor2_H2'),('R5_H7','R5_H7')]:
            if not np.array_equal(generators[name].state, saved[oldname+'_state']):
                raise ValueError('frozen control endpoint response state mismatch: '+name)
        for anchor,a in anchors.items():
            result = dict(run=str(directory),load=data['load'],records=prefix['records'],
                observation_sha256=digest.hexdigest(),anchor=anchor,fit_status=a['fit_status'],
                x=a['x'],Imax_A=imax,arms={})
            for name in ARMS:
                try:
                    compressed = transported(final[name], a['x'])
                except ValueError as error:
                    compressed = str(error)
                envelope = m.rc_envelope(a['a'],a['shape'],reg['center'],imax) if name != 'R5_H7' else None
                detail, M = m.analyze(a['roots'][name],a['K'],L,a['x'],(a['end'],a['F']),
                    compressed,model,envelope,sigma_sum)
                # New fields are checked against their independent joint factor reduction;
                # unchanged controls additionally use original saved factors.
                oldname = {'TaylorRC_H2':'Taylor2_H2','R5_H7':'R5_H7'}.get(name)
                root = saved[oldname+'_root'] if oldname else final[name].root
                Jfactor = root@a['Dfeature'][name]@a['K']
                relative = (Jfactor@M).T@(Jfactor@M)+M.T@M
                ev = np.linalg.eigvalsh(relative)
                now = np.array(detail['variants']['combined']['relative_precision_eigenvalues'])
                control = float(max(abs(ev-now))/max(1.,max(abs(ev))))
                detail['controls'] = dict(other_column_max_whitened_defect=a['other_error'][name],
                    residual_partition_max_whitened_defect=a['residual_split_error'][name],
                    factor_relative_eigenvalue_discrepancy=control,
                    frozen_control_name=oldname, response_state_bitwise_match=True if oldname else None)
                if control > 1e-7 or a['other_error'][name] > 1e-7 or a['residual_split_error'][name] > 1e-7:
                    raise AssertionError('partition/factor numerical control')
                if name == 'TaylorRC_TaylorH2':
                    bc,vbound = h_envelope(a['a'],a['shape'],reg['center'])
                    eta_upper = np.sqrt(sigma_sum)*np.linalg.norm(bc@abs(a['K']@M))
                    measured = detail['variants']['H_only']['eta']
                    if measured > eta_upper+1e-8:raise AssertionError('H6 envelope consistency')
                    detail['H6_envelope'] = dict(voltage_error_bound_V=float(vbound),
                        eta_upper=float(eta_upper),epsilon_upper=float(2*eta_upper+eta_upper*eta_upper),
                        measured_eta=measured,scope='Conditional floating diagnostic, not runtime certificate')
                detail['storage'] = final[name].storage()
                result['arms'][name] = detail
            results.append(result)
            print(json.dumps(dict(stage='anchor_complete',run=directory.name,load=data['load'],anchor=anchor)),flush=True)
    return dict(run=str(directory),bindings=bindings,anchors=results)


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--runs',nargs='+',type=Path,default=[Path('experiments/rc_sensitivity_basis_001/pilot001'),Path('experiments/rc_sensitivity_basis_001/full001')])
    parser.add_argument('--loads',nargs='+',default=['rest','multiscale','embedded'],choices=['rest','multiscale','embedded'])
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--build-dir',type=Path,required=True)
    args = parser.parse_args()
    if args.out.exists():raise ValueError('refuse overwrite')
    if args.build_dir.exists():raise ValueError('refuse build directory overwrite')
    binaries={mode:build(args.build_dir/mode,mode) for mode in ['collocation','derivative']}
    sources = source_receipt()
    artifacts = {str(p.relative_to(ROOT)):identity(p) for p in (ROOT/'specifications/hysteresis_sensitivity_basis_001').glob('*.md')}
    artifacts['experiments/hysteresis_sensitivity_basis_001/response.c']=identity(ROOT/'experiments/hysteresis_sensitivity_basis_001/response.c')
    runs = [measure(directory,args.loads,binaries) for directory in args.runs]
    verify_sources(sources)
    for path,expected in artifacts.items():
        if identity(ROOT/path) != expected:raise ValueError('protocol changed')
    write(args.out,dict(schema='hysteresis_sensitivity_basis_v1',status='completed_same_anchor_diagnostic',
        source=sources,protocol=artifacts,binaries={k:identity(v) for k,v in binaries.items()},runs=runs,
        scope='Saved correlated synthetic prefixes, no refits/truth/coverage. Float diagnostics, no interval certificate or promotion.',
        storage=dict(Taylor_factor_B=4760,Taylor_partial_subtotal_B=5168,new_runtime_bytes=0,
                     diagnostic_augmented_root_B=51*51*8,diagnostic_chunk_augmented_rows_B=1024*51*8,
                     scope='Diagnostic arrays are desktop scratch, not a firmware allocation; complete memory unqualified')))


if __name__ == '__main__':main()
