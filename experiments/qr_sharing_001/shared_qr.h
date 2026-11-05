/* Shared Givens insertion, preserving the original mutation and check order.
   packed!=0: history_store (six-byte IEEE high bits, rounded on every write).
   packed==0: native double factor. R and x do not alias; extents are caller-owned.
   No staging copy: read every updated coefficient from its actual storage. */
static double qr_read(const void*R,unsigned p,unsigned packed){
 return packed?history_get((const history_store*)R,p):((const double*)R)[p];
}
static void qr_write(void*R,unsigned p,unsigned packed,double v){
 if(packed)history_put((history_store*)R,p,v);else ((double*)R)[p]=v;
}
static __attribute__((noinline,noclone)) int shared_insert(void*R,int n,double*x,unsigned packed){
 unsigned p=0;
 for(int j=0;j<n;j++){
  double a=qr_read(R,p,packed),b=x[j],h=hypot(a,b);
  if(!isfinite(h))return -1;
  if(h==0){p+=n-j;continue;}
  double c=a/h,s=b/h;qr_write(R,p++,packed,h);
  if(!isfinite(qr_read(R,p-1,packed)))return -1;
  for(int k=j+1;k<n;k++){
   double r=qr_read(R,p,packed),v=x[k];qr_write(R,p,packed,c*r+s*v);x[k]=c*v-s*r;
   if(!isfinite(qr_read(R,p,packed))||!isfinite(x[k]))return -1;
   p++;
  }
 }
 return 0;
}
