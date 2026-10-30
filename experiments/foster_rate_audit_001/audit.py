"""Bounded clock/dt/partition controls; do not change saved campaigns."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import numpy as np
from experiments.foster_campaign_001.backend import CBackend, PythonBackend
from experiments.foster_feedback_001.estimator import Model, prior
from experiments.foster_campaign_001.telemetry import PARAMETERS

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
BASE=ROOT/'experiments/foster_campaign_c_001'
CONFIG=json.loads((ROOT/'experiments/foster_feedback_001/calibration.json').read_text())

def replay(bank,obs,block=16):
    for i in range(0,len(obs),block):bank.advance(i,obs[i:i+block])
    return bank.full_message()

def main():
    source=BASE/'c100_plots/case_0000/observations.npy'
    obs=np.load(source)
    report={'source':str(source.relative_to(ROOT)),
            'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
            'records':len(obs),'clock_controls':[]}
    with tempfile.TemporaryDirectory() as temporary:
        root=Path(temporary)
        for rate in [35,100,200]:
            d=root/str(rate);d.mkdir();shutil.copy2(BASE/'c35/model.so',d/'model.so')
        # Exactly the same observations, including dt, under different clock units.
        # Variable intervals all belong to both1050Hz and2100Hz grids.
        variable=obs[:257].copy()
        variable[:,0]=np.resize([1/35,1/70,1/1050],len(variable))
        for kind in [CBackend,PythonBackend]:
            for encoding in ['float64','float32']:
                for rates,rows in [([35,100],variable),([100,200],obs[:1027])]:
                    outputs=[]
                    for rate in rates:
                        bank=kind(root/str(rate),CONFIG,'a'*64,'b'*64,encoding,rate)
                        outputs.append(replay(bank,rows))
                    equal=outputs[0].tobytes()==outputs[1].tobytes()
                    assert equal
                    report['clock_controls'].append(dict(backend=kind.__name__,encoding=encoding,
                        clock_rates=rates,records=len(rows),full_message_byte_equal=equal))
        # Physical propagation at constant I/T: same one-second interval split
        # into1/35/100 steps, without adding measurement likelihoods.
        model=Model(root/'100/model.so',CONFIG);x,_=prior(CONFIG)
        end_reference=None;transport_reference=None;physical=[]
        for rate in [1,35,100]:
            rows=np.tile([1/rate,.02,25.,3.7,.004],(rate,1))
            _,_,end,F=model.evaluate(x,rows)
            if end_reference is None:end_reference=end;transport_reference=F
            e=float(np.max(abs(end-end_reference)));f=float(np.max(abs(F-transport_reference)))
            assert e<1e-12 and f<1e-12
            physical.append(dict(rate_Hz=rate,endpoint_max_abs=e,transport_max_abs=f))
        report['constant_input_one_second_propagation']=physical
        # Clock validation is an admission rule: unsupported intervals are rejected,
        # never replaced by a rounded dt in the physical model.
        bank=CBackend(root/'35',CONFIG,'a'*64,'b'*64,'float64',35)
        try:bank.advance(0,obs[:1])
        except ValueError:pass
        else:raise AssertionError('1050Hz grid must reject0.01s')
        assert bank.counts()['received_records']==0
        report['unsupported_clock_grid_rejects_before_consuming']=True
        # Repartition identical evidence; each observation consumed exactly once.
        # This probes nonlinear approximation and stopping, not different Fs.
        comparisons=[]
        for encoding in ['float64','float32']:
            base=None
            for block,rounds in [(16,4),(8,4),(4,4),(16,12)]:
                config=copy.deepcopy(CONFIG);config['numerical']['max_rounds']=rounds
                bank=CBackend(root/'100',config,'a'*64,'b'*64,encoding,100)
                m=replay(bank,obs,block)
                if base is None:base=m
                comparisons.append(dict(encoding=encoding,block_records=block,max_rounds=rounds,
                    final_Q_ref_Ah=float(np.exp(m[5])),final_SOC=float(m[0]),
                    Q_change_percent=float(100*np.expm1(m[5]-base[5])),
                    SOC_change_pp=float(100*(m[0]-base[0])),counts=bank.counts()))
        report['same_observations_partition_and_rounds']=comparisons
    # Read only endpoint telemetry from existing owner campaigns; no long rerun.
    runs=[]
    for name in ['run_20261030_100426_239149','run_20261030_101732_461642']:
        case=ROOT/'experiments/foster_campaign_001'/name/'case_0000'
        if not (case/'result.json').exists():continue
        s=json.loads((case/'result.json').read_text())
        truth=np.load(case/'truth.npy',mmap_mode='r');arms={}
        for encoding,a in s['arms'].items():
            trace=np.load(case/(encoding+'_trace.npy'),mmap_mode='r');end=trace[a['outputs']-1]
            actual=truth[int(end[0])-1,5:16]
            arms[encoding]={'final_parameter_error_percent':dict(zip(PARAMETERS,(100*(end[11:22]/actual-1)).tolist())),
                            'Q_SOC_statistics':a['all']}
        runs.append(dict(case=str(case.relative_to(ROOT)),rate_Hz=s['sample_rate_Hz'],
            result_sha256=hashlib.sha256((case/'result.json').read_bytes()).hexdigest(),arms=arms))
    report['existing_owner_runs']=runs
    report['status']='controls_passed; cause_of_owner_RC_bias_not_isolated'
    report['limits']='Clock invariance and one-second exact dynamics do not certify nonlinear filtering, coverage or long-term accuracy. Repartitioning changes Gaussian linearization and encoding cadence.'
    target=HERE/'result.json'
    with target.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
    print(json.dumps({'clock_controls':len(report['clock_controls']),'physical':physical,'partition':comparisons},indent=2))

if __name__=='__main__':main()
