"""Iteration2: preserve16-record steady windows; overlapping24-record detection only."""
import numpy as np
from .schedule import schedules

def sparse_schedules(obs,taus):
    plans={};details={};n=len(obs)
    for label,base in [('sparse_current','current'),('sparse_vi','joint_vi')]:
        first=0;ends=[];active=0
        while first<n:
            width=min(16,n-first)
            if first+24<=n:
                view=obs[first:first+24]
                # Exact-current control: no assumed current sensor noise floor.
                if np.ptp(view[:,1])>1e-14:
                    candidate,info=schedules(view,taus)
                    if info['nonflat_current_tiles']:
                        width=int(candidate[base][0]);active+=1
            first+=width;ends.append(first)
        plans[label]=np.array(ends,dtype=np.uint64)
        details[label]=dict(tokens=len(ends),nonflat_candidate_windows=active,short_windows=int(np.sum(np.diff(np.r_[0,ends])<16)))
    lengths=np.diff(np.r_[np.uint64(0),plans['sparse_vi']])
    # Keep exact multiset, sample count and number of fits; destroy event alignment.
    lengths=np.random.default_rng(20261030).permutation(lengths)
    plans['sparse_displaced']=np.cumsum(lengths,dtype=np.uint64)
    return plans,dict(raw_buffer_bytes=24*5*8,max_lookahead_samples=24,scope='Rolling detector buffer; implementation is Python reference. Shuffled schedule is offline control only.',arms=details)
