from pathlib import Path
import argparse,collections,hashlib,json,math,struct,subprocess,zlib,bz2,lzma,random
from .codecs import lz_encode,lz_decode,bpe9_encode,bpe9_decode,huff_encode,huff_decode,pack_bits,read_bits,get,block_lz_encode,block_lz_decode

def extract(path):
 b=Path(path).read_bytes();off=struct.unpack_from('<I',b,32)[0];es,n,si=struct.unpack_from('<HHH',b,46)
 sections=[struct.unpack_from('<IIIIIIIIII',b,off+i*es) for i in range(n)];names=b[sections[si][4]:sections[si][4]+sections[si][5]]
 named={names[s[0]:].split(b'\0',1)[0].decode():(i,s) for i,s in enumerate(sections)}
 ti,t=named['.text'];_,r=named['.rodata'];segments=[b[r[4]:r[4]+r[5]]];marks=[];tables={};addresses=[]
 for line in subprocess.check_output(['arm-none-eabi-readelf','-sW',path],text=True).splitlines():
  x=line.split()
  if len(x)<8:continue
  if x[6]==str(ti) and x[7] in ('$d','$t'):marks.append((int(x[1],16),x[7]))
  if x[7] in ('config_mean','config_scale','config_center','config_P','config_V'):
   a=int(x[1],16)-r[3];size=int(x[2]);tables[x[7]]=segments[0][a:a+size];addresses.extend(range(a,a+size))
 marks.sort()
 for i,(a,k) in enumerate(marks):
  if k=='$d':
   end=marks[i+1][0] if i+1<len(marks) else t[3]+t[5];segments.append(b[t[4]+a-t[3]:t[4]+end-t[3]])
 occupied=set(addresses);residual=bytes(x for i,x in enumerate(segments[0]) if i not in occupied)+b''.join(segments[1:])
 return segments,tables,residual

def entropy(data):
 c=collections.Counter(data);return -sum(n*math.log2(n/len(data)) for n in c.values())/8 if data else 0

def rearrange(data,width,xor=False,inverse=False):
 n=len(data)//width;end=n*width;tail=data[end:];a=bytearray(data[:end])
 if inverse:
  a=bytearray(a[k*n+i] for i in range(n) for k in range(width))
  if xor:
   for i in range(width,end):a[i]^=a[i-width]
 else:
  if xor:a=bytearray(v^(a[i-width] if i>=width else 0) for i,v in enumerate(a))
  a=bytearray(a[width*i+k] for k in range(width) for i in range(n))
 return bytes(a)+tail

