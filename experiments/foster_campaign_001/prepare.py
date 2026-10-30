"""Source-distribution adapter for the frozen Foster campaign preparation."""
import json
import shutil
import subprocess
import sys
from experiments.foster_feedback_001.run import HERE, ROOT, read, qualify
from experiments.structured_joint_001.qualify import ident, write
from specifications.evidence_feedback_001.protocol import digest
from .evidence import verify_parent


def prepare(out,args):
    out.mkdir(parents=True,exist_ok=False)
    previous=ROOT/'specifications/evidence_feedback_001'
    preserved=read(previous/'qualification001/reservation.json')['preserved_artifacts']
    preserved.update(read(previous/'verification.json')['artifacts'])
    preserved[str((previous/'verification.json').relative_to(ROOT))]=ident(previous/'verification.json')
    verification=verify_parent(ROOT,preserved)
    files=list(HERE.glob('*.py'))+list(HERE.glob('*.c'))+list(HERE.glob('*.json'))
    files+=[previous/'protocol.py',previous/'model.json',previous/'contract.json',ROOT/'experiments/structured_joint_001/qualify.py']
    sources={str(p.relative_to(ROOT)):ident(p) for p in files}
    for p in files:
        target=out/'source_snapshot'/p.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
    write(out/'reservation.json',dict(source_identities=sources,preserved_artifacts=preserved,
        parent_evidence_verification=verification,
        source_revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        branch=subprocess.check_output(['git','branch','--show-current'],text=True).strip(),
        command=sys.argv,configuration=vars(args)))
    command=['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-pedantic','-fno-fast-math','-ffp-contract=off',
             '-shared','-fPIC',str(HERE/'model.c'),'-lm','-o',str(out/'model.so')]
    build=subprocess.run(command,capture_output=True,text=True)
    write(out/'build.json',dict(command=command,returncode=build.returncode,stdout=build.stdout,stderr=build.stderr))
    if build.returncode:raise RuntimeError(build.stderr)
    config=read(HERE/'calibration.json');write(out/'calibration.json',config)
    model_id=digest(dict(model=read(previous/'model.json'),source=sources[str((HERE/'model.c').relative_to(ROOT))],calibration=config))
    report=qualify((out/'model.so').resolve(),config,model_id);write(out/'qualification.json',report)
    print(json.dumps(dict(qualification=report['status'],passing_checks=report['passing_checks'],failures=report['failed_checks'])),flush=True)
    if report['status']!='passed':raise ValueError('targeted qualification failed; preserved run directory')
    return config,model_id
