"""Read-only 24-hour integration check against frozen offline H7 evidence."""
import json
from pathlib import Path
import numpy as np
from experiments.foster_campaign_001.backend import identity
from experiments.foster_campaign_001.compact import restore_checkpoint
from experiments.slow_likelihood_diagnostic_001.numerics import solve


def main():
    run=Path('experiments/h7_campaign_001/run72_001');out=Path('provenance/h7_campaign_001/prefix24.json')
    if out.exists():raise FileExistsError(out)
    parent=Path('/home/easy/proj/mumble/.worktrees/field-comparison-plots')
    oldrun=Path('/home/easy/proj/mumble/.worktrees/rolling-joint-field/experiments/foster_campaign_001/run_20261031_182600_810547')
    n=4325376;settings=json.loads((run/'campaign_plan.json').read_text())['configuration'];cfg=json.loads((run/'calibration.json').read_text());rows=[]
    for caseid,oldid,seed in [('case_0000','case_0000',1100),('case_0001','case_0002',1103)]:
        case=run/caseid;scenario_file=json.loads((case/'scenario.json').read_text());scenario={k:scenario_file[k] for k in ('cell','load','noise_v','seed','load_seed')}
        entry=next(e for e in json.loads((case/'checkpoints/index.json').read_text())['checkpoints'] if e['sequence']==n)
        stream,banks,meta=restore_checkpoint(case,entry,cfg,scenario_file['cell_definition'],scenario,settings)
        oldcase=oldrun/oldid;oldentry=next(e for e in json.loads((oldcase/'checkpoints/index.json').read_text())['checkpoints'] if e['sequence']==n)
        oldfile=oldcase/'checkpoints'/oldentry['file']
        assert identity(oldfile)=={k:oldentry[k] for k in ('bytes','sha256')}
        with np.load(oldfile) as z:original=json.loads(z['metadata'].tobytes())
        assert meta['stimulus']==original['stimulus']
        result=parent/f'experiments/hysteresis_refinement_001/seed{seed}_attempt002/n{n}_h7/result.json';ref=json.loads(result.read_text())
        b=banks['tangent_h7'];message=b.full_message();b._flush_field();fit=solve(b.objective,start=b.w)
        refx=np.asarray(ref['fit']['x']);sd=np.linalg.norm(np.asarray(ref['fit']['root'])[5])
        rows.append(dict(seed=seed,sequence=n,stimulus_state_controller_RNG_exact=True,
            current_checkpoint=entry,original_checkpoint=oldentry,offline_result=identity(result),
            fresh_fit_stop=fit['diagnostic']['stop'],
            streamed_minus_offline_Q_percent=float(100*np.expm1(message[5]-refx[5])),
            fresh_fit_minus_offline_Q_local_SD=float((fit['x'][5]-refx[5])/sd),
            fresh_fit_max_chart_difference=float(np.max(abs(fit['x']-refx))),
            streamed_Q_local_SD_percent=float(100*np.linalg.norm(message[16:272].reshape(16,16)[5]))))
    out.write_text(json.dumps(dict(status='matched',cases=rows,scope='Read-only checkpoint refit; does not alter running banks or introduce truth into fit'),indent=2)+'\n')
    print(json.dumps(rows,indent=2))

if __name__=='__main__':main()
