"""Verify the contract artifacts and earlier evidence without rerunning fits."""
import ast
import json
from pathlib import Path
from experiments.structured_joint_001.qualify import ident, write

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]


def read(p):return json.loads(p.read_text())


def main():
    reservation=read(HERE/'qualification001/reservation.json');result=read(HERE/'qualification001/result.json')
    checks=[]
    def check(name,ok):checks.append(dict(name=name,passed=bool(ok)))
    for path,expected in reservation['preserved_artifacts'].items():check('preserved/'+path,ident(ROOT/path)==expected)
    for path,expected in reservation['source_identities'].items():
        check('source/'+path,ident(ROOT/path)==expected)
        check('snapshot/'+path,ident(HERE/'qualification001/source_snapshot'/path)==expected)
    check('qualification',result['status']=='passed' and result['passing_checks']==143 and not result['failed_checks'])
    for p in HERE.glob('*.py'):ast.parse(p.read_text(),filename=str(p));check('syntax/'+p.name,True)
    contract=read(HERE/'contract.json');model=read(HERE/'model.json')
    check('five_states',len(model['dynamic_states'])==5)
    check('eleven_parameters',len(model['learned_parameters'])==11)
    check('gamma_units',model['units']['gamma_plus']==model['units']['gamma_minus']=='dimensionless')
    check('model_binding',contract['model_binding']['normative_model']=='model.json')
    if any(not c['passed'] for c in checks):raise RuntimeError(json.dumps([c for c in checks if not c['passed']]))
    summary=dict(schema='mumble.evidence_feedback.receipt.v1',status='contract_and_finite_protocol_controls_complete',
        branch=reservation['branch'],source_revision=reservation['source_revision'],
        contract='specifications/evidence_feedback_001/contract.json',model='specifications/evidence_feedback_001/model.json',
        targeted_checks=result['passing_checks'],earlier_artifacts_preserved=len(reservation['preserved_artifacts']),
        adopted_user_model=dict(states=5,learned_parameters=11,voltage_hysteresis_sign='+Hh',
                               normalized_throughput='abs(I)*dt/(3600*Q_Ah)',gamma_units='dimensionless'),
        ownership='EstimateView is reporting only; EvidenceToken owns a disjoint prior-free retirement interval; FeedbackMessage owns one root prior plus the retired prefix',
        semantics='Marginal joint boundary kernel/message; no posterior-as-measurement, repeated prior, hidden aging rate, or test-rig input in compressor',
        OCV='Nearly linear reference with explicit calibration/residual support; unknownslope/capacity/normalizedhysteresis scaling ambiguity is tested',
        storage=contract['storage_estimates'],
        implemented='Pure generic transaction/ownership protocol plus separate analytic qualification backend',
        not_implemented=['Foster evidence-token producer','C rolling feedback adapter','nonlinear compressed representation','Arrhenius forward implementation','parameter-drift learner','completeSRAM layout','power-loss durability'],
        next=contract['next_gate'],production_changed=False,physical_coverage_validated=False,lifetime_qualified=False,
        commands=['OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -B -m specifications.evidence_feedback_001.qualification',
                  'python3 -B -m specifications.evidence_feedback_001.closeout'])
    write(HERE/'summary.json',summary)
    artifacts={str(p.relative_to(ROOT)):ident(p) for p in sorted(HERE.rglob('*'))
               if p.is_file() and '__pycache__' not in p.parts and p.name!='verification.json'}
    write(HERE/'verification.json',dict(status='passed',passing_checks=len(checks),checks=checks,artifacts=artifacts,
          scope='Contract identity, preserved earlier evidence, model binding, syntax and saved finite qualification; no physical run'))
    print(json.dumps(dict(status=summary['status'],targeted_checks=summary['targeted_checks'],
                         verification_checks=len(checks),artifacts=len(artifacts),preserved=summary['earlier_artifacts_preserved'])))


if __name__=='__main__':main()
