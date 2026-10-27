#!/usr/bin/env python3
"""Verify closed outputs and score saved estimates; no inference/model calls."""
import os
os.environ.setdefault('MPLCONFIGDIR','/tmp/mumble-desktop-history-matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import desktop as d

out=d.HERE/'attempt001';receipt=d.load(out/'receipt.json')
assert receipt['status']=='completed'
for name,identity in receipt['files'].items():assert d.runner.identity(out/name)==identity,name
assert d.sources()==receipt['sources']
for mode in ('fidelity','causal'):
    a=out/(mode+'.stdout');b=out/(mode+'.stdout.copy')
    assert d.runner.identity(a)==d.runner.identity(b) and a.stat().st_ino!=b.stat().st_ino
q=d.load(d.HERE/'qualification/development001/receipt.json')
assert q['status']=='passed' and q['sources']==receipt['sources']
assert d.runner.identity(d.HERE/'qualification/development001/replay.so')==q['binary']
plan=d.load(d.HERE/'plan.json')
checkpoints=[d.load(out/'causal'/('checkpoint_'+str(n)+'.json')) for n in plan['checkpoints']]
for c in checkpoints:
    assert c['iterations'][0]['total']>=c['total']
    assert all(not t['accepted'] or t['after_total']<t['total'] for t in c['iterations'])
    assert 0<=c['endpoint'][0]<=1 and abs(c['endpoint'][4])<=1
    assert max(abs(v) for v in c['endpoint'][1:4])<=.25
    assert np.isfinite(c['x']).all()
fidelity=d.load(out/'fidelity/result.json');causal=d.load(out/'causal/result.json')
assert fidelity['available_nodes']==545 and fidelity['interval_NLL'][1]<=.1
assert causal['reference_reads']==causal['saved_anchor_reads']==causal['truth_reads']==0

# Only now, after both workers closed and their output hashes were fixed, read
# existing published scalar truth for scoring. No raw truth replay or fit.
truth_path=d.HERE.parent/'live_anchor_integration_001/reporting_continuation001/summary.json'
truth=d.load(truth_path);reference=np.array(truth['static_reference'])
old=next(c for c in truth['fixed_checkpoint_points'] if c['next_index']==252000)
final=checkpoints[-1];x=np.array(final['x']);physical=x.copy();physical[:6]=np.exp(x[:6])
Qerr=100*(physical[5]/reference[5]-1);SOCerr=100*(final['endpoint'][0]-old['current_truth'][0])
summary={'schema':'mumble_desktop_history_review_v1','status':'verified_desktop_baseline',
    'source_revision':receipt['source_revision'],'independent_reviewer':False,
    'worker_metadata_note':'Worker result.source_revision contains the plan base_revision, not executed source. This review and execution receipt carry the authoritative executed source revision; original worker outputs are preserved.',
    'fidelity':fidelity,'causal':causal,'qualification_checks':q['checks'],
    'scoring_after_execution_closure':True,'scoring_source':{'path':str(truth_path.relative_to(d.ROOT)),**d.runner.identity(truth_path)},
    'final_point_errors':{'Q_percent':Qerr,'SOC_percentage_points':SOCerr,
        'physical_parameters':physical.tolist(),'static_reference':reference.tolist()},
    'same_prefix_original_rolling_errors':{'Q_percent':old['Q_error_percent'],'SOC_percentage_points':old['current_SOC_error_pp']},
    'stops':[{'prefix':c['prefix'],'status':c['status'],'iterations':len(c['iterations']),
        'accepted_steps':sum(t['accepted'] for t in c['iterations']),
        'last_projected_gradient_inf':c['iterations'][-1]['projected_gradient_inf']} for c in checkpoints],
    'resources':{'decoded_history_bytes':causal['observation_bytes'],'history_bytes_per_sample':24,
        'worker_peak_RSS_bytes':max(c['peak_RSS_bytes'] for c in receipt['children']),
        'fidelity_CPU_s':receipt['children'][0]['CPU_s'],'causal_CPU_s':receipt['children'][1]['CPU_s'],
        'causal_wall_s':receipt['children'][1]['wall_s'],'supervisor_inclusive_CPU_s':receipt['CPU_s']},
    'limits':['Same recurrence in frozen reference; independent physical algebra checked on fabricated cases only.',
        'One cell, one two-hour source prefix, five sparse learning checkpoints; not a robustness campaign.',
        'Two no-decreasing-step stops remain explicit; three checkpoints meet projected-gradient tolerance. No global or all-parameter convergence claim.',
        'Different optimizer and update cadence from compact learner: point-accuracy improvement cannot be uniquely attributed to history storage.',
        'No calibrated uncertainty; solver GN/majorizer is not validated posterior precision.',
        'Memory grows with duration and replay cost grows with prefix. No firmware or M3 promotion.'],
    'next':'Use this unchanged desktop baseline to measure causal history-refresh/compression accuracy and resource tradeoffs, then return to the10KiB deployment goal.'}
report=d.HERE/'reporting001';report.mkdir()
fig,ax=plt.subplots(1,2,figsize=(10,4),layout='constrained')
minutes=[c['elapsed_s']/60 for c in checkpoints]
ax[0].plot(minutes,[1000*np.exp(c['x'][5]) for c in checkpoints],marker='o',label='Desktop estimate')
ax[0].axhline(1000*reference[5],color='gray',linestyle='--',label='Synthetic reference (scoring only)')
ax[0].set(xlabel='Received source duration (minutes)',ylabel='Capacity (mAh)',title='Five public-start learning checkpoints');ax[0].legend(fontsize=8)
ax[1].bar(['Compact original','Structured repair','Desktop replay'],[252.96040615922539,185.61224225666956,fidelity['oscillation_NLL']],color=['#777777','#bd7b22','#245f9a'])
ax[1].axhline(.1,color='black',linestyle='--');ax[1].set(ylabel='Error oscillation (NLL)',title='Same frozen 545 points; gate = 0.1')
for a in ax:a.grid(axis='y',alpha=.2)
fig.savefig(report/'comparison.png',dpi=160);fig.savefig(report/'comparison.svg');plt.close(fig)
summary['figures']={n:d.runner.identity(report/n) for n in ('comparison.png','comparison.svg')}
summary['report_script']=d.runner.identity(d.HERE/'report_saved.py')
d.runner.save(d.HERE/'result_review.json',summary)
print({'status':summary['status'],'Q_error_percent':Qerr,'SOC_error_pp':SOCerr,'resources':summary['resources']})
