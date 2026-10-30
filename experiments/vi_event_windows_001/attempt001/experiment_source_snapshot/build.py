"""Isolated builds: production sources remain unchanged; every adaptation is saved."""
import hashlib,json,subprocess
from pathlib import Path
from experiments.foster_campaign_001.backend import prepare_c
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
def identity(p):return dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def build(out,rate,cfg,epsilon):
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    _,original=prepare_c(out,rate,cfg)
    snapshot=out/'backend_c/source_snapshot/experiments'
    source=snapshot/'foster_campaign_c_001/rolling.c'
    text=source.read_text()
    adaptations=[
      ('#include <string.h>','#include <string.h>\n#include "robust.h"'),
      ('*cost+=r[i]*r[i];','*cost+=2*experiment_rho(r[i]);'),
      ('s->cost+=s->residual[i]*s->residual[i];','s->cost+=2*experiment_rho(s->residual[i]);'),
      ('B[i*16+j]=z/obs[5*i+4];','B[i*16+j]=z/obs[5*i+4]*experiment_sqrt_weight(residual[i]);'),
      ('g+=B[k*16+i]*residual[k];','g+=B[k*16+i]*residual[k]*experiment_sqrt_weight(residual[k]);'),
      ('r=fb_token(s->anchor,','r=experiment_token(s->anchor,')]
    for old,new in adaptations:
        if text.count(old)!=1:raise ValueError(('source adaptation anchor changed',old))
        text=text.replace(old,new)
    generated=out/'rolling_experiment.c';generated.write_text(text)
    for name in ['robust.h','replay.c']:(out/name).write_bytes((HERE/name).read_bytes())
    header=snapshot/'foster_c_history_001/baseline.h'
    paths=[generated,out/'replay.c',snapshot/'foster_c_history_001/history.c',snapshot/'foster_c_baseline_001/numeric.c',snapshot/'foster_bounded_hysteresis_001/model.c']
    binary=out/'experiment.so'
    flags=['-std=c11','-O2','-fno-fast-math','-ffp-contract=off','-Wall','-Wextra','-Werror','-pedantic','-fPIC','-shared','-DFB_PROFILE','-D_POSIX_C_SOURCE=200809L',f'-DFB_CLOCK_HZ={original["tick_hz"]}','-DFB_MODEL_STAGE=2','-DFB_OPT_STAGE=3','-DFB_HISTORY_STAGE=2',f'-DEXP_EPS={epsilon}','-DEXP_SCALE=20.0','-include',str(header),'-I',str(header.parent)]
    cmd=['cc',*flags,*map(str,paths),'-lm','-o',str(binary)];subprocess.run(cmd,check=True)
    receipt=dict(command=cmd,epsilon=epsilon,scale=20,baseline=original,adaptations=adaptations,sources={str(p):identity(p) for p in [*paths,out/'robust.h',header]},binary=identity(binary))
    (out/'build.json').write_text(json.dumps(receipt,indent=2)+'\n');return binary
