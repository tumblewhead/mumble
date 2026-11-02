"""Conditional bounded-error SOC/Q certificate using verified LP dual bounds.

Inputs: public hard support, exact I/dt at25C, and bounded-error voltage samples.
No plant truth, H7 covariance, or posterior is used to form the feasible set.
"""
from fractions import Fraction as F
import hashlib
import json
import math

import numpy as np
from scipy.optimize import linprog
from .interval import Interval as IV, exp_minus, display_bounds, rational_pair

N=11
DEFAULT_BOX=[['.2','.9'],['-.02','.02'],['-.02','.02'],['-.02','.02'],
             [str(F(1,F('.075'))),str(F(1,F('.045')))],['.04','.2'],
             ['.01','.09'],['.02','.15'],['.04','.2'],['.004','.03'],['-.03','.03']]
DEFAULT_SHAPE=['.07','.7','6','100','160']


class Response:
    """All chronological intervals, conditional amplitudes and interval shape."""
    def __init__(self,shape=DEFAULT_SHAPE,relative_radius='0',slope='1.15'):
        radius=F(relative_radius)
        if not 0<=radius<1:raise ValueError('rate-box radius')
        self.shape=[IV.bounds(F(x)*(1-radius),F(x)*(1+radius)) for x in shape]
        if len(self.shape)!=5 or any(s.lo<=0 for s in self.shape) or not all(self.shape[i].hi<self.shape[i+1].lo for i in (0,1)):
            raise ValueError('positive ordered rate support')
        self.slope=F(slope);self.A=F(0);self.amin=F(0);self.amax=F(0)
        self.E=[IV.bounds(1) for _ in range(3)];self.u=[IV.bounds(0) for _ in range(3)]
        self.Eh=IV.bounds(1);self.uh=IV.bounds(0);self.count=0

    def advance(self,dt,current):
        dt,current=F(dt),F(current)
        if not 0<=dt<=1 or abs(current)>F('.25'):raise ValueError('response support')
        self.A+=current*dt/3600;self.amin=min(self.amin,self.A);self.amax=max(self.amax,self.A)
        for j in range(3):
            decay=exp_minus(IV.bounds(dt)/self.shape[j])
            self.E[j]=decay*self.E[j]
            self.u[j]=current+decay*(self.u[j]-current)
        if current:
            sign=1 if current>0 else -1
            decay=exp_minus(self.shape[3 if current>0 else 4]*abs(current)*dt/F(3600))
            self.Eh=decay*self.Eh;self.uh=sign+decay*(self.uh-sign)
        self.count+=1
        return [IV.bounds(self.slope),*[-e for e in self.E],IV.bounds(-self.slope*self.A),
                IV.bounds(-current),*[-v for v in self.u],self.uh,self.Eh]


def dual_lower(c,A,b,box,multipliers):
    """Exact weak duality plus public-box support; no optimality assumption."""
    if len(c)!=N or len(A)!=len(b) or len(A)!=len(multipliers):raise ValueError('dual dimensions')
    residual=[F(x) for x in c];bound=F(0)
    for row,rhs,raw in zip(A,b,multipliers):
        value=max(F(0),F(raw))
        if not value:continue
        bound-=value*rhs
        for j,x in enumerate(row):residual[j]+=value*x
    return bound+sum((v*(lo if v>=0 else hi) for v,(lo,hi) in zip(residual,box)),F(0))


