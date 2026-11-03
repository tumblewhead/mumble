"""Read-only QR covariance and partition diagnostics after unchanged joint fits."""
import numpy as np
from experiments.joint_precision_attribution_001 import metrics as m
from .field import features_jacobian,transported
from experiments.hysteresis_mixed_completion_001.run import prediction,forecast_metrics,future_tasks
from experiments.hysteresis_sensitivity_basis_001.reference import envelope as h_envelope


def covariance_root(rows, L):
    R=np.linalg.qr(np.vstack((np.eye(16),rows)),mode='r')
    return L@np.linalg.solve(R,np.eye(16))


def direct_trace(model,obs,x,L):
    root=np.zeros((16,16));end=x.copy();F=np.eye(16)
    for start in range(0,len(obs),1024):
        o=obs[start:start+1024];_,J,new,A=model.evaluate(end,o)
        root=np.linalg.qr(np.vstack((root,(J@F@L)/o[:,4,None])),mode='r')
        end,F=new,A@F
    return root,end,F


def partition_trace(generator,final,model,obs,x,L):
    a,shape,B,K=m.coordinates(x,L)
    Dfeatures=features_jacobian(final,x)@B
    features=final.features(x)
    root=np.zeros((51,51));end=x.copy();F=np.eye(16)
    other=split=0.
    for start in range(0,len(obs),1024):
        o=obs[start:start+1024];v,J,new,A=model.evaluate(end,o)
        Jx=(J@F)/o[:,4,None];Jc=Jx@B;Jw=Jx@L;r=(v-o[:,3])/o[:,4]
        rows=generator.rows(start,o)
        dr,dh=m.separate(rows@Dfeatures-Jc)
        er,eh=dr[:,:11]@a,dh[:,:11]@a
        other=max(other,float(np.max(abs((rows@Dfeatures-Jc)[:,m.OTHER]))))
        split=max(split,float(np.max(abs(rows@features-r-er-eh))))
        root=m.append(root,np.column_stack((Jw,dr,dh,r,er,eh)))
        end,F=new,A@F
    if not np.array_equal(generator.state,final.state):raise ValueError('replayed field endpoint changed')
    if max(other,split)>1e-7:raise ValueError('physical partition consistency')
    return root,end,F,a,shape,K,dict(other_column_max_defect=other,residual_partition_max_defect=split,response_state_bitwise_match=True)


