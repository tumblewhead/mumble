"""Read compact summaries/checkpoint metadata; never modify or refit a campaign."""
import json
from pathlib import Path
import numpy as np
from experiments.foster_campaign_001.backend import identity
from experiments.foster_campaign_001.telemetry import PARAMETERS

RUN = Path('experiments/foster_campaign_001/run_20261101_071802_121297')
BASE = Path('experiments/h7_campaign_001/run72_001')
OUT = Path('provenance/h7_campaign_720h_001/comparison.json')

def read(path):
    return json.loads(path.read_text())

def main():
    if OUT.exists():
        raise FileExistsError(OUT)
    review = read(OUT.parent/'review.json')
    baseline = read(Path('provenance/h7_campaign_001/run72_review.json'))
    assert review['summary_identity'] == identity(RUN/'summary.json')
    rows = []
    for case, old in zip(review['cases'], baseline['cases']):
        assert case['case'] == old['case'] and case['scenario'] == old['scenario']
        directory = RUN/case['case']
        for name, expected in case['identities'].items():
            assert identity(directory/name) == expected
        entries = read(directory/'checkpoints/index.json')['checkpoints']
        oldentries = read(BASE/case['case']/'checkpoints/index.json')['checkpoints']
        oldmap = {e['sequence']: e for e in oldentries}
        common = max(e['sequence'] for e in entries if e['sequence'] in oldmap)
        entry = next(e for e in entries if e['sequence'] == common)
        current = directory/'checkpoints'/entry['file']
        previous = BASE/case['case']/'checkpoints'/oldmap[common]['file']
        assert identity(current) == {k:entry[k] for k in ('bytes','sha256')}
        assert identity(previous) == {k:oldmap[common][k] for k in ('bytes','sha256')}
        with np.load(current) as a, np.load(previous) as b:
            names = [k for k in a.files if not k.endswith('metadata')]
            raw_parity = all(np.array_equal(a[k],b[k]) for k in names)
            native_type = np.dtype([('factor','f8',(153,)),('anchor','f8',(16,)),
                                    ('source','u8'),('count','u8'),('magic','u8')],align=True)
            parity = True
            source_ids = {}
            for k in names:
                if k.endswith('__native'):
                    assert a[k].nbytes == b[k].nbytes == native_type.itemsize == 1376
                    ca=np.frombuffer(a[k].tobytes(),dtype=native_type)[0]
                    cb=np.frombuffer(b[k].tobytes(),dtype=native_type)[0]
                    parity = parity and all(np.array_equal(ca[f],cb[f]) for f in ('factor','anchor','count','magic'))
                    source_ids[k] = [int(cb['source']),int(ca['source'])]
                else:
                    parity = parity and np.array_equal(a[k],b[k])
            ma = json.loads(a['metadata'].tobytes()); mb = json.loads(b['metadata'].tobytes())
            parity = parity and ma['stimulus'] == mb['stimulus'] and ma['stats'] == mb['stats']
        # Metadata-only scan: counters bound onset to checkpoint intervals.
        timeline = []
        for e in entries:
            path = directory/'checkpoints'/e['file']
            assert identity(path) == {k:e[k] for k in ('bytes','sha256')}
            with np.load(path) as z:
                m = json.loads(z['metadata'].tobytes())
                timeline.append(dict(hours=e['sequence']/50/3600,stats=m['stats'],identity=e))
        row = dict(case=case['case'],scenario=case['scenario'],common_prefix_hours=common/50/3600,
                   common_prefix_estimator_state_stimulus_stats_exact=parity,raw_context_byte_parity=raw_parity,
                   native_source_ids_72_720=source_ids,arms={})
        with np.load(directory/'plot_summary.npz') as z:
            for arm, report in case['arms'].items():
                prior = old['arms'][arm]
                final = report['metrics']; n = final['outputs']
                first = {}
                for q in ('Q','SOC'):
                    for j,e in enumerate(timeline):
                        if e['stats'][arm]['all'][q+'_3sd_misses']:
                            first[q] = [timeline[j-1]['hours'] if j else 0, e['hours']]
                            break
                selected = []
                for target in (72,144,360,648,720):
                    e = min(timeline,key=lambda x:abs(x['hours']-target))
                    stat=e['stats'][arm]['all']
                    selected.append(dict(requested_hours=target,hours=e['hours'],
                        outputs=stat['outputs'],Q_misses=stat['Q_3sd_misses'],SOC_misses=stat['SOC_3sd_misses']))
                half = min(timeline,key=lambda x:abs(x['hours']-360))
                end_stats=timeline[-1]['stats'][arm]
                last_count=n-half['stats'][arm]['all']['outputs']
                late={}
                for t in (72,360,648):
                    mask=(z[arm+'_last']/50/3600>t)&(z[arm+'_count']>0)
                    late[str(t)]={q:[float(z[arm+'_low'][mask,i].min()),float(z[arm+'_high'][mask,i].max())]
                                 for q,i in [('Q_error_percent',-4),('SOC_error_pp',-3)]}
                errors=report['final_reference_parameter_error_percent']
                worst=max(PARAMETERS[1:8],key=lambda k:abs(errors[k]))
                row['arms'][arm]=dict(final_Q_percent=final['final_Q_percent'],final_SOC_pp=final['final_SOC_pp'],
                    Q_local_sd_ratio_720_to_72=report['final_Q_local_SD_percent']/prior['final_Q_local_SD_percent'],
                    Q_error_local_SD=report['final_Q_error_local_SD'],Q_misses=final['Q_3sd_misses'],SOC_misses=final['SOC_3sd_misses'],
                    Q_miss_fraction=final['Q_3sd_misses']/n,SOC_miss_fraction=final['SOC_3sd_misses']/n,
                    additional_Q_misses_after_72=final['Q_3sd_misses']-prior['metrics']['Q_3sd_misses'],
                    additional_SOC_misses_after_72=final['SOC_3sd_misses']-prior['metrics']['SOC_3sd_misses'],
                    refresh_rejections_after_72=report['field_history']['rejected']-prior['field_history']['rejected'],
                    final_max_RC_percent=report['final_max_abs_RC_error_percent'],worst_final_RC_parameter=worst,
                    previous_max_RC_percent=prior['final_max_abs_RC_error_percent'],
                    first_miss_checkpoint_interval_hours=first,cumulative_misses_at_checkpoints=selected,
                    last_half_SOC_misses=final['SOC_3sd_misses']-half['stats'][arm]['all']['SOC_3sd_misses'],
                    last_half_SOC_miss_fraction=(final['SOC_3sd_misses']-half['stats'][arm]['all']['SOC_3sd_misses'])/last_count,
                    SOC_misses_by_current={k:end_stats[k]['SOC_3sd_misses'] for k in ('current_zero','current_nonzero')},
                    late_ranges=late)
        rows.append(row)
    aggregates={}
    for arm in ('tangent64','tangent_h7'):
        reports=[c['arms'][arm] for c in review['cases']];n=sum(r['outputs'] for r in reports)
        aggregates[arm]=dict(outputs=n,Q_misses=sum(r['metrics']['Q_3sd_misses'] for r in reports),
            SOC_misses=sum(r['metrics']['SOC_3sd_misses'] for r in reports),
            max_final_Q_percent=max(abs(r['metrics']['final_Q_percent']) for r in reports),
            max_final_SOC_pp=max(abs(r['metrics']['final_SOC_pp']) for r in reports),
            max_final_RC_percent=max(r['final_max_abs_RC_error_percent'] for r in reports))
        for q in ('Q','SOC'):aggregates[arm][q+'_miss_fraction']=aggregates[arm][q+'_misses']/n
    result=dict(status='reviewed',run=str(RUN),source_revision=review['source_revision'],
        summary_identity=identity(RUN/'summary.json'),review_identity=identity(OUT.parent/'review.json'),
        baseline_review_identity=identity(Path('provenance/h7_campaign_001/run72_review.json')),
        bin_policy='Late ranges include complete 0.36-hour bins intersecting the requested interval; extrema are actual recorded output errors, not ratios of separate extrema.',
        first_miss_policy='Onset bounded by consecutive checkpoint counters, not an exact event time.',
        scope='Stationary cells with cyclic temperature; correlated outputs are descriptive diagnostics, not independent coverage trials.',
        prefix_policy='Compare every state array and FTContext factor, anchor, count and magic; source identity differs with the duration-bearing stimulus recipe and is reported separately. Raw-byte comparison is also retained.',
        aggregates=aggregates,cases=rows)
    OUT.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(aggregates,indent=2))
    for c in rows:
        a=c['arms']['tangent_h7']
        print(c['case'],'prefix exact',c['common_prefix_estimator_state_stimulus_stats_exact'],
              'first misses',a['first_miss_checkpoint_interval_hours'],'late miss fraction',a['last_half_SOC_miss_fraction'])

if __name__=='__main__':
    main()
