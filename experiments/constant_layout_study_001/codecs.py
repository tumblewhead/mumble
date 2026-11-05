"""Small reference codecs for size studies; no firmware readiness claim."""
import collections,struct,heapq

def pack_bits(items):
 out=bytearray();v=0;n=0
 for x,w in items:
  v=(v<<w)|x;n+=w
  while n>=8:n-=8;out.append((v>>n)&255)
 if n:out.append((v<<(8-n))&255)
 return bytes(out)

def read_bits(data):
 for x in data:
  for k in range(7,-1,-1):yield (x>>k)&1

def get(bits,n):
 v=0
 for _ in range(n):v=(v<<1)|next(bits)
 return v

def lz_encode(data,ob=11):
 lb=16-ob;limit=(1<<lb)+2;positions=collections.defaultdict(list);out=bytearray(struct.pack('<H',len(data)));i=0
 while i<len(data):
  flagpos=len(out);out.append(0)
  for bit in range(8):
   if i==len(data):break
   best=0;dist=0
   if i+3<=len(data):
    for j in reversed(positions[data[i:i+3]]):
     if i-j>(1<<ob):break
     n=3
     while n<limit and i+n<len(data) and data[j+n]==data[i+n]:n+=1
     if n>best:best=n;dist=i-j
     if best==limit:break
   count=best if best>=3 else 1
   if count>1:out[flagpos]|=1<<bit;out+=struct.pack('<H',((dist-1)<<lb)|(count-3))
   else:out.append(data[i])
   for j in range(i,i+count):positions[data[j:j+3]].append(j)
   i+=count
 return bytes(out)

def lz_decode(blob,ob=11):
 total=struct.unpack_from('<H',blob)[0];lb=16-ob;i=2;out=bytearray()
 while len(out)<total:
  flags=blob[i];i+=1
  for bit in range(8):
   if len(out)==total:break
   if flags&(1<<bit):
    token=struct.unpack_from('<H',blob,i)[0];i+=2;dist=(token>>lb)+1;n=(token&((1<<lb)-1))+3
    for _ in range(n):out.append(out[-dist])
   else:out.append(blob[i]);i+=1
 assert i==len(blob);return bytes(out)

def bpe9_encode(data):
 a=list(data);rules=[];best=(len(data)+6,None)
 for _ in range(255):
  counts=collections.Counter(zip(a,a[1:]))
  if not counts:break
  pair,count=counts.most_common(1)[0]
  if count<3:break
  token=256+len(rules);out=[];i=0
  while i<len(a):
   if tuple(a[i:i+2])==pair:out.append(token);i+=2
   else:out.append(a[i]);i+=1
  rules.append(pair);a=out
  blob=bytes([len(rules)])+struct.pack('<HH',len(data),len(a))+pack_bits([(v,9) for pair in rules for v in pair]+[(v,9) for v in a])
  if len(blob)<best[0]:best=(len(blob),blob)
 # Explicit raw fallback is part of the format, not an uncharged selector.
 return b'\0'+struct.pack('<HH',len(data),len(data))+data if best[1] is None else best[1]

def bpe9_decode(blob):
 nr=blob[0];n,t=struct.unpack_from('<HH',blob,1)
 if not nr:assert len(blob)==5+n;return blob[5:]
 bits=read_bits(blob[5:]);rules=[(get(bits,9),get(bits,9)) for _ in range(nr)];out=bytearray()
 for _ in range(t):
  stack=[get(bits,9)]
  while stack:
   x=stack.pop()
   if x<256:out.append(x)
   else:stack.extend(reversed(rules[x-256]))
 assert len(out)==n;return bytes(out)

def huff_encode(data):
 counts=collections.Counter(data);heap=[(c,i,[i]) for i,c in counts.items()];heapq.heapify(heap);lengths={x:0 for x in counts};serial=256
 while len(heap)>1:
  c,_,a=heapq.heappop(heap);d,_,b=heapq.heappop(heap)
  for x in a+b:lengths[x]+=1
  heapq.heappush(heap,(c+d,serial,a+b));serial+=1
 if len(lengths)==1:lengths[next(iter(lengths))]=1
 code=0;old=0;codes={}
 for x in sorted(lengths,key=lambda x:(lengths[x],x)):
  w=lengths[x];code<<=w-old;codes[x]=(code,w);code+=1;old=w
 dense=max(lengths.values(),default=0)<=15 and 128<=2*len(lengths)+2
 header=pack_bits([(lengths.get(x,0),4) for x in range(256)]) if dense else struct.pack('<H',len(lengths))+bytes(v for x,w in sorted(lengths.items()) for v in (x,w))
 return bytes([int(dense)])+struct.pack('<H',len(data))+header+pack_bits([codes[x] for x in data])

def huff_decode(blob):
 dense=blob[0];n=struct.unpack_from('<H',blob,1)[0];i=3
 if dense:
  bits=read_bits(blob[i:i+128]);lengths={x:w for x in range(256) if (w:=get(bits,4))};i+=128
 else:
  k=struct.unpack_from('<H',blob,i)[0];i+=2;lengths=dict(zip(blob[i:i+2*k:2],blob[i+1:i+2*k:2]));i+=2*k
 code=old=0;codes={}
 for x in sorted(lengths,key=lambda x:(lengths[x],x)):
  w=lengths[x];code<<=w-old;codes[(code,w)]=x;code+=1;old=w
 bits=read_bits(blob[i:]);out=bytearray()
 for _ in range(n):
  c=w=0
  while (c,w) not in codes:c=(c<<1)|next(bits);w+=1
  out.append(codes[(c,w)])
 return bytes(out)

def block_lz_encode(data,block=128):
 chunks=[]
 for i in range(0,len(data),block):
  raw=data[i:i+block];a=lz_encode(raw,10);chunks.append(b'\1'+a if len(a)<len(raw) else b'\0'+raw)
 header=struct.pack('<HH',len(data),block);offset=0
 for a in chunks:header+=struct.pack('<H',offset);offset+=len(a)
 return header+b''.join(chunks)

def block_lz_decode(blob):
 n,block=struct.unpack_from('<HH',blob);count=(n+block-1)//block;base=4+2*count
 offsets=list(struct.unpack_from('<'+'H'*count,blob,4))+[len(blob)-base];out=bytearray()
 for i in range(count):
  a=blob[base+offsets[i]:base+offsets[i+1]];out+=lz_decode(a[1:],10) if a[0] else a[1:]
 assert len(out)==n;return bytes(out)
