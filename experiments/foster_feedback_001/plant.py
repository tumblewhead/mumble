"""Independent scalar synthetic plant and acquisition, used only by the harness."""
import math
import numpy as np

CELLS={
    'A':[.06,.1,.04,.05,.08,.5,.12,5.,.015,6.,9.],
    'B':[.0567,.107,.043,.065,.076,.62,.125,5.5,.014,5.8,9.3],
}


def scalar_step(state,parameters,dt,current,ocv_a,ocv_b):
    z,v1,v2,v3,h=map(float,state);p=list(map(float,parameters))
    z-=current*dt/(3600*p[0]);volts=[]
    for v,r,tau in [(v1,p[2],p[3]),(v2,p[4],p[5]),(v3,p[6],p[7])]:
        decay=math.exp(-dt/tau);volts.append(decay*v+(1-decay)*r*current)
    if current:
        decay=math.exp(-p[9 if current>0 else 10]*abs(current)*dt/(3600*p[0]))
        h=decay*h+(1-decay)*(1 if current>0 else -1)
    if not 0<=z<=1 or not -1<=h<=1:raise ValueError('plant outside physical domain')
    voltage=ocv_a+ocv_b*z+p[8]*h-current*p[1]-sum(volts)
    return [z,*volts,h],voltage


def generate(config,n,cell='B',noise_v=.004,seed=314159,temperature='cycle'):
    if cell not in CELLS or n<1 or noise_v<=0:raise ValueError('invalid plant configuration')
    t=(np.arange(n)+1)/35;start=np.arange(n)/35
    T=25+8*np.sin(2*np.pi*t/3600) if temperature=='cycle' else np.full(n,25.)
    T=-40+np.floor((T+40)/.0625+.5)*.0625
    phase=np.fmod(start,160);I=np.where(phase<70,.03,np.where((phase>=80)&(phase<150),-.03,0.))
    I[(start>=5400)&(start<10800)]=0.
    I=-.256+np.floor((I+.256)/.000125+.5)*.000125
    parameters=np.array(CELLS[cell])[None,:]*np.exp(np.array(config['arrhenius_A_K'])[None,:]*(1/(T[:,None]+273.15)-1/config['reference_temperature_K']))
    state=[.63,.001,-.002,.001,.15];truth=np.empty((n,4));voltage=np.empty(n)
    for k in range(n):
        state,voltage[k]=scalar_step(state,parameters[k],1/35,float(I[k]),config['ocv_intercept_V'],config['ocv_slope_V_per_SOC'])
        truth[k]=parameters[k,0],parameters[k,1],state[0],voltage[k]
    noisy=voltage+np.random.default_rng(seed).normal(0,noise_v,n)
    codes=np.floor((noisy-1.5)*1024+.5)
    if np.any((codes<0)|(codes>4095)):raise ValueError('ADC range; no clipping')
    obs=np.column_stack([np.full(n,1/35),I,T,1.5+codes/1024,np.full(n,math.sqrt(noise_v**2+(1/1024)**2/12))])
    return obs,truth
