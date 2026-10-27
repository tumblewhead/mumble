#!/usr/bin/env python3
"""Reassemble absent gzip originals from verified byte chunks; never overwrite."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile


def require(condition, message):
    if not condition:raise ValueError(message)


def pairs(items):
    result={}
    for key,value in items:
        require(key not in result,"Duplicate JSON key")
        result[key]=value
    return result


def read_json(path):
    return json.loads(path.read_bytes(),object_pairs_hook=pairs,
        parse_constant=lambda x:(_ for _ in ()).throw(ValueError(x)))


def identity(path):
    digest,size=hashlib.sha256(),0
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,"rb") as source:
        require(stat.S_ISREG(os.fstat(source.fileno()).st_mode),"Expected regular file")
        while block:=source.read(1048576):digest.update(block);size+=len(block)
    return {"bytes":size,"sha256":digest.hexdigest()}


def safe(root,relative):
    name=Path(relative)
    require(not name.is_absolute() and ".." not in name.parts,"Unsafe transport path")
    path=root/name
    for ancestor in (path,*path.parents):
        if ancestor==root:break
        require(not ancestor.is_symlink(),"Symlink in transport path")
    require(path.resolve().is_relative_to(root),"Transport path escapes root")
    return path


def fsync_directory(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)


def concatenate(source_root,row,destination=None):
    whole,size=hashlib.sha256(),0
    for part in row["parts"]:
        digest,length=hashlib.sha256(),0
        require(type(part["bytes"]) is int and 0<part["bytes"]<=4000000,"Invalid chunk extent")
        with safe(source_root,part["path"]).open("rb") as source:
            while block:=source.read(1048576):
                length+=len(block);size+=len(block)
                require(length<=part["bytes"] and size<=row["original_identity"]["bytes"],"Chunk/whole extent exceeded")
                digest.update(block);whole.update(block)
                if destination is not None:destination.write(block)
        require({"bytes":length,"sha256":digest.hexdigest()}=={k:part[k] for k in ("bytes","sha256")},
                "Chunk bytes differ")
    actual={"bytes":size,"sha256":whole.hexdigest()}
    require(actual==row["original_identity"],"Concatenated original differs")
    return actual


def main():
    here=Path(__file__).resolve().parent;source_root=here.parents[2]
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,default=source_root)
    parser.add_argument("--verify-only",action="store_true")
    args=parser.parse_args();target_root=args.root.resolve()
    require(target_root.is_dir(),"Destination root must already exist")
    receipt=read_json(here/"receipt.json")
    require(receipt["status"]=="completed","Transport packaging did not complete")
    require(identity(Path(__file__).resolve())==receipt["restore_helper_identity"],"Bound restorer source differs")
    require(identity(here/"manifest.json")==receipt["manifest_identity"],"Transport manifest differs")
    manifest=read_json(here/"manifest.json")
    require(manifest["schema"]=="mumble_live_anchor_transport_manifest_v1" and manifest["chunk_max_bytes"]==4000000,
            "Transport manifest policy differs")
    rows=manifest["roles"]
    expected={"experiments/live_anchor_integration_001/reporting001/trajectory.csv.gz",
              "experiments/live_anchor_integration_001/publication001/trace_original.jsonl.gz",
              "experiments/live_anchor_integration_001/publication_recovery001/trace_independent_copy.jsonl.gz"}
    require(len(rows)==3 and {r["original_path"] for r in rows}==expected,"Transport role inventory differs")
    # Check every concatenation and all existing destinations before any write.
    for row in rows:
        concatenate(source_root,row)
        target=safe(target_root,row["original_path"])
        if target.exists():require(identity(target)==row["original_identity"],"Existing gzip differs; refusing repair/overwrite: "+str(target))
    results=[]
    for row in rows:
        target=safe(target_root,row["original_path"])
        if args.verify_only:
            results.append({"path":row["original_path"],"status":"matching_existing" if target.exists() else "verified_restorable"});continue
        if target.exists():
            require(identity(target)==row["original_identity"],"Existing gzip changed after preflight")
            results.append({"path":row["original_path"],"status":"matching_existing_preserved"});continue
        target.parent.mkdir(parents=True,exist_ok=True);target=safe(target_root,row["original_path"])
        temporary=None
        try:
            with tempfile.NamedTemporaryFile(mode="wb",prefix=".restore_transport_",dir=target.parent,delete=False) as handle:
                temporary=Path(handle.name);concatenate(source_root,row,handle)
                handle.flush();os.fsync(handle.fileno())
            os.link(temporary,target)  # Atomic installation; fails if target exists.
            fsync_directory(target.parent)
            require(identity(target)==row["original_identity"],"Installed gzip changed")
            results.append({"path":row["original_path"],"status":"restored_absent_gzip"})
        finally:
            if temporary is not None:temporary.unlink(missing_ok=True);fsync_directory(target.parent)
    print(json.dumps({"status":"verified" if args.verify_only else "restored_or_already_identical",
        "roles":results,"recompression_or_data_decoding":False,"scientific_status_changed":False},indent=2))


if __name__=="__main__":main()
