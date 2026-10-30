"""Independent Python-path check of the same three short failures."""
import json
import numpy as np
from experiments.foster_campaign_001.backend import PythonBackend
from experiments.foster_feedback_001.history import message
from .failures import HERE,RUN

def main():
    if (HERE/'python_failures.json').exists():raise FileExistsError('preserved receipt already exists: python_failures.json')
    config=json.loads((RUN/'calibration.json').read_text());reports=[]
    for case in ['case_0001','case_0004','case_0007']:
        path=RUN/case;result=json.loads((path/'result.json').read_text())
        end=result['arms']['float64']['failure']['index']+1
        obs=np.load(path/'observations.npy',mmap_mode='r')[:end]
        bank=PythonBackend(RUN,config,result['source_id'],result['model_id'],'float64',35)
        original=bank.bank.backend.advance;last={}
        def record(prior,token):
            payload=original(prior,token);last['candidate']=payload;return payload
        bank.bank.backend.advance=record
        for first in range(0,len(obs),16):
            try:bank.advance(first,obs[first:first+16])
            except ValueError as e:
                failure=str(e);break
        else:raise AssertionError('expected reference-path domain rejection')
        m,L,z=message(last['candidate']);assert m[4]<-1
        assert bank.failure_index==result['arms']['float64']['failure']['index']
        reports.append(dict(case=case,seed=result['scenario']['seed'],failure_index=bank.failure_index,
            failure=failure,candidate_h=float(m[4]),candidate_SOC=float(m[0]),counts=bank.counts()))
    with (HERE/'python_failures.json').open('x') as f:json.dump(reports,f,indent=2);f.write('\n')
    print(json.dumps(reports,indent=2))

if __name__=='__main__':main()
