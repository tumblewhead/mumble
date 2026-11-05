import collections,struct

def encode(values,mode):
 raw=b''.join(struct.pack('<d',v) for v in values);n=len(values)
 if mode=='xorplane':
  raw=bytes(v^(raw[i-8] if i>=8 else 0) for i,v in enumerate(raw))
 if mode!='raw':raw=bytes(raw[8*i+k] for k in range(8) for i in range(n))
 a=list(raw);rules=[];length={i:1 for i in range(256)}
 for token in (i for i in range(256) if i not in set(raw)):
  counts=collections.Counter(zip(a,a[1:]));pairs=[p for p,c in counts.most_common() if c>4 and length[p[0]]+length[p[1]]<=255]
  if not pairs:break
  pair=pairs[0];out=[];i=0
  while i<len(a):
   if tuple(a[i:i+2])==pair:out.append(token);i+=2
   else:out.append(a[i]);i+=1
  if len(a)-len(out)<=4:break
  length[token]=length[pair[0]]+length[pair[1]];rules.append((token,*pair,length[token]));a=out
 return bytes([len(rules),n])+bytes(x for r in rules for x in r)+bytes(a)

def decode(blob,mode):
 nr,n=blob[:2];rules={blob[2+4*i]:blob[3+4*i:5+4*i] for i in range(nr)}
 def expand(x):return b''.join(expand(v) for v in rules[x]) if x in rules else bytes([x])
 raw=b''.join(expand(x) for x in blob[2+4*nr:]);assert len(raw)==8*n
 if mode!='raw':raw=bytes(raw[k*n+i] for i in range(n) for k in range(8))
 if mode=='xorplane':
  raw=bytearray(raw)
  for i in range(8,len(raw)):raw[i]^=raw[i-8]
 return bytes(raw)
