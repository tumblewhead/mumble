"""Isolated shared-math variants; baseline estimator/model/storage unchanged."""
from pathlib import Path
from fractions import Fraction as F
from decimal import Decimal,localcontext
import math,json,hashlib,subprocess
from experiments.sram_size_001.generate import generate as base_generate
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
VARIANTS=('baseline','bernstein','bernstein_seed','horner_seed','procedural','horner','procedural_shared','bernstein_low','bernstein_medium','bernstein_small','procedural_horner')

def coefficients():
 e=[F(1,math.factorial(k+1)) for k in range(15)]
 l=[F(1,2*k+1) for k in range(13)]
 b=[F(1)]
 for k in range(1,8):b.append(b[-1]*(F(1,2)-k+1)/k)
 return [e,l,b]

def header(path,variant):
 if variant not in VARIANTS:raise ValueError('variant')
 s=(ROOT/'experiments/sram_size_001/tiny_math.h').read_text()
 if variant=='baseline':path.write_text(s);return
 kinds=3 if variant.endswith('_seed') else 2
 engine=''
 if variant.startswith('procedural'):
  engine='''/* One coefficient-generating series engine. No coefficient LUT. */
static double sm_eval(unsigned kind,double x){
 double term=1,sum=1;unsigned count=kind?12:14;
 for(unsigned k=1;k<=count;k++){term*=x*(kind?2*k-1:1)/(kind?2*k+1:k+1);sum+=term;}
 return sum;
}
'''
  if variant=='procedural_horner':engine='''static double sm_eval(unsigned kind,double x){
 double y=0;int n=kind?12:14;
 for(int k=n;k>=0;k--){if(kind)y=1./(2*k+1)+x*y;else y=(1+x*y)/(k+1);}
 return y;
}
'''
 else:
  tables=[]
  for kind,power in enumerate(coefficients()[:kinds]):
   if variant=='bernstein_low':power=power[:13] if kind==0 else power[:11]
   if variant=='bernstein_medium':power=power[:9] if kind==0 else power[:7]
   if variant=='bernstein_small':power=power[:6]
   if variant.startswith('bernstein'):
    lo,span=[(F(-1,2),F(1)),(F(0),F(1,16)),(F(-3,5),F(6,5))][kind];n=len(power)-1
    a=[sum(power[j]*math.comb(j,k)*lo**(j-k)*span**k for j in range(k,n+1)) for k in range(n+1)]
    coeff=[sum(a[k]*F(math.comb(i,k),math.comb(n,k)) for k in range(i+1)) for i in range(n+1)]
   else:coeff=power
   with localcontext() as c:
    c.prec=80;factor=Decimal('2.5').sqrt() if kind==2 else Decimal(1)
    tables.append([float(Decimal(v.numerator)/Decimal(v.denominator)*factor) for v in coeff])
  for k,table in enumerate(tables):engine+='static const double sm_c'+str(k)+'[]={'+','.join(v.hex() for v in table)+'};\n'
  engine+='static double sm_eval(unsigned kind,double x){\n const double*c=kind==0?sm_c0:sm_c1;unsigned n=kind==0?'+str(len(tables[0])-1)+':'+str(len(tables[1])-1)+';\n'
  if kinds==3:engine+=' if(kind==2){c=sm_c2;n=7;}\n'
  if variant.startswith('bernstein'):
   engine+=' double t=kind==0?x+.5:x*16;\n'
   if kinds==3:engine+=' if(kind==2)t=(x-1)/3;\n'
   engine+=' double work['+str(max(map(len,tables)))+'];for(unsigned j=0;j<=n;j++)work[j]=c[j];\n for(unsigned k=n;k;k--)for(unsigned j=0;j<k;j++)work[j]=(1-t)*work[j]+t*work[j+1];\n return work[0];\n}\n'
  else:
   if kinds==3:engine+=' if(kind==2)x=(x-2.5)/2.5;\n'
   engine+=' double y=c[n];while(n)y=c[--n]+x*y;return y;\n}\n'
 if variant in ('procedural_shared','procedural_horner'):engine=engine.replace('static double sm_eval','static __attribute__((noinline,noclone)) double sm_eval')
 a=s.index('/* Shared degree13');b=s.index('static inline double tm_exp(',a)
 s=s[:a]+engine+'static inline double tm_expm1_reduced(double r){return r*sm_eval(0,r);}\n'+s[b:]
 a=s.index(' double t=(m-1)/(m+1)');b=s.index('\n}',a)
 s=s[:a]+' double t=(m-1)/(m+1);\n return n*0x1.62e42fee00000p-1+(2*t*sm_eval(1,t*t)+n*0x1.a39ef35793c76p-33);'+s[b:]
 s=s.replace('double z=x*x,y=1./25.;for(int k=23;k>=3;k-=2)y=1./k+z*y;return x*(1+z*y);','return x*sm_eval(1,x*x);')
 if kinds==3:
  a=s.index(' double y=tm_value((tm_bits(x)>>1)');b=s.index('\n return y*scale;',a)
  s=s[:a]+''' uint64_t bits=tm_bits(x);int exponent=(int)(bits>>52)-1023;
 double m=tm_value((bits&UINT64_C(0xfffffffffffff))|UINT64_C(0x3ff0000000000000));
 if(exponent%2){m*=2;exponent--;}
 double y=sm_eval(2,m);
 for(unsigned k=0;k<3;k++)y=.5*(y+m/y);
 y=tm_scale(y,exponent/2);
'''+s[b:]
 path.write_text(s)

def generate(directory,variant,history_bits=64):
 directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
 h=directory/'shared_math.h';header(h,variant)
 p=base_generate(directory,'tiny','cardinal',True,history_bits)
 p.write_text(p.read_text().replace(str(ROOT/'experiments/sram_size_001/tiny_math.h'),str(h.resolve())))
 (directory/'generation.json').write_text(json.dumps(dict(variant=variant,history_bits=history_bits,header_sha256=hashlib.sha256(h.read_bytes()).hexdigest(),core_sha256=hashlib.sha256(p.read_bytes()).hexdigest()),indent=2)+'\n')
 return p

def build(directory,variant):
 directory=Path(directory).resolve()/variant;src=generate(directory,variant)
 binary=directory/'rowwise.so'
 subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-fno-fast-math','-ffp-contract=off','-fPIC','-shared',str(src),'-lm','-o',str(binary)],check=True)
 (directory/'build.json').write_text(json.dumps(dict(configuration=dict(variant=variant),binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest()),indent=2))
 return directory
