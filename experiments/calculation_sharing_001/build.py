"""Isolated RC calculation sharing. Same arithmetic, storage, model and prior."""
from pathlib import Path
import json, hashlib, subprocess, re
from experiments.shared_math_001.build import generate as base_generate
VARIANTS=('baseline','feature_rows','feature_rows_shared','rc_readout','rc_readout_shared','rc_geometry','rc_geometry_shared','rc_coordinate','rc_coordinate_shared','rc_coordinate_support','chart_shared','rc_coordinate_support_chart','rc_tau','rc_tau_support','exp_chart','rc_tau_support_exp')

def generate(directory,variant='rc_tau_support',history_bits=48):
 if variant not in VARIANTS:raise ValueError(variant)
 p=base_generate(directory,'procedural_horner',history_bits)
 s=p.read_text()
 if variant.startswith('feature_rows'):
  start=s.index('  unsigned b=coordinate-1;double tau=0,vf=0,ff=0,dvf=0,dff=0;')
  stop=s.index('\n }else{',start)
  s=s[:start]+'''  /* RC endpoint = sum of full-bank coefficient rows times carried state.
     feature derivatives are raw chart coordinates; scale exactly once below.
     Fit derivative scratch is dead during transport. Output d is c->trial;
     neither it nor the carried state aliases the derivative scratch. */
  unsigned b=coordinate-1;double *row=c->qr.scratch.fit.d;*value=0;
  for(unsigned forced=0;forced<2;forced++)for(unsigned j=0;j<13;j++){
   double coefficient,state=(forced?m->forced_rc:m->free_rc)[13*b+j];
   if(feature(m,w,3+(2*b+forced)*13+j,1,&coefficient,row))return -1;
   *value+=state*coefficient;
   for(unsigned k=0;k<16;k++)d[k]+=state*row[k];
  }''' +s[stop:]
  if variant=='feature_rows_shared':
   old='static int feature(';assert s.count(old)==1
   s=s.replace(old,'static __attribute__((noinline,noclone)) int feature(')
 if variant.startswith('rc_readout'):
  helper='''/* Shared RC calculation. Caller zeroes d; derivatives are raw chart units.
     mode 0/1: free/forced feature; mode 2: full carried-state transport.
     Bit 2 selects projected feature weights; transport always uses full poles.
     Sum response shapes before amplitude multiplication, matching original
     transport association and avoiding new intermediate amplitude overflow. */
static void rc_readout(const model*m,const double*w,unsigned b,unsigned pole,
 unsigned mode,double*value,double*d){
 double tau=0,vf=0,ff=0,dvf=0,dff=0;
 for(unsigned k=0;k<=b;k++)tau+=exp(chart(m,w,8+2*k));
 double u=log(tau/m->center[b]);unsigned kind=mode&3;
 if(kind==2){
  for(unsigned j=0;j<13;j++){
   double v,dv;spline(m,u,j,0,&v,&dv);
   vf+=v*m->free_rc[13*b+j];ff+=v*m->forced_rc[13*b+j];
   dvf+=dv*m->free_rc[13*b+j];dff+=dv*m->forced_rc[13*b+j];
  }
 }else spline(m,u,pole,(mode&4)!=0,&vf,&dvf);
 unsigned ai=kind==1?7+2*b:1+b;
 double a=kind==1?exp(chart(m,w,ai)):chart(m,w,ai);
 *value=a*vf;d[ai]=kind==1?*value:vf;double slope=a*dvf;
 if(kind==2){double R=exp(chart(m,w,7+2*b));*value+=R*ff;d[7+2*b]=R*ff;slope+=R*dff;}
 for(unsigned k=0;k<=b;k++)d[8+2*k]=slope*exp(chart(m,w,8+2*k))/tau;
}
'''
  if variant=='rc_readout_shared':helper=helper.replace('static void rc_readout','static __attribute__((noinline,noclone)) void rc_readout')
  marker='/* One feature and one derivative row, physical chart coordinates. */'
  assert s.count(marker)==1;s=s.replace(marker,helper+marker)
  start=s.index('  unsigned block=(row-3)/n,j=(row-3)%n,b=block/2,forced=block%2;')
  stop=s.index('\n }else if(row<hstart+12)',start)
  s=s[:start]+'''  unsigned block=(row-3)/n,j=(row-3)%n;
  rc_readout(m,w,block/2,j,block%2+(full?0:4),value,d);'''+s[stop:]
  start=s.index('  unsigned b=coordinate-1;double tau=0,vf=0,ff=0,dvf=0,dff=0;')
  stop=s.index('\n }else{',start)
  s=s[:start]+'  rc_readout(m,w,coordinate-1,0,2,value,d);'+s[stop:]
 if variant.startswith('rc_geometry'):
  helper='''/* One ordered pole coordinate calculation, with the same binary64
     operations as the two original paths. g[2..2+b] caches exp results;
     derivative products keep their original multiply-then-divide ordering. */
static void rc_geometry(const model*m,const double*w,unsigned b,double*g){
 double tau=0;
 for(unsigned k=0;k<=b;k++){g[2+k]=exp(chart(m,w,8+2*k));tau+=g[2+k];}
 g[0]=tau;g[1]=log(tau/m->center[b]);
}
'''
  if variant=='rc_geometry_shared':helper=helper.replace('static void rc_geometry','static __attribute__((noinline,noclone)) void rc_geometry')
  marker='/* One feature and one derivative row, physical chart coordinates. */'
  if variant.startswith('rc_coordinate_support'):marker='/* Domain matches'
  assert s.count(marker)==1;s=s.replace(marker,helper+marker)
  old='''  double tau=0;
  for(unsigned k=0;k<=b;k++)tau+=exp(chart(m,w,8+2*k));
  double v,dv;spline(m,log(tau/m->center[b]),j,!full,&v,&dv);'''
  assert s.count(old)==1;s=s.replace(old,'''  double g[5];rc_geometry(m,w,b,g);
  double v,dv;spline(m,g[1],j,!full,&v,&dv);''')
  s=s.replace('a*dv*exp(chart(m,w,8+2*k))/tau','a*dv*g[2+k]/g[0]')
  old='''  unsigned b=coordinate-1;double tau=0,vf=0,ff=0,dvf=0,dff=0;
  for(unsigned k=0;k<=b;k++)tau+=exp(chart(m,w,8+2*k));
  double u=log(tau/m->center[b]);'''
  assert s.count(old)==1;s=s.replace(old,'''  unsigned b=coordinate-1;double g[5],vf=0,ff=0,dvf=0,dff=0;
  rc_geometry(m,w,b,g);double u=g[1];''')
  s=s.replace('(bv*dvf+R*dff)*exp(chart(m,w,8+2*k))/tau','(bv*dvf+R*dff)*g[2+k]/g[0]')
 if variant.startswith('rc_coordinate'):
  helper='''/* Shared ordered pole sum and log coordinate. Four argument registers;
     caller retains tau for the unchanged derivative multiply/divide sequence. */
static double rc_coordinate(const model*m,const double*w,unsigned b,double*tau){
 *tau=0;
 for(unsigned k=0;k<=b;k++)*tau+=exp(chart(m,w,8+2*k));
 return log(*tau/m->center[b]);
}
'''
  if variant=='rc_coordinate_shared':helper=helper.replace('static double rc_coordinate','static __attribute__((noinline,noclone)) double rc_coordinate')
  marker='/* One feature and one derivative row, physical chart coordinates. */'
  if variant.startswith('rc_coordinate_support'):marker='/* Domain matches'
  assert s.count(marker)==1;s=s.replace(marker,helper+marker)
  old='''  double tau=0;
  for(unsigned k=0;k<=b;k++)tau+=exp(chart(m,w,8+2*k));
  double v,dv;spline(m,log(tau/m->center[b]),j,!full,&v,&dv);'''
  assert s.count(old)==1;s=s.replace(old,'''  double tau,u=rc_coordinate(m,w,b,&tau);
  double v,dv;spline(m,u,j,!full,&v,&dv);''')
  old='''  unsigned b=coordinate-1;double tau=0,vf=0,ff=0,dvf=0,dff=0;
  for(unsigned k=0;k<=b;k++)tau+=exp(chart(m,w,8+2*k));
  double u=log(tau/m->center[b]);'''
  assert s.count(old)==1;s=s.replace(old,'''  unsigned b=coordinate-1;double tau,vf=0,ff=0,dvf=0,dff=0;
  double u=rc_coordinate(m,w,b,&tau);''')
 if variant.startswith('rc_coordinate_support'):
  s=s.replace('double q=exp(-chart(m,w,5)),s=0;','double q=exp(-chart(m,w,5));')
  old='s+=exp(chart(m,w,8+2*j));double u=log(s/m->center[j]);'
  assert s.count(old)==1;s=s.replace(old,'double tau,u=rc_coordinate(m,w,j,&tau);')
 if variant in ('chart_shared','rc_coordinate_support_chart'):
  old='static double chart(';assert s.count(old)==1
  s=s.replace(old,'static __attribute__((noinline,noclone)) double chart(')
 if variant.startswith('rc_tau'):
  helper='''/* Shared ordered pole sum; log remains at the caller's stack depth. */
static __attribute__((noinline,noclone)) double rc_tau(const model*m,const double*w,unsigned b){
 double tau=0;for(unsigned k=0;k<=b;k++)tau+=exp(chart(m,w,8+2*k));return tau;
}
'''
  marker='/* Domain matches';assert s.count(marker)==1;s=s.replace(marker,helper+marker)
  old='double tau=0;\n  for(unsigned k=0;k<=b;k++)tau+=exp(chart(m,w,8+2*k));'
  assert s.count(old)==1;s=s.replace(old,'double tau=rc_tau(m,w,b);')
  old='double tau=0,vf=0,ff=0,dvf=0,dff=0;\n  for(unsigned k=0;k<=b;k++)tau+=exp(chart(m,w,8+2*k));'
  assert s.count(old)==1;s=s.replace(old,'double tau=rc_tau(m,w,b),vf=0,ff=0,dvf=0,dff=0;')
  if variant.startswith('rc_tau_support'):
   s=s.replace('double q=exp(-chart(m,w,5)),s=0;','double q=exp(-chart(m,w,5));')
   old='s+=exp(chart(m,w,8+2*j));double u=log(s/m->center[j]);'
   assert s.count(old)==1;s=s.replace(old,'double u=log(rc_tau(m,w,j)/m->center[j]);')
 if variant in ('exp_chart','rc_tau_support_exp'):
  s,count=re.subn(r'exp\(chart\(m,w,([^()]*)\)\)',r'exp_chart(m,w,\1)',s)
  assert count>=6
  helper='''/* Shared positive parameter transform, with unchanged chart and exp. */
static __attribute__((noinline,noclone)) double exp_chart(const model*m,const double*w,unsigned j){
 return exp(chart(m,w,j));
}
'''
  marker='static double cheb(';assert s.count(marker)==1;s=s.replace(marker,helper+marker)
 p.write_text(s)
 (Path(directory)/'sharing_generation.json').write_text(json.dumps(dict(variant=variant,history_bits=history_bits,core_sha256=hashlib.sha256(p.read_bytes()).hexdigest()),indent=2)+'\n')
 return p

def build(directory,variant,history_bits=48):
 d=Path(directory).resolve()/variant;src=generate(d,variant,history_bits);binary=d/'rowwise.so'
 cmd=['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-fno-fast-math','-ffp-contract=off','-fPIC','-shared',str(src),'-lm','-o',str(binary)]
 subprocess.run(cmd,check=True)
 (d/'build.json').write_text(json.dumps(dict(configuration=dict(variant=variant,history_bits=history_bits),binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),command=cmd),indent=2)+'\n')
 return d
