"""VI waveform scheduling; observes measured rows and public RC time scales only."""
import numpy as np
WIDTH=24
SPLITS=np.arange(8,17)

def detrend(x,t):
    """Remove intercept/slope for matching only; estimator still gets original data."""
    tc=t-t.mean(axis=-1,keepdims=True);xc=x-x.mean(axis=-1,keepdims=True)
    den=np.sum(tc*tc,axis=-1,keepdims=True)
    return xc-tc*np.divide(np.sum(xc*tc,axis=-1,keepdims=True),den,out=np.zeros_like(den),where=den>0)

def unit(x):
    norm=np.linalg.norm(x,axis=-1,keepdims=True)
    # Floating-point degeneracy test, not an event/noise acceptance threshold.
    return np.divide(x,norm,out=np.zeros_like(x),where=norm>1e-14)

def schedules(obs,taus):
    n=len(obs);tiles=n//WIDTH
    rows=np.asarray(obs[:tiles*WIDTH]).reshape(tiles,WIDTH,5)
    t=np.cumsum(rows[:,:,0],axis=1)
    current=unit(detrend(rows[:,:,1],t));voltage=unit(detrend(rows[:,:,3],t))
    ci=[];joint=[]
    for k in SPLITS:
        step=np.broadcast_to((np.arange(WIDTH)>=k).astype(float),t.shape)
        current_match=np.sum(current*unit(detrend(step,t)),axis=1)
        options=[]
        for tau in [0.,*taus]:
            response=step if tau==0 else np.where(step>0,-np.expm1(-(t-t[:,k-1,None])/tau),0.)
            vm=np.sum(voltage*unit(detrend(response,t)),axis=1)
            options.append(-current_match*vm)
        ci.append(abs(current_match));joint.append(np.max(options,axis=0))
    ci=np.array(ci).T; joint=np.array(joint).T
    flat=np.linalg.norm(current,axis=1)==0
    def choose(score):
        # Prefer central split for exact ties; no favorable-noise rejection.
        order=np.array([4,3,5,2,6,1,7,0,8]);k=SPLITS[order[np.argmax(score[:,order],axis=1)]]
        k[flat]=12;return k
    ki=choose(ci);kv=choose(joint)
    def endpoints(k):
        result=np.column_stack((np.arange(tiles)*WIDTH+k,(np.arange(tiles)+1)*WIDTH)).ravel().tolist()
        last=tiles*WIDTH
        while last<n:last=min(last+16,n);result.append(last)
        return np.array(result,dtype=np.uint64)
    def fixed(width):return np.minimum(np.arange(width,n+width,width),n).astype(np.uint64)
    # Offline diagnostic: identical split multiset, shifted away from its source tile.
    displacement=max(1,tiles//3)
    plans=dict(fixed16=fixed(16),fixed12=fixed(12),current=endpoints(ki),joint_vi=endpoints(kv),displaced_vi=endpoints(np.roll(kv,displacement)))
    report=dict(tiles=tiles,flat_current_tiles=int(flat.sum()),nonflat_current_tiles=int((~flat).sum()),joint_vs_current_different=int(np.sum(kv!=ki)),joint_noncentral_splits=int(np.sum(kv!=12)),displacement_tiles=displacement,lookahead_samples=WIDTH,raw_buffer_bytes=WIDTH*5*8,score_quantiles=np.quantile(joint.max(axis=1),[0,.5,.9,.99,1]).tolist() if tiles else [],split_histogram={str(k):int(np.sum(kv==k)) for k in SPLITS})
    return plans,report
