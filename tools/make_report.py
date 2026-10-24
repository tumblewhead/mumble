#!/usr/bin/env python3
"""Render a self-contained study report and scientific figures from receipts."""
from pathlib import Path
import base64
import html
import json
import math
import os
import statistics
os.environ.setdefault('MPLCONFIGDIR','/tmp/scm35-mpl')
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'report'
OUT.mkdir(exist_ok=True)

def read(name):return json.loads((ROOT/name).read_text())
def fmt(x,n=4):return '—' if x is None else f'{x:.{n}g}'
def table(headers,rows):
    return '<div class="table-wrap"><table><thead><tr>'+''.join('<th>'+html.escape(str(x))+'</th>' for x in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+html.escape(str(x))+'</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table></div>'
def image_data(path):return 'data:image/png;base64,'+base64.b64encode(path.read_bytes()).decode()

def make_figures(main,manifest):
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.titlesize':12,
                         'axes.labelsize':10,'figure.facecolor':'#f7f9fc','axes.facecolor':'white',
                         'axes.spines.top':False,'axes.spines.right':False,'savefig.facecolor':'#f7f9fc'})
    fig,axes=plt.subplots(3,1,figsize=(10.4,10),sharex=True,gridspec_kw={'height_ratios':[.8,1,1]},layout='constrained')
    trace=np.loadtxt(ROOT/'data'/manifest['cases'][0]['csv'],delimiter=',',skiprows=1)
    time=np.cumsum(trace[:,1])/60
    axes[0].plot(time,trace[:,2]*1000,color='#24364b',lw=.9)
    axes[0].axvspan(30,35,color='#e1e7ef',zorder=0)
    axes[0].set(ylabel='Current (mA)',title='A. One chronological history: fast pulses, sustained loads, reversals, quiet use')
    axes[0].text(32.5,65,'3 mA tail',ha='center',fontsize=9,color='#56677a')
    colors={'cell_a':'#076b95','cell_b':'#db7044'}
    styles=['-','--',':']
    for case in manifest['cases']:
        rows=sorted([r for r in main['records'] if r['case_id']==case['case_id']],key=lambda r:r['checkpoint_s'])
        x=[r['checkpoint_s']/60 for r in rows]
        seed=case['seed']-202610240
        for ax,key in ((axes[1],'current_SOC_abs_error_pp'),(axes[2],'capacity_abs_relative_error_percent')):
            y=[max(r['scores'][key],1e-8) for r in rows]
            ax.plot(x,y,color=colors[case['cell']],ls=styles[seed],marker='o',ms=3.5,lw=1.6,
                    label=('Cell A' if case['cell']=='cell_a' else 'Cell B') if seed==0 else None)
    axes[1].set(yscale='log',ylabel='Absolute SOC error\n(percentage points)',title='B. Current SOC: all six runs below 0.5 pp from the 10-minute checkpoint')
    axes[2].set(yscale='log',ylabel='Absolute capacity error (%)',xlabel='Elapsed physical time (minutes)',title='C. Capacity: all six runs below 0.5% from the 15-minute checkpoint')
    for ax in axes[1:]:
        ax.axhline(.5,color='#687c90',ls='--',lw=.9)
        ax.text(34.8,.5,' 0.5 threshold',va='bottom',ha='right',fontsize=9,color='#56677a')
        ax.grid(axis='y',which='major',color='#e3e9ef')
        ax.axvline(400/60,color='#8b97a5',ls=':',lw=1)
        ax.legend(loc='upper right',frameon=False,ncol=2)
    axes[2].set(xlim=(0,35))
    fig.suptitle('35 Hz battery estimation over time',fontsize=18,fontweight='bold',x=.07,ha='left')
    fig.supxlabel('Two cells × three noise seeds · 1 mV iid voltage noise · known illustrative OCV · matched 25 °C model\nPoints are tested prefixes; lines connect points and do not certify intervening performance.',fontsize=9,color='#56677a')
    path=OUT/'SCM-35Hz-Convergence.png';fig.savefig(path,dpi=160);plt.close(fig)

    keys=['R0','tau1','tau2','tau3','gamma_plus','gamma_minus','H','current_soc','Q_Ah']
    labels=['Ohmic R0','Fast pole τ1','Middle pole τ2','Slow pole τ3','Discharge hysteresis γ+','Charge hysteresis γ−','Hysteresis amplitude H','Current SOC','Capacity Q']
    rows=sorted([r for r in main['records'] if r['case_id']=='cell_a_35hz_s202610240'],key=lambda r:r['checkpoint_s'])
    value={'unexcited':0,'unresolved':1,'provisional':2};mark=['U','?','P']
    matrix=np.array([[value[r['assessment']['parameters'][k]['status']] for r in rows] for k in keys])
    fig,ax=plt.subplots(figsize=(11.3,6),layout='constrained')
    cmap=ListedColormap(['#d9e1eb','#f4d8a0','#85c7c7'])
    ax.imshow(matrix,cmap=cmap,vmin=0,vmax=2,aspect='auto')
    ax.set_xticks(range(len(rows)),[str(r['checkpoint_s']) for r in rows])
    ax.set_yticks(range(len(keys)),labels)
    ax.set(xlabel='Requested checkpoint (seconds; equally spaced columns)',title='What the estimator says it knows — first cell, first noise seed')
    for i in range(len(keys)):
        for j in range(len(rows)):ax.text(j,i,mark[matrix[i,j]],ha='center',va='center',color='#24364b',fontweight='bold')
    ax.set_xticks(np.arange(-.5,len(rows),1),minor=True);ax.set_yticks(np.arange(-.5,len(keys),1),minor=True)
    ax.grid(which='minor',color='white',linewidth=2);ax.tick_params(which='minor',bottom=False,left=False)
    ax.legend(handles=[Patch(color=c,label=t) for c,t in zip(cmap.colors,['U: stimulus absent','?: unresolved','P: passes local precision screen'])],loc='upper center',bbox_to_anchor=(.45,-.16),ncol=3,frameon=False)
    fig.supxlabel('“Provisional” is a local diagnostic, not a confidence certificate. R0 and the fastest pole remain unresolved here.\nDefaults: 10% relative two-sigma half-width; SOC 5 percentage points. Early optimizer limits also withhold local ranges.',fontsize=9,color='#56677a')
    knowledge=OUT/'SCM-35Hz-Knowledge.png';fig.savefig(knowledge,dpi=160);plt.close(fig)
    return path,knowledge

