"""Selected common-nuisance necessary rows; not an exact physical feasible set."""
import copy
import math
from fractions import Fraction
import numpy as np
from .intervals import *
from .native_kernels import exp_iv
from . import thermal_displacement as td

NCOORD=12
BUDGET=128

def enc(x):return [np.asarray(x[0]).tolist(),np.asarray(x[1]).tolist()]
def dec(x):return np.asarray(x[0],float),np.asarray(x[1],float)
def take(x,k):return x[0][...,k],x[1][...,k]
def stack(xs):return np.stack([x[0] for x in xs],-1),np.stack([x[1] for x in xs],-1)
def blend(x,y,w):
 out=[]
 for ww in w:
  out.append(add(mul(point(ww),x),mul(sub(point(1.),point(ww)),y)))
 return intersect(hull(*out),hull(x,y))
def scalar_charge(ticks):
 if not ticks:return point(0.)
 f=Fraction(int(ticks),126000000000);v=float(f)
 return down(v),up(v)
def admission(k):return k==1 or (k<=512 and k>0 and k&(k-1)==0) or k==1050 or k%350==0

def ocv_ref(z,controls):
 vals=(np.broadcast_to(controls[0],z[0].shape+(4,)).copy(),np.broadcast_to(controls[1],z[1].shape+(4,)).copy())
 zz=z[0][...,None],z[1][...,None]
 for _ in range(3): vals=add(mul(sub(point(1.),zz),(vals[0][...,:-1],vals[1][...,:-1])),mul(zz,(vals[0][...,1:],vals[1][...,1:])))
 return take(vals,0)

def monotone_ref(z,controls):
 # Evaluate endpoints separately; all configured cubics are monotone.
 lo=ocv_ref(point(z[0]),controls)[0];hi=ocv_ref(point(z[1]),controls)[1]
 return lo,hi

