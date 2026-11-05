from pathlib import Path
import ctypes,hashlib,json,math,random,subprocess
root=Path(__file__).resolve().parents[3]/'experiments/integer_qr_001'
out=Path('/tmp/integer_qr_review');out.mkdir(parents=True,exist_ok=True)
src=out/'guard.c';src.write_text(f'#include "{root}/kernel.h"\nuint64_t sq(uint64_t n){{return iq_sqrt_guard(n);}}\nuint64_t ratio(uint64_t a,uint64_t b){{return iq_ratio(a,b);}}\n')
subprocess.run(['cc','-O2','-shared','-fPIC','-fsanitize=undefined','-fno-sanitize-recover=all',str(src),'-o',str(out/'guard.so')],check=True)
lib=ctypes.CDLL(str(out/'guard.so'));lib.sq.argtypes=[ctypes.c_uint64];lib.sq.restype=ctypes.c_uint64;lib.ratio.argtypes=[ctypes.c_uint64]*2;lib.ratio.restype=ctypes.c_uint64
rng=random.Random(713)
for i in range(100000):
 if i<100:n=i
 elif i<110:n=(1<<64)-1-(i-100)
 else:n=rng.randrange(1<<64)
 scaled=n<<32;s=math.isqrt(scaled);s+=scaled-s*s>s
 assert lib.sq(n)==s,(n,s,lib.sq(n))
 a=rng.randrange((1<<29)+1);b=rng.randrange((1<<29)+1);n=a*a+b*b
 scaled=n<<32;s=math.isqrt(scaled);s+=scaled-s*s>s
 num=a<<46;q,r=divmod(num,s);q+=2*r>=s
 assert lib.ratio(a<<16,s)==q
print(json.dumps({'sqrt_exact_controls':100000,'ratio_exact_controls':100000,'source_sha256':hashlib.sha256((root/'kernel.h').read_bytes()).hexdigest()}))
