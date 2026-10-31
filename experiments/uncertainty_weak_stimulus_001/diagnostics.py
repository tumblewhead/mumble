"""Read-only likelihood diagnostics. No plant, scenario or truth imports."""
import ctypes as C
import hashlib
import json
from pathlib import Path
import subprocess
import time

import numpy as np
from experiments.foster_feedback_001.estimator import DP
from experiments.foster_uncertainty_audit_001.conditional_packet import partition
from experiments.joint_rate_history_001.field import Field, pointer
from experiments.slow_likelihood_diagnostic_001.numerics import features_jacobian, solve

ROOT = Path(__file__).resolve().parents[2]
CONVERGED = {'GN_decrement_at_cost_roundoff', 'gradient'}
GROUPS = ['OCV_charge', 'ohmic', 'RC1', 'RC2', 'RC3', 'hysteresis']


def write(path, value):
    def convert(obj):
        if isinstance(obj,np.ndarray): return obj.tolist()
        if isinstance(obj,np.generic): return obj.item()
        raise TypeError(type(obj))
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, indent=2, default=convert, allow_nan=False)+'\n')
    temp.replace(path)


def identity(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''): h.update(block)
    return dict(bytes=path.stat().st_size, sha256=h.hexdigest())


def build_parts(destination):
    """Instrument an unchanged recurrence for diagnostic component outputs only."""
    source = ROOT/'experiments/foster_bounded_hysteresis_001/model.c'
    text = source.read_text()
    signature = 'const double *factors,double *voltage,double *J,double *endpoint,double *F) {'
    assert text.count(signature) == 2  # internal predictor and exported cached wrapper
    text = text.replace(signature, signature[:-3]+',double *parts,double *partJ) {',1)
    marker = '        if(!isfinite(voltage[i]))return -8;'
    additions = '''
        if(parts) {
            double *v=parts+6*i, *D=partJ+96*i;
            v[0]=cal[1]+cal[2]*state[0]; v[1]=-I*p[1];
            for(int k=0;k<3;k++)v[2+k]=-state[1+k];
            v[5]=p[8]*h;
            for(int j=0;j<16;j++) {
                D[j]=cal[2]*S[0][j]; D[16+j]=-I*(j==6?p[1]:0.);
                for(int k=0;k<3;k++)D[16*(2+k)+j]=-S[1+k][j];
                D[80+j]=(j==13?p[8]:0.)*h+p[8]*dh*S[4][j];
            }
        }
'''
    assert text.count(marker) == 1
    text = text.replace(marker, marker+additions)
    text = text.replace('predict(x,obs,n,cal,0,voltage,J,endpoint,F);', 'predict(x,obs,n,cal,0,voltage,J,endpoint,F,0,0);')
    text = text.replace('predict(x,obs,n,cal,factors,voltage,J,endpoint,F);', 'predict(x,obs,n,cal,factors,voltage,J,endpoint,F,0,0);')
    text += '''
int foster_parts(const double *x,const double *obs,int n,const double *cal,
                 double *voltage,double *J,double *endpoint,double *F,
                 double *parts,double *partJ) {
    return predict(x,obs,n,cal,0,voltage,J,endpoint,F,parts,partJ);
}
'''
    destination.mkdir(parents=True,exist_ok=False)
    generated = destination/'parts.c'; generated.write_text(text)
    binary = destination/'parts.so'
    command = ['cc','-std=c11','-O2','-fno-fast-math','-ffp-contract=off',
               '-Wall','-Wextra','-Werror','-pedantic','-fPIC','-shared',
               '-I',str(ROOT/'experiments/foster_c_history_001'),str(generated),'-lm','-o',str(binary)]
    subprocess.run(command,check=True)
    write(destination/'build.json', dict(original_source=identity(source),instrumented_source=identity(generated),
          binary=identity(binary),command=command, purpose='diagnostic component outputs; no changed recurrence'))
    return binary


