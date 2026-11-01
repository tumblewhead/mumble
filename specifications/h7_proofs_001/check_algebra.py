"""Exact polynomial identities, not a proof assistant or C verifier.

Sparse monomial dictionaries over Fraction; no numerical tolerances.
"""
from fractions import Fraction as F
import json
from pathlib import Path

class Poly:
    def __init__(self,value=0):self.c=dict(value) if isinstance(value,dict) else ({():F(value)} if value else {})
    @staticmethod
    def variable(name):return Poly({(name,):F(1)})
    def __add__(self,b):
        b=b if isinstance(b,Poly) else Poly(b);out=self.c.copy()
        for k,v in b.c.items():out[k]=out.get(k,F(0))+v
        return Poly({k:v for k,v in out.items() if v})
    __radd__=__add__
    def __neg__(self):return Poly({k:-v for k,v in self.c.items()})
    def __sub__(self,b):return self+(-b if isinstance(b,Poly) else -Poly(b))
    def __rsub__(self,b):return Poly(b)-self
    def __mul__(self,b):
        b=b if isinstance(b,Poly) else Poly(b);out={}
        for k,v in self.c.items():
            for l,w in b.c.items():
                m=tuple(sorted(k+l));out[m]=out.get(m,F(0))+v*w
        return Poly({k:v for k,v in out.items() if v})
    __rmul__=__mul__
    def __pow__(self,n):
        out=Poly(1)
        for _ in range(n):out=out*self
        return out

def identities():
    a,b,c,d,t,x,y,z,s,r,j,e,k=[Poly.variable(n) for n in ('a','b','c','d','t','x','y','z','s','r','j','e','k')]
    h=F(1,2)
    return {
        'rational_Givens_preserves_every_Gram_entry':((1-t*t)*a+2*t*b)*((1-t*t)*c+2*t*d)+(-2*t*a+(1-t*t)*b)*(-2*t*c+(1-t*t)*d)-(1+t*t)**2*(a*c+b*d),
        'convex_state_bound_square':(1-a)*x*x+a*y*y-((1-a)*x+a*y)**2-a*(1-a)*(x-y)**2,
        'affine_transport_contraction':(a*x+(1-a)*s)-(a*y+(1-a)*s)-a*(x-y),
        'augmented_prior_at_anchor':(a+(x-a))**2-x*x,
        'perturbed_likelihood_gradient':(j+k)*(r+e)-j*r-(j*e+k*r+k*e),
        'centered_scalar_Gram_error':h*e*((x+d)**2-x*x)-(e*x*d+h*e*d*d),
        'TV_extremum_nonnegative_square':(t-s)**2*z-(t*t-z)*(z-s*s)-(z-s*t)**2,
        'SOC_joint_linear_variance':(x+a*y)**2-(x*x+2*a*x*y+a*a*y*y)
    }

def main():
    checks=identities()
    assert all(not v.c for v in checks.values())
    # Exact counterexamples to tempting but false stronger statements.
    interpolation=-(F(1,2)**2)+F(1,2)+1
    assert interpolation==F(5,4)>1
    omitted_cross=F(1)+F(1);actual=omitted_cross+2*F(-9,10)
    assert actual==F(1,5) and omitted_cross/actual==10
    receipt=dict(status='exact_polynomial_identities_checked',identities={k:'zero polynomial' for k in checks},
        counterexamples={'bounded_node_interpolation':{'nodes':[-1,0,1],'values':[-1,1,1],'polynomial':'1+x-x^2','p_at_half':'5/4'},
                        'discarded_SOC_cross_term':{'diagonal_variance':'2','full_variance':'1/5','variance_ratio':'10'},
                        'recycled_posterior':{'root_prior_precision':1,'data_precision':1,'correct_precision':2,'posterior_plus_same_data_precision':3}},
        scope='Exact rational algebra checks. Inequality hypotheses, induction and analytic probability arguments are proved in the accompanying manuscript, not machine-verified here.')
    print(json.dumps(receipt,indent=2))
if __name__=='__main__':main()