class Certificate:
    def __init__(self,source,*,shape=DEFAULT_SHAPE,rate_radius='0',box=DEFAULT_BOX,
                 voltage_bound='.001',stride=175,slope='1.15',intercept='3'):
        self.box=[(F(a),F(b)) for a,b in box]
        if len(self.box)!=N or any(a>b for a,b in self.box) or self.box[4][0]<=0:raise ValueError('public amplitude box')
        if type(stride) is not int or stride<1:raise ValueError('positive evidence stride')
        self.source=str(source);self.delta=F(voltage_bound);self.intercept=F(intercept)
        if self.delta<0 or F(slope)<=0:raise ValueError('voltage envelope/calibration')
        self.response=Response(shape,rate_radius,slope);self.stride=stride;self.A=[];self.b=[];self.rows=0
        self.binding=dict(source_id=self.source,shape=list(shape),rate_radius=str(rate_radius),
            box=[[str(a),str(b)] for a,b in self.box],voltage_bound=str(self.delta),stride=stride,
            slope=str(slope),intercept=str(intercept),temperature_C=25,model='stationary_linear_OCV_Foster_hysteresis_v1')
        self.configuration_id=hashlib.sha256(json.dumps(self.binding,sort_keys=True).encode()).hexdigest()
        self.maxabs=[max(abs(a),abs(b)) for a,b in self.box]
        for sign in (-1,1):
            row=[F(0)]*N;row[10]=F(sign);row[9]=-1;self.A.append(row);self.b.append(F(0))

    def advance(self,first,rows):
        if type(first) is not int or first!=self.response.count:raise ValueError('certificate source/order')
        obs=np.asarray(rows)
        if obs.ndim!=2 or obs.shape[1]!=5 or not np.isfinite(obs).all():raise ValueError('finite observations')
        if np.any(obs[:,2]!=25) or np.any(obs[:,0]<0) or np.any(obs[:,0]>1) or np.any(abs(obs[:,1])>.25):
            raise ValueError('certificate requires exact I/dt and constant25C')
        for dt,current,_,voltage,_ in obs:
            beta=self.response.advance(float(dt),float(current))
            if self.response.count%self.stride:continue
            midpoint=[x.midpoint for x in beta]
            remainder=sum((x.radius*m for x,m in zip(beta,self.maxabs)),F(0))
            y=F(float(voltage))-self.intercept
            self.A.extend([midpoint,[-x for x in midpoint]])
            self.b.extend([y+self.delta+remainder,-y+self.delta+remainder]);self.rows+=1

    def constraints(self):
        A=self.A.copy();b=self.b.copy()
        # Physical SOC support at all prefix charge extrema, not just selected V.
        low=[F(0)]*N;low[0]=-1;low[4]=self.response.amax
        high=[F(0)]*N;high[0]=1;high[4]=-self.response.amin
        A.extend([low,high]);b.extend([F(0),F(1)])
        for j,(lo,hi) in enumerate(self.box):
            lower=[F(0)]*N;lower[j]=-1;upper=[F(0)]*N;upper[j]=1
            A.extend([lower,upper]);b.extend([-lo,hi])
        return A,b

    def query(self,soc_point=None,q_point=None,soc_tolerance='.005',q_tolerance='.01'):
        A,b=self.constraints();matrix=np.asarray(A,dtype=float);rhs=np.asarray(b,dtype=float)
        # Find a strict interior candidate, then check it against exact constraints.
        witness=linprog(np.r_[np.zeros(N),-1.],A_ub=np.c_[matrix,np.ones(len(b))],b_ub=rhs,
                        bounds=[(None,None)]*N+[(0,None)],method='highs')
        result=dict(source_id=self.source,configuration_id=self.configuration_id,records=self.response.count,
            selected_voltage_rows=self.rows,linear_constraints=len(b),
            floating_LP_matrix_B=matrix.nbytes+rhs.nbytes,
            scope='Conditional bounded-error enclosure on declared stationary public family; not Gaussian coverage or H7 full-domain authorization.',
            execution='unresolved',authorization='unresolved')
        if not witness.success:
            result['reason']='no_verified_feasible_witness';return result
        point=[F(float(x)) for x in witness.x[:N]]
        if any(sum((x*y for x,y in zip(row,point)),F(0))>v for row,v in zip(A,b)):
            result['reason']='LP_witness_failed_exact_verification';return result
        result['feasible_witness']=[rational_pair(x) for x in point]
        bounds={}
        for name,c in [('SOC',[F(1),0,0,0,-self.response.A,0,0,0,0,0,0]),
                       ('inverse_Q',[0,0,0,0,F(1),0,0,0,0,0,0])]:
            ends=[]
            for sign in (1,-1):
                objective=[sign*F(x) for x in c]
                fit=linprog(np.asarray(objective,dtype=float),A_ub=matrix,b_ub=rhs,
                            bounds=[(None,None)]*N,method='highs')
                dual=(-fit.ineqlin.marginals if fit.success else np.zeros(len(b)))
                if not np.isfinite(dual).all():dual=np.zeros(len(b))
                ends.append(max(dual_lower(objective,A,b,self.box,[float(x) for x in dual]),
                                dual_lower(objective,A,b,self.box,[0.]*len(b))))
            lo,hi=ends[0],-ends[1]
            if lo>hi:raise ValueError('crossed certified bounds')
            bounds[name]=(lo,hi)
        invlo,invhi=bounds.pop('inverse_Q')
        if invlo<=0:result['reason']='nonpositive_inverse_capacity_bound';return result
        bounds['Q']=(1/invhi,1/invlo)
        result.update(execution='verified_outer_enclosure',authorization='query_specific',
                      enclosures={name:display_bounds(*value) for name,value in bounds.items()})
        for name,point,tolerance in [('SOC',soc_point,F(soc_tolerance)),('Q',q_point,F(q_tolerance))]:
            lo,hi=bounds[name];middle=(lo+hi)/2
            if tolerance<0 or (name=='Q' and tolerance>=1):raise ValueError('query tolerance')
            def accepted(value):
                value=F(value)
                return ((1-tolerance)*hi<=value<=(1+tolerance)*lo if name=='Q'
                        else max(abs(value-lo),abs(value-hi))<=tolerance)
            result[name]=dict(midpoint_exact=rational_pair(middle),midpoint_authorized=accepted(middle),
                H7_point_authorized=accepted(float(point)) if point is not None and math.isfinite(point) else False,
                tolerance=str(tolerance),units='relative' if name=='Q' else 'SOC_fraction')
        return result
