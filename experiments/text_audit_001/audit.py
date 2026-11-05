"""Linked M23 .text census and inline-aware diagnostic attribution.
The -g build must preserve allocated sections byte-for-byte before attribution.
Every .text halfword is counted once; aliases cannot inflate totals.
"""
from pathlib import Path
import argparse,subprocess,json,hashlib,collections,re

def call(args,**kw):return subprocess.check_output(args,text=True,**kw)
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def sections(elf):
 result={}
 for line in call(['arm-none-eabi-size','-A',str(elf)]).splitlines():
  a=line.split()
  if len(a)==3 and a[0].startswith('.') and a[1].isdigit() and a[2].isdigit():result[a[0]]=dict(bytes=int(a[1]),address=int(a[2]))
 return result

def run(measurement,out):
 measurement=Path(measurement).resolve();out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
 record=json.loads(measurement.read_text())['results'][0];elf=Path(record['command'][-1]);debug=out/'debug.elf'
 cmd=record['command'].copy();cmd.insert(1,'-g');cmd[-1]=str(debug);cmd=[('-Wl,--gc-sections,-Map='+str(out/'debug.map')) if x.startswith('-Wl,--gc-sections,-Map=') else x for x in cmd]
 subprocess.run(cmd,check=True)
 origsec,dbgsec=sections(elf),sections(debug);compared={}
 for name,s in origsec.items():
  if not 0x10000000<=s['address']<0x10020000 or not s['bytes']:continue
  if dbgsec.get(name)!=s:raise ValueError('allocated section layout changed '+name)
  if name=='.bss':compared[name]=dict(layout_identical=True);continue
  paths=[]
  for tag,source in [('original',elf),('debug',debug)]:
   p=out/(tag+name+'.bin');subprocess.run(['arm-none-eabi-objcopy','-O','binary','--only-section='+name,str(source),str(p)],check=True);paths.append(p)
  if paths[0].read_bytes()!=paths[1].read_bytes():raise ValueError('allocated bytes changed '+name)
  compared[name]=dict(bytes=s['bytes'],sha256=digest(paths[0]),identical=True)
 text=origsec['.text'];start=text['address'];stop=start+text['bytes'];assert text['bytes']%2==0
 symbols=collections.defaultdict(list)
 for line in call(['arm-none-eabi-nm','-S','--size-sort',str(elf)]).splitlines():
  a=line.split()
  if len(a)==4 and a[2] in ('t','T') and int(a[1],16)>0:
   addr,size=int(a[0],16),int(a[1],16)
   if start<=addr<stop:symbols[(addr,size)].append(a[3])
 ranges=[dict(address=a,bytes=n,names=names)for (a,n),names in symbols.items()]
 # Conflicting overlapping extents are reported rather than silently summed.
 ownership=collections.Counter();overlaps=[]
 for addr in range(start,stop,2):
  owners=[i for i,s in enumerate(ranges)if s['address']<=addr<s['address']+s['bytes']]
  if len(owners)>1:overlaps.append(hex(addr))
  ownership[owners[0] if owners else -1]+=2
 for i,s in enumerate(ranges):s['counted_text_B']=ownership[i];s['text_percent']=100*ownership[i]/text['bytes']
 ranges.sort(key=lambda s:s['counted_text_B'],reverse=True)
 addresses=list(range(start,stop,2))
 p=subprocess.run(['arm-none-eabi-addr2line','-a','-f','-i','-e',str(debug)],input=''.join(hex(a)+'\n'for a in addresses),capture_output=True,text=True,check=True)
 (out/'inline_addresses.txt').write_text(p.stdout)
 frames={};addr=None;lines=[]
 def flush():
  if addr is not None:frames[addr]=[dict(function=lines[i],location=lines[i+1])for i in range(0,len(lines)-1,2)]
 for line in p.stdout.splitlines():
  if re.fullmatch('0x[0-9a-fA-F]+',line):flush();addr=int(line,16);lines=[]
  else:lines.append(line)
 flush();assert len(frames)==len(addresses)
 leaf=collections.Counter();paths=collections.Counter()
 for addr in addresses:
  stack=frames[addr];names=tuple(f['function']for f in stack)or('??',)
  leaf[names[0]]+=2;paths[names]+=2
 callees=collections.Counter()
 dis=call(['arm-none-eabi-objdump','-d',str(elf)]);(out/'disassembly.txt').write_text(dis)
 for line in dis.splitlines():
  m=re.search(r'\bblx?\s+[0-9a-f]+\s+<([^>]+)>',line)
  if m:callees[m[1]]+=1
 result=dict(schema='linked_text_census_v1',source_measurement=str(measurement),source_measurement_sha256=digest(measurement),elf=str(elf),elf_sha256=digest(elf),debug_command=cmd,debug_elf_sha256=digest(debug),allocated_sections=origsec,debug_code_identity=compared,text_B=text['bytes'],symbols=ranges,symbol_unowned_B=ownership[-1],overlapping_symbol_halfwords=overlaps,inline_leaf_bytes=dict(leaf.most_common()),inline_paths=[dict(frames=list(k),bytes=v)for k,v in paths.most_common()],static_call_sites=dict(callees.most_common()),limits=['Symbol extents include embedded literal pools/padding, not only instructions.','DWARF inline leaf attribution is compiler metadata, not a unique causal source-code cost.','Do not add physical-symbol and inline-attribution tables: they partition the same bytes.','Static call-site counts are not runtime call counts or CPU profiles.','Removing a function does not necessarily save its reported bytes; relinking changes inlining and retained helpers.'])
 assert sum(leaf.values())==text['bytes'];assert sum(s['counted_text_B']for s in ranges)+ownership[-1]==text['bytes']
 (out/'census.json').write_text(json.dumps(result,indent=2)+'\n')
 print('text',text['bytes'],'unowned',ownership[-1],'overlaps',len(overlaps));print('leaf',leaf.most_common(25));print('calls',callees.most_common(12))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--measurement',required=True);p.add_argument('--out',required=True);a=p.parse_args();run(a.measurement,a.out)
