"""One parameter per page, one case per panel; bounded plotting summaries only."""
import json
import math
from pathlib import Path
import numpy as np
from .telemetry import PARAMETERS
from .rate import LEGACY_RATE


def error_bins(case,report,arm,truth,start_hour=0.,end_hour=None,points=2000):
    from .plot import parameter_error
    if report.get('recording')=='compact':
        with np.load(case/'plot_summary.npz',allow_pickle=False) as z:
            rate=report.get('sample_rate_Hz',LEGACY_RATE)
            first=z[arm+'_first']/(3600*rate);last=z[arm+'_last']/(3600*rate)
            mask=last>start_hour
            if end_hour is not None:mask &= first<=end_hour
            return dict(first=first[mask],last=last[mask],**{
                k:100*(z[arm+'_'+k][mask,22:33]/truth[None,:]-1) for k in ('low','high','mean')})
    rows=np.load(case/(arm+'_trace.npy'),mmap_mode='r')[:report['arms'][arm]['outputs']]
    first=np.searchsorted(rows[:,1],start_hour*3600,side='right')
    last=len(rows) if end_hour is None else np.searchsorted(rows[:,1],end_hour*3600,side='right')
    rows=rows[first:last];n=len(rows)
    output={k:[] for k in ('first','last','low','high','mean')}
    if not n:return {k:np.empty((0,11)) if k in ('low','high','mean') else np.empty(0) for k in output}
    edges=np.linspace(0,n,min(n,points)+1,dtype=int)
    for first,last in zip(edges[:-1],edges[1:]):
        low=np.full(11,np.inf);high=-low;total=np.zeros(11)
        for offset in range(first,last,8192):
            values=100*(rows[offset:min(offset+8192,last),22:33]/truth[None,:]-1)
            low=np.minimum(low,values.min(axis=0));high=np.maximum(high,values.max(axis=0));total+=values.sum(axis=0)
        output['first'].append(rows[first,1]/3600);output['last'].append(rows[last-1,1]/3600)
        output['low'].append(low);output['high'].append(high);output['mean'].append(total/(last-first))
    return {k:np.asarray(v) for k,v in output.items()}


def render_error_comparisons(campaign,reports,destination,start_hour=0.,end_hour=None):
    import matplotlib.pyplot as plt
    from .plot import ARM_COLORS
    if not reports:return []
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=False)
    data=[]
    for report in sorted(reports,key=lambda r:r['directory']):
        case=campaign/report['directory'];cell=json.loads((case/'scenario.json').read_text())['cell_definition']
        truth=np.array([cell['parameters'][name] for name in PARAMETERS])
        if not np.isfinite(truth).all() or np.any(truth<=0):raise ValueError('positive reference truth required')
        data.append((report,{arm:error_bins(case,report,arm,truth,start_hour,end_hour) for arm in report['arms']}))
    files=[]
    # Keep figures readable when campaigns exceed16cases: paginate, never squeeze.
    for offset in range(0,len(data),16):
        page=data[offset:offset+16];cols=min(4,len(page));rows=math.ceil(len(page)/cols)
        for j,name in enumerate(PARAMETERS):
            fig,axes=plt.subplots(rows,cols,figsize=(4.3*cols,3.0*rows),layout='constrained',squeeze=False)
            handles={}
            for ax,(report,arms) in zip(axes.flat,page):
                for arm,values in arms.items():
                    x=np.column_stack([values['first'],values['last']]).ravel();mean=np.repeat(values['mean'][:,j],2)
                    low=np.repeat(values['low'][:,j],2);high=np.repeat(values['high'][:,j],2)
                    color=ARM_COLORS[arm];style='--' if arm=='tangent64' else '-'
                    ax.fill_between(x,low,high,color=color,alpha=.16)
                    line,=ax.plot(x,mean,label=arm,color=color,linestyle=style,lw=.9);handles[arm]=line
                scenario=report['scenario'];title=f"{report['directory']} · {scenario['cell']} · {scenario['load']}\n{1000*scenario['noise_v']:g} mV · noise seed {scenario['seed']}"
                if 'load_seed' in scenario:title+=f" · load {scenario['load_seed']}"
                ax.set_title(title,fontsize=8);ax.axhline(0,color='#555555',lw=.6);ax.grid(alpha=.2)
                ax.set_yscale('symlog',linthresh=1.);ax.set_xlabel('Simulated hours');ax.set_ylabel('Error (% of reference truth)')
                ax.set_ylim(-max(abs(v) for v in ax.get_ylim()),max(abs(v) for v in ax.get_ylim()))
            for ax in list(axes.flat)[len(page):]:ax.set_visible(False)
            fig.legend(handles.values(),handles.keys(),loc='outside upper right',fontsize=9)
            fig.suptitle(name+' relative error — one case per panel\nZero = truth; bin means/ranges; signed symlog (linear within ±1%); each panel has its own limits',fontsize=11)
            suffix='' if len(data)<=16 else f'_page{offset//16+1:02d}'
            for ext in ('png','pdf'):
                path=destination/(name+suffix+'.'+ext)
                if path.exists():raise FileExistsError('comparison plot exists: '+str(path))
                fig.savefig(path,dpi=150);files.append(str(path.relative_to(destination.parent)))
            plt.close(fig)
    return files
