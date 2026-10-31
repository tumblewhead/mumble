"""Prior-free continuous likelihood field over eleven amplitudes and five rates.

Response functions are approximated; the lifted quadratic and its QR accumulation
are exact up to floating-point arithmetic. No independent-coordinate posterior
or particle approximation is substituted for the original joint prior.
"""
import ctypes as C
import math
from pathlib import Path
import subprocess
import numpy as np
from numpy.polynomial.chebyshev import chebvander
from experiments.foster_uncertainty_audit_001.conditional_packet import partition, transport

DP=C.POINTER(C.c_double)
HERE=Path(__file__).resolve().parent

def pointer(a):return a.ctypes.data_as(DP)

def build(destination):
    destination.mkdir(parents=True,exist_ok=True)
    binary=destination/'response.so'
    subprocess.run(['cc','-std=c11','-O2','-fno-fast-math','-ffp-contract=off',
                    '-Wall','-Wextra','-Werror','-pedantic','-fPIC','-shared',str(HERE/'probe.c'),
                    '-lm','-o',str(binary)],check=True)
    return binary


class Field:
    def __init__(self, config, center, halfwidth, degree, binary, source='fixture'):
        if config.get('hysteresis_chart')!='bounded':raise ValueError('bounded original chart required')
        self.config=config;self.source=source;self.count=0;self.noise=0.
        calibration=np.asarray([config['reference_temperature_K'],config['ocv_intercept_V'],config['ocv_slope_V_per_SOC'],*config['arrhenius_A_K']],dtype=float)
        if calibration.shape!=(14,) or not np.isfinite(calibration).all() or calibration[0]<=0 or calibration[2]<=0:
            raise ValueError('calibration shape/support')
        if not isinstance(degree,int) or not 1<=degree<=8:raise ValueError('degree1..8')
        self.degree=degree;self.n=degree+1
        self.center=np.asarray(center,dtype=float).copy();self.halfwidth=np.broadcast_to(halfwidth,(5,)).copy()
        if self.center.shape!=(5,) or not np.isfinite(self.center).all() or np.any(self.center<=0) or not np.isfinite(self.halfwidth).all() or np.any(self.halfwidth<=0):raise ValueError('rate box')
        # An ordered rectangular computational box must remain ordered at all T.
        for T in [15,35]:
            f=np.exp(np.asarray(config['arrhenius_A_K'])*(1/(T+273.15)-1/config['reference_temperature_K']))
            low=self.center[:3]*np.exp(-self.halfwidth[:3])*f[[3,5,7]]
            high=self.center[:3]*np.exp(self.halfwidth[:3])*f[[3,5,7]]
            if np.any(high[:-1]>=low[1:]):raise ValueError('rate box crosses physical pole ordering')
        self.nodes=np.cos(np.pi*(np.arange(self.n)+.5)/self.n)
        V=chebvander(self.nodes,degree);self.p1=np.ascontiguousarray(np.linalg.inv(V))
        self.pairs=[(i,j) for i in range(self.n) for j in range(self.n) if i+j<=degree]
        V2=np.column_stack([np.outer(V[:,i],V[:,j]).ravel() for i,j in self.pairs])
        self.p2=np.ascontiguousarray(np.linalg.pinv(V2));self.b=len(self.pairs)
        self.rates=np.ascontiguousarray(self.center[:,None]*np.exp(self.halfwidth[:,None]*self.nodes))
        self.width=4+6*self.n+2*self.b
        self.root=np.zeros((self.width,self.width))
        self.state=np.zeros(6*self.n+2*self.n*self.n+3)
        self.state[:3*self.n]=1;self.state[6*self.n:6*self.n+self.n*self.n]=1
        self.cal=np.array([config['reference_temperature_K'],config['ocv_intercept_V'],config['ocv_slope_V_per_SOC'],*config['arrhenius_A_K']])
        self.lib=C.CDLL(str(Path(binary).resolve()));self.fn=self.lib.response_rows
        self.fn.argtypes=[DP,C.c_size_t,DP,C.c_int,C.c_int,DP,DP,DP,DP,DP];self.fn.restype=C.c_int

    def features(self, chart):
        chart=np.asarray(chart,dtype=float)
        if chart.shape!=(16,) or not np.isfinite(chart).all():raise ValueError('finite16D chart required')
        amplitude,shape=partition(chart)
        if not np.isfinite(amplitude).all() or np.any(amplitude[4:10]<=0):raise ValueError('physical amplitude support')
        t=np.log(shape/self.center)/self.halfwidth
        if not np.isfinite(t).all() or np.any(abs(t)>1+1e-12):raise ValueError('outside computational rate box; unresolved, not excluded')
        A,lo,hi=self.state[-3:];z,q,H,B=amplitude[[0,4,9,10]]
        if z-q*hi<0 or z-q*lo>1 or abs(B)>H:raise ValueError('physical trajectory support')
        T=chebvander(t,self.degree);h=np.array([T[3,i]*T[4,j] for i,j in self.pairs])
        values=[amplitude[0],amplitude[4],amplitude[5]]
        for j in range(3):
            values.extend(amplitude[1+j]*T[j]);values.extend(amplitude[6+j]*T[j])
        values.extend(amplitude[9]*h);values.extend(amplitude[10]*h);values.append(1.)
        return np.asarray(values)

    def update(self, first, observations, source=None, return_rows=False):
        if first!=self.count or (source is not None and source!=self.source):raise ValueError('source/order mismatch')
        obs=np.ascontiguousarray(observations,dtype=float)
        if obs.ndim!=2 or obs.shape[1]!=5 or not np.isfinite(obs).all() or np.any(obs[:,0]<0) or np.any(obs[:,0]>1) or np.any(abs(obs[:,1])>.25) or np.any(obs[:,2]<15) or np.any(obs[:,2]>35) or np.any(obs[:,4]<=0):raise ValueError('observation support')
        rows=np.empty((len(obs),self.width));state=self.state.copy()
        status=self.fn(pointer(obs),len(obs),pointer(self.cal),self.n,self.b,pointer(self.rates),pointer(self.p1),pointer(self.p2),pointer(state),pointer(rows))
        if status or not np.isfinite(rows).all():raise ValueError('response recurrence failed')
        root=np.linalg.qr(np.vstack([self.root,rows]),mode='r')
        root*=np.where(np.diag(root)<0,-1.,1.)[:,None]
        self.root=root;self.state=state;self.count+=len(obs)
        self.noise+=float(np.log(obs[:,4]).sum()+len(obs)*.5*math.log(2*math.pi))
        return rows if return_rows else None

    def residual(self,chart):return self.root@self.features(chart)
    def nll(self,chart):
        r=self.residual(chart);return .5*float(r@r)+self.noise
    def outgoing(self,chart):
        amplitude,shape=partition(chart);self.features(chart)
        t=np.log(shape/self.center)/self.halfwidth;T=chebvander(t,self.degree)
        h=np.array([T[3,i]*T[4,j] for i,j in self.pairs]);n=self.n
        E=self.state[:3*n].reshape(3,n);u=self.state[3*n:6*n].reshape(3,n)
        Eh=self.state[6*n:6*n+n*n];uh=self.state[6*n+n*n:6*n+2*n*n]
        coeff=np.r_[self.state[-3],[T[j]@self.p1@E[j] for j in range(3)],
                    [T[j]@self.p1@u[j] for j in range(3)],h@self.p2@Eh,h@self.p2@uh]
        return transport(coeff)@amplitude
    def storage(self):
        root=self.width*(self.width+1)//2*8
        return dict(degree=self.degree,lifted_width=self.width,packed_root_B=root,
                    packed_likelihood_transport_domain_B=root+8*(self.width-3)+80+24+16,
                    live_collocation_state_B=self.state.nbytes,
                    exclusions='Binding metadata, projection matrices, prior, solver/window workspace; Python allocations exceed packed estimate')
