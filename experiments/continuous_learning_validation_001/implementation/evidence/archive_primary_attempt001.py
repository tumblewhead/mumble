import hashlib,io,json,lzma,pathlib,tarfile,time

ROOT=pathlib.Path('/workspace/scratch/df37870c5570/mumble')
BASE=ROOT/'experiments/continuous_learning_validation_001/implementation'
PRIMARY=BASE/'primary'
OUT=BASE/'evidence'
OUT.mkdir(exist_ok=False)
PART_BYTES=4*1024*1024
started=time.monotonic()
files=sorted(p for p in PRIMARY.rglob('*') if p.is_file())
members=[]
for path in files:
    size=path.stat().st_size;h=hashlib.sha256();g=hashlib.sha1(b'blob '+str(size).encode()+b'\0')
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block);g.update(block)
    members.append({'path':path.relative_to(ROOT).as_posix(),'bytes':size,'sha256':h.hexdigest(),
                    'git_blob_sha1':g.hexdigest(),'mode':'100755' if path.stat().st_mode&0o111 else '100644'})

class PartsWriter:
    def __init__(self):self.stream=None;self.part_h=None;self.part_bytes=0;self.parts=[];self.total=0;self.h=hashlib.sha256()
    def writable(self):return True
    def write(self,data):
        data=memoryview(data);size=len(data)
        while data:
            if self.stream is None:
                self.path=OUT/('primary.tar.xz.part-'+str(len(self.parts)).zfill(3))
                self.stream=self.path.open('xb');self.part_h=hashlib.sha256();self.part_bytes=0
            count=min(len(data),PART_BYTES-self.part_bytes);block=data[:count]
            if self.total+count>140*1024*1024:raise RuntimeError('Transport archive reservation exceeded; original evidence untouched')
            self.stream.write(block);self.part_h.update(block);self.h.update(block)
            self.part_bytes+=count;self.total+=count;data=data[count:]
            if self.part_bytes==PART_BYTES:self.finish_part()
        return size
    def flush(self):
        if self.stream:self.stream.flush()
    def finish_part(self):
        if self.stream:
            self.stream.close();self.stream=None
            self.parts.append({'path':self.path.relative_to(ROOT).as_posix(),'bytes':self.part_bytes,'sha256':self.part_h.hexdigest()})
            print(json.dumps({'event':'archive_part','parts':len(self.parts),'compressed_bytes':self.total,'wall_s':time.monotonic()-started}),flush=True)

writer=PartsWriter()
with lzma.LZMAFile(writer,'w',format=lzma.FORMAT_XZ,check=lzma.CHECK_CRC64,preset=6) as compressed:
    with tarfile.open(fileobj=compressed,mode='w|',format=tarfile.PAX_FORMAT) as archive:
        for path,member in zip(files,members):
            info=tarfile.TarInfo(member['path']);info.size=member['bytes'];info.mode=int(member['mode'][-3:],8)
            info.uid=0;info.gid=0;info.uname='';info.gname='';info.mtime=0
            with path.open('rb') as stream:archive.addfile(info,stream)
writer.finish_part()

class PartsReader:
    def __init__(self,parts):self.parts=iter(parts);self.stream=None
    def read(self,size):
        if size<0:raise ValueError('Unbounded archive read forbidden')
        output=bytearray()
        while len(output)<size:
            if self.stream is None:
                part=next(self.parts,None)
                if part is None:break
                self.stream=(ROOT/part['path']).open('rb')
            block=self.stream.read(size-len(output))
            if block:output.extend(block)
            else:self.stream.close();self.stream=None
        return bytes(output)

expected={m['path']:m for m in members};verified=[]
with tarfile.open(fileobj=PartsReader(writer.parts),mode='r|xz') as archive:
    for item in archive:
        assert item.isfile() and item.name in expected,item.name
        h=hashlib.sha256();count=0
        with archive.extractfile(item) as stream:
            for block in iter(lambda:stream.read(1024*1024),b''):h.update(block);count+=len(block)
        member=expected[item.name]
        assert count==member['bytes'] and h.hexdigest()==member['sha256'],item.name
        verified.append(item.name)
assert len(verified)==len(members) and len(set(verified))==len(members)
result={'schema':'mumble_continuous_lossless_evidence_index_v1','status':'verified_lossless',
        'archive_format':'POSIX tar in XZ/CRC64, ordered concatenated4MiB pieces; deterministic metadata',
        'archive_sha256':writer.h.hexdigest(),'archive_bytes':writer.total,'parts':writer.parts,
        'members':members,'member_count':len(members),'original_bytes':sum(m['bytes'] for m in members),
        'roundtrip_members_verified':len(verified),'wall_s':time.monotonic()-started,
        'scope':'Transport/preservation only after the single completed primary and its single scoring helper; no numerical results recomputed, source/noise/learner/scorer calls0.',
        'restoration':'Concatenate parts in listed order, verify archive_sha256, then extract from repository root. Existing small text receipts are also published directly; exact original bytes/hashes remain in this archive.'}
(OUT/'index.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:result[k] for k in ['status','archive_bytes','member_count','original_bytes','roundtrip_members_verified','wall_s']},indent=2),flush=True)