class JointRows:
 def __init__(self,est,prior):
  n=est.n;self.n=n;self.epoch_start=est.next_index;self.source_count=0
  p=est.p;zz=est.z0
  A=monotone_ref(zz,p['ocv_ref']);K=intersect(ocv_ref(zz,p['ocv_kappa']),(np.min(p['ocv_kappa'][0]),np.max(p['ocv_kappa'][1])))
  def repeat(x):return np.broadcast_to(x[0],(n,)).copy(),np.broadcast_to(x[1],(n,)).copy()
  H=repeat(p['H_ref']);eta=mul(H,iv(prior['h']))
  self.box=stack([A,K]+[repeat(iv(prior['v'][k])) for k in range(3)]+[repeat(take(p['R_ref'],k)) for k in range(4)]+[H,eta,est.u])
  self.original_box=tuple(x.copy() for x in self.box)
  self.hprior=iv(prior['h']);self.E=point(np.ones((n,3)));self.F=point(np.zeros((n,3)))
  self.Ah=point(np.ones(n));self.Bh=point(np.zeros(n));self.records=[]
  self.rest_open=True;self.rest_end_index=None;self.rest_anchors=[];self.pairs=[];self.pair_budget_full=False
  self.budget_full=False;self.query_count=0;self.certified_bounds=0;self.failed_lp=0
 def clone(self):
  obj=copy.copy(self)
  for k in ['box','E','F','Ah','Bh']:setattr(obj,k,tuple(v.copy() for v in getattr(self,k)))
  obj.records=list(self.records);obj.pairs=list(self.pairs);obj.rest_anchors=copy.deepcopy(self.rest_anchors)
  return obj
 def propagate(self,est,tube,current,a,ah):
  if current!=0.:
   if self.rest_open:self.rest_end_index=est.next_index
   self.rest_open=False;self.rest_anchors=[]
  if self.rest_open:
   for anchor in self.rest_anchors:anchor['Eseg']=enc(intersect(mul(dec(anchor['Eseg']),a),(0.,1.)))
  d=sub(take(tube,0),point(0.)) # tube is relative to Tr already.
  er=exp_iv(neg(mul(est.p['beta_R'],(d[0][:,None],d[1][:,None]))))
  target=mul((er[0][:,1:],er[1][:,1:]),est.current_interval(current))
  self.E=intersect(mul(self.E,a),(0.,1.));self.F=blend(self.F,target,a)
  self.Ah=intersect(mul(self.Ah,ah),(0.,1.));self.Bh=intersect(blend(self.Bh,point(1. if current>=0 else -1.),ah),(-1.,1.))
 def advance_rest(self,est,boundary,core_source,surface_source):
  if self.rest_open and self.rest_anchors:
   td.advance([a['thermal'] for a in self.rest_anchors],est,iv(boundary['ambient_K']),core_source,surface_source)
 def admit_rest_pairs(self,est,rec):
  if not self.rest_open or rec['current_A']!=0. or rec['charge_ticks']!=0:return
  for anchor in self.rest_anchors:
   if len(self.pairs)>=BUDGET:self.pair_budget_full=True;break
   old=self.records[anchor['record_index']]
   if old['current_A']!=0. or old['charge_ticks']!=0:raise ValueError('rest pair chronology')
   delta=td.delta(anchor['thermal'],est)
   Ea=dec(old['E']);Eseg=dec(anchor['Eseg'])
   pc=mul(Ea,sub(point(1.),Eseg))
   Ta=dec(old['Tc']);Tb=dec(rec['Tc']);Th=hull(Ta,Tb)
   expbar=exp_iv(neg(mul(est.p['beta_H'],sub(Th,point(est.tr)))))
   etac=mul(mul(est.p['beta_H'],delta),expbar)
   zero=point(np.zeros(self.n))
   a=stack([zero,delta]+[take(pc,k) for k in range(3)]+[zero]*5+[etac,zero])
   obs=sub(dec(rec['observation']),dec(old['observation']))
   m=(a[0]+a[1])/2;bounds=sub(obs,sum_iv(mul(sub(a,point(m)),self.box)))
   self.pairs.append({'start_index':old['sample_index'],'end_index':rec['sample_index'],'start_record':anchor['record_index'],'end_record':len(self.records)-1,'coefficient':enc(a),'normal':m.tolist(),'observation':enc(obs),'necessary_bounds':enc(bounds),'delta_Tc':enc(delta),'Eseg':anchor['Eseg']})
  if len(self.rest_anchors)<64:
   self.rest_anchors.append({'record_index':len(self.records)-1,'thermal':td.initialize(est),'Eseg':enc(point(np.ones((self.n,3))))})
 def record(self,est,observation,current):
  self.source_count+=1
  return {'sample_index':est.next_index,'epoch_count':self.source_count,'charge_ticks':est.charge_ticks,'current_A':current,'observation':enc(observation),'Tc':enc(add(take(est.thermal(),0),point(est.tr))),'E':enc(self.E),'F':enc(self.F),'Ah':enc(self.Ah),'Bh':enc(self.Bh)}
 def coeff(self,est,record):
  Tc=dec(record['Tc']);q=scalar_charge(record['charge_ticks']);z0=est.z0
  z=intersect(sub(z0,mul(q,take(self.box,11))),(0.,1.))
  bad=z[0]>z[1];est.active &= ~bad
  z=(np.where(bad,0.,z[0]),np.where(bad,1.,z[1]));seg=hull(z0,z)
  w=est.ocv_controls(Tc)
  dcontrols=mul(point(3.),sub((w[0][:,1:],w[1][:,1:]),(w[0][:,:-1],w[1][:,:-1])))
  zs=seg[0][:,None],seg[1][:,None]
  vv=dcontrols
  for _ in range(2):vv=add(mul(sub(point(1.),zs),(vv[0][:,:-1],vv[1][:,:-1])),mul(zs,(vv[0][:,1:],vv[1][:,1:])))
  # Also intersect convex-hull derivative controls, always enclosing.
  D=intersect(take(vv,0),(np.min(dcontrols[0],axis=1),np.max(dcontrols[1],axis=1)))
  dt=sub(Tc,point(est.tr));er=exp_iv(neg(mul(take(est.p['beta_R'],0),dt)))
  eh=exp_iv(neg(mul(est.p['beta_H'],dt)))
  E,F,Ah,Bh=[dec(record[k]) for k in ['E','F','Ah','Bh']]
  return stack([point(np.ones(self.n)),dt]+[neg(take(E,k)) for k in range(3)]+[neg(mul(er,est.current_interval(record['current_A'])))]+[neg(take(F,k)) for k in range(3)]+[neg(mul(eh,Bh)),neg(mul(eh,Ah)),neg(mul(q,D))])
 def contract_one(self,est,record):
  coef=self.coeff(est,record);obs=dec(record['observation'])
  # A necessary interval row contractor; retains its projection but not this
  # entire source relation unless the fixed admission schedule stores it.
  for _ in range(2):
   for j in range(NCOORD):
    aj=take(coef,j);usable=(aj[0]>1e-200)|(aj[1]<-1e-200) # optional contractor abstains on unsafe reciprocal
    other=point(np.zeros(self.n))
    for k in range(NCOORD):
     if k!=j:other=add(other,mul(take(coef,k),take(self.box,k)))
    safe=(np.where(usable,aj[0],1.),np.where(usable,aj[1],1.))
    bound=div(sub(obs,other),safe)
    usable &= np.isfinite(bound[0]) & np.isfinite(bound[1])
    self.box[0][:,j]=np.where(usable,np.maximum(self.box[0][:,j],bound[0]),self.box[0][:,j])
    self.box[1][:,j]=np.where(usable,np.minimum(self.box[1][:,j],bound[1]),self.box[1][:,j])
   self._active(est)
   if not np.any(est.active):return
   self.sanitize(est)
 def _active(self,est):est.active &= np.all(self.box[0]<=self.box[1],axis=1)
 def sanitize(self,est):
  if not np.any(est.active):return
  i=int(np.flatnonzero(est.active)[0]);bad=~est.active
  for k in ['box','E','F','Ah','Bh']:
   x=getattr(self,k);x[0][bad]=x[0][i];x[1][bad]=x[1][i]
 def support_sync(self,est):
  self.box[0][:,11]=np.maximum(self.box[0][:,11],est.u[0]);self.box[1][:,11]=np.minimum(self.box[1][:,11],est.u[1])
  kr=intersect(ocv_ref(est.z0,est.p['ocv_kappa']),(np.min(est.p['ocv_kappa'][0]),np.max(est.p['ocv_kappa'][1])))
  self.box[0][:,1]=np.maximum(self.box[0][:,1],kr[0]);self.box[1][:,1]=np.minimum(self.box[1][:,1],kr[1])
  ar=monotone_ref(est.z0,est.p['ocv_ref']);self.box[0][:,0]=np.maximum(self.box[0][:,0],ar[0]);self.box[1][:,0]=np.minimum(self.box[1][:,0],ar[1])
  self._active(est);self.sanitize(est)
 def necessary_rows(self,est):
  # Binary64 m is an exactly represented chosen row center. Outward epsilon
  # covers every coefficient perturbation over the current certified box.
  rows=[];updated=[]
  for rec in self.records:
   a=self.coeff(est,rec);m=np.asarray(rec['normal'],float)
   rem=sum_iv(mul(sub(a,point(m)),self.box))
   obs=dec(rec['observation'])
   bounds=intersect(dec(rec['necessary_bounds']),sub(obs,rem))
   est.active &= bounds[0]<=bounds[1]
   new=dict(rec);new['necessary_bounds']=enc(bounds);updated.append(new)
   rows.append((m,bounds))
  self.records=updated
  updated_pairs=[]
  for rec in self.pairs:
   a=dec(rec['coefficient']);m=np.asarray(rec['normal'],float);obs=dec(rec['observation'])
   bounds=intersect(dec(rec['necessary_bounds']),sub(obs,sum_iv(mul(sub(a,point(m)),self.box))))
   est.active &= bounds[0]<=bounds[1]
   new=dict(rec);new['necessary_bounds']=enc(bounds);updated_pairs.append(new);rows.append((m,bounds))
  self.pairs=updated_pairs
  return rows
 def query(self,est):
  from .certified_lp import project
  rows=self.necessary_rows(est);self.query_count+=1
  for i in np.flatnonzero(est.active):
   A=[];b=[]
   for m,y in rows:A.extend([m[i],-m[i]]);b.extend([float(y[1][i]),float(-y[0][i])])
   # Exact projected compatibility eta0/Href in the original h0 support.
   row=np.zeros(NCOORD);row[10]=1.;row[9]=-float(self.hprior[1]);A.append(row);b.append(0.)
   row=np.zeros(NCOORD);row[10]=-1.;row[9]=float(self.hprior[0]);A.append(row);b.append(0.)
   lo,hi,report=project(np.asarray(A),np.asarray(b),self.box[0][i],self.box[1][i])
   self.box[0][i]=lo;self.box[1][i]=hi
   if report.get('empty',False):est.active[i]=False
   self.certified_bounds+=report.get('tightened_bounds',0);self.failed_lp+=report.get('fallbacks',0)
  self._active(est);self.sanitize(est)
 def feedback(self,est,link_z=True):
  est.u=intersect(est.u,take(self.box,11))
  if link_z:
   # Reference-temperature monotone inverse links aggregate A0 back to z0.
   target=take(self.box,0);lo=np.zeros(self.n);hi=np.ones(self.n)
   for _ in range(18):
    m=(lo+hi)/2;y=monotone_ref(point(m),est.p['ocv_ref']);sel=y[1]<target[0];lo=np.where(sel,m,lo);hi=np.where(sel,hi,m)
   zl=lo;lo=np.zeros(self.n);hi=np.ones(self.n)
   for _ in range(18):
    m=(lo+hi)/2;y=monotone_ref(point(m),est.p['ocv_ref']);sel=y[0]>target[1];hi=np.where(sel,m,hi);lo=np.where(sel,lo,m)
   est.z0=intersect(est.z0,(zl,hi))
  p0=(self.box[0][:,2:5],self.box[1][:,2:5]);rr=(self.box[0][:,6:9],self.box[1][:,6:9])
  est.v=intersect(est.v,add(mul(self.E,p0),mul(self.F,rr)))
  h0=intersect(div(take(self.box,10),take(self.box,9)),self.hprior)
  est.h=intersect(est.h,add(mul(self.Ah,h0),self.Bh))
  est.active &= (est.z0[0]<=est.z0[1])&(est.u[0]<=est.u[1])&np.all(est.v[0]<=est.v[1],axis=1)&(est.h[0]<=est.h[1])
  self.sanitize(est);est._sanitize_inactive()
 def assimilate(self,est,observation,current):
  self.support_sync(est)
  if not np.any(est.active):return
  rec=self.record(est,observation,current);self.contract_one(est,rec)
  if not np.any(est.active):return
  if admission(self.source_count):
   if len(self.records)<BUDGET:
    a=self.coeff(est,rec);m=(a[0]+a[1])/2;rec['normal']=m.tolist()
    rec['necessary_bounds']=enc(sub(dec(rec['observation']),sum_iv(mul(sub(a,point(m)),self.box))))
    self.records.append(rec);self.admit_rest_pairs(est,rec);self.query(est)
   else:self.budget_full=True
  if np.any(est.active):self.feedback(est,link_z=admission(self.source_count))
 def dump(self):
  return {'rest_open':self.rest_open,'rest_end_index':self.rest_end_index,'rest_anchors':self.rest_anchors,'pairs':self.pairs,'pair_budget_full':self.pair_budget_full,'box':enc(self.box),'original_box':enc(self.original_box),'hprior':enc(self.hprior),'E':enc(self.E),'F':enc(self.F),'Ah':enc(self.Ah),'Bh':enc(self.Bh),'records':self.records,'epoch_start':self.epoch_start,'source_count':self.source_count,'budget_full':self.budget_full,'query_count':self.query_count,'certified_bounds':self.certified_bounds,'failed_lp':self.failed_lp}
 def load(self,obj,est):
  trial=self.clone()
  for k in ['box','E','F','Ah','Bh']:
   x=dec(obj[k]);shape=getattr(self,k)[0].shape
   if any(v.shape!=shape or not np.all(np.isfinite(v)) for v in x):raise ValueError('joint snapshot shape/finite')
   if np.any(x[0][est.active]>x[1][est.active]):raise ValueError('joint snapshot inverted active interval')
   setattr(trial,k,x)
  if obj['original_box']!=enc(self.original_box) or obj['hprior']!=enc(self.hprior):raise ValueError('joint snapshot prior mismatch')
  for k in ['epoch_start','source_count','query_count','certified_bounds','failed_lp']:
   if type(obj[k]) is not int or obj[k]<0:raise ValueError('joint snapshot counter')
   setattr(trial,k,obj[k])
  if trial.epoch_start<1 or trial.source_count!=est.assimilations or trial.epoch_start+trial.source_count!=est.next_index:raise ValueError('joint snapshot chronology')
  if type(obj['budget_full']) is not bool:raise ValueError('joint snapshot budget')
  trial.budget_full=obj['budget_full'];rows=obj['records']
  if not isinstance(rows,list) or len(rows)>BUDGET:raise ValueError('joint snapshot record budget')
  last=0
  for r in rows:
   k=r['epoch_count']
   if type(k) is not int or not last<k<=trial.source_count or not admission(k) or r['sample_index']!=trial.epoch_start+k-1:raise ValueError('joint snapshot row source')
   if type(r['charge_ticks']) is not int or abs(r['charge_ticks'])>k*10000:raise ValueError('joint snapshot charge')
   if not isinstance(r['current_A'],(int,float)) or not math.isfinite(r['current_A']) or not -.01<=r['current_A']<=.01:raise ValueError('joint snapshot current')
   for name,shape in [('observation',()),('Tc',(self.n,)),('E',(self.n,3)),('F',(self.n,3)),('Ah',(self.n,)),('Bh',(self.n,)),('necessary_bounds',(self.n,))]:
    x=dec(r[name])
    if any(v.shape!=shape or not np.all(np.isfinite(v)) for v in x) or np.any((x[0]>x[1]) if name!='necessary_bounds' else (x[0][est.active]>x[1][est.active])):raise ValueError('joint snapshot row interval')
   normal=np.asarray(r['normal'],float)
   if normal.shape!=(self.n,NCOORD) or not np.all(np.isfinite(normal)):raise ValueError('joint snapshot normal')
   last=k
  trial.records=copy.deepcopy(rows)
  if np.any(trial.box[0][est.active]<self.original_box[0][est.active]) or np.any(trial.box[1][est.active]>self.original_box[1][est.active]):raise ValueError('joint snapshot outside prior')
  for name in ['E','Ah']:
   x=getattr(trial,name)
   if np.any(x[0][est.active]<0) or np.any(x[1][est.active]>1):raise ValueError('joint snapshot decay')
  if type(obj['rest_open']) is not bool or type(obj['pair_budget_full']) is not bool:raise ValueError('joint rest snapshot flags')
  trial.rest_open=obj['rest_open'];trial.pair_budget_full=obj['pair_budget_full'];trial.rest_end_index=obj['rest_end_index']
  if trial.rest_open:
   if trial.rest_end_index is not None or est.last_current!=0. or est.charge_ticks!=0 or any(r['current_A']!=0. or r['charge_ticks']!=0 for r in rows):raise ValueError('joint rest flag contradiction')
  else:
   if type(trial.rest_end_index) is not int or not trial.epoch_start<=trial.rest_end_index<est.next_index:raise ValueError('joint rest end chronology')
   if any((r['current_A']!=0. or r['charge_ticks']!=0) for r in rows if r['sample_index']<trial.rest_end_index):raise ValueError('joint rest history contradiction')
  if not isinstance(obj['pairs'],list) or len(obj['pairs'])>BUDGET:raise ValueError('joint pair budget')
  for p in obj['pairs']:
   if type(p['start_record']) is not int or type(p['end_record']) is not int or not 0<=p['start_record']<p['end_record']<len(rows):raise ValueError('joint pair source records')
   a,b=rows[p['start_record']],rows[p['end_record']]
   if trial.rest_end_index is not None and b['sample_index']>=trial.rest_end_index:raise ValueError('joint pair crosses rest end')
   if any(r['current_A']!=0. or r['charge_ticks']!=0 for r in rows[p['start_record']:p['end_record']+1]):raise ValueError('joint pair crosses nonrest record')
   if p['start_index']!=a['sample_index'] or p['end_index']!=b['sample_index'] or any(r['charge_ticks']!=0 or r['current_A']!=0. for r in [a,b]):raise ValueError('joint pair source identity')
   for name,shape in [('coefficient',(self.n,NCOORD)),('observation',()),('necessary_bounds',(self.n,)),('delta_Tc',(self.n,)),('Eseg',(self.n,3))]:
    x=dec(p[name])
    if any(v.shape!=shape or not np.all(np.isfinite(v)) for v in x) or np.any((x[0]>x[1]) if name!='necessary_bounds' else (x[0][est.active]>x[1][est.active])):raise ValueError('joint pair interval')
   m=np.asarray(p['normal'],float)
   if m.shape!=(self.n,NCOORD) or not np.all(np.isfinite(m)):raise ValueError('joint pair normal')
  trial.pairs=copy.deepcopy(obj['pairs'])
  anchors=obj['rest_anchors']
  if not isinstance(anchors,list) or len(anchors)>64 or (not trial.rest_open and anchors):raise ValueError('joint rest anchor budget')
  previous=-1
  for a in anchors:
   k=a['record_index']
   if type(k) is not int or not previous<k<len(rows):raise ValueError('joint rest anchor ordering')
   td.validate(a['thermal'],self.n,est.config_hash,trial.epoch_start,est.next_index,rows[k]['sample_index'])
   if a['thermal']['anchor_Tc_K']!=rows[k]['Tc']:raise ValueError('joint rest temperature identity')
   x=dec(a['Eseg'])
   if any(v.shape!=(self.n,3) or not np.all(np.isfinite(v)) for v in x) or np.any(x[0]>x[1]) or np.any(x[0]<0) or np.any(x[1]>1):raise ValueError('joint rest decay')
   previous=k
  trial.rest_anchors=copy.deepcopy(anchors)
  return trial
