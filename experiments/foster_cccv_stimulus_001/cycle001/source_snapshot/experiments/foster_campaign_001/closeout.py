"""Bind preserved evidence and finite campaign/telemetry checks to this extension."""
import json
from pathlib import Path
import numpy as np
from .run import ident, ROOT, HERE, BASE
from experiments.structured_joint_001.qualify import write


def main():
    checks=[]
    def check(name, ok):
        checks.append(dict(name=name,passed=bool(ok)))
        if not ok:
            raise AssertionError(name)
    previous=json.loads((BASE/'verification.json').read_text())['artifacts']
    for name,expected in previous.items():
        check('preserved/'+name,ident(ROOT/name)==expected)
    smoke=HERE/'smoke001'
    manifest=json.loads((smoke/'manifest.json').read_text())['artifacts']
    for name,expected in manifest.items():
        check('smoke/'+name,ident(smoke/name)==expected)
    # Executed campaign implementation remains the same; later additions are
    # documentation, receipt code and extra tests, not retuning of this run.
    for name in ['run.py','stimulus.py','telemetry.py','plot.py']:
        check('executed_source/'+name,ident(HERE/name)==ident(smoke/'source_snapshot'/HERE.relative_to(ROOT)/name))
    summary=json.loads((smoke/'summary.json').read_text())
    check('eight completed cases',summary['status']=='completed' and len(summary['cases'])==8)
    for r in summary['cases']:
        case=smoke/r['directory']
        check(r['directory']+'/plots',r['plots']=='completed')
        truth=np.load(case/'truth.npy',mmap_mode='r')
        for kind,arm in r['arms'].items():
            check(r['directory']+'/'+kind+'/source',arm['received_records']==arm['retired_records']==1260 and arm['pending_records']==0)
            count=arm['outputs'];rows=np.load(case/(kind+'_trace.npy'),mmap_mode='r')[:count]
            check(r['directory']+'/'+kind+'/finite',np.isfinite(rows).all())
            check(r['directory']+'/'+kind+'/chronology',np.all(np.diff(rows[:,0])>0) and rows[-1,0]==1260)
            csv=np.loadtxt(case/(kind+'_trace.csv'),delimiter=',',skiprows=1)
            check(r['directory']+'/'+kind+'/CSV',np.array_equal(csv[:,:39],rows) and
                  np.array_equal(csv[:,39:],truth[rows[:,0].astype(int)-1]))
    for name in ['signals','states','parameters_reference','parameters_effective','capacitances','errors']:
        check('zoom/'+name,all((HERE/'zoom001'/(name+'.'+ext)).is_file() for ext in ['png','pdf']))
    receipt=dict(status='runner_verified_accuracy_and_aging_unqualified',
        source_revision=json.loads((smoke/'reservation.json').read_text())['source_revision'],
        harness_tests=dict(command='OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -B -m unittest experiments.foster_campaign_001.test_campaign -v',
                           tests=10,status='passed',basis='Executed final test suite in this development session; tests include failed-case continuation and plot extrema'),
        parent_qualification=json.loads((smoke/'qualification.json').read_text())['passing_checks'],
        preserved_parent_artifacts=len(previous),smoke_cases=8,simulated_seconds_per_case=36,
        arms=16,records_per_arm=1260,plots_per_case=6,
        max_smoke_encoding_Q_percent=max(r['encoding_difference']['Q_percent'] for r in summary['cases']),
        next='Use local long campaigns to inspect nonlinear history/rolling uncertainty and encoding sensitivity; no estimator repair or tuning in this extension',
        checks=checks,passing_checks=len(checks),
        numeric_logging_MB_per_hour_both=126000*247/1e6,
        history_two_messages_plus_float32_token_B=6269,
        complete_SRAM_B=None,coverage_validated=False,aging_implemented=False)
    write(HERE/'summary.json',receipt)
    artifacts={str(f.relative_to(ROOT)):ident(f) for f in sorted(HERE.rglob('*'))
               if f.is_file() and '__pycache__' not in f.parts}
    write(HERE/'verification.json',dict(status='passed',artifacts=artifacts,
          scope='Current extension source, preserved eight-case execution and zoom; parent artifacts independently verified. Finite harness checks only.'))
    print(json.dumps(dict(checks=len(checks),artifacts=len(artifacts),parent_artifacts=len(previous))))


if __name__=='__main__':
    main()