class Parts:
    def __init__(self,binary,model):
        self.lib=C.CDLL(str(binary.resolve()));self.fn=self.lib.foster_parts;self.cal=model.cal
        self.fn.argtypes=[DP,DP,C.c_int]+[DP]*7;self.fn.restype=C.c_int

    def evaluate(self,x,obs):
        x=np.ascontiguousarray(x);obs=np.ascontiguousarray(obs)
        v=np.empty(len(obs));J=np.empty((len(obs),16));end=np.empty(16);F=np.empty((16,16))
        parts=np.empty((len(obs),6));partJ=np.empty((len(obs),6,16))
        status=self.fn(pointer(x),pointer(obs),len(obs),*[pointer(a) for a in [self.cal,v,J,end,F,parts,partJ]])
        if status:raise ValueError('parts model domain/status '+str(status))
        return v,J,end,F,parts,partJ


def field_rows(field,obs):
    """Emit coefficients without QR storage; preserve original recurrence/order."""
    obs=np.ascontiguousarray(obs);rows=np.empty((len(obs),field.width))
    status=field.fn(pointer(obs),len(obs),pointer(field.cal),field.n,field.b,
                    pointer(field.rates),pointer(field.p1),pointer(field.p2),pointer(field.state),pointer(rows))
    if status:raise ValueError('field recurrence status '+str(status))
    field.count+=len(obs)
    return rows


def groups(field):
    return [[0,1,field.width-1],[2],*[list(range(3+2*i*field.n,3+2*(i+1)*field.n)) for i in range(3)],
            list(range(3+6*field.n,field.width-1))]


def partition_audit(parts, model, obs, x, L, config, binary, chunk=4096):
    field=Field(config,partition(model_origin(config))[1],1.,5,binary)
    phi=field.features(x);dphi=features_jacobian(field,x)@L
    cols=groups(field);end=x.copy();F=np.eye(16)
    contributions=np.zeros((6,16));direct=np.zeros(16);res2=np.zeros(6)
    jac2=np.zeros(6);max_sum_res=0.;max_sum_jac=0.;root=np.zeros((16,16))
    exact_g=np.zeros(16);field_g=np.zeros(16)
    parity=dict(voltage=0.,jacobian=0.,endpoint=0.,transport=0.)
    for first in range(0,len(obs),chunk):
        o=obs[first:first+chunk]
        v,J,newend,A,p,D=parts.evaluate(end,o)
        # Instrumentation checked against the actual archived C binary at every block.
        vv,JJ,ee,AA=model.evaluate(end,o)
        for key,a,b in [('voltage',v,vv),('jacobian',J,JJ),('endpoint',newend,ee),('transport',A,AA)]:
            parity[key]=max(parity[key],float(np.max(abs(a-b),initial=0)))
        Be=(J@F@L)/o[:,4,None]
        De=(D@(F@L))/o[:,4,None,None]
        pe=p/o[:,4,None];pe[:,0]-=o[:,3]/o[:,4]
        rows=field_rows(field,o)
        pf=np.column_stack([rows[:,c]@phi[c] for c in cols])
        Df=np.stack([rows[:,c]@dphi[c] for c in cols],axis=1)
        rf=rows@phi;Bf=rows@dphi;re=(v-o[:,3])/o[:,4]
        d=pe-pf;delta=De-Df
        contributions += np.einsum('ni,nj->ji',Be,d)+np.einsum('nji,n->ji',delta,rf)
        direct += Be.T@(re-rf)+(Be-Bf).T@rf
        exact_g+=Be.T@re;field_g+=Bf.T@rf
        res2+=(d*d).sum(axis=0);jac2+=(delta*delta).sum(axis=(0,2))
        max_sum_res=max(max_sum_res,float(np.max(abs(d.sum(axis=1)-(re-rf)))))
        max_sum_jac=max(max_sum_jac,float(np.max(abs(delta.sum(axis=1)-(Be-Bf)))))
        root=np.linalg.qr(np.vstack([root,Be]),mode='r')
        end=newend;F=A@F
    physical_root=np.linalg.solve(L.T,root.T).T
    nuisance=[i for i in range(16) if i!=5]
    U,s,_=np.linalg.svd(physical_root[:,nuisance],full_matrices=False)
    tolerance=np.finfo(float).eps*max(physical_root.shape)*s[0]
    rank=int((s>tolerance).sum());q=physical_root[:,5]
    qres=q-U[:,:rank]@(U[:,:rank].T@q)
    info=float(qres@qres)
    return dict(groups=GROUPS,gradient_contributions=contributions,gradient_defect_direct=direct,
        exact_data_gradient=exact_g,field_data_gradient=field_g,
        contribution_sum_max_abs_error=float(np.max(abs(contributions.sum(axis=0)-direct))),
        voltage_partition_sum_max_abs_error=max_sum_res,jacobian_partition_sum_max_abs_error=max_sum_jac,
        residual_defect_RMS=np.sqrt(res2/len(obs)),jacobian_defect_RMS=np.sqrt(jac2/len(obs)),
        instrumented_vs_archived_model_max_abs=parity,
        data_Q_information=dict(coordinate='logQ with all15 original-chart nuisance coordinates free',
            information=info,local_SD_if_full_rank=float(1/np.sqrt(info)) if info>0 else None,
            nuisance_singular_values=s,nuisance_rank=rank,numerical_rank_tolerance=tolerance,
            projection_relative_residual=float(np.linalg.norm(qres)/np.linalg.norm(q)) if np.linalg.norm(q)>0 else 0.,
            prior_included=False),data_root_whitened=root)


