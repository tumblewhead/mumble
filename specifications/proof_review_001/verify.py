"""Check review completeness and artifact identity, not mathematical validity."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT/'specifications/proof_review_001/manifest.json'
PROOFS = 'specifications/proof_review_001/proofs'
REVIEWS = 'provenance/proof_review_001/reviews'
VERSIONS = 'provenance/proof_review_001/versions'
EXPECTED = {f'{family}{i}' for family in ('D', 'K') for i in range(8)}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(name):
    return (ROOT/name).read_bytes()


def check(manifest, reader=read):
    entries = manifest['entries']
    require(len(entries) == len(EXPECTED), 'Incomplete/duplicate proof set')
    require({e['proof_id'] for e in entries} == EXPECTED, 'Wrong proof identities')
    expected_rounds = set()
    tasks = set()
    for e in entries:
        pid, rounds = e['proof_id'], e['rounds']
        require(type(rounds) is int and rounds >= 1, 'Invalid review count')
        require(e['proof_path'] == f'{PROOFS}/{pid}.md', 'Unexpected proof path')
        require(digest(reader(e['proof_path'])) == e['proof_sha256'], 'Stale proof identity')
        final = f'{REVIEWS}/{pid}_r{rounds}.json'
        task = f'/root/review_{pid.lower()}_r{rounds}'
        require(e['review_path'] == final, 'Wrong final review')
        report_bytes = reader(final)
        require(digest(report_bytes) == e['review_sha256'], 'Changed review artifact')
        r = json.loads(report_bytes)
        require(r['proof_id'] == pid and r['proof_sha256'] == e['proof_sha256'], 'Review bound to different proof')
        require(r['verdict'] == 'accept', 'Final review is not accepting')
        require(not r['findings'], 'Final packet has undisposed findings')
        require(r['reviewer_task'].split(':', 1)[0] == task == e['reviewer_task'], 'Wrong reviewer identity')
        require(task not in tasks, 'Reviewer reused for distinct final proofs')
        require(e['reviewer_context'] == 'fresh_fork_none', 'Review context not declared fresh')
        tasks.add(task)
        expected_rounds.update(f'{REVIEWS}/{pid}_r{n}.json' for n in range(1, rounds+1))
    rounds = manifest['review_rounds']
    require(len(rounds) == len(expected_rounds), 'Incomplete review history')
    require({r['report_path'] for r in rounds} == expected_rounds, 'Missing/duplicate review history')
    for item in rounds:
        data = reader(item['report_path'])
        require(digest(data) == item['report_sha256'], 'Historical report changed')
        report = json.loads(data)
        pid = report['proof_id']
        n = int(Path(item['report_path']).stem.rsplit('_r', 1)[1])
        entry = next(e for e in entries if e['proof_id'] == pid)
        source = f'{PROOFS}/{pid}.md' if n == entry['rounds'] else f'{VERSIONS}/{pid}_r{n}.md'
        require(item['proof_path'] == source, 'Wrong reviewed version path')
        actual = digest(reader(source))
        require(actual == item['proof_sha256'] == report['proof_sha256'], 'Historical proof binding changed')
        require(item['verdict'] == report['verdict'], 'Historical verdict changed')
        task = f'/root/review_{pid.lower()}_r{n}'
        require(report['reviewer_task'].split(':', 1)[0] == task == item['reviewer_task'], 'Historical reviewer mismatch')
        require(item['context'] == 'fresh_fork_none', 'Historical context not declared fresh')
    return {'status': 'artifact_consistency_pass', 'final_proofs': len(entries),
            'individual_review_reports': len(rounds),
            'scope': 'Identity/completeness checks only; no mathematical or reviewer-authentication guarantee.'}


def negative_controls(manifest):
    cases = []
    missing = deepcopy(manifest)
    missing['entries'].pop()
    cases.append(('missing_proof', missing, read))
    stale = deepcopy(manifest)
    stale['entries'][0]['proof_sha256'] = '0'*64
    cases.append(('stale_proof', stale, read))
    changed = deepcopy(manifest)
    changed['entries'][0]['review_sha256'] = '0'*64
    cases.append(('changed_review', changed, read))
    # In-memory adverse review with a matching updated checksum: the verdict
    # predicate must reject it independently of checksum checking.
    rejected = deepcopy(manifest)
    target = rejected['entries'][0]['review_path']
    r = json.loads(read(target))
    r['verdict'] = 'revise'
    payload = json.dumps(r).encode()
    rejected['entries'][0]['review_sha256'] = digest(payload)
    cases.append(('nonaccepting_review', rejected, lambda name: payload if name == target else read(name)))
    outcomes = {}
    for name, candidate, reader in cases:
        try:
            check(candidate, reader)
        except ValueError:
            outcomes[name] = 'rejected'
        else:
            raise AssertionError(f'Adverse case passed: {name}')
    return outcomes


if __name__ == '__main__':
    m = json.loads(MANIFEST.read_text())
    result = check(m)
    result['negative_controls'] = negative_controls(m)
    print(json.dumps(result, indent=2))
