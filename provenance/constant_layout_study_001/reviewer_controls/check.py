"""Independent reviewer controls; run from repository root with python3 -B."""
import hashlib,json,random,struct,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from experiments.constant_layout_study_001 import codecs as c,study as s

r=random.Random(20261104);count=0;block_count=0
for n in [0,1,2,3,7,8,9,15,16,17,31,32,33,63,64,65,127,128,129,255,256,257,513,2049]:
 for a in [bytes(r.randrange(256) for _ in range(n)),bytes(r.randrange(4) for _ in range(n)),b'\xff'*n,(bytes(range(256))*9)[:n]]:
  for ob in (10,11,12):assert c.lz_decode(c.lz_encode(a,ob),ob)==a
  assert c.bpe9_decode(c.bpe9_encode(a))==a
  assert c.huff_decode(c.huff_encode(a))==a
  for block in (32,64,128,256):
   blob=c.block_lz_encode(a,block);assert c.block_lz_decode(blob)==a
   total,w=struct.unpack_from('<HH',blob);nb=(total+w-1)//w;base=4+2*nb
   offsets=[struct.unpack_from('<H',blob,4+2*i)[0] for i in range(nb)]+[len(blob)-base]
   decoded=[]
   for i in range(nb):
    chunk=blob[base+offsets[i]:base+offsets[i+1]]
    assert chunk[0] in (0,1)
    raw=c.lz_decode(chunk[1:],10) if chunk[0] else chunk[1:]
    assert len(raw)==min(w,total-i*w);decoded.append(raw)
   assert b''.join(decoded)==a;block_count+=1
  for w in (2,4,8):
   for xor in (False,True):
    full=len(a)//w*w;words=[a[i:i+w] for i in range(0,full,w)]
    expected=bytes(words[i][k]^(words[i-1][k] if xor and i else 0) for k in range(w) for i in range(len(words)))+a[full:]
    assert s.rearrange(a,w,xor)==expected
    assert s.rearrange(expected,w,xor,True)==a
   for packed in (False,True):
    d=s.dictionaries(a,w,packed);assert d['bytes']==d['header_B']+d['table_B']+d['indices_B']
  count+=1

p='experiments/shared_constant_block_001/baseline/tiny_cardinal/probe.elf';parts,tables,rest=s.extract(p)
b=Path(p).read_bytes();o=struct.unpack_from('<I',b,32)[0];es,n,si=struct.unpack_from('<HHH',b,46);ss=[struct.unpack_from('<IIIIIIIIII',b,o+i*es) for i in range(n)];names=b[ss[si][4]:ss[si][4]+ss[si][5]];ro=next(s for s in ss if names[s[0]:].split(b'\0',1)[0]==b'.rodata')
spans=[]
for l in subprocess.check_output(['arm-none-eabi-readelf','-sW',p],text=True).splitlines():
 x=l.split()
 if len(x)>=8 and x[7] in tables:spans.append((int(x[1],16)-ro[3],int(x[2])))
assert len(spans)==5 and sum(n for o,n in spans)==920
assert len(set(i for o,n in spans for i in range(o,o+n)))==920
assert all(o>=0 and o+n<=len(parts[0]) for o,n in spans)
directory=b''.join(struct.pack('<HH',o,n) for o,n in spans);assert len(directory)==20
num=b''.join(tables.values());out=bytearray(1642);mask=set();pos=0
for i in range(0,len(directory),4):
 o,n=struct.unpack_from('<HH',directory,i);out[o:o+n]=num[pos:pos+n];pos+=n;mask.update(range(o,o+n))
j=iter(rest)
for i in range(len(out)):
 if i not in mask:out[i]=next(j)
assert bytes(out)==b''.join(parts)

# Build independent exact coefficient layouts and decode serialized headers.
coeff=tables['config_P']+tables['config_V'];words=[coeff[i:i+8] for i in range(0,len(coeff),8)]
high=list(dict.fromkeys(w[7] for w in words));bits=max(1,(len(high)-1).bit_length())
top=struct.pack('<HB',len(words),len(high))+bytes(high)+b''.join(w[:7] for w in words)+c.pack_bits([(high.index(w[7]),bits) for w in words])
n,k=struct.unpack_from('<HB',top);palette=top[3:3+k];it=c.read_bits(top[3+k+7*n:]);decoded=b''.join(top[3+k+7*i:3+k+7*i+7]+bytes([palette[c.get(it,max(1,(k-1).bit_length()))]]) for i in range(n));assert decoded==coeff
ints=[int.from_bytes(w,'little') for w in words];exps=[(x>>52)&2047 for x in ints];low=min(exps);width=max(1,(max(exps)-low).bit_length())
packed=struct.pack('<HHB',len(words),low,width)+c.pack_bits([(((x>>63)<<(52+width))|((((x>>52)&2047)-low)<<52)|(x&((1<<52)-1)),53+width) for x in ints])
n,low,width=struct.unpack_from('<HHB',packed);it=c.read_bits(packed[5:]);out=[]
for _ in range(n):
 x=c.get(it,53+width);mantissa=x&((1<<52)-1);exponent=((x>>52)&((1<<width)-1))+low;sign=x>>(52+width)
 out.append((mantissa|(exponent<<52)|(sign<<63)).to_bytes(8,'little'))
assert b''.join(out)==coeff
values=struct.unpack('<'+'d'*len(words),coeff);rounded=struct.unpack('<'+'f'*len(words),struct.pack('<'+'f'*len(words),*values))
report=json.loads(Path(sys.argv[1]).read_text())
stream=c.lz_encode(b''.join(parts),11);position=2;decoded=bytearray();distances=[];lengths=[]
while len(decoded)<1642:
 flags=stream[position];position+=1
 for bit in range(8):
  if len(decoded)==1642:break
  if (flags>>bit)&1:
   token=int.from_bytes(stream[position:position+2],'little');position+=2;distance=token//32+1;length=token%32+3
   assert distance<=len(decoded);distances.append(distance);lengths.append(length)
   for _ in range(length):decoded.append(decoded[-distance])
  else:decoded.append(stream[position]);position+=1
assert bytes(decoded)==b''.join(parts) and position==len(stream)
assert report['whole_lzss_11_access']=={'matches':len(distances),'maximum_backward_distance':max(distances),'maximum_match_length':max(lengths)}
cf=report['coefficient_formats'];assert cf['top_byte_dictionary_B']==len(top) and cf['exponent_range_packed_B']==len(packed)
assert cf['float32_max_absolute_coefficient_error']==max(abs(a-b) for a,b in zip(values,rounded))
assert cf['float32_max_relative_coefficient_error']==max(abs((a-b)/a) for a,b in zip(values,rounded) if a)
files=['experiments/constant_layout_study_001/codecs.py','experiments/constant_layout_study_001/study.py',sys.argv[1]]
print(json.dumps({'status':'pass','codec_layout_cases':count,'block_cases':block_count,'partition_reconstruction':'exact','coefficient_reconstruction':'exact','float32_error_reproduction':'exact','source_sha256':{f:hashlib.sha256(Path(f).read_bytes()).hexdigest() for f in files}},indent=2))
