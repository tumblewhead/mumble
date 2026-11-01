"""Matched ordered suffix backend timing, including periodic refresh and batching."""
import argparse
import json
from pathlib import Path
import time
from experiments.foster_campaign_001.backend import identity
from experiments.foster_campaign_001.compact import restore_checkpoint

def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('campaign',type=Path);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();case=a.campaign/'case_0000';r=json.loads((case/'result.json').read_text())
    entries=json.loads((case/'checkpoints/index.json').read_text())['checkpoints'];entry=entries[-2]
    cfg=json.loads((a.campaign/'calibration.json').read_text());plan=json.loads((a.campaign/'campaign_plan.json').read_text())
    cell=json.loads((case/'scenario.json').read_text())['cell_definition']
    stream,banks,_=restore_checkpoint(case,entry,cfg,cell,r['scenario'],plan['configuration'])
    timing={kind:0. for kind in banks};start=stream.index
    count=min(16384,r['records']-start)//16*16
    for chunk in range(0,count,4096):
        first=stream.index;obs,_,_=stream.read(min(4096,count-chunk))
        for j in range(0,len(obs),16):
            for kind,bank in banks.items():
                begin=time.perf_counter();bank.advance(first+j,obs[j:j+16]);timing[kind]+=time.perf_counter()-begin
    result=dict(scope='Host backend advance including per-window validation/readout, field batching and scheduled fits; stimulus generation, disk and plotting excluded; not M23 timing',
                first=start,records=count,windows=count//16,seconds_by_arm=timing,
                microseconds_per_window={kind:1e6*t/(count//16) for kind,t in timing.items()},
                campaign=str(a.campaign),checkpoint=entry,source=identity(Path(__file__)),counts={k:b.counts() for k,b in banks.items()})
    a.out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result['microseconds_per_window']))
if __name__=='__main__':main()