def add_readouts(fields,factory,model,obs,mean,L,center,fit_report):
    """Never changes selected fits; fit-to-fit readouts require both fits converged."""
    cache={};qr={}
    for name,fit in fit_report['arms'].items():
        if 'selected' not in fit:
            qr[name]=dict(status='no_selected_fit',fit_status=fit['status']);continue
        x=np.asarray(fit['selected']['x']);w=np.asarray(fit['selected']['w'])
        if not np.allclose(x,mean+L@w,atol=1e-12,rtol=0):raise ValueError('fit coordinate identity')
        a,shape,_,_=m.coordinates(x,L)
        row=dict(status='local_diagnostic',fit_status=fit['status'],
                 physical=dict(SOC0=float(a[0]),v0=a[1:4],h0=float(np.tanh(x[4])),Q_Ah=float(1/a[4]),
                               R0=float(a[5]),R=a[6:9],H_V=float(a[9]),tau=shape[:3],
                               gamma_plus=float(shape[3]/a[4]),gamma_minus=float(shape[4]/a[4])),
                 log_rate_offsets=np.log(shape/center),minimum_box_margin=float(np.min(1-abs(np.log(shape/center)))))
        if name=='direct':
            J,end,F=direct_trace(model,obs,x,L)
            C=covariance_root(J,L);Cdirect=C
        else:
            root,end,F,a,shape,K,controls=partition_trace(factory(name),fields[name],model,obs,x,L)
            try:comp=transported(fields[name],x)
            except ValueError as error:comp=str(error)
            env=m.rc_envelope(a,shape,center,float(np.max(abs(obs[:,1])))) if name.startswith('TaylorRC_') else None
            detail,M=m.analyze(root,K,L,x,(end,F),comp,model,env,float(np.sum(obs[:,4]**-2)))
            Cdirect=L@M
            J=fields[name].root@features_jacobian(fields[name],x)@L
            C=covariance_root(J,L)
            row['partition_diagnostics']=detail;row['controls']=controls
            if getattr(fields[name],'hkind',None)=='TaylorH2':
                bc,ev=h_envelope(a,shape,center)
                eta=float(np.sqrt(np.sum(obs[:,4]**-2))*np.linalg.norm(bc@abs(K@M)))
                row['H6_envelope']=dict(voltage_error_bound_V=ev,eta_upper=eta,epsilon_upper=2*eta+eta*eta)
            ratio=np.linalg.norm(F[0]@C)/np.linalg.norm(F[0]@Cdirect)
            measured=detail['variants']['combined']['SOC_direct_transport']['SD_ratio_range'][0]
            row['controls']['factor_vs_augmented_QR_SOC_ratio_difference']=float(ratio-measured)
            if abs(ratio-measured)>1e-7*max(1,abs(ratio)):raise ValueError('covariance QR consistency')
        direct_Q_sd=float(np.linalg.norm(Cdirect[5]));direct_SOC_sd=float(np.linalg.norm(F[0]@Cdirect))
        row.update(Q_log_SD=float(np.linalg.norm(C[5])),SOC_direct_transport_SD_pp=float(100*np.linalg.norm(F[0]@C)),
                   Q_same_anchor_SD_ratio=float(np.linalg.norm(C[5])/direct_Q_sd),
                   SOC_same_anchor_direct_transport_SD_ratio=float(np.linalg.norm(F[0]@C)/direct_SOC_sd),
                   origin_chart_SD=np.linalg.norm(C,axis=1),direct_endpoint_SOC=float(end[0]),
                   historical_solver_Q_SD_ratio_to_QR=float(np.linalg.norm(np.asarray(fit['selected']['root'])[5])/np.linalg.norm(C[5])))
        transports={'direct_C':(end,F)}
        if name!='direct':
            if isinstance(comp,str):row['compressed_transport']=dict(status='unsupported',reason=comp)
            else:
                ce,cD=comp;transports['compressed']=comp
                row['compressed_transport']=dict(status='supported',SOC=float(ce[0]),
                    SOC_SD_pp=float(100*np.linalg.norm(cD[0]@C)),
                    SOC_same_anchor_SD_ratio=float(np.linalg.norm(cD[0]@C)/direct_SOC_sd),
                    h=float(np.tanh(ce[4])),RC_difference_mV=1000*(ce[1:4]-end[1:4]))
        cache[name]=(x,C,end,F,transports)
        qr[name]=row
    ref=cache.get('direct') if fit_report['arms']['direct']['status']=='converged' else None
    forecasts={}
    if ref is not None:
        for task,o in future_tasks().items():
            try:forecasts[task]=prediction(model,ref[2],ref[3]@ref[1],o)
            except ValueError as error:forecasts[task]=str(error)
    for name,row in qr.items():
        if ref is None or row['fit_status']!='converged' or name not in cache:
            row['fit_comparison']=dict(status='unresolved_candidate_or_reference');continue
        x,C,end,F,transports=cache[name];rx,rC,re,rF,_=ref
        row['fit_comparison']=dict(status='local_converged_diagnostic',
            Q_relative_difference_percent=float(100*np.expm1(x[5]-rx[5])),
            Q_log_difference_in_reference_SD=float((x[5]-rx[5])/np.linalg.norm(rC[5])),
            direct_SOC_difference_pp=float(100*(end[0]-re[0])),
            direct_SOC_difference_in_reference_SD=float((end[0]-re[0])/np.linalg.norm(rF[0]@rC)),
            Q_SD_ratio_to_reference_fit=float(np.linalg.norm(C[5])/np.linalg.norm(rC[5])),
            SOC_direct_SD_ratio_to_reference_fit=float(np.linalg.norm(F[0]@C)/np.linalg.norm(rF[0]@rC)),
            origin_joint_local_distance=float(np.linalg.norm(np.linalg.solve(rC,x-rx))))
        row['forecasts']=[]
        for transport,(e,D) in transports.items():
            for task,o in future_tasks().items():
                f=dict(transport=transport,task=task)
                try:
                    if isinstance(forecasts[task],str):raise ValueError('reference forecast: '+forecasts[task])
                    pred=prediction(model,e,D@C,o)
                    f.update(status='supported',**forecast_metrics(pred,forecasts[task]))
                except ValueError as error:f.update(status='unsupported',reason=str(error))
                row['forecasts'].append(f)
        if 'compressed' in transports:
            ce,cD=transports['compressed']
            row['fit_comparison'].update(compressed_SOC_difference_pp=float(100*(ce[0]-re[0])),
                SOC_compressed_SD_ratio_to_reference_fit=float(np.linalg.norm(cD[0]@C)/np.linalg.norm(rF[0]@rC)))
    fit_report['QR_readouts']=qr
