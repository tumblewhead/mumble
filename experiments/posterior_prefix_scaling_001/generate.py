"""Once-only fabricated input creation; plant data never passed to inference."""
import math
from pathlib import Path
import json
import numpy as np
from common import HERE,save,runner


def generate(out, plan_path=None):
    plan_path=HERE/'plan.json' if plan_path is None else Path(plan_path)
    plan=json.loads(plan_path.read_text())
    fixture=plan['input_fixture'];rng=np.random.default_rng(fixture['generation_seed'])
    x=fixture['plant_initial_x']
    z,rc,h=x[11],list(x[12:15]),x[15]
    logq,r0=x[5:7];rates=fixture['health_rates']
    rows=[];truth=[]
    for index in range(max(plan['prefixes'])):
        dt=fixture['dt_multipliers_repeated'][index%8]/plan['nominal_Hz']
        current=fixture['current_A_repeated'][index%16]
        days,throughput=dt/86400,abs(current)*dt/3600
        mu=(logq+rates[0]*days+rates[1]*throughput,r0+rates[2]*days+rates[3]*throughput)
        var=(rates[4]**2*days+rates[5]**2*throughput,rates[6]**2*days+rates[7]**2*throughput)
        health=[]
        for j,(lower,upper) in enumerate(((math.log(.03),math.log(.1)),(0.,1.))):
            for trial in range(256):
                value=mu[j]+math.sqrt(var[j])*float(rng.normal())
                if lower<=value<=upper:break
            else:raise RuntimeError('fixture health sampling limit')
            health.append(value)
        logq,r0=health
        z-=current*dt/(3600*math.exp(logq))
        for j in range(3):
            e=math.exp(-dt/math.exp(x[j]))
            rc[j]=e*rc[j]+(1-e)*x[7+j]*current
        if current:
            e=math.exp(-math.exp(x[3 if current>0 else 4])*abs(current)*dt/3600)
            h=e*h+(1-e)*(1 if current>0 else -1)
        voltage=3+1.15*z+.08*math.tanh(8*(z-.5))-current*r0-sum(rc)-x[10]*h
        observed=voltage+fixture['voltage_noise_sd_V']*float(rng.normal())
        rows.append(dict(source_id=fixture['source_id'],index=index,dt=dt,current=current,
                         voltage=observed,measurement_valid=True,input_known=True,temperature_C=25.))
        truth.append(dict(index=index,fast=[z]+rc+[h],health=[logq,r0],mean_voltage=voltage))
    out.mkdir(parents=True)
    for n in plan['prefixes']:
        save(out/f'observations_{n}.json',dict(source_id=fixture['source_id'],records=rows[:n]))
    save(out/'plant_truth_not_inference.json',dict(initial_x=x,states=truth))
    # Deliberately exclude plant initial state, latent states and generator seed.
    inference=dict(profile_rates=fixture['health_rates'],source_id=fixture['source_id'],
                   **plan['inference'],prefixes=plan['prefixes'],caps=plan['caps'],cost_probes=plan['cost_probes'])
    save(out/'inference.json',inference)
    save(out/'manifest.json',dict(plan=runner.identity(plan_path),
        generator=runner.identity(HERE/'generate.py'),
        files={p.name:runner.identity(p) for p in out.iterdir() if p.is_file()},
        plant_inference_separation='No solver worker receives plan.json or plant_truth_not_inference.json'))


if __name__=='__main__':
    import sys
    generate(Path(sys.argv[1]).resolve())