def dictionaries(data,width,packed):
 pad=(-len(data))%width;a=data+bytes(pad);words=[a[i:i+width] for i in range(0,len(a),width)];unique=list(dict.fromkeys(words));bits=max(1,(len(unique)-1).bit_length()) if packed else (8 if len(unique)<=256 else 16)
 indices=[unique.index(x) for x in words];blob=struct.pack('<HHBB',len(data),len(unique),width,bits)+b''.join(unique)+pack_bits([(x,bits) for x in indices])
 n,u,w,bits2=struct.unpack_from('<HHBB',blob);table=[blob[6+i*w:6+(i+1)*w] for i in range(u)];it=read_bits(blob[6+u*w:]);decoded=b''.join(table[get(it,bits2)] for _ in words)[:n];assert decoded==data
 return {'bytes':len(blob),'unique_words':len(unique),'index_bits':bits,'table_B':width*len(unique),'indices_B':(len(words)*bits+7)//8,'header_B':6}

def codec_results(data):
 r={'raw':len(data)}
 for ob in (10,11,12):
  a=lz_encode(data,ob);assert lz_decode(a,ob)==data;r['lzss_'+str(ob)]=len(a)
 a=bpe9_encode(data);assert bpe9_decode(a)==data;r['bpe9']=len(a)
 a=huff_encode(data);assert huff_decode(a)==data;r['huffman']=len(a)
 co=zlib.compressobj(9,zlib.DEFLATED,-15);a=co.compress(data)+co.flush();assert zlib.decompress(a,-15)==data;r['deflate_raw']=len(a)+2 # explicit decoded length
 a=bz2.compress(data,9);assert bz2.decompress(a)==data;r['bzip2_container']=len(a)
 a=lzma.compress(data,format=lzma.FORMAT_ALONE,preset=9);assert lzma.decompress(a,format=lzma.FORMAT_ALONE)==data;r['lzma_alone']=len(a)
 return r

def run(elf,out):
 root=Path(out);root.mkdir(parents=True,exist_ok=False);segments,tables,residual=extract(elf);raw=b''.join(segments);numeric=b''.join(tables.values())
 rng=random.Random(773)
 cases=[b'',b'\0'*300,b'abc'*150,bytes(range(256)),bytes(rng.randrange(256) for _ in range(600))]
 for a in cases:
  codec_results(a)
  for block in (32,64,128,256):assert block_lz_decode(block_lz_encode(a,block))==a
  for w in (2,4,8):
   for xor in (False,True):assert rearrange(rearrange(a,w,xor),w,xor,True)==a
 corpus={'whole':raw,'numeric_tables':numeric,'remaining_data':residual,**tables}
 report={'source_elf':elf,'elf_sha256':hashlib.sha256(Path(elf).read_bytes()).hexdigest(),'total_B':len(raw),'rodata_B':len(segments[0]),'literal_pool_B':sum(map(len,segments[1:])),'segment_count':len(segments),'directory_B':4*len(segments),'whole_sha256':hashlib.sha256(raw).hexdigest(),'corpora':{},'whole_layouts':{},'partitioned_layouts':{}}
 for name,data in corpus.items():
  c=collections.Counter(data);report['corpora'][name]={'bytes':len(data),'distinct_bytes':len(c),'zero_bytes':c[0],'byte_entropy_bits':entropy(data)*8/len(data),'zero_order_ideal_B':entropy(data),'codecs':codec_results(data),'word_dictionary':{str(w)+('_packed' if packed else '_byte'):dictionaries(data,w,packed) for w in (2,4,8) for packed in (False,True)}}
 stream=lz_encode(raw,11);i=2;decoded=0;distances=[];lengths=[]
 while decoded<len(raw):
  flags=stream[i];i+=1
  for bit in range(8):
   if decoded==len(raw):break
   if flags&(1<<bit):
    v=struct.unpack_from('<H',stream,i)[0];i+=2;distances.append((v>>5)+1);lengths.append((v&31)+3);decoded+=lengths[-1]
   else:decoded+=1;i+=1
 report['whole_lzss_11_access']={'matches':len(distances),'maximum_backward_distance':max(distances),'maximum_match_length':max(lengths)}
 report['bounded_blocks']={}
 for block in (32,64,128,256):
  blob=block_lz_encode(raw,block);assert block_lz_decode(blob)==raw
  report['bounded_blocks'][str(block)]={'stream_with_block_directory_B':len(blob),'with_original_segment_directory_B':len(blob)+120,'maximum_decoded_block_B':block}
 # Exact coefficient top-byte dictionary and exponent-range packing layouts.
 coeff=tables['config_P']+tables['config_V'];words=[coeff[i:i+8] for i in range(0,len(coeff),8)];high=list(dict.fromkeys(x[7] for x in words));nb=max(1,(len(high)-1).bit_length())
 blob=struct.pack('<HB',len(words),len(high))+bytes(high)+b''.join(x[:7] for x in words)+pack_bits([(high.index(x[7]),nb) for x in words]);nn,nh=struct.unpack_from('<HB',blob);hh=blob[3:3+nh];low=blob[3+nh:3+nh+7*nn];it=read_bits(blob[3+nh+7*nn:]);decoded=b''.join(low[7*i:7*i+7]+bytes([hh[get(it,max(1,(nh-1).bit_length()))]]) for i in range(nn));assert decoded==coeff
 ints=[int.from_bytes(x,'little') for x in words];exps=[(x>>52)&2047 for x in ints];lo=min(exps);eb=max(1,(max(exps)-lo).bit_length())
 packed=struct.pack('<HHB',len(words),lo,eb)+pack_bits([((x&((1<<52)-1))|(((x>>52)&2047)-lo)<<52|((x>>63)<<(52+eb)),53+eb) for x in ints]);nn,emin,ew=struct.unpack_from('<HHB',packed);it=read_bits(packed[5:]);recovered=[]
 for _ in range(nn):
  v=get(it,53+ew);recovered.append(((v&((1<<52)-1))|(((v>>52)&((1<<ew)-1))+emin)<<52|(v>>(52+ew))<<63).to_bytes(8,'little'))
 assert b''.join(recovered)==coeff
 f32=b''.join(struct.pack('<f',struct.unpack('<d',x)[0]) for x in words);rounded=[struct.unpack_from('<f',f32,i*4)[0] for i in range(len(words))];values=[struct.unpack('<d',x)[0] for x in words]
 report['coefficient_formats']={'original_B':len(coeff),'top_byte_dictionary_B':len(blob),'top_byte_symbols':len(high),'exponent_range_packed_B':len(packed),'exponent_bits':eb,'float32_B':len(f32),'float32_max_absolute_coefficient_error':max(abs(x-y) for x,y in zip(values,rounded)),'float32_max_relative_coefficient_error':max(abs((x-y)/x) for x,y in zip(values,rounded) if x),'scope':'float32 is lossy and unqualified;coefficient error is not voltage or estimator error;format reconstruction tested for lossless alternatives'}
 report['numeric_byte_planes']=[{'byte':k,'distinct':len(set(numeric[k::8])),'ideal_B':entropy(numeric[k::8]),'zero_bytes':numeric[k::8].count(0)} for k in range(8)]
 report['coefficient_byte_planes']=[{'byte':k,'ideal_B':entropy((tables['config_P']+tables['config_V'])[k::8]),'distinct':len(set((tables['config_P']+tables['config_V'])[k::8]))} for k in range(8)]
 report['whole_layouts']['original']=codec_results(raw)
 for w in (2,4,8):
  for xor in (False,True):
   name=('xor_' if xor else '')+'plane'+str(w);data=rearrange(raw,w,xor);assert rearrange(data,w,xor,True)==raw
   report['whole_layouts'][name]=codec_results(data)
   parts=[rearrange(s,w,xor) for s in segments];assert [rearrange(s,w,xor,True) for s in parts]==segments
   report['whole_layouts']['per_segment_'+name]=codec_results(b''.join(parts))
 for w in (4,8):
  for xor in (False,True):
   n=rearrange(numeric,w,xor);r=rearrange(residual,4,False)
   report['partitioned_layouts'][('xor_' if xor else '')+'numeric_plane'+str(w)]={'numeric':codec_results(n),'remaining':codec_results(r),'extra_split_directory_B':20,'selectors_B':2,'note':'Additional20B stores5 numeric source spans;original120B segment directory still charged; inverse permutations fixed by format.'}
 (root/'result.json').write_text(json.dumps(report,indent=2)+'\n')
 print('whole layouts best stream bytes, before120B directory/1B transform selector:')
 for name,r in report['whole_layouts'].items():print(name,sorted(r.items(),key=lambda x:x[1])[:3])
 print('corpora:',[(k,v['bytes'],v['codecs']) for k,v in report['corpora'].items()])
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--elf',required=True);p.add_argument('--out',required=True);a=p.parse_args();run(a.elf,a.out)
