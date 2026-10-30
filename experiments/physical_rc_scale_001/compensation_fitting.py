"""Nonnegative additive information in physical and response coordinates."""
import math
import numpy as np
from experiments.partition_coordinate_fit_001 import coordinates as c
from experiments.partition_coordinate_fit_001.stable_normalizer import log_mass

AREF=-math.expm1(-1.)


def objective(theta,design,target,lo,hi,a,charge=None):
    if charge is not None:charge(len(target))
    c.old.require(np.isfinite(theta).all() and abs(theta[-2])<=40 and 0<=theta[-1]<=1,'combined objective domain')
    rho=(AREF/a)**2-1
    d=1+theta[-1]*rho
    sd=np.exp(theta[-2])/np.sqrt(d)
    mu=design@theta[:-2]
    residual=(mu-target)/sd
    left,right=(lo-mu)/sd,(hi-mu)/sd
    logz=log_mass(left,right)
    pa=np.exp(-.5*left**2-.5*c.old.LOG2PI-logz)
    pb=np.exp(-.5*right**2-.5*c.old.LOG2PI-logz)
    scale_score=1-residual**2+left*pa-right*pb
    loss=float(np.mean(.5*residual**2+np.log(sd)+.5*c.old.LOG2PI+logz))
    gradient=np.r_[design.T@((residual+pa-pb)/sd)/len(target),
                   np.mean(scale_score),np.mean(-.5*scale_score*rho/d)]
    c.old.require(np.isfinite(loss) and np.isfinite(gradient).all(),'nonfinite combined objective')
    return loss,gradient


def residual(theta,g):
    projected=g.copy()
    if theta[-1]==0:projected[-1]=min(g[-1],0.)
    if theta[-1]==1:projected[-1]=max(g[-1],0.)
    return float(np.abs(projected).max())


def fit(raw,values,lo,hi,a,beta,logsd,config,charge=None,initial_fraction=0.):
    n=len(values)
    q,r=np.linalg.qr(raw,mode='reduced')
    transform=r/np.sqrt(n);design=q*np.sqrt(n)
    scale=math.exp(float(logsd))
    theta=np.r_[transform@beta/scale,0.,initial_fraction]
    target,lower,upper=values/scale,lo/scale,hi/scale
    evaluations=0
    def evaluate(t):
        nonlocal evaluations
        c.old.require(evaluations<config['evaluations_per_conditional'],'evaluation cap')
        evaluations+=1
        return objective(t,design,target,lower,upper,a,charge)
    loss,g=evaluate(theta);initial=loss;initial_gradient=residual(theta,g)
    metric=np.eye(len(theta));metric[-2,-2]=.5
    status='iteration_limit';iterations=0;rejected=0
    for iteration in range(config['iterations_per_conditional']):
        if residual(theta,g)<=config['gradient_infinity_tolerance']:
            status='constrained_gradient_tolerance_met';break
        direction=-metric@g
        boundary=None
        if theta[-1]+direction[-1]<0:boundary=0.
        if theta[-1]+direction[-1]>1:boundary=1.
        if boundary is not None:
            direction[-1]=boundary-theta[-1]
            cross=metric[:-1,-1]/metric[-1,-1]
            inverse_free=metric[:-1,:-1]-np.outer(metric[:-1,-1],metric[-1,:-1])/metric[-1,-1]
            direction[:-1]=-inverse_free@g[:-1]+cross*direction[-1]
        slope=float(g@direction)
        if not np.isfinite(direction).all() or slope>=0:
            status='no_feasible_descent';break
        accepted=False
        for backtrack in range(config['backtracking_attempts']):
            if evaluations>=config['evaluations_per_conditional']:
                status='evaluation_limit';break
            fraction=2.**(-backtrack)
            trial=theta+fraction*direction
            if boundary is not None and backtrack==0:trial[-1]=boundary
            try:new_loss,new_g=evaluate(trial)
            except c.old.Unavailable:
                rejected+=1;continue
            if new_loss<=loss+config['armijo']*fraction*slope:
                accepted=True;break
            rejected+=1
        if not accepted:
            if status!='evaluation_limit':status='line_search_unresolved'
            break
        step,change=trial-theta,new_g-g
        curvature=float(step@change)
        if curvature>config['curvature_relative_guard']*np.linalg.norm(step)*np.linalg.norm(change):
            matrix=np.eye(len(theta))-np.outer(step,change)/curvature
            metric=matrix@metric@matrix.T+np.outer(step,step)/curvature
        else:
            metric=np.eye(len(theta));metric[-2,-2]=.5
        theta,loss,g=trial,new_loss,new_g;iterations=iteration+1
    final=residual(theta,g)
    if final<=config['gradient_infinity_tolerance']:status='constrained_gradient_tolerance_met'
    c.old.require(loss<=initial+1e-12,'combined objective increased')
    return scale*np.linalg.solve(transform,theta[:-2]),logsd+float(theta[-2]),float(theta[-1]),dict(
        status=status,iterations=iterations,evaluations=evaluations,rejected_trials=rejected,
        initial_mean_NLL=initial+logsd,final_mean_NLL=loss+logsd,
        initial_gradient_infinity=initial_gradient,final_gradient_infinity=final,
        information_fraction=float(theta[-1]),fraction_gradient=float(g[-1]),
        scope='Constrained first-order fit check; nonlinear mean/scale family, no global optimum or coverage claim')
