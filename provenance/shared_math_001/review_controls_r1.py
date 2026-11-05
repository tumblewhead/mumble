import ctypes as C,json,math,random,struct,subprocess,hashlib
from pathlib import Path
from fractions import Fraction as F
ROOT=Path(__file__).resolve().parents[2]
variants=('baseline','bernstein','bernstein_seed','horner_seed','procedural')
def neighbors(x):return [math.nextafter(x,-math.inf),x,math.nextafter(x,math.inf)]
def bits(x):return struct.unpack('>Q',struct.pack('>d',x))[0]
def frombits(x):return struct.unpack('>d',struct.pack('>Q',x))[0]
def metric(fn,op,points,ref):
 maxu=0;worst=None;bad=[]
 for x,y in points:
  try:b=ref(x,y)
  except OverflowError:b=math.inf
  except ValueError:b=math.nan
  a=fn(op,x,y)
  if math.isnan(b):ok=math.isnan(a)
  elif math.isinf(b):ok=a==b
  else:ok=math.isfinite(a)
  if not ok:bad.append([x.hex(),y.hex(),a.hex(),b.hex()]);continue
  if math.isfinite(b):
   u=abs(a-b)/math.ulp(b)
   if u>maxu:maxu=u;worst=[x.hex(),y.hex(),a.hex(),b.hex()]
 return dict(count=len(points),max_ulp=maxu,worst=worst,classification_mismatches=bad[:10],mismatch_count=len(bad))
rng=random.Random(93117)
pos=[frombits(rng.randrange(1,0x7ff0000000000000)) for _ in range(20000)]
pos+=sum((neighbors(math.ldexp(1.,e)) for e in (-1074,-1022,-1021,-2,-1,0,1,2,1022,1023)),[])
pos+=[float.fromhex('0x1.fffffffffffffp1023')]
special=[-math.inf,-1.,-0.,0.,math.inf,math.nan]
exppts=sum((neighbors(x) for x in (-745.1332191019411,-709.,-.5,-.25,0.,.25,.5,709.782712893384)),[])
exppts+=sum((neighbors((k+.5)*math.log(2)) for k in range(-1000,1001,17)),[])
logpts=pos+sum((neighbors(x) for x in (math.sqrt(2),1.,.5,2.,math.nextafter(0.,1.))),[])+special
atanhpts=sum((neighbors(x) for x in (-1.,-.25,0.,.25,1.)),[])+special
hypotpts=[(pos[i],pos[-i-1]) for i in range(len(pos))]+[(x,y) for x in special+[float.fromhex('0x1.fffffffffffffp1023'),math.ulp(0.)] for y in special+[1.]]
cases=[('exp',0,[(x,0.) for x in exppts+special],lambda x,y:math.exp(x)),('expm1',1,[(x,0.) for x in exppts+special],lambda x,y:math.expm1(x)),('log',2,[(x,0.) for x in logpts],lambda x,y:math.log(x)),('sqrt',3,[(x,0.) for x in pos+special],lambda x,y:math.sqrt(x)),('hypot',4,hypotpts,math.hypot),('tanh',5,[(x,0.) for x in exppts+special+sum((neighbors(x) for x in (-20.,20.)),[])],lambda x,y:math.tanh(x)),('atanh',6,[(x,0.) for x in atanhpts],lambda x,y:math.atanh(x))]
# Python math raises at zero log and atanh +-1, whereas the documented C wrappers return poles.
def logref(x,y):return -math.inf if x==0 else math.log(x)
def atanhref(x,y):return math.copysign(math.inf,x) if abs(x)==1 else math.atanh(x)
cases[2]=(*cases[2][:3],logref);cases[6]=(*cases[6][:3],atanhref)
result={}
for v in variants:
 d=ROOT/'experiments/shared_math_001/attempt001/host'/v
 lib=C.CDLL(str(d/'math.so'));fn=lib.evaluate;fn.argtypes=[C.c_uint,C.c_double,C.c_double];fn.restype=C.c_double
 result[v]={name:metric(fn,op,points,ref) for name,op,points,ref in cases}
 result[v]['signed_zero']={name:bits(fn(op,-0.,0.))==bits(-0.) for name,op in [('expm1',1),('sqrt',3),('tanh',5),('atanh',6)]}
 target=ROOT/'experiments/shared_math_001/attempt001/target'/v/'tiny_cardinal'
 records=[]
 for line in (target/'symbols.txt').read_text().splitlines():
  a=line.split()
  if len(a)==4 and ('__aeabi_' in a[3] or a[3] in ('__eqdf2','__nedf2','__ledf2','__ltdf2','__gedf2','__gtdf2')):records.append((int(a[0],16),int(a[1],16),a[3]))
 intervals=sorted(set((a,a+b) for a,b,n in records));merged=[]
 for a,b in intervals:
  if merged and a<=merged[-1][1]:merged[-1][1]=max(b,merged[-1][1])
  else:merged.append([a,b])
 result[v]['double_helper_unique_B']=sum(b-a for a,b in merged)
 result[v]['double_helper_symbols']=[n for a,b,n in records]
 result[v]['source_header_sha256']=hashlib.sha256((d/'shared_math.h').read_bytes()).hexdigest()
# Independent exact coefficient transform verifies p(lo+span*t) == sum(bi B_i^n(t)).
checks=[]
sqrt_coeff=[F(1)]
for k in range(1,8):sqrt_coeff.append(sqrt_coeff[-1]*(F(1,2)-k+1)/k)
for p,lo,span in [([F(1,math.factorial(k+1)) for k in range(15)],F(-1,2),F(1)),([F(1,2*k+1) for k in range(13)],F(0),F(1,16)),(sqrt_coeff,F(-3,5),F(6,5))]:
 n=len(p)-1;a=[sum(p[j]*math.comb(j,k)*lo**(j-k)*span**k for j in range(k,n+1)) for k in range(n+1)]
 b=[sum(a[k]*F(math.comb(i,k),math.comb(n,k)) for k in range(i+1)) for i in range(n+1)]
 reconstructed=[sum(b[i]*math.comb(n,i)*math.comb(n-i,j-i)*(-1)**(j-i) for i in range(j+1)) for j in range(n+1)]
 checks.append(a==reconstructed)
out=dict(scope='Independent deterministic boundary and random bit-pattern host controls; no exhaustive error or target execution certificate',seed=93117,algebra_exact_E_L_sqrt_bernstein=checks,variants=result)
p=ROOT/'provenance/shared_math_001/review_controls_r1.json';p.parent.mkdir(exist_ok=True);p.write_text(json.dumps(out,indent=2,allow_nan=False)+'\n')
for v,z in result.items():print(v,{k:(q['max_ulp'],q['mismatch_count']) for k,q in z.items() if isinstance(q,dict) and 'max_ulp' in q},'helpers',z['double_helper_unique_B'])
