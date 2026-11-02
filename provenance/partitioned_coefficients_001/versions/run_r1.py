"""Run registered finite representation probes, not a posterior/coverage campaign."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from .representation import Coefficients
from experiments.conditional_architecture_001.run import public_queries
from experiments.conditional_architecture_001.conditional import chart_amplitude_jacobian
from experiments.foster_campaign_001.backend import ROOT, prepare_c, identity
from experiments.foster_campaign_001.compact import StimulusStream
from experiments.foster_campaign_001.stimulus import cells
from experiments.foster_campaign_001.run import parser as campaign_parser
from experiments.foster_feedback_001.estimator import Model
from experiments.foster_uncertainty_audit_001.conditional_packet import chart_from, partition
from experiments.hysteresis_refinement_001.field import build, MixedField, features_jacobian
from experiments.h7_history_quality_001.history import write, source_receipt, verify_sources


def chart_shape_jacobian(shape):
    D=np.zeros((16,5));tau=shape[:3]
    D[8,0]=1
    D[10,:2]=[-tau[0]/(tau[1]-tau[0]),tau[1]/(tau[1]-tau[0])]
    D[12,1:3]=[-tau[1]/(tau[2]-tau[1]),tau[2]/(tau[2]-tau[1])]
    D[14,3]=D[15,4]=1
    return D


class Direct:
    def __init__(self,model,a,s):
        self.model=model;self.a=a;self.state=chart_from(a,s);self.D=np.column_stack((chart_amplitude_jacobian(a),chart_shape_jacobian(s)))
        self.cost=0.;self.g=np.zeros(16);self.P=np.zeros((11,11));self.error=None
    def advance(self,obs):
        if self.error:return
        try:
            v,J,end,F=self.model.evaluate(self.state,obs)
            B=(J@self.D)/obs[:,4,None];r=(v-obs[:,3])/obs[:,4]
            self.cost+=.5*float(r@r)+float(np.log(obs[:,4]).sum()+len(obs)*.5*np.log(2*np.pi))
            self.g+=B.T@r;self.P+=B[:,:11].T@B[:,:11];self.state=end;self.D=F@self.D
        except ValueError as e:self.error=str(e)
    def evaluate(self):
        if self.error:raise ValueError(self.error)
        return dict(nll=self.cost,gradient_amplitude=self.g[:11],gradient_shape=self.g[11:],precision_amplitude=self.P,end=partition(self.state)[0])


def compare(q,ref,scale):
    dg=np.r_[(q['gradient_amplitude']-ref['gradient_amplitude'])*scale,q['gradient_shape']-ref['gradient_shape']]
    rg=np.r_[ref['gradient_amplitude']*scale,ref['gradient_shape']]
    dp=scale[:,None]*(q['precision_amplitude']-ref['precision_amplitude'])*scale[None,:]
    rp=scale[:,None]*ref['precision_amplitude']*scale[None,:]
    eig=np.linalg.eigvalsh(scale[:,None]*q['precision_amplitude']*scale[None,:])
    out=dict(nll_defect=float(q['nll']-ref['nll']),scaled_joint_gradient_defect=float(np.linalg.norm(dg)),
             relative_joint_gradient_defect=float(np.linalg.norm(dg)/max(1,np.linalg.norm(rg))),
             scaled_amplitude_precision_defect=float(np.linalg.norm(dp)),relative_amplitude_precision_defect=float(np.linalg.norm(dp)/max(1,np.linalg.norm(rp))),
             endpoint_SOC_error_pp=float(100*(q['end'][0]-ref['end'][0])),
             endpoint_RC_max_error_V=float(np.max(abs(q['end'][1:4]-ref['end'][1:4]))),
             endpoint_Hh_error_V=float(q['end'][10]-ref['end'][10]),
             scaled_amplitude_precision_min_eigenvalue=float(eig[0]),precision_min_to_max=float(eig[0]/max(1,abs(eig[-1]))))
    if 'gram' in q:
        scale12=np.r_[scale,1.];ge=np.linalg.eigvalsh(scale12[:,None]*q['gram']*scale12[None,:])
        out['scaled_augmented_gram_min_eigenvalue']=float(ge[0]);out['gram_min_to_max']=float(ge[0]/max(1,abs(ge[-1])))
    return out


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--out',required=True,type=Path)
    p.add_argument('--records',nargs='+',type=int,default=[21008,35520,126000]);p.add_argument('--loads',nargs='+',choices=['rest','multiscale','embedded'],default=['rest','multiscale','embedded'])
    args=p.parse_args()
    if any(n<=0 for n in args.records):p.error('positive prefixes required')
    args.out.mkdir(parents=True,exist_ok=False)
    config=json.loads((ROOT/'experiments/foster_feedback_001/calibration.json').read_text());config['hysteresis_chart']='bounded'
    center,_,amplitudes=public_queries(config)
    ts=[np.zeros(5)]+[sign*.9*np.eye(5)[j] for j in range(5) for sign in (-1,1)]
    ts+=list(np.random.default_rng(20261102).uniform(-.9,.9,(6,5)))
    queries=[dict(id=f't{ti}_a{ai}',a=a,s=center*np.exp(t),selection='public') for ti,t in enumerate(ts) for ai,a in enumerate(amplitudes)]
    witness_path=ROOT/'experiments/conditional_architecture_001/domain001/result.json'
    witness=json.loads(witness_path.read_text());a,s=partition(np.array(witness['rejection']['candidate_chart']))
    queries.append(dict(id='preserved_domain_exit',a=a,s=s,selection='outcome_selected_diagnostic_only'))
    binary=build(args.out/'response');cbinary=prepare_c(args.out,35,config)[0];model=Model(cbinary,config)
    sources=source_receipt()
    write(args.out/'registration.json',dict(source=sources,contract='specifications/partitioned_coefficients_001/README.md',
         contract_identity=identity(ROOT/'specifications/partitioned_coefficients_001/README.md'),
         config=config,queries=queries,center=center,log_halfwidth=np.ones(5),prefixes=args.records,loads=args.loads,
         witness=identity(witness_path),native_response=identity(binary),direct_C=identity(cbinary)))
    results=[]
    for load in args.loads:
        directory=args.out/f'case_{len(results):04d}';directory.mkdir()
        settings=vars(campaign_parser().parse_args([]));settings.update(sample_rate_hz=35,current_a=.06,temperature='fixed',temperature_mean_c=25.,field_refresh_seconds=60)
        case=dict(cell='B',load=load,noise_v=.0002,seed=1103,load_seed=7)
        recipe=dict(case=case,settings=settings,cell=cells()['B']);source=hashlib.sha256(json.dumps(recipe,sort_keys=True).encode()).hexdigest()
        stream=StimulusStream(config,cells()['B'],case,settings);digest=hashlib.sha256()
        arms={name:Coefficients(config,center,binary,d,sparse,source) for name,d,sparse in [('linear',1,False),('quadratic',2,False),('sparse_quadratic',2,True)]}
        h7=MixedField(config,center,1.,7,binary,source);direct=[Direct(model,q['a'],q['s']) for q in queries]
        times={k:0. for k in [*arms,'H7','direct_all_queries']};prefixes=[]
        result=dict(load=load,recipe=recipe,source_id=source,status='running',prefixes=prefixes)
        write(directory/'result.json',result)
        for target in sorted(set(args.records)):
            while stream.index<target:
                first=stream.index;obs,_,_=stream.read(min(1024,target-first))
                if stream.failure or not len(obs):raise ValueError('fixture incomplete')
                digest.update(obs.astype('<f8',copy=False).tobytes())
                for name,arm in arms.items():
                    start=time.process_time();arm.advance(first,obs,source);times[name]+=time.process_time()-start
                start=time.process_time();h7.update(first,obs);times['H7']+=time.process_time()-start
                start=time.process_time()
                for ref in direct:ref.advance(obs)
                times['direct_all_queries']+=time.process_time()-start
            records=[]
            for query,ref in zip(queries,direct):
                record=dict(id=query['id'],selection=query['selection'],arms={})
                scale=np.maximum(abs(query['a']),[.1,.01,.01,.01,1.,.01,.01,.01,.01,.001,.001])
                try:
                    reference=ref.evaluate();record['direct']=dict(status='supported',nll=reference['nll'])
                except ValueError as e:record['direct']=dict(status='unsupported',reason=str(e));reference=None
                for name in [*arms,'H7']:
                    try:
                        if name=='H7':
                            x=chart_from(query['a'],query['s']);r=h7.residual(x)
                            J=h7.root@features_jacobian(h7,x)@np.column_stack((chart_amplitude_jacobian(query['a']),chart_shape_jacobian(query['s'])))
                            g=J.T@r;value=dict(nll=.5*float(r@r)+h7.noise,gradient_amplitude=g[:11],gradient_shape=g[11:],precision_amplitude=J[:,:11].T@J[:,:11],end=h7.outgoing(x))
                        else:value=arms[name].evaluate(query['a'],query['s'])
                        record['arms'][name]=dict(status='supported',metrics=compare(value,reference,scale) if reference else None)
                    except ValueError as e:record['arms'][name]=dict(status='unsupported',reason=str(e))
                records.append(record)
            witness_match=None
            if load=='embedded' and target==35520:
                witness_match=digest.hexdigest()==witness['observation_sha256']
                if not witness_match:raise ValueError('preserved domain witness stream changed')
            prefixes.append(dict(records=target,hours=target/35/3600,observation_sha256=digest.hexdigest(),preserved_witness_digest_matches=witness_match,queries=records,timing_cpu_s=times.copy()))
            result.update(storage={k:v.storage() for k,v in arms.items()},H7_storage=h7.storage(),timing_scope='Host process CPU, cumulative updates only. Direct sums52 independent probes; H7/native vs Python contraction costs not M23 timing.')
            write(directory/'result.json',result)
            print(json.dumps(dict(load=load,records=target,timing=times)),flush=True)
        result['status']='completed_probes_not_qualified';write(directory/'result.json',result);results.append(result)
        write(args.out/'summary.json',dict(status='running',cases=results))
    verify_sources(sources)
    write(args.out/'summary.json',dict(status='completed_probes_not_qualified',cases=results))

if __name__=='__main__':main()
