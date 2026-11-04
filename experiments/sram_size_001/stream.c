/* Stationary25C/affine OCV stream. Compact state Hfree6,Hforced6,path3;
   full RC free39/forced39. Mutable response pointers must name writable arrays.
   One serialized owner. Any failure invalidates the context; no rollback copy.
   Caller owns identity, sequence and normalization and quarantines failed input. */
int stream_row(core*c,const double*V,const double*ocv,const double*o){
 for(unsigned k=0;k<5;k++)if(!isfinite(o[k]))goto fail;
 double dt=o[0],I=o[1],sigma=o[4];
 if(dt<0||dt>1||fabs(I)>.25||o[2]!=25||sigma<=0)goto fail;
 double *s=(double*)c->m.legacy,*free=(double*)c->m.free_rc,*forced=(double*)c->m.forced_rc;
 double *row=c->phi;
 s[12]+=I*dt/3600;
 if(s[12]<s[13])s[13]=s[12];
 if(s[12]>s[14])s[14]=s[12];
 row[0]=ocv[1]/sigma;row[1]=-ocv[1]*s[12]/sigma;row[2]=-I/sigma;
 for(unsigned b=0;b<3;b++){
  for(unsigned k=0;k<6;k++)row[3+6*b+k]=0;
  for(unsigned j=0;j<13;j++){
   unsigned ix=13*b+j;
   double dose=dt/(c->m.center[b]*exp(((int)j-6)*.25));
   double a=exp(-dose),one=-expm1(-dose);
   free[ix]*=a;forced[ix]=a*forced[ix]+one*I;
   for(unsigned k=0;k<3;k++){
    row[3+6*b+k]-=free[ix]*V[3*j+k]/sigma;
    row[6+6*b+k]-=forced[ix]*V[3*j+k]/sigma;
   }
  }
 }
 if(I!=0){
  unsigned j=I>0?1:2,l=I>0?2:1,jj=I>0?3:5;
  double dose=c->m.center[I>0?3:4]*fabs(I)*dt/3600;
  double a=exp(-dose),one=-expm1(-dose),e1=-dose*a,e2=(dose*dose-dose)*a;
  for(unsigned kind=0;kind<2;kind++){
   double*v=s+6*kind,old0=v[0],oldj=v[j],oldl=v[l],target=kind?(I>0?1:-1):0;
   for(unsigned k=0;k<6;k++)v[k]*=a;
   v[0]+=one*target;v[j]+=e1*(old0-target);
   v[jj]+=2*e1*oldj+e2*(old0-target);v[4]+=e1*oldl;
  }
 }
 for(unsigned kind=0;kind<2;kind++){
  const double*v=s+6*(1-kind);double*r=row+21+6*kind;
  r[0]=(v[0]+.25*v[3]+.25*v[5])/sigma;r[1]=v[2]/sigma;r[2]=.25*v[5]/sigma;
  r[3]=v[1]/sigma;r[4]=v[4]/sigma;r[5]=.25*v[3]/sigma;
 }
 row[33]=(ocv[0]-o[3])/sigma;
 for(unsigned k=0;k<34;k++)if(!isfinite(row[k]))goto fail;
 return 0;
fail:c->qr.lease.valid=0;return -1;
}
int stream_ingest(core*c,history_store*history,const double*V,const double*ocv,const double*o){
 if(!c->qr.lease.valid)return -1;
 if(stream_row(c,V,ocv,o)||ingest(c,history)){c->qr.lease.valid=0;return -1;}
 return 0;
}
