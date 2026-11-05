from pathlib import Path
import ctypes,hashlib,json,math,random,struct,subprocess
root=Path(__file__).resolve().parents[3]
src=root/'experiments/integer_qr_001/integrate.py'
s=src.read_text();body=s.split('float v=x[j]*@SCALE@.f;',1)[1].split('row[j]=q;',1)[0]
out=Path('/tmp/integer_qr_review');out.mkdir(exist_ok=True)
c=out/'conversion.c';c.write_text('#include <stdint.h>\nint32_t quant(float v){'+body+'return q;}\n')
subprocess.run(['cc','-O2','-shared','-fPIC','-fsanitize=undefined,float-cast-overflow','-fno-sanitize-recover=all',str(c),'-o',str(out/'conversion.so')],check=True)
lib=ctypes.CDLL(str(out/'conversion.so'));lib.quant.argtypes=[ctypes.c_float];lib.quant.restype=ctypes.c_int32
rng=random.Random(714);tests=0
values=[0.,0.5,-0.5,8388609.,-8388609.,2.**29,-2.**29]
for i in range(100000):
 bits=rng.randrange(1<<32);v=struct.unpack('f',struct.pack('I',bits))[0]
 if math.isfinite(v) and abs(v)<=2**29:values.append(v)
for center in (0x3f000000,0x3fc00000,0x4affffff,0x4b000000):
 for delta in range(-5,6):
  v=struct.unpack('f',struct.pack('I',center+delta))[0];values.extend([v,-v])
for v in values:
 expected=int(math.copysign(math.floor(abs(v)+.5),v));assert lib.quant(v)==expected,(v,lib.quant(v),expected);tests+=1
result={'status':'passed','conversion_cases':tests,'source_sha256':hashlib.sha256(src.read_bytes()).hexdigest()}
Path(__file__).with_name('conversion_result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
