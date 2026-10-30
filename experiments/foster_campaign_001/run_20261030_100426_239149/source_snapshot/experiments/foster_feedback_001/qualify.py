"""Finite physical producer, Gaussian adapter and ownership checks."""
import json
import math
import numpy as np
from .estimator import Model,Rolling,prior,fit
from .history import pack_message,message,pack_kernel,GaussianBackend,kernel
from .plant import scalar_step,CELLS,generate
from specifications.evidence_feedback_001.protocol import EvidenceToken,Boundary,digest


def physical_parameters(x):
    p=np.exp(x[5:]);p[5]+=p[3];p[7]+=p[5];return p


def qualify(binary,config,model_id):
    model=Model(binary,config);x,L=prior(config);checks=[]
    def check(name,ok,**details):checks.append(dict(name=name,passed=bool(ok),**details))
    def close(name,a,b,atol=1e-10,rtol=1e-9):
        check(name,np.allclose(a,b,atol=atol,rtol=rtol),max_abs=float(np.max(np.abs(np.asarray(a)-b),initial=0)))
    # Independent scalar state recurrence, each sign, zero current and changingT.
    rows=[]
    for i in range(64):rows.append([0. if i==0 else (1/35 if i%3 else 2/35),[.03,0.,-.03][i%3],20+i%11,3.7,.004])
    obs=np.array(rows);v,J,end,F=model.evaluate(x,obs);state=x[:5].tolist();reference=[]
    for row in obs:
        p=physical_parameters(x)*np.exp(np.array(config['arrhenius_A_K'])*(1/(row[2]+273.15)-1/config['reference_temperature_K']))
        state,voltage=scalar_step(state,p,row[0],row[1],config['ocv_intercept_V'],config['ocv_slope_V_per_SOC']);reference.append(voltage)
    close('independent forward voltage',v,reference);close('independent endpoint',end[:5],state)
    for j in range(16):
        delta=1e-6 if j not in [1,2,3] else 1e-7;xp=x.copy();xm=x.copy();xp[j]+=delta;xm[j]-=delta
        vp,_,ep,_=model.evaluate(xp,obs);vm,_,em,_=model.evaluate(xm,obs)
        close('voltage derivative/'+str(j),J[:,j],(vp-vm)/(2*delta),atol=2e-8,rtol=2e-5)
        close('transport derivative/'+str(j),F[:,j],(ep-em)/(2*delta),atol=2e-8,rtol=2e-5)
    # Same declared local linearization, independent retained-row Gaussian oracle.
    obs[:,3]=v+.002*np.sin(np.arange(len(v)))
    rolling=Rolling(binary,config,digest('qualification'),model_id)
    head=rolling.history.read();A=J/obs[:,4,None];r=(v-obs[:,3])/obs[:,4]
    c=float(np.log(obs[:,4]).sum()+len(obs)*.5*math.log(2*math.pi))
    B=A@L;P=np.linalg.inv(np.eye(16)+B.T@B);w=-P@B.T@r
    expected_mean=end+F@L@w;expected_cov=F@L@P@L.T@F.T
    S=np.eye(len(obs))+B@B.T
    expected_logZ=-c-.5*(r@np.linalg.solve(S,r)+np.linalg.slogdet(S)[1])
    for encoding in ['float64','float32']:
        payload=pack_kernel(x,end,F,A,r,c,encoding)
        token=EvidenceToken(rolling.binding,Boundary(0,0),Boundary(64,1920),head.message_id,payload)
        m,root,logZ=message(GaussianBackend().advance(head.payload,token))
        tol=2e-10 if encoding=='float64' else 2e-6
        close('retained linearized mean/'+encoding,m,expected_mean,atol=tol,rtol=tol)
        close('retained joint covariance/'+encoding,root@root.T,expected_cov,atol=tol,rtol=tol)
        close('retained normalization/'+encoding,logZ,expected_logZ,atol=tol,rtol=tol)
        check('token numeric bytes/'+encoding,len(payload)==(3537 if encoding=='float64' else 1901))
    # Continuous parameter values are evaluated directly, not selected from nodes.
    for q in [.0523,.0567,.0591]:
        a=x.copy();a[5]=math.log(q);_,_,e,_=model.evaluate(a,np.array([[1.,.03,25.,3.7,.004]]))
        close('continuousQ/'+str(q),e[0],x[0]-.03/(3600*q))
    streams={};diagnostic=[]
    for cell in ['A','B']:
        data,truth=generate(config,512,cell=cell)
        arms=[Rolling(binary,config,digest('short'+cell),model_id,e) for e in ['float64','float32']]
        for i,row in enumerate(data):
            for arm in arms:arm.offer(i,*map(float,row))
        for arm in arms:
            check('owned source once/'+cell+'/'+arm.encoding,arm.history.read().boundary.sequence==512 and arm.window.query_scope(arm.history.read())==(512,512))
        a,b=[arm.readout(float(data[-1,2])) for arm in arms]
        check('short encodingQ/'+cell,abs(100*(a['Q']-b['Q'])/a['Q'])<=.5)
        check('short encodingSOC/'+cell,abs(100*(a['SOC']-b['SOC']))<=.5)
        settings={**config['numerical'],'max_rounds':30}
        anchor,physical,stop=fit(model,x,L,data,settings)
        # Retained nonlinear MAP/GN diagnostic is not an exact Bayesian oracle.
        diagnostic.append(dict(cell=cell,rolling=a,retained_point_Q=math.exp(anchor[5]),retained_SOC=float(physical[2][0]),
            retained_stop=stop,truth_Q=float(truth[-1,0]),truth_SOC=float(truth[-1,2]),
            scope='Short nonlinear retained-data MAP comparison; no posterior coverage or convergence equivalence claim'))
    # Prior message is immutable on independent queries and rejected duplicate.
    saved=rolling.history.read()
    check('read immutability',rolling.history.read()==saved)
    try:arms[0].offer(511,*map(float,data[-1]))
    except ValueError:check('duplicate rejected',True)
    else:check('duplicate rejected',False)
    return dict(status='passed' if all(c['passed'] for c in checks) else 'failed',
                passing_checks=sum(c['passed'] for c in checks),failed_checks=[c for c in checks if not c['passed']],
                checks=checks,retained_nonlinear_diagnostics=diagnostic,
                scope='Finite model derivatives, local linearized Gaussian ownership/transport and short stream checks; not global nonlinear posterior qualification')
