"""Check reviewed-version bindings; this does not automatically prove mathematics.

Run this acceptance gate after tests. Changed sources/proofs require renewed
qualification/review, not editing an expected hash to silence a failing check.
"""
import argparse
import hashlib
import json
from pathlib import Path
from experiments.foster_campaign_001.backend import ROOT


def verify(root,manifest):
    if manifest.get('schema')!='architecture_proof_gate_v1':raise ValueError('gate schema')
    root=Path(root).resolve()
    def path(name):
        p=(root/name).resolve()
        if not p.is_relative_to(root):raise ValueError('binding outside root')
        return p
    bindings=manifest['bindings']
    for name,expected in bindings.items():
        data=path(name).read_bytes()
        if len(data)!=expected['bytes'] or hashlib.sha256(data).hexdigest()!=expected['sha256']:
            raise ValueError('reviewed identity changed: '+name)
    for check in manifest['assertions']:
        if check['file'] not in bindings:raise ValueError('unbound assertion')
        value=json.loads(path(check['file']).read_text())
        for key in check['keys']:value=value[key]
        if value!=check['equals']:raise ValueError('qualification assertion: '+check['file'])
    if not manifest['bindings'] or not manifest['assertions']:raise ValueError('empty qualification')
    return dict(status='reviewed_bindings_match',files=len(bindings),
        scope='Frozen review/test/evidence identity check only; open contracts and physical/runtime premises remain open.')


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--manifest',type=Path,default=ROOT/'provenance/architecture_reuse_001/gate.json')
    args=p.parse_args();print(json.dumps(verify(ROOT,json.loads(args.manifest.read_text())),indent=2))


if __name__=='__main__':main()
