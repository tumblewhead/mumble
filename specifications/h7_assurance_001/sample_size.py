"""Planning calculations for independent Bernoulli scenario outcomes only."""
import math

def zero_failure_upper(n,alpha=.05):
    if isinstance(n,bool) or not isinstance(n,int) or n<1 or not 0<alpha<1:
        raise ValueError('positive integer n and alpha in (0,1) required')
    return -math.expm1(math.log(alpha)/n)

def required_zero_failures(max_failure_probability,alpha=.05):
    if not 0<max_failure_probability<1 or not 0<alpha<1:
        raise ValueError('probabilities must be in (0,1)')
    return math.ceil(math.log(alpha)/math.log1p(-max_failure_probability))

if __name__=='__main__':
    import json
    print(json.dumps({'assumptions':'Independent identically distributed complete scenarios, fixed design, zero failures; not shared-cell factorial outputs.',
        'one_sided_confidence':.95,'zero_failure_requirements':{str(p):required_zero_failures(p) for p in (.01,.001,.0001)},
        'upper_failure_probability':{str(n):zero_failure_upper(n) for n in (20,300,500,1000,8000)}},indent=2))

def binomial_cdf(k,n,p):
    """Small planning-only exact binomial sum evaluated in log space."""
    if k<0:return 0.
    if k>=n:return 1.
    if p==0:return 1.
    if p==1:return 0.
    logs=[math.lgamma(n+1)-math.lgamma(i+1)-math.lgamma(n-i+1)+i*math.log(p)+(n-i)*math.log1p(-p) for i in range(k+1)]
    peak=max(logs)
    return min(1.,math.exp(peak)*math.fsum(math.exp(x-peak) for x in logs))

def coverage_power(n,null_miss=.06,true_miss=.05,alpha=.025):
    lo,hi=-1,n
    while hi-lo>1:
        mid=(lo+hi)//2
        if binomial_cdf(mid,n,null_miss)<=alpha:lo=mid
        else:hi=mid
    return dict(n=n,max_misses_to_reject_null=lo,type_I=binomial_cdf(lo,n,null_miss),power=binomial_cdf(lo,n,true_miss))