def main():
    data=read('results/streaming_results.json');manifest=read('data/manifest.json')
    tail=read('results/tail_only_result.json');profiles=read('results/profile_results.json')
    comp=read('results/compression_results.json');refine=read('results/refinement_220.json')
    fig,knowledge=make_figures(data,manifest)
    finals=[r for r in data['records'] if r['checkpoint_s']==2100]
    metric=data['summary']['final_point_metrics']
    checkpoints=[400,600,900,1800,2100]
    progression=[]
    for t in checkpoints:
        rows=[r for r in data['records'] if r['checkpoint_s']==t]
        progression.append([f'{t} s',fmt(max(r['scores']['current_SOC_abs_error_pp'] for r in rows),5),fmt(max(r['scores']['capacity_abs_relative_error_percent'] for r in rows),5)])
    criteria=[('R0',10,'R0 <10%'),('R1',10,'R1 <10%'),('R2',10,'R2 <10%'),('R3',10,'R3 <10%'),
              ('tau1',10,'τ1 <10%'),('tau2',10,'τ2 <10%'),('tau3',10,'τ3 <10%'),
              ('gamma_plus',10,'γ+ <10%'),('gamma_minus',10,'γ− <10%'),('H',10,'H <10%'),
              ('current_soc',.5,'Current SOC <0.5 pp'),('Q_Ah',5,'Capacity <5%'),('Q_Ah',.5,'Capacity <0.5%'),
              ('R0',5,'R0 <5%'),('tau1',5,'τ1 <5%'),('R1',.5,'R1 <0.5%'),('tau1',.5,'τ1 <0.5%')]
    conv=[]
    for key,threshold,label in criteria:
        rows=[r for r in data['convergence'] if r['metric']==key and r['threshold']==threshold]
        times=[r['time_s'] for r in rows if r['time_s'] is not None]
        conv.append([label,f'{len(times)}/6',('—' if not times else str(min(times)) if min(times)==max(times) else f'{min(times)}–{max(times)}')+' s' if times else 'Not reached',f'{6-len(times)}/6' if len(times)<6 else '0/6'])
    first={r['checkpoint_s']:r for r in data['records'] if r['case_id']=='cell_a_35hz_s202610240'}
    readiness=[]
    for key,limit,field,label in [('current_soc',.005,'local_halfwidth','SOC local half-width ≤0.5 pp'),
                                  ('Q_Ah',.005,'relative_halfwidth','Q local relative half-width ≤0.5%'),
                                  ('R0',.10,'relative_halfwidth','R0 local relative half-width ≤10%'),
                                  ('tau1',.10,'relative_halfwidth','τ1 local relative half-width ≤10%'),
                                  ('tau2',.10,'relative_halfwidth','τ2 local relative half-width ≤10%'),
                                  ('tau3',.10,'relative_halfwidth','τ3 local relative half-width ≤10%')]:
        times=[]
        for case in manifest['cases']:
            rows=sorted([r for r in data['records'] if r['case_id']==case['case_id']],key=lambda r:r['checkpoint_s'])
            targets=[r['assessment']['parameters'][key] for r in rows]
            ok=[p['status']=='provisional' and p[field] is not None and p[field]<=limit for p in targets]
            found=next((r['checkpoint_s'] for j,r in enumerate(rows) if all(ok[j:])),None)
            if found is not None:times.append(found)
        readiness.append([label,f'{len(times)}/6',('—' if not times else str(min(times)) if min(times)==max(times) else f'{min(times)}–{max(times)}')+' s' if times else 'Not reached'])
    qualification=[]
    for t in [10,400,600,900,2100]:
        p=first[t]['assessment']['parameters']['Q_Ah']
        qualification.append([str(t),fmt(p['point']*1000,6),' to '.join(fmt(x*1000,6) for x in p['local_range']),p['status'],p['range_kind'].replace('_',' ')])
    target_profiles=[]
    for p in profiles['profiles']:
        if p['checkpoint_s'] in [600,900,2100] and p['target'] in ['Q_Ah','current_soc','gamma_minus','tau1']:
            mult=1000 if p['target']=='Q_Ah' else 100 if p['target']=='current_soc' else 1
            name={'Q_Ah':'Q (mAh)','current_soc':'SOC (%)','gamma_minus':'γ− (per Ah)','tau1':'τ1 (s)'}[p['target']]
            target_profiles.append([str(p['checkpoint_s']),name,' to '.join(fmt(x*mult,7) for x in p['support_bracket']),str(p.get('optimizer_unresolved',0)),str(p.get('missing_optimizations',0))])
    carry=[]
    for label,r in [('Complete observed history',tail['full_history_reference']),('Last 300 s only',tail['records'][0])]:
        s=r['scores'];a=r['assessment']['parameters']
        carry.append([label,fmt(s['voltage_rmse_mV'],7),fmt(s['current_SOC_abs_error_pp'],6),fmt(s['capacity_abs_relative_error_percent'],6),a['current_soc']['status']+' / '+a['Q_Ah']['status']])
    compression=[]
    for r in comp['records']:
        f=r['result'];s=r['scores']
        compression.append([r['cell'].replace('cell_','').upper(),r['method'],str(f['features']),fmt(100*(1-f['features']/f['samples']),5)+'%',fmt(s['voltage_rmse_mV'],10),fmt(s['capacity_abs_relative_error_percent'],6),fmt(s['current_SOC_abs_error_pp'],6),fmt(f['elapsed_cpu_s']+f['basis_seconds'],5)])
    memory=[]
    for r in comp['records'][:3]:
        f=r['result'];memory.append([r['method'],str(f['payload_bytes']),str(f['basis_bytes']),str(f['retained_bytes']),str(f['setup_peak_bytes'])])
    final_errors=[]
    for key in ['R0','R1','R2','R3','tau1','tau2','tau3','H','gamma_plus','gamma_minus','Q_Ah']:
        final_errors.append([key,fmt(max(abs(r['scores']['parameter_relative_errors_percent'][key]) for r in finals),6)])
    metrics={'sampling_Hz':35,'cases':6,'prefix_fits':60,'samples_per_full_history':73500,
             'summary':data['summary'],'time_criteria':conv,'local_readiness':readiness,'carry_control':carry,
             'main_uncertainty':'local diagnostic only','nonlinear_profiles':'finite grid; unresolved outside points withheld',
             'compression_fits':len(comp['records']),'hardware_port_complete':False}
    (OUT/'report_metrics.json').write_text(json.dumps(metrics,indent=2)+'\n')
    body=f'''
<header><p class="eyebrow">RESEARCH REFERENCE · C99 · 35 HZ</p><h1>Learn what the stimulus supports.<br>Carry the evidence forward.</h1>
<p class="lead">A working C estimator and a measured convergence study for a battery whose parameters become observable at different times.</p>
<p class="sub">Fresh three-mode experiment · two cells × three noise seeds · October 2026</p></header>
<section class="cards"><div><b>600 s</b><span>All six SOC estimates below 0.5 percentage-point error</span></div><div><b>900 s</b><span>All six capacity estimates below 0.5% error</span></div><div><b>723</b><span>Event-local features in the one-anchor comparison, from 73,500 samples</span></div></section>
<section><h2>What is implemented</h2><p>The C implementation estimates three RC modes, ohmic resistance, asymmetric throughput hysteresis, capacity, initial SOC and entering dynamic states. It also reports an individual status and uncertainty diagnostic for each target. A numerical point remains visible without being presented as known. Earlier observations are carried forward by replaying the complete observed history at each checkpoint.</p>
<p><strong>This is a host reference, not a completed Cortex-M23 port.</strong> The physical propagation and assessment modules use fixed-size caller-owned memory, but the fit and explicit projection construction still allocate history-sized buffers. The package contains source, data, reproducible runners, verification receipts and this report.</p></section>
<section><h2>Experiment contract</h2><p>Each run ingests 73,500 point observations over 2,100 seconds at 35 Hz. Current is piecewise constant during each interval and terminal voltage is measured at its end. Current, timing, the OCV curve and temperature are exact in this experiment; voltage noise is independent Gaussian with 1 mV standard deviation. Both synthetic cells have constant parameters and the generating model matches the fitted model.</p>
<p>The actual numerical measured OCV–SOC table was not provided, so this run uses the explicit illustrative curve U(z)=3+1.15z+0.08 tanh(8(z−0.5)) V. The executable accepts a measured monotone 25 °C table through <code>--ocv</code>. These results therefore establish behavior under a known curve, not performance on the user’s measured cell.</p>
{table(['Quantity','Cell A','Cell B'],[['Capacity','60 mAh','64.7 mAh'],['Initial SOC','80%','78%'],['RC time constants','50 ms, 500 ms, 5 s','75 ms, 650 ms, 7.5 s'],['R0','0.12 Ω','0.16 Ω'],['R1, R2, R3','0.18, 0.22, 0.28 Ω','0.22, 0.27, 0.33 Ω'],['Hysteresis amplitude','25 mV','30 mV'],['γ+ / γ−','220 / 370 per Ah','330 / 500 per Ah']])}
<p>All these quantities and the entering RC/hysteresis states are unknown to the estimator. Truth is supplied only to independent post-fit scoring. Seven nonlinear coordinates and nine conditional linear amplitudes give sixteen fitted quantities. The initial conditions are not reset at event boundaries.</p>
<div class="equation">zₖ₊₁ = zₖ − Iₖ Δtₖ / (3600 Q)<br>vᵢ,ₖ₊₁ = e<sup>−Δtₖ/τᵢ</sup>vᵢ,ₖ + RᵢIₖ(1 − e<sup>−Δtₖ/τᵢ</sup>)<br>hₖ₊₁ = e<sup>−γ±|Iₖ|Δtₖ/3600</sup>hₖ + (1 − e<sup>−γ±|Iₖ|Δtₖ/3600</sup>)sign(Iₖ)<br>Vₖ = U₂₅(zₖ) − R₀Iₖ − Σvᵢ,ₖ − Hhₖ</div>
<p>Positive current discharges. At rest the polarization states relax; SOC and throughput hysteresis do not. Capacity is in Ah and current stays in measured amperes, independent of candidate capacity.</p></section>
<section><h2>The stimulus gives different information at different times</h2>
{table(['Elapsed time','Stimulus and purpose'],[['0–10 s','Rest with unknown entering polarization'],['10–40 s','Thirty short discharge-pulse groups; early fast-mode information'],['40–400 s','Sustained discharge and relaxation; no charging observations yet'],['400–1,800 s','Charge/discharge reversals and varied levels; separate SOC, capacity and hysteresis'],['1,800–2,100 s','3 mA weak-use tail; test retention of earlier evidence']])}
<p>The first negative-current observation occurs at 400.028571 s, so the 400-second fit contains no charging sample. The total net movement is about 21–23 SOC percentage points. This numerical schedule is not a hardware excitation prescription. The user’s reported 20 Hz degradation and 1 kHz diminishing returns motivated the nominal rate; this study does not independently compare those sample rates.</p>
<img src="{image_data(fig)}" alt="Current history and six-run SOC and capacity errors against physical elapsed time"></section>
<section><h2>Convergence: accuracy and self-knowledge are separate</h2><p>“Reached” below means the first requested checkpoint strictly below the stated truth-error threshold at that and every later requested checkpoint. It does not claim the crossing happened exactly then, that every intervening instant passes, or that later untested operation will pass. The sample times are 10, 40, 220, 400, 600, 900, 1,200, 1,500, 1,800 and 2,100 seconds.</p>
{table(['Empirical accuracy criterion','Runs reached','First passing checkpoint range','Not reached by 2,100 s'],conv)}
<p>Early point accuracy is not sufficient evidence for releasing a parameter. Some targets happen to fit well before the likelihood narrows enough to support them. The default reporter also withholds local intervals when the selected optimization has not met its numerical stopping criteria.</p>
{table(['Time','Worst current-SOC error (pp)','Worst capacity error (%)'],progression)}
<p>At 2,100 seconds the largest voltage RMSE is {metric['max_voltage_RMSE_mV']:.6f} mV. The worst current-SOC error is {metric['max_current_SOC_abs_error_pp']:.8f} percentage points and the worst capacity error is {metric['max_capacity_abs_relative_error_percent']:.7f}%. These very small errors reflect the ideal matched-model setup. They are not predictions of field accuracy.</p>
<details><summary>Final parameter errors across six runs</summary>{table(['Parameter','Worst absolute relative error (%)'],final_errors)}</details></section>
<section><h2>The estimator explicitly reports unresolved quantities</h2><p>The C assessment distinguishes <strong>unexcited</strong>, <strong>unresolved</strong> and <strong>provisional</strong>. Unexcited means a supported structural check finds the relevant stimulus absent. Unresolved includes null directions, excessive uncertainty, numerical limits and unsupported coordinate charts. Provisional means a finite local range passes an engineering precision screen; it does not assert nonlinear or real-world validity.</p>
<p>The assessment uses the undamped joint likelihood matrix, with the correct cross-covariances for current SOC and h₀=u₀/H. A target with a material component in a numerical null direction retains its declared support. A pseudoinverse is never used to turn an unobserved direction into zero variance. Bounds are not used to clip a range into apparent precision, and a near-zero hysteresis amplitude makes the h₀ ratio unavailable.</p>
<p>Default screens use a two-sigma half-width of at most 10% for positive physical parameters and five percentage points for SOC. These are configurable thresholds on a local approximation, not calibrated probability statements. Entering nuisance states have no automatic release threshold.</p>
<p>A stricter reporting screen can be evaluated without looking at truth. The following times require a usable local range at every remaining checkpoint. SOC and capacity pass the stricter 0.5 pp / 0.5% screens at the same checkpoints as their empirical accuracy crossings; the fast pole and R₀ show the gap between point accuracy and supported precision.</p>
{table(['Local two-sigma range criterion','Runs reached','First passing checkpoint range'],readiness)}
<img src="{image_data(knowledge)}" alt="Per-target provisional, unresolved and unexcited statuses across ten prefixes">
{table(['Time (s)','Q point (mAh)','Reported Q range (mAh)','Status','Range meaning'],qualification)}
<p>The 400-second capacity point in the first run is close to 60 mAh, but the reporter correctly retains the 30–100 mAh support. Before current reversal, γ− is unexcited. By 900 seconds, capacity, current SOC and both hysteresis rates pass their local screens in this run. R₀ and the fastest pole still do not pass the 10% local-width screen at the final time. Useful SOC and capacity estimation therefore does not require every model coordinate to be known.</p></section>
<section><h2>Nonlinear checks and numerical limits</h2><p>Selected targets were held fixed while the C solver refit the remaining admitted quantities. The profile grid used prior support and local curvature, never truth. A fixed current SOC uses z₀=z<sub>end</sub>+D/Q and the matching chain rule. Its constrained-coordinate matrix is explicitly rejected as an unrestricted covariance matrix.</p>
{table(['Time (s)','Profile target','Heuristic grid bracket','Unfinished fits','Missing fits'],target_profiles)}
<p>These brackets use a Δnegative-log-likelihood threshold of two relative to the lowest observed feasible cost. They are finite-grid local-optimization evidence, not global exclusion proofs or calibrated confidence intervals. A low-cost feasible candidate can serve as a witness. An unfinished high-cost optimization cannot justify an outside boundary; that side falls back to declared support when no converged outside point is available.</p>
<p>The 29 selected profiles produced 369 numerical candidates: 296 met stopping criteria and 73 did not; one additional attempted fit failed operationally. All returned candidates were independently evaluated. No heuristic bracket uses an unfinished outside point. One extreme, high-cost, unfinished candidate had sub-10⁻¹⁶ V amplitude-bound roundoff that made a naive u₀/H ratio invalid; the reporter now suppresses that near-zero ratio. It did not affect accepted profile points.</p>
<p>The main 60-fit campaign had 50 numerical successes and ten iteration limits. A same-prefix capacity profile found a 220-second solution with a negative log likelihood lower by {refine['improvement_over_original']:.6f}. An unrestricted refinement confirmed it, but capacity stayed near the 100 mAh search bound and SOC error remained about 2.82 percentage points. The original campaign is preserved and the refinement is saved separately. This is evidence for retaining the early “unresolved” designation, not silently replacing a difficult result.</p></section>
<section><h2>Carry evidence through weak use</h2><p>The final five minutes alone have insufficient information to recover the history. The full-history fit retains the earlier pulse and reversal evidence. A fresh fit to just the quiet tail has unknown entering states and cannot reliably separate SOC and capacity, even while fitting voltage closely.</p>
{table(['Evidence used','Voltage RMSE (mV)','SOC error (pp)','Capacity error (%)','SOC / capacity status'],carry)}
<p>This control is one first-cell/first-seed example. The tail-only fit also reached its iteration limit, so its exact errors cannot be assigned solely to structural observability. The broad uncertainty and absent charging direction still remain explicit. Carry-forward here means retaining actual observations and replaying them; a warm start alone would not preserve their uncertainty or identifiability.</p></section>
<section><h2>Event-local compression works here, with visible costs</h2><p>The supplemental comparison uses 106 constant-current event blocks, the same nominal initialization and three starts for every method, and one seed from each cell. The one-anchor tangent method preserves local amplitude and sensitivity directions. The hybrid method adds four prior anchors and their mean-response differences. Neither basis uses fitted truth or a future full-history solution.</p>
{table(['Cell','Method','Features','Payload reduction','Raw voltage RMSE (mV)','Q error (%)','SOC error (pp)','Fit + basis CPU (s)'],compression)}
<p>The original idea extends from one global projection to event-local blocks while preserving carried physical state. Here 723 one-anchor features retain close SOC/capacity fits, and 1,442 hybrid features reproduce the full fit much more closely. These are event blocks, not yet a learned vocabulary of multi-event words.</p>
<div class="equation">L(θ) = [‖Qᵀr(θ)‖² + ‖(I−QQᵀ)r(θ)‖²] / (2σ²)</div>
<p>This identity shows the limitation. Compression retains the first term. If every relevant sensitivity direction lies in the retained basis, the first-order information is preserved at that anchor. Nonlinear changes outside that span can change the discarded term. More anchors help in these examples; they do not prove global sufficiency. The event’s entering state and prior evidence remain part of its meaning.</p>
{table(['Method','Feature payload bytes','Stored basis bytes','Total retained bytes','Accounted setup peak bytes'],memory)}
<p>Feature payload reduction is not firmware memory reduction. The explicit one-anchor representation retains about 9.0 MB on this host, and hybrid about 24.4 MB; their fitting plus basis construction is slower than the roughly 3-second full fit. Hybrid construction also peaks above the full method. The numbers support pursuing compact analytical event accumulators rather than claiming that this explicit basis implementation meets the MCU budget.</p></section>
<section><h2>Verification and execution scope</h2><p>C performs all model propagation, optimization, projection and final qualification. Python generates synthetic traces, orchestrates jobs, recomputes physical predictions independently, scores truth errors and draws these figures. The complete command, initial guess source, binary/source hashes, return status and numerical diagnostics are retained for each fit.</p>
<ul><li>All 60 main candidates were independently recomputed; maximum absolute raw-objective discrepancy was 2.33×10⁻⁸.</li><li>The C forward model and independent predictor agreed over 147,000 truth-generated samples to about 1.46×10⁻¹² V.</li><li>Finite-difference, state-carry, ordering, rest ambiguity, projection, constraint restoration and public-API canaries are included.</li><li>The C and Python qualification layers agree across 61 stored fits and 1,098 target reports; no optimization was repeated for that comparison.</li><li>The final CLI assessment integration was checked against the preserved benchmark executable with identical commands. Core fit outputs are unchanged.</li><li>Address/undefined-behavior instrumentation was used on the estimator test; leak scanning and MCU stack/cycle measurements were not performed.</li></ul>
<p>Across the six final full-history campaign fits, median host C CPU time was {metric['median_C_CPU_s']:.6f} seconds. This is time for a complete retrospective prefix fit, not per-sample inference latency. It is not transferable to a Cortex-M23. Main full-fit retained allocations total 49,394,072 bytes, including 47,040,000 bytes of cached rows. The fixed physical state is 280 bytes, model row 648 bytes, assessment workspace 4,224 bytes and assessment output 2,488 bytes on this host. A complete SRAM/stack budget remains to be designed.</p></section>
<section><h2>Next engineering step</h2><p>The next implementation should make every event update conditional on the directions it can support, retain earlier qualified evidence and track its age and compatibility, and propagate SOC continuously between slower parameter updates. A residual inconsistency check must reopen uncertainty when the cell or operating regime changes. The current experiment uses constant parameters and does not validate aging or drift handling.</p>
<p>For bounded memory, candidate approaches include exact event accumulators for a fixed model chart, a bounded set of retained excitation windows, and controlled relinearization with a residual guard. Their validity must be compared against this replay reference. A word can then be scored by its marginal contribution given existing evidence and its entering state; a universal context-free catalog of useful token strings would miss that dependence.</p>
<p>Repeated independent observations reduce noise in already observed directions, but cannot create an absent direction. Retaining a normalized average without count, variance or correlation information would lose that distinction. Observation provenance is also necessary to avoid counting the same evidence twice.</p>
<p>Before field claims, use the measured OCV table and test current/voltage offsets, filtered or correlated noise, time jitter, temperature variation, model mismatch and gradual or abrupt parameter changes. The very small matched-model errors here should not be used as a real-cell accuracy specification.</p></section>
<footer><p>Reproducible files: README.txt; src/ and include/; data/manifest.json and six CSVs; results/streaming_results.json; profile_results.json; compression_results.json; tail_only_result.json; independent validation receipts; tools/ runners.</p><p>Source archive and this standalone report accompany the study. All numerical findings above are derived from the included receipts; the report can be regenerated with tools/make_report.py.</p></footer>
'''
    style='''*{box-sizing:border-box}body{margin:0;background:#f1f4f8;color:#233449;font:16px/1.65 system-ui,-apple-system,Segoe UI,sans-serif}main{max-width:1120px;margin:0 auto;background:white;padding:56px 64px}header{border-bottom:3px solid #076b95;padding-bottom:28px;margin-bottom:28px}.eyebrow{font-size:12px;letter-spacing:.16em;font-weight:750;color:#076b95}h1{font-size:42px;line-height:1.16;letter-spacing:-.025em;margin:14px 0 22px}h2{font-size:25px;line-height:1.3;color:#113f5e;margin:0 0 18px}.lead{font-size:20px;max-width:850px}.sub,footer{color:#647487;font-size:13px}section{margin:42px 0}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.cards div{background:#eaf3f8;padding:21px;border-top:3px solid #076b95}.cards b{display:block;font-size:32px;color:#07577a}.cards span{display:block;font-size:14px;line-height:1.5;margin-top:5px}p{margin:14px 0}img{width:100%;height:auto;border:1px solid #e1e7ef;margin:18px 0}.table-wrap{overflow:auto;margin:22px 0}table{border-collapse:collapse;width:100%;font-size:13px;line-height:1.5}th{background:#eaf0f5;text-align:left;color:#29445d;padding:11px 12px;white-space:nowrap}td{padding:10px 12px;border-bottom:1px solid #e5ebf0;vertical-align:top}tr:nth-child(even) td{background:#fafbfd}.equation{background:#f5f8fa;border-left:3px solid #65a6b4;padding:19px 22px;margin:24px 0;font-family:Georgia,serif;font-size:18px;line-height:1.9;overflow:auto}code{font-size:14px;background:#edf2f5;padding:2px 5px}details{padding:16px 0}summary{cursor:pointer;color:#076b95;font-weight:650}li{margin:8px 0}footer{border-top:1px solid #dce4ec;margin-top:46px;padding-top:20px}@media(max-width:760px){main{padding:28px 20px}h1{font-size:32px}.cards{grid-template-columns:1fr}h2{font-size:22px}}@media print{body{background:white}main{padding:0}section{break-inside:auto}h2{break-after:avoid}tr,img{break-inside:avoid}details{display:block}}'''
    document='<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SCM 35 Hz C estimator — conditional learning and convergence</title><style>'+style+'</style></head><body><main>'+body+'</main></body></html>'
    path=OUT/'SCM-35Hz-Results.html';path.write_text(document)
    print(json.dumps({'report':str(path),'bytes':path.stat().st_size,'figures':[str(fig),str(knowledge)]}))

if __name__=='__main__':main()
