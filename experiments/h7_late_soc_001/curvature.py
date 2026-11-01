"""Supplemental local field curvature; no original observations or truth input."""
import json,copy
from pathlib import Path
import numpy as np
from experiments.foster_campaign_001.compact import restore_checkpoint
from experiments.hysteresis_refinement_001.field import Compressed,transported
from .diagnostic import RUN,OUT,write

config=json.loads((RUN/'calibration.json').read_text());settings=json.loads((RUN/'campaign_plan.json').read_text())['configuration'];results=[]
for name in ('case_0007','case_0006'):
    c=RUN/name;record=json.loads((OUT/name/'result.json').read_text());cell=json.loads((c/'scenario.json').read_text())
    scenario={k:cell[k] for k in ('cell','load','seed','noise_v')}
    _,banks,_=restore_checkpoint(c,record['start'],config,cell['cell_definition'],scenario,settings)
    for label in ('start','first_miss','peak','end'):
        with np.load(OUT/name/(label+'_probe.npz')) as z:
            f=copy.copy(banks['tangent_h7'].field);f.root=z['root'].copy();f.state=z['state'].copy()
            mean,L,w=z['mean'],z['L'],z['w'];obj=Compressed(f,mean,L)
            cost,g,P,_,_=obj(w);end,D=transported(f,mean+L@w);v=D[0]@L
            u=np.linalg.solve(P,v);sd=np.sqrt(v@u);direction=u/sd
            delta=-np.linalg.solve(P,g);shift=v@delta/sd
            curves=[]
            for step in (.1,.03,.01):
                gp=obj(w+step*direction)[1];gm=obj(w-step*direction)[1]
                curves.append(dict(step_local_SD=step,observed_over_GN_SOC_direction=float(direction@(gp-gm)/(2*step))))
            results.append(dict(case=name,probe=label,GN_correction_SOC_local_SD=float(shift),
                GN_decrement=float(np.sqrt(max(0,-g@delta))),cost_roundoff_stop_threshold=float(np.sqrt(32*np.spacing(max(cost,1)))),curvature=curves))
p=OUT/'curvature.json'
if p.exists():raise FileExistsError(p)
write(p,dict(scope='Directional finite differences of compressed-field gradient, not retained-data/global posterior curvature.',results=results))
for r in results:print(r['case'],r['probe'],r['GN_correction_SOC_local_SD'],r['curvature'])
