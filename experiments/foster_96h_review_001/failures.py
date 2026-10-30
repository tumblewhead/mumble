"""Reproduce only three short failed prefixes using the original saved library."""
import ctypes as C
import hashlib
import json
from pathlib import Path
import subprocess
import numpy as np
from experiments.foster_c_baseline_001.reference import Baseline,library,ptr,DP
from experiments.foster_feedback_001.estimator import Model

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
RUN=ROOT/'experiments/foster_campaign_001/run_20261030_174341_464520'

def identity(p):return {'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}

def main():
    if (HERE/'failures.json').exists():raise FileExistsError('preserved receipt already exists: failures.json')
    build=json.loads((RUN/'backend_c/build.json').read_text())
    binary=RUN/'backend_c/estimator.so';assert identity(binary)==build['binary']
    header=RUN/'backend_c/source_snapshot/experiments/foster_c_history_001/baseline.h'
    assert identity(header)==build['sources']['experiments/foster_c_history_001/baseline.h']
    cmd=['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-pedantic','-shared','-fPIC','-I',str(header.parent),str(HERE/'inspect.c'),'-o',str(HERE/'inspect.so')]
    subprocess.run(cmd,check=True)
    lib=library(binary);ins=C.CDLL(str(HERE/'inspect.so'))
    ins.review_context_size.restype=C.c_size_t
    assert ins.review_context_size()==lib.fb_context_bytes()
    ins.review_state.argtypes=[C.c_void_p,DP,DP,C.POINTER(C.c_uint64)]
    config=json.loads((RUN/'calibration.json').read_text());model=Model(binary,config)
    reports=[]
    for case in ['case_0001','case_0004','case_0007']:
        p=RUN/case;result=json.loads((p/'result.json').read_text())
        for encoding,width in [('float64',8),('float32',4)]:
            saved=result['arms'][encoding];n=saved['failure']['index']+1
            obs=np.array(np.load(p/'observations.npy',mmap_mode='r')[:n])
            bank=Baseline(lib,width);assert bank.cfg==config
            status,trace=bank.replay(obs);assert status==-4
            expected=np.load(p/(encoding+'_message.npy'))
            assert bank.snapshot().tobytes()==expected.tobytes()
            candidate=np.empty(273);anchor=np.empty(16);counts=(C.c_uint64*4)()
            ins.review_state(bank.context,ptr(candidate),ptr(anchor),counts)
            assert counts[1]==saved['retired_records'] and counts[2]==saved['pending_records']==16
            pending=obs[int(counts[1]):int(counts[0])]
            before=model.evaluate(expected[:16],pending)
            fitted=model.evaluate(anchor,pending)
            try:model.evaluate(candidate[:16],np.empty((0,5)))
            except ValueError as e:rejection=str(e)
            else:raise AssertionError('candidate should fail physical-domain check')
            np.save(HERE/f'{case}_{encoding}_candidate.npy',candidate)
            np.save(HERE/f'{case}_{encoding}_anchor.npy',anchor)
            np.save(HERE/f'{case}_{encoding}_pending.npy',pending)
            reports.append(dict(case=case,seed=result['scenario']['seed'],encoding=encoding,
                status=status,physical_candidate_rejection=rejection,received_records=int(counts[0]),
                retired_records=int(counts[1]),pending_records=int(counts[2]),generation=int(counts[3]),
                failure_time_s=n/35,committed_message_byte_equal=True,
                committed_SOC=float(expected[0]),committed_h=float(expected[4]),
                prior_propagated_h=float(before[2][4]),fit_anchor_h=float(anchor[4]),
                fitted_endpoint_h=float(fitted[2][4]),candidate_h=float(candidate[4]),candidate_SOC=float(candidate[0]),
                candidate_all_finite=bool(np.isfinite(candidate).all()),
                candidate_history_h_shift_from_fitted_endpoint=float(candidate[4]-fitted[2][4]),
                diagnosis='valid prior propagation and fitted trajectory; unconstrained local-Gaussian history update produces out-of-domain candidate before commit'))
    receipt=dict(command=cmd,binary=identity(binary),header=identity(header),failures=reports,
        scope='Only saved prefixes through their first rejection; no full96h campaign rerun, no original file modified, no repair applied.')
    with (HERE/'failures.json').open('x') as f:json.dump(receipt,f,indent=2);f.write('\n')
    print(json.dumps(reports,indent=2))

if __name__=='__main__':main()
