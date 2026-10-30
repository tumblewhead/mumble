"""Verify contiguous mixed-range packing versus per-curve padding."""
import json
from pathlib import Path
import shutil
import numpy as np
from .splines import Codebook,monotone
from .qualify import HERE,ROOT,Checks,ident,write


def main():
    out=HERE/'packing001';out.mkdir(exist_ok=False)
    sources=[Path(__file__),HERE/'splines.py',HERE/'qualify.py']
    ids={str(p.relative_to(ROOT)):ident(p) for p in sources}
    write(out/'reservation.json',dict(status='reserved_before_execution',source_identities=ids,
          layout='32 age,4 measured-temperature,24 anchored thermal coefficients; descriptors external',bits=[8,12,16],
          command='python3 -B -m experiments.monotone_codebook_001.packing_check'))
    for p in sources:
        q=out/'source_snapshot'/p.relative_to(ROOT);q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q)
    c=Checks();rows=[]
    down=np.array([1.,.95,.82,.7]);directions=[-1,1,1,1,1,-1,-1,-1]
    ages=np.array([down if d<0 else 2-down for d in directions])
    temperature=np.array([25.,45.,5.,30.]);thermal=np.tile([-.24,-.16,-.08],8)
    values=np.r_[ages.ravel(),temperature,thermal]
    lo=(.5,)*32+(-20.,)*4+(-.3,)*24;hi=(1.5,)*32+(60.,)*4+(.3,)*24
    for bits in (8,12,16):
        book=Codebook(lo,hi,bits);packet=book.encode(values);decoded=book.decode(packet)
        c.ok(str(bits)+'/payload_length',len(packet)==60*bits//8)
        c.ok(str(bits)+'/roundtrip',book.encode(decoded)==packet)
        c.ok(str(bits)+'/coefficient_bound',np.all(abs(values-decoded)<=book.delta/2+1e-14))
        for i,d in enumerate(directions):
            monotone(decoded[4*i:4*i+4],d);c.ok(str(bits)+'/monotone_health/'+str(i),True)
        rows.append(dict(bits=bits,contiguous_payload_B=len(packet),coefficient_count=60,
                         floating_payload_B=60*8,descriptors_and_uncertainty_included=False))
    for path,expected in ids.items():c.ok('source/'+path,ident(ROOT/path)==expected)
    write(out/'result.json',dict(status='passed' if all(q['passed'] for q in c.items) else 'failed',checks=c.items,packing=rows))
    print(json.dumps(dict(checks=len(c.items),packing=rows)))


if __name__=='__main__':main()
