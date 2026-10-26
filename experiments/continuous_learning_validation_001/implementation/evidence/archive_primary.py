#!/usr/bin/env python3
"""Deterministic lossless primary transport; no generator/learner/scorer calls.
Existing byte-identical parts are reused. Short writes are retried; all new
files are fsynced and read back. Every archive member is compared with its
immutable original before index publication. No extracted copy is retained.
"""
import argparse,hashlib,json,lzma,os,pathlib,re,stat,tarfile,time,traceback
P=pathlib.Path
PART_BYTES=4*1024*1024
ARCHIVE_LIMIT=140*1024*1024
PRIMARY_REL=P('experiments/continuous_learning_validation_001/implementation/primary')

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def syncdir(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)

def write_checked(path,data):
    expected=hashlib.sha256(data).hexdigest()
    with path.open('xb',buffering=0) as f:
        remaining=memoryview(data)
        while remaining:
            block=remaining[:1024*1024];n=f.write(block)
            if type(n) is not int or not 0<n<=len(block):raise OSError('Invalid/zero write: '+str(path))
            remaining=remaining[n:]
        f.flush();os.fsync(f.fileno())
    if path.stat().st_size!=len(data) or sha(path)!=expected:raise OSError('Readback mismatch: '+str(path))
    return expected

def publish(path,data):
    if path.exists():raise FileExistsError('Refusing existing artifact: '+str(path))
    temporary=path.with_name(path.name+'.pending')
    expected=write_checked(temporary,data)
    if path.exists():raise FileExistsError('Target appeared: '+str(path))
    temporary.rename(path);syncdir(path.parent)
    if path.stat().st_size!=len(data) or sha(path)!=expected:raise OSError('Published readback mismatch: '+str(path))

def inventory(root,primary):
    files=[];members=[]
    for path in sorted(primary.rglob('*')):
        if path.is_symlink():raise RuntimeError('Refusing primary symlink: '+str(path))
        if not path.is_file():continue
        st=path.stat();size=st.st_size
        if not stat.S_ISREG(st.st_mode):raise RuntimeError('Nonregular primary file: '+str(path))
        h=hashlib.sha256();g=hashlib.sha1(b'blob '+str(size).encode()+b'\0');count=0
        with path.open('rb') as f:
            for block in iter(lambda:f.read(1024*1024),b''):h.update(block);g.update(block);count+=len(block)
        if count!=size or path.stat().st_size!=size:raise RuntimeError('Original changed: '+str(path))
        files.append(path)
        members.append({'path':path.relative_to(root).as_posix(),'bytes':size,'sha256':h.hexdigest(),
                        'git_blob_sha1':g.hexdigest(),'mode':'100755' if st.st_mode&0o111 else '100644'})
    return files,members

class PartsWriter:
    def __init__(self,root,out,started,max_new):
        self.root=root;self.out=out;self.started=started;self.max_new=max_new
        self.buffer=bytearray();self.parts=[];self.repairs=[];self.total=0;self.new=0;self.reused=0;self.h=hashlib.sha256()
    def writable(self):return True
    def flush(self):pass
    def write(self,data):
        data=memoryview(data);size=len(data)
        if self.total+size>ARCHIVE_LIMIT:raise RuntimeError('Transport reservation exceeded; originals untouched')
        while data:
            count=min(len(data),PART_BYTES-len(self.buffer));block=data[:count]
            self.buffer.extend(block);self.h.update(block);self.total+=count;data=data[count:]
            if len(self.buffer)==PART_BYTES:self.finish_part()
        return size
    def finish_part(self):
        if not self.buffer:return
        number=len(self.parts);path=self.out/('primary.tar.xz.part-'+str(number).zfill(3))
        expected=hashlib.sha256(self.buffer).hexdigest()
        reused=path.is_file() and path.stat().st_size==len(self.buffer) and path.read_bytes()==self.buffer
        if reused:self.reused+=1
        else:
            if self.new+len(self.buffer)>self.max_new:raise RuntimeError('New transport-byte allowance exceeded before write')
            temporary=path.with_name(path.name+'.repair-pending');write_checked(temporary,self.buffer);self.new+=len(self.buffer)
            preserved=None
            if path.exists():
                saved=self.out/('packaging_attempt001_broken_part-'+str(number).zfill(3)+'.bin')
                if saved.exists():raise FileExistsError('Refusing preserved failed part overwrite: '+str(saved))
                preserved={'path':saved.relative_to(self.root).as_posix(),'bytes':path.stat().st_size,'sha256':sha(path)}
                path.rename(saved)
            temporary.rename(path);syncdir(self.out)
            self.repairs.append({'part_number':number,'preserved_previous':preserved,'replacement_bytes':len(self.buffer),'replacement_sha256':expected})
        if path.stat().st_size!=len(self.buffer) or sha(path)!=expected:raise OSError('Part readback mismatch: '+str(path))
        self.parts.append({'path':path.relative_to(self.root).as_posix(),'bytes':len(self.buffer),'sha256':expected})
        self.buffer.clear()
        print(json.dumps({'event':'archive_part_verified','part_number':number,'reused':reused,'compressed_bytes':self.total,'new_part_bytes':self.new,'wall_s':time.monotonic()-self.started}),flush=True)

