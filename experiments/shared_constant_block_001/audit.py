"""Offline whole-linked-constant envelope; not executable compressed-literal code."""
from pathlib import Path
import struct,subprocess,json,argparse
from experiments.constant_codebook_001.codec import encode,decode

def run(elf,out):
 b=Path(elf).read_bytes();off=struct.unpack_from('<I',b,32)[0];es,n,si=struct.unpack_from('<HHH',b,46)
 sections=[struct.unpack_from('<IIIIIIIIII',b,off+i*es) for i in range(n)];names=b[sections[si][4]:sections[si][4]+sections[si][5]]
 named={names[s[0]:].split(b'\0',1)[0].decode():(i,s) for i,s in enumerate(sections)}
 ti,t=named['.text'];_,r=named['.rodata'];segments=[b[r[4]:r[4]+r[5]]];marks=[]
 for line in subprocess.check_output(['arm-none-eabi-readelf','-sW',elf],text=True).splitlines():
  x=line.split()
  if len(x)>=8 and x[6]==str(ti) and x[7] in ('$d','$t'):marks.append((int(x[1],16),x[7]))
 marks.sort()
 for i,(a,k) in enumerate(marks):
  if k=='$d':
   end=marks[i+1][0] if i+1<len(marks) else t[3]+t[5];segments.append(b[t[4]+a-t[3]:t[4]+end-t[3]])
 raw=b''.join(segments);padding=(-len(raw))%8;padded=raw+bytes(padding)
 # Reuse bit-preserving binary64 packer; assert this host preserves every chunk.
 vals=struct.unpack('<'+'d'*(len(padded)//8),padded);assert b''.join(struct.pack('<d',v) for v in vals)==padded
 results={}
 for mode in ['raw','plane']:
  blob=encode(vals,mode);assert decode(blob,mode)==padded
  results[mode]={'blob_bytes':len(blob),'offset_length_directory_B':4*len(segments),'payload_plus_directory_B':len(blob)+4*len(segments),'rules':blob[0]}
 result={'source_elf':elf,'rodata_bytes':len(segments[0]),'literal_data_bytes':sum(map(len,segments[1:])),'total_raw_bytes':len(raw),'segments':len(segments),'padding_bytes':padding,'encodings':results,'scope':'offline compression only;4B directory provides uint16 decoded offset and length per segment;original addresses,decoder,access rewriting and scratch excluded. Literal pools include addresses and padding.'}
 Path(out).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--elf',required=True);p.add_argument('--out',required=True);a=p.parse_args();run(a.elf,a.out)
