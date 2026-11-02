"""Small exact-integer outward interval engine, fixed 80-bit dyadic grid.

No binary-libm result is used to certify exponential bounds. This is desktop
proof scaffolding, not a target arithmetic implementation.
"""
from dataclasses import dataclass
from fractions import Fraction as F
from functools import lru_cache

BITS=80
S=1<<BITS


def ceildiv(a,b):return -((-a)//b)


@dataclass(frozen=True)
class Interval:
    lo:int
    hi:int

    def __post_init__(self):
        if type(self.lo) is not int or type(self.hi) is not int or self.lo>self.hi:
            raise ValueError('ordered integer interval required')

    @classmethod
    def bounds(cls,lo,hi=None):
        lo=F(lo);hi=lo if hi is None else F(hi)
        if lo>hi:raise ValueError('crossed bounds')
        return cls((lo*S).__floor__(),(hi*S).__ceil__())

    def __add__(self,other):
        other=as_interval(other);return Interval(self.lo+other.lo,self.hi+other.hi)
    __radd__=__add__
    def __neg__(self):return Interval(-self.hi,-self.lo)
    def __sub__(self,other):return self+-as_interval(other)
    def __rsub__(self,other):return as_interval(other)+-self
    def __mul__(self,other):
        other=as_interval(other);values=[self.lo*other.lo,self.lo*other.hi,self.hi*other.lo,self.hi*other.hi]
        return Interval(min(values)//S,ceildiv(max(values),S))
    __rmul__=__mul__
    def __truediv__(self,other):
        other=as_interval(other)
        if other.lo<=0<=other.hi:raise ValueError('division interval contains zero')
        vals=[F(a*S,b) for a in (self.lo,self.hi) for b in (other.lo,other.hi)]
        return Interval(min(vals).__floor__(),max(vals).__ceil__())
    @property
    def midpoint(self):return F(self.lo+self.hi,2*S)
    @property
    def radius(self):return F(self.hi-self.lo,2*S)
    def contains(self,x):return F(self.lo,S)<=F(x)<=F(self.hi,S)


def as_interval(x):return x if isinstance(x,Interval) else Interval.bounds(x)


@lru_cache(maxsize=128)
def exp_minus(x):
    """Enclose exp(-x) for nonnegative interval x; exact input-key cache only."""
    if not isinstance(x,Interval) or x.lo<0:raise ValueError('nonnegative interval exponent required')
    def endpoint(integer):
        reduced=F(integer,S);squarings=0
        while reduced>1:
            reduced/=2;squarings+=1
        # For 0<=x<=1, S_33 <= exp(-x) <= S_32 by alternating series.
        total=F(1);term=F(1)
        for n in range(1,34):
            term*=-reduced/n;total+=term
            if n==32:upper=total
        result=Interval.bounds(total,upper)
        for _ in range(squarings):result=result*result
        return result
    lower=endpoint(x.hi);upper=endpoint(x.lo)
    return Interval(lower.lo,upper.hi)


def rational_pair(x):return [x.numerator,x.denominator]


def display_bounds(lo,hi):
    """Exact endpoints are authoritative; float endpoints round outward."""
    import math
    lo,hi=F(lo),F(hi)
    a,b=float(lo),float(hi)
    if F(a)>lo:a=math.nextafter(a,-math.inf)
    if F(b)<hi:b=math.nextafter(b,math.inf)
    return dict(exact=[rational_pair(lo),rational_pair(hi)],outer_float=[a,b])
