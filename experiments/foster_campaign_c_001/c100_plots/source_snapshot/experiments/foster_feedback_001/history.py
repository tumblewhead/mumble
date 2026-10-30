"""Generic local-Gaussian evidence encoding and boundary conditioning.

No battery, physical coefficients, observations, load, truth or aging rules.
The producer supplies a likelihood root and deterministic transport object.
"""
import math
import numpy as np

D=16
TRI=np.triu_indices(D+1)


def pack_message(mean,root,log_evidence):
    a=np.r_[mean,np.asarray(root).ravel(),log_evidence].astype('<f8')
    if a.size!=273 or not np.isfinite(a).all():raise ValueError('invalid Gaussian message')
    return a.tobytes()


def message(payload):
    if type(payload) is not bytes or len(payload)!=2184:raise ValueError('message format/length')
    a=np.frombuffer(payload,dtype='<f8')
    if not np.isfinite(a).all():raise ValueError('nonfinite message')
    return a[:16],a[16:272].reshape(16,16),float(a[-1])


def pack_kernel(anchor,endpoint,F,A,residual,noise_constant,encoding):
    # QR retains every cross term and orthogonal residual. No incoming prior.
    augmented=np.column_stack([A,residual])
    if len(augmented)<D+1:augmented=np.vstack([augmented,np.zeros((D+1-len(augmented),D+1))])
    R=np.linalg.qr(augmented,mode='r')
    dtype='<f8' if encoding=='float64' else '<f4' if encoding=='float32' else None
    if dtype is None:raise ValueError('unknown coefficient encoding')
    values=np.r_[R[TRI],np.asarray(F).ravel()].astype(dtype)
    centers=np.r_[anchor,endpoint,noise_constant].astype('<f8')
    if not np.isfinite(values).all() or not np.isfinite(centers).all():raise ValueError('coefficient range unresolved')
    return (b'8' if encoding=='float64' else b'4')+centers.tobytes()+values.tobytes()


def kernel(payload):
    if type(payload) is not bytes or payload[:1] not in (b'8',b'4'):raise ValueError('kernel format')
    dtype='<f8' if payload[:1]==b'8' else '<f4'
    if len(payload)!=265+409*np.dtype(dtype).itemsize:raise ValueError('kernel length')
    centers=np.frombuffer(payload[1:265],dtype='<f8')
    a=np.frombuffer(payload[265:],dtype=dtype).astype(float)
    if not np.isfinite(a).all() or not np.isfinite(centers).all():raise ValueError('invalid kernel values')
    R=np.zeros((17,17));R[TRI]=a[:153]
    return centers[:16],centers[16:32],a[153:].reshape(16,16),R[:,:16],R[:,16],float(centers[-1])


class GaussianBackend:
    def validate_message(self,payload):message(payload)

    def advance(self,prior,token):
        m,L,logZ=message(prior)
        anchor,end,F,A,r,c=kernel(token.payload)
        residual=r+A@(m-anchor);B=A@L
        precision=np.eye(D)+B.T@B;C=np.linalg.cholesky(precision)
        w=-np.linalg.solve(C.T,np.linalg.solve(C,B.T@residual))
        mean=m+L@w;root=np.linalg.solve(C,L.T).T
        fitted=residual+B@w
        increment=-c-.5*(fitted@fitted+w@w+2*np.log(np.diag(C)).sum())
        return pack_message(end+F@(mean-anchor),F@root,logZ+float(increment))


def numeric_storage(encoding,block_records=16):
    token=3537 if encoding=='float64' else 1901
    return dict(message_payload_B=2184,token_payload_B=token,
                two_messages_plus_token_B=4368+token,raw_window_numeric_B=block_records*5*8,
                excludes='Python objects, protocol metadata, native Jacobians, optimizer matrices, QR/solve scratch, allocator/stack',
                complete_subsystem_B=None)
