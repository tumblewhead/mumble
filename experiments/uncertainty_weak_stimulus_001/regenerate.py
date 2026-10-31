"""Harness-only regeneration using the original worktree and archived binaries.

Invoke by file path: --source-root controls imports BEFORE any campaign import.
Only observations and endpoint messages are exported to inference; truth scoring
is a separate file. Original campaigns and their sources are never modified.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--source-root', type=Path, required=True)
    p.add_argument('--case', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--weak', action='store_true')
    args = p.parse_args()
    sys.path.insert(0, str(args.source_root.resolve()))
    import numpy as np
    from experiments.foster_campaign_001.compact import CHUNK, restore_checkpoint, atomic_json
    from experiments.foster_campaign_001.backend import identity

    case, out = args.case.resolve(), args.out.resolve()
    run = case.parent
    settings = json.loads((run/'campaign_plan.json').read_text())['configuration']
    config = json.loads((run/'calibration.json').read_text())
    scenario_file = json.loads((case/'scenario.json').read_text())
    scenario = {k: scenario_file[k] for k in ('cell', 'load', 'noise_v', 'seed', 'load_seed') if k in scenario_file}
    entries = json.loads((case/'checkpoints/index.json').read_text())['checkpoints']
    assert entries[0]['sequence'] == 0
    stream, banks, meta = restore_checkpoint(case, entries[0], config, scenario_file['cell_definition'], scenario, settings)
    rate = stream.rate
    target = round(4*3600*rate)
    interval = banks['field64'].interval
    n = target if args.weak else target//interval*interval
    last_refresh = n//interval*interval
    end = n+round(.5*3600*rate)
    # Validate a saved checkpoint after the heldout segment when one exists.
    later = next((e['sequence'] for e in entries if e['sequence'] >= end), end)
    stop = max(end, later)
    out.mkdir(parents=True, exist_ok=False)
    obsfile = np.lib.format.open_memmap(out/'observations.npy', mode='w+', dtype='float64', shape=(end,5))
    atomic_json(out/'registration.json', dict(source_case=str(case), source_root=str(args.source_root.resolve()),
        source_binding=meta['binding'], original_source_id=meta['source_id'], fit_records=n,
        holdout_records=end-n, last_refresh_records=last_refresh, validation_stop_records=stop, sample_rate_Hz=rate,
        new_continuation=args.weak, continuation='same absolute schedule and RNG state; no resets',
        configuration=settings, command=sys.argv))
    atomic_json(out/'calibration.json', config)
    captured = {}
    last_refresh_arrays = {}
    refreshes = []
    field = banks['field64']
    original_replace = field._replace

    def recording_replace(sequence):
        before = field.full_message().copy() if sequence in (n,last_refresh) else None
        accepted = original_replace(sequence)
        after = field.full_message()
        refreshes.append(dict(sequence=sequence, accepted=accepted, Q_Ah=float(np.exp(after[5])),
                              SOC=float(after[0]), Q_log_sd=float(np.linalg.norm(after[16:272].reshape(16,16)[5]))))
        if sequence == n:
            captured['field_pre_refresh'] = before
            captured['field_post_refresh'] = after.copy()
        if sequence == last_refresh:
            last_refresh_arrays.update(before=before,after=after.copy(),origin_w=field.w.copy())
        return accepted

    field._replace = recording_replace
    checks = []
    truth_endpoint = None
    began = time.perf_counter()
    checkpoint_map = {e['sequence']: e for e in entries if 0 < e['sequence'] <= stop}
    while stream.index < stop:
        first = stream.index
        next_checkpoint = min((s for s in checkpoint_map if s > first), default=stop)
        obs, truth, _ = stream.read(min(CHUNK, stop-first, next_checkpoint-first))
        if stream.failure or len(obs) == 0:
            raise RuntimeError(('plant regeneration failed', stream.failure))
        upto = min(len(obs), max(0, end-first))
        if upto:
            obsfile[first:first+upto] = obs[:upto]
        if first < n <= stream.index:
            truth_endpoint = truth[n-first-1].copy()
        # No estimator work after the training prefix; later checkpoint validates
        # physical/controller/RNG chronology independently of fitting.
        for offset in range(0, min(len(obs), max(0,n-first)), 16):
            rows = obs[offset:offset+16]
            for bank in banks.values():
                bank.advance(first+offset, rows)
            if first+offset+len(rows) == n:
                for kind, bank in banks.items():
                    captured[kind] = bank.full_message().copy()
                captured['field_origin_w'] = field.w.copy()
                captured['field_counts'] = field.counts()
        if stream.index in checkpoint_map:
            entry = checkpoint_map[stream.index]
            saved_stream, saved_banks, _ = restore_checkpoint(case, entry, config, scenario_file['cell_definition'], scenario, settings)
            check = dict(sequence=stream.index, identity=entry,
                         stimulus_exact=(stream.snapshot() == saved_stream.snapshot()))
            if stream.index <= n:
                check['messages_exact'] = {k: bool(np.array_equal(b.full_message(), saved_banks[k].full_message())) for k,b in banks.items()}
                check['field_arrays_exact'] = {k: bool(np.array_equal(v,saved_banks['field64'].checkpoint_arrays()[k]))
                                               for k,v in field.checkpoint_arrays().items()}
            checks.append(check)
            atomic_json(out/'checkpoint_checks.json', checks)
            if not check['stimulus_exact'] or not all(check.get('messages_exact',{}).values()) or not all(check.get('field_arrays_exact',{}).values()):
                raise RuntimeError(('regeneration mismatch', check))
            print(json.dumps(dict(checkpoint_records=stream.index, checks='exact', wall_s=time.perf_counter()-began)), flush=True)
    obsfile.flush()
    arrays = {k:v for k,v in captured.items() if isinstance(v,np.ndarray)}
    np.savez(out/'messages.npz', **arrays)
    np.savez(out/'last_refresh.npz', **last_refresh_arrays)
    atomic_json(out/'truth_for_postfit_only.json', dict(endpoint=truth_endpoint.tolist(),
        reference_parameters=scenario_file['cell_definition']['parameters'], sequence=n))
    atomic_json(out/'refreshes.json', refreshes)
    atomic_json(out/'regeneration.json', dict(status='validated', fit_records=n, holdout_records=end-n,
        last_refresh_records=last_refresh,last_refresh=identity(out/'last_refresh.npz'),
        observations=identity(out/'observations.npy'), messages=identity(out/'messages.npz'),
        checkpoint_checks=checks, field_counts=captured['field_counts'], wall_s=time.perf_counter()-began,
        semantics='Same-prefix saved-source replay from origin. Weak future newly generated; no full truth/trace arrays.',
        source_case=str(case), sample_rate_Hz=rate))
    print('Regeneration: '+str(out/'regeneration.json'), flush=True)


if __name__ == '__main__':
    main()
