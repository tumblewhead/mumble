"""Continuous rolling Foster producer plus generic history feedback adapter."""
import ctypes as C
import math
import numpy as np
from specifications.evidence_feedback_001.protocol import Binding,Boundary,EvidenceToken,History,WindowOwnership,digest
from .history import GaussianBackend,pack_message,message,pack_kernel

DP=C.POINTER(C.c_double)


def prior(config):
    p=config['prior_mean_physical'];tau=p['tau']
    x=np.r_[p['z'],p['v'],p['h'],np.log([p['Q'],p['R0'],p['R'][0],tau[0],p['R'][1],tau[1]-tau[0],
            p['R'][2],tau[2]-tau[1],p['H'],p['gamma_plus'],p['gamma_minus']])]
    return x,np.diag(config['prior_chart_sd'])


class Model:
    def __init__(self,binary,config):
        self.lib=C.CDLL(str(binary));self.fn=self.lib.foster_predict
        self.fn.argtypes=[DP,DP,C.c_int,DP,DP,DP,DP,DP];self.fn.restype=C.c_int
        self.cal=np.array([config['reference_temperature_K'],config['ocv_intercept_V'],config['ocv_slope_V_per_SOC'],*config['arrhenius_A_K']],dtype=float)

    def evaluate(self,x,obs):
        x=np.ascontiguousarray(x,dtype=float);obs=np.ascontiguousarray(obs,dtype=float)
        if x.shape!=(16,) or obs.ndim!=2 or obs.shape[1]!=5:raise ValueError('model input shape')
        v=np.empty(len(obs));J=np.empty((len(obs),16));end=np.empty(16);F=np.empty((16,16))
        args=[a.ctypes.data_as(DP) for a in [x,obs,self.cal,v,J,end,F]]
        status=self.fn(args[0],args[1],len(obs),*args[2:])
        if status:raise ValueError('physical model domain/status '+str(status))
        return v,J,end,F


def fit(model,mean,L,obs,settings):
    w=np.zeros(16);evaluations=0;stop='round_limit';rounds=0
    def evaluate(latent):
        nonlocal evaluations
        physical=model.evaluate(mean+L@latent,obs);evaluations+=1
        residual=(physical[0]-obs[:,3])/obs[:,4]
        cost=.5*(latent@latent+residual@residual)
        return cost,residual,physical
    cost,residual,physical=evaluate(w)
    for iteration in range(settings['max_rounds']):
        rounds=iteration+1;B=(physical[1]@L)/obs[:,4,None]
        gradient=w+B.T@residual
        if np.max(np.abs(gradient))<=settings['gradient_inf_tolerance']:stop='gradient';break
        step=-np.linalg.solve(np.eye(16)+B.T@B,gradient)
        if np.max(np.abs(step))<=settings['latent_step_tolerance']:stop='step';break
        accepted=False
        for power in range(settings['fractions']):
            trial=w+(2.**-power)*step
            try:newcost,newres,newphysical=evaluate(trial)
            except ValueError:continue
            if newcost<cost:
                w,cost,residual,physical=trial,newcost,newres,newphysical;accepted=True;break
        if not accepted:stop='no_descent';break
    return mean+L@w,physical,dict(stop=stop,rounds=rounds,evaluations=evaluations,cost=cost)


class Rolling:
    def __init__(self,binary,config,source_id,model_id,encoding='float64'):
        self.config=config;self.model=Model(binary,config);self.encoding=encoding;self.backend=GaussianBackend()
        self.binding=Binding(source_id,model_id,digest('continuous_gap_chart16_v1'),digest('declared_gaussian_sigma_plus_ADCvariance'),
            digest(config),digest('stationary_reference_no_process_noise'),digest('mean_path_model_domain_localGaussian_tails_unresolved'),
            digest('local_QR_deterministic_transport_'+encoding),16,1050)
        x,L=prior(config)
        self.history=History(self.binding,digest(dict(mean=x.tolist(),root=L.tolist())),pack_message(x,L,0.),self.backend,2184)
        self.window=WindowOwnership(self.history.read());self.rows=[];self.next_index=0;self.ticks=0
        self.block=config['numerical']['block_records'];self.last_diagnostics=None

    def offer(self,index,dt,current,temperature,voltage,sigma):
        if index!=self.next_index:raise ValueError('source order')
        values=np.array([dt,current,temperature,voltage,sigma],dtype=float)
        if not np.isfinite(values).all() or sigma<=0 or dt<0:raise ValueError('invalid observation')
        ticks=round(dt*1050)
        if abs(ticks/1050-dt)>1e-12:raise ValueError('interval not represented by declared clock')
        if len(self.rows)>=self.block:raise ValueError('unretired full window')
        self.window.offer(index);self.rows.append(values);self.next_index+=1;self.ticks+=ticks
        if len(self.rows)==self.block:return self.retire()
        return None

    def retire(self):
        if not self.rows:return None
        head=self.history.read();self.window.query_scope(head);obs=np.asarray(self.rows)
        mean,L,logZ=message(head.payload)
        before=self.model.evaluate(mean,obs)
        anchor,physical,diagnostics=fit(self.model,mean,L,obs,self.config['numerical'])
        v,J,end,F=physical;A=J/obs[:,4,None];residual=(v-obs[:,3])/obs[:,4]
        noise=float(np.log(obs[:,4]).sum()+len(obs)*.5*math.log(2*math.pi))
        payload=pack_kernel(anchor,end,F,A,residual,noise,self.encoding)
        token=EvidenceToken(self.binding,head.boundary,Boundary(self.next_index,self.ticks),head.message_id,payload)
        preview=self.backend.advance(head.payload,token)
        outmean,outroot,_=message(preview)
        # A producer-side domain check; compressor has no physical model.
        self.model.evaluate(outmean,np.empty((0,5)))
        ticket=self.history.prepare(token,self.window.end);receipt=self.history.commit(ticket)
        new=self.history.read()
        if new.payload!=preview:raise RuntimeError('backend purity violated')
        self.window.acknowledge(receipt,new);self.rows=[]
        diagnostics.update(records=new.boundary.sequence,generation=new.generation,
            initial_predictive_RMS=float(np.sqrt(np.mean(((before[0]-obs[:,3])/obs[:,4])**2))),
            fitted_RMS=float(np.sqrt(np.mean(residual**2))),token_bytes=len(payload),
            uncertainty='local Gaussian, physical tails and coverage unvalidated')
        self.last_diagnostics=diagnostics
        return self.readout(float(obs[-1,2])),diagnostics

    def readout(self,temperature):
        head=self.history.read();m,L,logZ=message(head.payload);var=np.sum(L*L,axis=1)
        qfactor=math.exp(self.config['arrhenius_A_K'][0]*(1/(temperature+273.15)-1/self.config['reference_temperature_K']))
        q=math.exp(m[5])*qfactor
        return dict(Q=q,Q_ref=math.exp(m[5]),SOC=float(m[0]),Q_log_sd=math.sqrt(var[5]),SOC_sd=math.sqrt(var[0]),
            Q_SOC_chart_covariance=float(L[5]@L[0]),
            Q_interval_3sd=[q*math.exp(-3*math.sqrt(var[5])),q*math.exp(3*math.sqrt(var[5]))],
            chart_mean=m.tolist(),chart_sd=np.sqrt(var).tolist(),log_evidence=logZ,
            records=head.boundary.sequence,physical_point='transformed Gaussian chart mean; Q is lognormal median')