class PartsReader:
    def __init__(self,root,parts):self.root=root;self.parts=iter(parts);self.stream=None
    def read(self,size):
        if size<0:raise ValueError('Unbounded archive read forbidden')
        output=bytearray()
        while len(output)<size:
            if self.stream is None:
                part=next(self.parts,None)
                if part is None:break
                self.stream=(self.root/part['path']).open('rb')
            block=self.stream.read(size-len(output))
            if block:output.extend(block)
            else:self.stream.close();self.stream=None
        return bytes(output)
    def close(self):
        if self.stream:self.stream.close();self.stream=None

def verify(root,writer,members):
    actual=hashlib.sha256();total=0
    for part in writer.parts:
        h=hashlib.sha256();count=0
        with (root/part['path']).open('rb') as f:
            for b in iter(lambda:f.read(1024*1024),b''):h.update(b);actual.update(b);count+=len(b)
        if count!=part['bytes'] or h.hexdigest()!=part['sha256']:raise RuntimeError('Part integrity mismatch: '+part['path'])
        total+=count
    if total!=writer.total or actual.hexdigest()!=writer.h.hexdigest():raise RuntimeError('Concatenated archive mismatch')
    expected={m['path']:m for m in members};verified=set();reader=PartsReader(root,writer.parts)
    try:
        with lzma.LZMAFile(reader,'rb') as decoded:
            with tarfile.open(fileobj=decoded,mode='r|') as archive:
                for item in archive:
                    if not item.isfile() or item.name not in expected or item.name in verified:raise RuntimeError('Unexpected/duplicate member: '+item.name)
                    member=expected[item.name]
                    if item.size!=member['bytes'] or item.mode!=int(member['mode'][-3:],8):raise RuntimeError('Member size/mode mismatch: '+item.name)
                    h=hashlib.sha256();count=0
                    with archive.extractfile(item) as packed,(root/item.name).open('rb') as original:
                        for b in iter(lambda:packed.read(1024*1024),b''):
                            if original.read(len(b))!=b:raise RuntimeError('Original/archive bytes differ: '+item.name)
                            h.update(b);count+=len(b)
                        if original.read(1):raise RuntimeError('Original has extra bytes: '+item.name)
                    if count!=member['bytes'] or h.hexdigest()!=member['sha256']:raise RuntimeError('Member SHA256 mismatch: '+item.name)
                    verified.add(item.name)
            # Tar EOF can precede XZ EOF: drain and check the XZ footer/CRC64.
            for unused in iter(lambda:decoded.read(1024*1024),b''):pass
    finally:reader.close()
    if len(verified)!=len(members):raise RuntimeError('Missing original members')
    return len(verified)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=P);parser.add_argument('--max-new-bytes',type=int,default=ARCHIVE_LIMIT);args=parser.parse_args()
    root=args.root
    if root is None:
        root=next((p for p in [P(__file__).resolve().parent/'mumble',*P(__file__).resolve().parents] if (p/'plans/continuous_learning_validation_001.json').is_file()),None)
    if root is None:raise RuntimeError('Pass --root pointing to the mumble repository')
    root=root.resolve();primary=root/PRIMARY_REL;out=root/PRIMARY_REL.parent/'evidence';out.mkdir(exist_ok=True)
    if (out/'index.json').exists():raise FileExistsError('Verified index exists; refusing packaging rerun')
    started=time.monotonic();source=P(__file__).read_bytes();copy=out/'archive_primary.py'
    if copy.resolve()!=P(__file__).resolve():
        if copy.exists():
            if copy.read_bytes()!=source:raise FileExistsError('Different reusable archiver source exists')
        else:publish(copy,source)
    try:
        files,members=inventory(root,primary);writer=PartsWriter(root,out,started,args.max_new_bytes)
        with lzma.LZMAFile(writer,'w',format=lzma.FORMAT_XZ,check=lzma.CHECK_CRC64,preset=6) as compressed:
            with tarfile.open(fileobj=compressed,mode='w|',format=tarfile.PAX_FORMAT) as archive:
                for path,member in zip(files,members):
                    info=tarfile.TarInfo(member['path']);info.size=member['bytes'];info.mode=int(member['mode'][-3:],8)
                    info.uid=0;info.gid=0;info.uname='';info.gname='';info.mtime=0
                    with path.open('rb') as stream:archive.addfile(info,stream)
        writer.finish_part();listed={v['path'] for v in writer.parts}
        stale=[p.name for p in out.iterdir() if re.fullmatch(r'primary\.tar\.xz\.part-\d{3}',p.name) and p.relative_to(root).as_posix() not in listed]
        if stale:raise RuntimeError('Unindexed old archive parts remain: '+','.join(stale))
        verified=verify(root,writer,members)
        result={'schema':'mumble_continuous_lossless_evidence_index_v1','status':'verified_lossless','primary_directory':PRIMARY_REL.as_posix(),
                'archive_format':'POSIX tar in XZ/CRC64, ordered concatenated4MiB pieces; deterministic metadata','archive_sha256':writer.h.hexdigest(),'archive_bytes':writer.total,
                'parts':writer.parts,'members':members,'member_count':len(members),'original_bytes':sum(m['bytes'] for m in members),'roundtrip_members_verified':verified,
                'member_bytes_compared_with_originals':True,'all_part_readbacks_verified':True,'XZ_footer_CRC64_verified':True,'reused_original_parts':writer.reused,
                'new_part_bytes_written':writer.new,'repair_records':writer.repairs,'wall_s':time.monotonic()-started,'archiver_path':copy.relative_to(root).as_posix(),
                'archiver_sha256':hashlib.sha256(source).hexdigest(),'prior_failed_attempt':(out/'packaging_attempt001_failure.json').relative_to(root).as_posix(),
                'scope':'Transport/preservation only; numerical/source/noise/learner/scorer calls0; primary writes0.',
                'restoration':'Concatenate parts in listed order, verify archive_sha256, then extract from repository root. Exact original bytes/hashes/modes remain in this archive.'}
        publish(out/'index.json',(json.dumps(result,indent=2)+'\n').encode())
        print(json.dumps({k:result[k] for k in ['status','archive_bytes','archive_sha256','member_count','original_bytes','roundtrip_members_verified','reused_original_parts','new_part_bytes_written','wall_s']},indent=2),flush=True)
    except BaseException as exc:
        failure={'schema':'mumble_continuous_packaging_failure_v1','attempt':2,'status':'failed_preserved','error_type':type(exc).__name__,'error':str(exc),'traceback':traceback.format_exc(),'wall_s':time.monotonic()-started,'scope':'Transport only; primary writes0; numerical/generator/learner/scorer calls0.'}
        path=out/'packaging_attempt002_failure.json'
        if not path.exists():publish(path,(json.dumps(failure,indent=2)+'\n').encode())
        raise

if __name__=='__main__':main()
