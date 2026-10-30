"""Verify saved pipeline evidence and summarize without repeating long runs."""
import ast
import json
from pathlib import Path
import numpy as np
from experiments.structured_joint_001.qualify import ident,write

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]


def read(p):return json.loads(p.read_text())


def main():
    checks=[]
    def check(name,ok):checks.append(dict(name=name,passed=bool(ok)))
    for name in ['development001','four_hour001']:
        run=HERE/name;reservation=read(run/'reservation.json')
        for p,expected in reservation['preserved_artifacts'].items():check(name+'/preserved/'+p,ident(ROOT/p)==expected)
        for p,expected in reservation['source_identities'].items():
            check(name+'/source/'+p,ident(ROOT/p)==expected)
            check(name+'/snapshot/'+p,ident(run/'source_snapshot'/p)==expected)
        for p,expected in read(run/'manifest.json')['artifacts'].items():check(name+'/artifact/'+p,ident(run/p)==expected)
        qualification=read(run/'qualification.json')
        check(name+'/qualification',qualification['status']=='passed' and qualification['passing_checks']==55)
        check(name+'/native_build',read(run/'build.json')['returncode']==0)
        r=read(run/'result.json')
        for kind,a in r['arms'].items():
            check(name+'/'+kind+'/source_consumption',a['status']=='completed' and
                  a['received_records']==a['retired_records']==r['records_requested'] and a['pending_records']==0)
            trace=np.load(run/(kind+'_trace.npy'))
            check(name+'/'+kind+'/outputs',len(trace)==a['all']['outputs']==a['generation'])
            check(name+'/'+kind+'/chronology',np.all(np.diff(trace[:,0])>0) and trace[-1,0]==r['records_requested'])
    run=HERE/'four_hour001';r=read(run/'result.json');a=r['arms']['float32']
    truth=np.load(run/'truth.npy',mmap_mode='r');audit=read(run/'retained_audit001/result.json');audit_plan=read(run/'retained_audit001/plan.json')
    check('audit_observation_identity',ident(run/'observations.npy')==audit_plan['observation_identity'])
    check('audit_binary_identity',ident(run/'model.so')==audit_plan['model_binary_identity'])
    check('audit_source_identity',ident(HERE/'retained_audit.py')==audit_plan['audit_source_identity'])
    check('audit_truth_isolation',audit['truth_reads']==0 and not audit['streaming_state_modified'])
    check('encoding_practical_scales',a['max_encoding_Q_percent']<=.5 and a['max_encoding_SOC_pp']<=.5)
    for p in HERE.glob('*.py'):ast.parse(p.read_text(),filename=str(p));check('syntax/'+p.name,True)
    if any(not x['passed'] for x in checks):raise RuntimeError(json.dumps([x for x in checks if not x['passed']]))
    summary=dict(schema='continuous_foster_feedback_summary_v1',status='pipeline_complete_four_hour_run_complete_sustained_capacity_and_uncertainty_unqualified',
        branch=reservation['branch'],source_revision=reservation['source_revision'],
        targeted_checks=55,preserved_earlier_artifacts=len(reservation['preserved_artifacts']),
        records=504000,simulated_hours=4,retired_tokens_per_arm=31500,
        model='Continuous five-state11-parameter userFoster,+Hh,normalized dimensionlessgamma,knownlinearOCV and knownArrheniuslaws,stationaryreferenceparameters',
        implementation='Experimental continuous rolling-boundary producer and genericGaussianfeedback adapter; legacyC rollingengine unchanged',
        history='Prior-free centeredQR likelihood plus joint first-order deterministictransport; rootprioronce and disjointsource retirement',
        encoding='float64 orfloat32 token coefficients; no physical parameter lattice or learnedshape dictionary',
        arms={k:{key:v[key] for key in ['status','retired_records','generation','final','all','phase','stops','storage']} for k,v in r['arms'].items()},
        max_encoding_Q_percent=a['max_encoding_Q_percent'],max_encoding_SOC_pp=a['max_encoding_SOC_pp'],
        run_wall_s=r['run_wall_s'],run_cpu_s=r['run_cpu_s'],preplot_total_wall_s=r['total_wall_s'],
        audit=dict(Q_error_percent=100*(audit['Q']/truth[-1,0]-1),SOC_error_pp=100*(audit['SOC']-truth[-1,2]),
                   status=audit['status'],wall_s=audit['wall_s'],scope=audit['scope']),
        command='OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -B -m experiments.foster_feedback_001.run --hours 4',
        next='Diagnose local nonlinear likelihood/transport projection, rolling refinement and uncertainty against retained evidence; preserve currentrun before anyrepair. Do not polish already-small coefficientencoding errors.',
        coverage_validated=False,aging_implemented=False,complete_SRAM_B=None,lifetime_qualified=False)
    write(HERE/'summary.json',summary)
    artifacts={str(p.relative_to(ROOT)):ident(p) for p in sorted(HERE.rglob('*'))
               if p.is_file() and '__pycache__' not in p.parts and p.name!='verification.json'}
    write(HERE/'verification.json',dict(status='passed',passing_checks=len(checks),checks=checks,artifacts=artifacts,
          scope='Evidence identities/source-once accounting and saved finite checks; scientific sustained-capacity/uncertainty limitations retained'))
    print(json.dumps(dict(status=summary['status'],checks=len(checks),artifacts=len(artifacts),preserved=summary['preserved_earlier_artifacts'])))


if __name__=='__main__':main()
