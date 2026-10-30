"""Stationary linear-OCV conditional likelihood prototype; no posterior/prior.

The factor is reusable in eleven amplitudes at ONE specified set of five rates.
It is not a complete bounded-memory representation over uncertain rates.
"""
from dataclasses import dataclass
import math
import numpy as np


def partition(chart):
    z,v1,v2,v3,eta=chart[:5];p=np.exp(chart[5:]);p[5]+=p[3];p[7]+=p[5]
    amplitude=np.array([z,v1,v2,v3,1/p[0],p[1],p[2],p[4],p[6],p[8],p[8]*np.tanh(eta)])
    shape=np.array([p[3],p[5],p[7],p[9]/p[0],p[10]/p[0]])
    return amplitude,shape


def chart_from(amplitude,shape):
    z,v1,v2,v3,q,r0,r1,r2,r3,H,b=amplitude;t1,t2,t3,kp,km=shape
    if min(q,r0,r1,r2,r3,H,t1,t2-t1,t3-t2,kp,km)<=0 or abs(b)>=H:raise ValueError('physical chart support')
    return np.r_[z,v1,v2,v3,np.arctanh(b/H),np.log([1/q,r0,r1,t1,r2,t2-t1,r3,t3-t2,H,kp/q,km/q])]


def transport(coeff):
    A=coeff[0];E=coeff[1:4];u=coeff[4:7];Eh,uh=coeff[7:9]
    M=np.eye(11);M[0,4]=-A
    for j in range(3):M[1+j,1+j]=E[j];M[1+j,6+j]=u[j]
    M[10,10]=Eh;M[10,9]=uh
    return M


@dataclass
class Packet:
    source: str
    begin: int
    end: int
    shape: np.ndarray
    root: np.ndarray
    noise_constant: float
    coeff: np.ndarray
    charge_min: float
    charge_max: float
    calibration: tuple

    def nll(self,amplitude):
        amplitude=np.asarray(amplitude,dtype=float)
        if amplitude.shape!=(11,) or not np.isfinite(amplitude).all():raise ValueError('amplitude shape/finite values')
        z=amplitude[0];q=amplitude[4];H=amplitude[9];b=amplitude[10]
        if min(amplitude[4:10])<=0 or abs(b)>H or z-q*self.charge_max<0 or z-q*self.charge_min>1:raise ValueError('unsupported physical path')
        residual=self.root@np.r_[amplitude,1.]
        return .5*float(residual@residual)+self.noise_constant

    def outgoing(self,amplitude):return transport(self.coeff)@amplitude


def make(obs,shape,config,source='diagnostic',begin=0):
    if len(shape)!=5 or not np.isfinite(shape).all() or not 0<shape[0]<shape[1]<shape[2] or min(shape[3:])<=0:raise ValueError('shape')
    obs=np.asarray(obs);rows=[];A=0.;Amin=0.;Amax=0.;E=np.ones(3);u=np.zeros(3);Eh=1.;uh=0.;noise=0.
    cal=(config['reference_temperature_K'],config['ocv_intercept_V'],config['ocv_slope_V_per_SOC'],*config['arrhenius_A_K'])
    if len(cal)!=14 or not np.isfinite(cal).all() or cal[0]<=0 or cal[2]<=0:raise ValueError('calibration')
    for dt,I,T,y,sigma in obs:
        if not np.isfinite([dt,I,T,y,sigma]).all() or not 0<=dt<=1 or abs(I)>.25 or not 15<=T<=35 or sigma<=0:raise ValueError('observation support')
        f=np.exp(np.asarray(config['arrhenius_A_K'])*(1/(T+273.15)-1/cal[0]))
        effective_tau=shape[:3]*f[[3,5,7]]
        if not np.isfinite(f).all() or not 0<effective_tau[0]<effective_tau[1]<effective_tau[2]:raise ValueError('effective thermal support')
        A+=I*dt/(3600*f[0]);Amin=min(Amin,A);Amax=max(Amax,A)
        decay=np.exp(-dt/(shape[:3]*f[[3,5,7]]));one=-np.expm1(-dt/(shape[:3]*f[[3,5,7]]));E*=decay;u=decay*u+one*f[[2,4,6]]*I
        if I:
            gi=9 if I>0 else 10;k=shape[3 if I>0 else 4];a=k*abs(I)*dt*f[gi]/(3600*f[0]);e=math.exp(-a);Eh*=e;uh=e*uh-math.expm1(-a)*np.sign(I)
        beta=np.r_[cal[2],-E,-cal[2]*A,-I*f[1],-u,f[8]*uh,f[8]*Eh]
        rows.append(np.r_[beta,cal[1]-y]/sigma);noise+=math.log(sigma)+.5*math.log(2*math.pi)
    matrix=np.asarray(rows).reshape(-1,12)
    if len(matrix)<12:matrix=np.vstack([matrix,np.zeros((12-len(matrix),12))])
    root=np.linalg.qr(matrix,mode='r')
    return Packet(source,begin,begin+len(obs),np.array(shape),root,noise,np.r_[A,E,u,Eh,uh],Amin,Amax,cal)


def compose(left,right):
    if left.source!=right.source or left.end!=right.begin or left.calibration!=right.calibration or not np.array_equal(left.shape,right.shape):raise ValueError('source/order/shape/calibration mismatch')
    affine=np.eye(12);affine[:11,:11]=transport(left.coeff)
    root=np.linalg.qr(np.vstack([left.root,right.root@affine]),mode='r')
    l=left.coeff;r=right.coeff
    coeff=np.r_[l[0]+r[0],r[1:4]*l[1:4],r[1:4]*l[4:7]+r[4:7],r[7]*l[7],r[7]*l[8]+r[8]]
    return Packet(left.source,left.begin,right.end,left.shape.copy(),root,left.noise_constant+right.noise_constant,coeff,min(left.charge_min,l[0]+right.charge_min),max(left.charge_max,l[0]+right.charge_max),left.calibration)
