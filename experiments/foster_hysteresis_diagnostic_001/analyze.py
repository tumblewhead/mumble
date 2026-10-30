"""Read-only hysteresis/voltage-component diagnosis of completed owner cases."""
import json
from pathlib import Path
import sys
import numpy as np
from experiments.foster_campaign_001.run import ident
from experiments.foster_campaign_001.plot import draw


def main():
    run=Path(sys.argv[1]).resolve();out=Path(sys.argv[2]).resolve();out.mkdir(exist_ok=False)
    snapshot=json.loads((run/'summary.json').read_text())
    config=json.loads((run/'calibration.json').read_text())
    (out/'source_summary_snapshot.json').write_text(json.dumps(snapshot,indent=2)+'\n')
    cases=[];plot_data=None
    for c in snapshot['cases']:
        if c['status']!='completed':continue
        case=run/c['directory'];scenario=json.loads((case/'scenario.json').read_text())
        meta=json.loads((case/'telemetry.json').read_text());cols=meta['trace_columns']
        truth=np.load(case/'truth.npy',mmap_mode='r');arms={}
        for kind,stat in c['arms'].items():
            count=stat['outputs'];rows=np.load(case/(kind+'_trace.npy'),mmap_mode='r')[:count]
            chart=np.load(case/(kind+'_chart.npy'),mmap_mode='r')[:count]
            # Scoring only: none of these truth quantities enters a fit.
            start=int(np.searchsorted(rows[:,1],rows[-1,1]-3600))
            r=rows[start:];ix=r[:,0].astype(int)-1;t=truth[ix]
            u=r[:,cols.index('H_V')]*r[:,cols.index('h')];ut=t[:,13]*t[:,4]
            hyst=u-ut;ocv=config['ocv_slope_V_per_SOC']*(r[:,6]-t[:,0])
            ohmic=-r[:,2]*(r[:,12]-t[:,6]);rc=-np.sum(r[:,7:10]-t[:,1:4],axis=1)
            total=r[:,5]-t[:,16]
            closure=float(np.max(np.abs(total-hyst-ocv-ohmic-rc)))
            assert closure<1e-12
            parameters={}
            for name,index in [('H_V',13),('gamma_plus',14),('gamma_minus',15)]:
                true=scenario['cell_definition']['parameters'][name]
                estimated=float(rows[-1,cols.index(name+'_ref')]);sd=float(chart[-1,16+index])
                parameters[name]=dict(truth_ref=true,estimate_ref=estimated,relative_error_percent=100*(estimated/true-1),
                    reported_log_sd=sd,log_error_over_reported_sd=float(np.log(estimated/true)/sd),
                    checkpoints={str(hour):float(rows[min(len(rows)-1,np.searchsorted(rows[:,1],hour*3600)),cols.index(name+'_ref')])
                                 for hour in [1,4,8,12] if hour*3600<=rows[-1,1]})
            arms[kind]=dict(parameters=parameters,final_time_h=float(rows[-1,1]/3600),
                last_hour=dict(Hh_bias_mV=float(np.mean(hyst)*1000),OCV_bias_mV=float(np.mean(ocv)*1000),
                    ohmic_bias_mV=float(np.mean(ohmic)*1000),RC_bias_mV=float(np.mean(rc)*1000),
                    Hh_RMSE_mV=float(np.sqrt(np.mean(hyst*hyst))*1000),
                    terminal_noiseless_RMSE_mV=float(np.sqrt(np.mean(total*total))*1000),
                    truth_h_range=[float(t[:,4].min()),float(t[:,4].max())],
                    estimate_h_range=[float(r[:,10].min()),float(r[:,10].max())],
                    truth_Hh_range_mV=[float(ut.min()*1000),float(ut.max()*1000)]),
                voltage_component_closure_max_V=closure,
                trace_identity=ident(case/(kind+'_trace.npy')),chart_identity=ident(case/(kind+'_chart.npy')))
            if c['directory']=='case_0001' and kind=='float64':
                plot_data=(r[:,1].copy(),u.copy(),ut.copy(),hyst.copy(),ocv.copy(),total.copy())
        cases.append(dict(directory=c['directory'],scenario=c['scenario'],arms=arms,
                          result_identity=ident(case/'result.json'),input_identities=json.loads((case/'inputs.json').read_text())))
    result=dict(status='read_only_completed_case_diagnosis',run=str(run),cases=cases,
        source_campaign_status_at_snapshot=snapshot['status'],fitting_performed=False,estimator_modified=False,
        derivation=dict(reference_cell='A at25C',Q_Ah=.06,current_A=.03,gamma_plus=6,gamma_minus=9,
            hysteresis_time_constants_s=[1200.,800.],cycle_pulse_s=50.,
            cycle_pulse_exponents=[50/1200,50/800],
            cycle_approach_fraction=[float(-np.expm1(-50/1200)),float(-np.expm1(-50/800))],
            multiscale_longest_pulse_s=120.,multiscale_longest_current_A=.0225,
            multiscale_longest_exponents=[6*.0225*120/(3600*.06),9*.0225*120/(3600*.06)],
            voltage_hysteresis='u=H*h; at fixed T and H: du/dxi=gamma_dir*(H*sign(I)-u)',
            pulse_response='u_next=u+gamma_dir*(H*sign(I)-u)*delta_xi+O((gamma_dir*delta_xi)^2)',
            fast_balanced_cycle_center='h_bar approximately (gamma_plus-gamma_minus)/(gamma_plus+gamma_minus), for equal per-polarity throughput and small pulse exponents',
            effective_terminal_slope='Ignoring relaxed RC terms at fixedT near that cycle center: dV/dt approximately I/(3600Q)*[-b+2H*gamma_plus*gamma_minus/(gamma_plus+gamma_minus)]'),
        limits=['Derived small-pulse approximations are not a proof of structural nonidentifiability.',
                'Repeated cycles and temperature changes can add information; no exclusion or exact likelihood ridge certified.',
                'Reported log SDs are approximate and known unvalidated, not confidence statements.',
                'Voltage is reconstructed after assimilation; small fit residual is not independent predictive validation.',
                'No retained nonlinear fit in this diagnosis: stimulus, optimization and history approximation contributions remain unseparated.'])
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    if plot_data:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        time,u,ut,hyst,ocv,total=plot_data
        fig,axes=plt.subplots(2,1,figsize=(11,7),layout='constrained',sharex=True)
        draw(axes[0],1000*ut,lambda ix:time[ix],'Plant Hh','#222222')
        draw(axes[0],1000*u,lambda ix:time[ix],'Estimated Hh','#dc7822')
        for values,label,color in [(hyst,'Hysteresis error','#dc7822'),(ocv,'OCV/SOC error','#3165b4'),(total,'Total fitted-voltage error','#222222')]:
            draw(axes[1],1000*values,lambda ix:time[ix],label,color)
        for ax in axes:ax.set_ylabel('mV');ax.grid(alpha=.2);ax.legend()
        axes[1].set_xlabel('Simulated hours')
        fig.suptitle('Cell A, cycle,8mV noise: last-hour voltage-error cancellation\nFloat64 history; assimilated fit, not a forecast')
        fig.savefig(out/'hysteresis_cancellation.png',dpi=150);plt.close(fig)
    (out/'manifest.json').write_text(json.dumps(dict(artifacts={f.name:ident(f) for f in out.iterdir() if f.is_file()},
        analysis_source=ident(Path(__file__))),indent=2)+'\n')
    print(json.dumps(dict(completed_cases=len(cases),result=str(out/'result.json'))))


if __name__=='__main__':main()
