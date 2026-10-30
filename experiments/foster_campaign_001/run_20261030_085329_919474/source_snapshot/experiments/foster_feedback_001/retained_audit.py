"""One separately registered full-prefix raw-data fit; no estimator feedback.

No scoring truth is loaded. This is nonlinear MAP/Gauss-Newton diagnosis, not
an exact marginal posterior oracle or a replacement streaming implementation.
"""
import json
from pathlib import Path
import sys
import time
import numpy as np
from .estimator import Model,prior,fit
from experiments.structured_joint_001.qualify import ident,write


def main():
    run=Path(sys.argv[1]).resolve();out=run/'retained_audit001';out.mkdir(exist_ok=False)
    config=json.loads((run/'calibration.json').read_text());obs=np.load(run/'observations.npy')
    settings={**config['numerical'],'max_rounds':30}
    write(out/'plan.json',dict(scope='One final-prefix retained raw-data fit from the same public prior; no truth reads or streaming-state changes',
        motivation='Completed stream has approximately2.4%Q bias through rest despite small coefficient-encoding differences',
        max_rounds=30,max_line_fractions=settings['fractions'],automatic_retries=0,
        observation_identity=ident(run/'observations.npy'),calibration_identity=ident(run/'calibration.json'),
        model_binary_identity=ident(run/'model.so'),audit_source_identity=ident(Path(__file__)),command=sys.argv))
    x,L=prior(config);model=Model(run/'model.so',config);started=time.perf_counter();cpu=time.process_time()
    anchor,physical,diagnostics=fit(model,x,L,obs,settings)
    # Compare native physical endpoint, not a linearized transported endpoint.
    v,J,end,F=physical;B=J@L/obs[:,4,None]
    C=np.linalg.cholesky(np.eye(16)+B.T@B);root=np.linalg.solve(C,L.T).T
    endpoint_root=F@root;sd=np.sqrt(np.sum(endpoint_root**2,axis=1))
    factor=np.exp(config['arrhenius_A_K'][0]*(1/(obs[-1,2]+273.15)-1/config['reference_temperature_K']))
    result=dict(status=diagnostics['stop'],diagnostics=diagnostics,records=len(obs),
        chart_point=anchor.tolist(),endpoint=end.tolist(),endpoint_chart_sd=sd.tolist(),
        Q_ref=float(np.exp(anchor[5])),Q=float(np.exp(anchor[5])*factor),SOC=float(end[0]),
        standardized_residual_RMS=float(np.sqrt(np.mean(((v-obs[:,3])/obs[:,4])**2))),
        wall_s=time.perf_counter()-started,cpu_s=time.process_time()-cpu,
        scope='Single public-start retained nonlinear MAP fit; GN covariance is local, not validated posterior coverage',
        truth_reads=0,streaming_state_modified=False)
    write(out/'result.json',result);print(json.dumps(result),flush=True)


if __name__=='__main__':main()
