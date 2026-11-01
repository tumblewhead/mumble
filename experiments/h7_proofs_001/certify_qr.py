"""Exact-dyadic, finite-witness certificates for the unmodified native QR kernel.

No claim about unbounded streams, the feature approximation or target libm.
All acceptance arithmetic uses Fraction; floats only generate/format witnesses.
"""
import ctypes as C
import hashlib
import json
from fractions import Fraction as F
from pathlib import Path
import shutil
import subprocess
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'experiments/h7_proofs_001/qr004'
D=16

def matrix(a):return [[F(float(x)) for x in row] for row in np.asarray(a)]
def transpose(A):return [list(r) for r in zip(*A)]
def product(A,B):
    Bt=transpose(B)
    return [[sum((x*y for x,y in zip(row,col)),F(0)) for col in Bt] for row in A]
def difference(A,B):return [[x-y for x,y in zip(a,b)] for a,b in zip(A,B)]
def eye(n):return [[F(i==j) for j in range(n)] for i in range(n)]
def infnorm(A):return max(sum(abs(x) for x in row) for row in A)
def gram(A):return product(transpose(A),A)
def scalar(q):return dict(numerator=str(q.numerator),denominator=str(q.denominator),approx=float(q))
def identity(p):return dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())

def certificate(rows,R,Q):
    rows,R,Q=(np.asarray(x,dtype=float) for x in (rows,R,Q))
    if rows.ndim!=2 or rows.shape[1]!=17 or len(rows)<1 or R.shape!=(17,17) or Q.shape!=(D,D):
        raise ValueError('certificate requires Nx17 rows,17x17 factor,16x16 whitener')
    if not all(np.isfinite(x).all() for x in (rows,R,Q)):
        raise ValueError('certificate inputs must be finite')
    A=matrix(rows);G=gram(A);U=matrix(R[:D,:D]);Q=matrix(Q)
    P=[row[:D] for row in G[:D]];Pc=gram(U)
    # ||I-UQ||inf <1 proves Q and U are nonsingular, by the Neumann lemma.
    inverse_residual=infnorm(difference(product(U,Q),eye(D)))
    Ft=product(transpose(Q),product(P,Q));Fc=product(transpose(Q),product(Pc,Q))
    radius=infnorm(difference(Ft,eye(D)));lower=1-radius
    delta=infnorm(difference(Fc,Ft))
    eps=delta/lower if lower>0 and inverse_residual<1 else None
    ratios=[Fc[j][j]/Ft[j][j] for j in range(D) if Ft[j][j]>0]
    return dict(exhibited_precision_ratio_min=scalar(min(ratios)) if ratios else None,exhibited_precision_ratio_max=scalar(max(ratios)) if ratios else None,inverse_residual=scalar(inverse_residual),reference_white_radius=scalar(radius),
                reference_white_lower=scalar(lower),white_gram_error=scalar(delta),
                epsilon=scalar(eps) if eps is not None else None,
                certifies_relative_precision_and_covariance=eps is not None and eps<1,
                full_augmented_gram_error_inf=scalar(infnorm(difference(gram(matrix(R)),G))))

def main():
    OUT.mkdir(parents=True,exist_ok=False)
    source=ROOT/'experiments/field_tangent_native_001'
    for n in ('kernel.c','kernel.h'):shutil.copy2(source/n,OUT/n)
    shutil.copy2(ROOT/'experiments/hysteresis_refinement_001/response.c',OUT/'response.c')
    (OUT/'wrapper.c').write_text('#include "kernel.c"\nint proof_rows(double *r,const double *a,size_t n) { double row[17]; for(size_t k=0;k<n;k++){memcpy(row,a+17*k,sizeof(row));int s=append(r,row);if(s)return s;} return 0;}\n')
    cmd=['cc','-DFT_HDEG=7','-std=c11','-O2','-fno-fast-math','-ffp-contract=off','-Wall','-Wextra','-Werror','-pedantic','-shared','-fPIC',str(OUT/'wrapper.c'),str(OUT/'response.c'),'-lm','-o',str(OUT/'proof.so')]
    subprocess.run(cmd,check=True)
    lib=C.CDLL(str(OUT/'proof.so'));dp=C.POINTER(C.c_double)
    lib.proof_rows.argtypes=[dp,dp,C.c_size_t];lib.proof_rows.restype=C.c_int
    rng=np.random.default_rng(721);base=rng.normal(size=(64,17));cases={
        'ordinary':base,
        'weak_rank_one':np.tile(base[0],(64,1)),
        'scaled':base*np.r_[np.geomspace(1e-4,1e4,16),1.],
        'coupled_large':base.copy()}
    cases['coupled_large'][:,0]=base[:,0]*1e10
    cases['coupled_large'][:,1]=cases['coupled_large'][:,0]+base[:,1]
    cases['coupled_tilted']=cases['coupled_large'].copy()
    cases['coupled_tilted'][:,1]=1.00000003*cases['coupled_large'][:,0]+base[:,1]
    records=[]
    for name,rows in cases.items():
        prior=np.c_[np.eye(16),np.zeros(16)];allrows=np.ascontiguousarray(np.vstack([prior,rows]))
        packed=np.zeros(153)
        assert lib.proof_rows(packed.ctypes.data_as(dp),allrows.ctypes.data_as(dp),len(allrows))==0
        R=np.zeros((17,17));R[np.triu_indices(17)]=packed
        Q=np.linalg.solve(R[:16,:16],np.eye(16))
        record=dict(case=name,binary64=certificate(allrows,R,Q))
        # Proposed storage quantization is assessed against the SAME original rows.
        R32=R.astype(np.float32).astype(np.float64)
        Q32=np.linalg.solve(R32[:16,:16],np.eye(16))
        record['binary32_stored_factor']=certificate(allrows,R32,Q32)
        np.savez(OUT/(name+'.npz'),rows=allrows,R=R,Q=Q,R32=R32,Q32=Q32)
        record['artifact']=identity(OUT/(name+'.npz'));records.append(record)
        print(name,{k:v['epsilon']['approx'] if v['epsilon'] else None for k,v in record.items() if k in ('binary64','binary32_stored_factor')},flush=True)
    receipt=dict(status='finite_witness_certificates_complete',cases=records,command=cmd,
        compiler=subprocess.check_output(['cc','--version'],text=True).splitlines()[0],
        source_identities={n:identity(OUT/n) for n in ('kernel.c','kernel.h','response.c','wrapper.c')},
        binary=identity(OUT/'proof.so'),certificate_source=identity(Path(__file__)),
        scope='Exact rational certificates for supplied binary64 rows and returned factors, all directions in16-dimensional local quadratic. Not a stream-wide or C/libm correctness proof.')
    (OUT/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
if __name__=='__main__':main()
