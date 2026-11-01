"""Finite exploration of the abstract evidence/publish protocol.

The induction is in OWNERSHIP.md. This model does not model floating-point values,
Python allocation failure or every machine instruction.
"""
from dataclasses import dataclass,replace
from collections import deque
import json

@dataclass(frozen=True)
class State:
    n:int=0
    history:tuple=()
    pending:tuple=()
    tangent:tuple=()
    published:int=0
    anchor_prefix:int=0
    prior_copies:int=1
    phase:str='ready'

def valid(s):
    prefix=tuple(range(s.n))
    return (s.phase in ('ready','query','recover','terminal') and s.history+s.pending==prefix and s.tangent==prefix and s.prior_copies==1
            and 0<=s.published<=s.n and 0<=s.anchor_prefix<=s.n
            and (s.phase!='ready' or s.published==s.n))

def transitions(s,limit):
    yield 'reject_invalid_or_wrong_source',s
    if s.phase=='terminal':return
    if s.pending:
        yield 'flush',replace(s,history=s.history+s.pending,pending=())
    if s.phase=='ready':
        for count in (1,2):
            if s.n+count<=limit:
                new=tuple(range(s.n,s.n+count))
                yield 'accept',replace(s,n=s.n+count,pending=s.pending+new,tangent=s.tangent+new,phase='query')
    else:
        yield 'query_success',replace(s,published=s.n,phase='ready')
        yield 'query_failure',replace(s,phase='recover')
        yield 'refresh_success',replace(s,history=s.history+s.pending,pending=(),tangent=tuple(range(s.n)),prior_copies=1,anchor_prefix=s.n,published=s.n,phase='ready')
        yield 'refresh_rejection',s
        yield 'unresolved_terminal',replace(s,phase='terminal')

def explore(limit=8):
    todo=deque([State()]);seen={State()};edges=0
    while todo:
        s=todo.popleft();assert valid(s)
        for name,t in transitions(s,limit):
            edges+=1;assert valid(t),(name,s,t)
            if t not in seen:seen.add(t);todo.append(t)
    return dict(prefix_limit=limit,states=len(seen),transitions=edges)

def mutations():
    s=State(n=2,pending=(0,1),tangent=(0,1),published=2)
    return {'duplicate_history':not valid(replace(s,history=(0,1))),
            'recycled_prior':not valid(replace(s,prior_copies=2)),
            'skipped_sample':not valid(replace(s,tangent=(0,))),
            'publish_without_evidence':not valid(replace(s,published=3)),
            'resume_without_publish':not valid(replace(s,n=3,pending=(0,1,2),tangent=(0,1,2),phase='ready'))}

if __name__=='__main__':
    m=mutations();assert all(m.values())
    print(json.dumps(dict(status='bounded_abstract_model_checked',exploration=explore(),mutations_detected=m,
        scope='Finite model, not unbounded model checking or full C/Python refinement proof.'),indent=2))
