"""Generate source-bound experimental cores from the reviewed implementation."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent

def generate(directory,math_kind='tiny',map_kind='spline',compact=False,history_bits=64):
 directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
 s=(ROOT/'experiments/bank_rowwise_001/core.c').read_text()
 assert history_bits in (48,64)
 assert math_kind in ('tiny','libm') and map_kind in ('spline','cardinal')
 s=s.replace('#include "../bank_memory_001/scratch_kernel.c"','#include "'+str(ROOT/'experiments/bank_memory_001/scratch_kernel.c')+'"')
 scratch=(ROOT/'experiments/bank_memory_001/scratch_kernel.c').read_text()
 scratch=scratch.replace('#include "qr.c"',(ROOT/'experiments/bank_memory_001/qr.c').read_text())
 scratch=scratch.replace('const double *history','const history_store *history').replace('history[index_of(width,i,j)]','history_get(history,index_of(width,i,j))')
 s=s.replace('#include "'+str(ROOT/'experiments/bank_memory_001/scratch_kernel.c')+'"',scratch)
 s=s.replace('memcpy(c->anchor,w,16*sizeof(double))','memmove(c->anchor,w,16*sizeof(double))')
 s=s.replace('const double *history','const history_store *history').replace('history[index_of(WIDTH,i,j)]','history_get(history,index_of(WIDTH,i,j))')
 storage=('#include "'+str(HERE/'history48.h')+'"\n') if history_bits==48 else 'typedef double history_store;\n#define history_get(p,i) ((p)[i])\n#define history_insert qr_insert\n'
 s=storage+s
 if math_kind=='tiny':s='#include "'+str(HERE/'tiny_math.h')+'"\n'+s
 if map_kind=='cardinal':
  start=s.index('static void spline(');end=s.index('/* Domain matches',start)
  s=s[:start]+'''/* Same fixed13 poles, new global polynomial weight map. Signed;
    no positivity/passivity or uniform error certificate is claimed. */
static void cardinal(double u,unsigned j,double *v,double *d){
 double x=4*u+6,p=1,q=0,denom=1;
 for(unsigned k=0;k<13;k++)if(k!=j){q=q*(x-k)+p;p*=x-k;denom*=(int)j-(int)k;}
 *v=p/denom;*d=4*q/denom;
}
static void spline(const model *m,double u,unsigned pole,int projected,double *v,double *d){
 if(!projected){cardinal(u,pole,v,d);return;}
 const double *a=m->projected_map+13*pole;
 double b1=0,b2=0,d1=0,d2=0;
 for(int j=12;j>=1;j--){double b=a[j]+2*u*b1-b2,dd=2*b1+2*u*d1-d2;b2=b1;b1=b;d2=d1;d1=dd;}
 *v=a[0]+u*b1-b2;*d=b1+u*d1-d2;
}
''' +s[end:]
 if compact:
  s=s.replace('m->legacy[38]','m->legacy[14]').replace('m->legacy[37]','m->legacy[13]').replace('m->legacy[36]','m->legacy[12]').replace('m->legacy+18+9*k','m->legacy+6*k')
  s+="""
/* Serialized row scratch contract: caller fills phi. Tangent consumes it first;
   destructive history insertion consumes it second. Neither aliases retained
   history/response. Any failure invalidates inference; caller quarantines stream. */
int ingest(core*c,history_store*history){
 if(append(c,c->phi,1)||history_insert(history,WIDTH,c->phi)){c->qr.lease.valid=0;return -1;}
 return 0;
}
"""
  s+='\n#include "'+str(HERE/'stream.c')+'"\n'
 s="""/* Candidate alias exceptions: initialize/fit may take own anchor/point as
   input. Internal step uses delta; transport uses trial; stream fills phi then
   append consumes it before history insertion overwrites it. These are serialized
   lifetime exceptions to the inherited no-external-alias contract below.
   tm_scale only receives exp's n in[-1075,1024] or line-search n in[-17,0].
   tm_nextup only receives positive finite cost>=1 and +infinity direction. */
"""+s
 p=directory/'core.c' ;p.write_text(s)
 (directory/'generation.json').write_text(json.dumps(dict(math=math_kind,map=map_kind,compact=compact,history_bits=history_bits,source_sha256=hashlib.sha256(s.encode()).hexdigest()),indent=2)+'\n')
 return p
