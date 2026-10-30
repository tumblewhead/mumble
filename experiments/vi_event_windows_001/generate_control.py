"""Independent harness-only multiscale input control; never imported by estimator."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
import argparse,json
from pathlib import Path
from experiments.foster_campaign_001.stimulus import generate,cells
from .build import identity,ROOT

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    cfg=json.loads((ROOT/'experiments/foster_feedback_001/calibration.json').read_text());cfg['hysteresis_chart']='bounded'
    (a.out/'calibration.json').write_text(json.dumps(cfg,indent=2)+'\n')
    folder=a.out/'case_0000';folder.mkdir();cell=cells()['B']
    _,_,report=generate(folder,cfg,810000,cell,'multiscale',.12,.002,2000,'cycle',sample_rate_hz=50,progress=lambda n:print('generated',n,flush=True))
    manifest=dict(status=report['status'],sample_rate_Hz=50,cases=[dict(directory=folder.name,scenario=dict(seed=2000,cell='B',load='multiscale',noise_v=.002))],generation=report,cell_definition=cell,hours=4.5,current_amplitude_A=.12,temperature=dict(mode='cycle',mean_C=25,amplitude_C=8,period_s=3600),input_identities={p.name:identity(p) for p in [folder/'observations.npy',folder/'truth.npy']},source_identities={str(p.relative_to(ROOT)):identity(p) for p in [Path(__file__).resolve(),ROOT/'experiments/foster_campaign_001/stimulus.py',ROOT/'experiments/foster_feedback_001/plant.py']})
    (a.out/'summary.json').write_text(json.dumps(manifest,indent=2)+'\n');print(report,flush=True)
    if report['status']!='generated':raise RuntimeError(report)
if __name__=='__main__':main()