def model_origin(config):
    from experiments.foster_campaign_001.coordinates import prior
    return prior(config)[0]


def fit_record(fit):
    return {k:fit[k] for k in ('x','w','root','diagnostic')}


def attempt_starts(objective,starts):
    fits=[];records=[]
    for label,w in starts:
        begin=time.perf_counter()
        try:
            fit=solve(objective,start=w)
            record=dict(start=label,**fit_record(fit),wall_s=time.perf_counter()-begin)
            if fit['diagnostic']['stop'] in CONVERGED:
                fits.append(fit);record['status']='converged_local_fit'
            else:record['status']='unresolved_local_fit'
        except (ValueError,OverflowError,np.linalg.LinAlgError) as e:
            record=dict(start=label,status='unresolved',reason=str(e),wall_s=time.perf_counter()-begin)
        records.append(record)
    return min(fits,key=lambda f:f['diagnostic']['cost']) if fits else None,records


def endpoint(mean,root):
    return dict(mean=mean,root=root,Q_Ah=float(np.exp(mean[5])),SOC=float(mean[0]),
                Q_log_sd=float(np.linalg.norm(root[5])),SOC_sd=float(np.linalg.norm(root[0])),
                Q_SOC_covariance=float(root[5]@root[0]))


def observed_directions(exact,w,L):
    _,g,P,_,_=exact(w)
    q=np.linalg.solve(P,L[5]);q/=np.sqrt(q@P@q)
    correction=-np.linalg.solve(P,g)
    directions=[('profile_Q_one_GN_SD',q)]
    length=np.sqrt(correction@P@correction)
    if length>0:directions.append(('correction_one_GN_SD',correction/length))
    results=[]
    for label,d in directions:
        for h in (.1,.03):
            try:
                gp=exact(w+h*d)[1];gm=exact(w-h*d)[1]
                Hd=(gp-gm)/(2*h)
                results.append(dict(direction=label,step_in_GN_SD=h,GN_curvature=float(d@P@d),
                    observed_curvature=float(d@Hd),direction_w=d))
            except ValueError as e:results.append(dict(direction=label,status='domain_unresolved',reason=str(e)))
    return results
