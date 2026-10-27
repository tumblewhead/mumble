#!/usr/bin/env python3
"""One opaque-byte split of three closed gzip roles, deduplicated by SHA256."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import sys
import time

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[3]
EXP="experiments/live_anchor_integration_001"
OUT=ROOT/EXP/"publication_transport001"
LIMIT=4000000
ORIGINALS=[("trajectory_csv_gzip",EXP+"/reporting001/trajectory.csv.gz",14400050,"f1bdf31d27132cd9f95760fd98e9eb6721fc7208fc396f74370be3fde6ad259a"),
    ("trace_original_gzip",EXP+"/publication001/trace_original.jsonl.gz",8568513,"1916a1a42aa2027000a75bcb445f1959861e58c21dc991988b2f5bf57c2c3a1c"),
    ("trace_independent_gzip",EXP+"/publication_recovery001/trace_independent_copy.jsonl.gz",8568513,"1916a1a42aa2027000a75bcb445f1959861e58c21dc991988b2f5bf57c2c3a1c")]


def main():
    spec=importlib.util.spec_from_file_location("transport_byte_helpers",OUT/"restore_transport.py")
    util=importlib.util.module_from_spec(spec);spec.loader.exec_module(util)
    require,identity=util.require,util.identity
    require({p.name for p in OUT.iterdir()}=={"package_transport.py","restore_transport.py","ARTIFACTS.md"},"Transport directory is not fresh")
    started,cpu_started=time.monotonic(),time.process_time()
    sources={p.relative_to(ROOT).as_posix():identity(p) for p in OUT.iterdir()}
    inputs,parts,roles,errors={},{},[],[]
    def encode(v):return (json.dumps(v,indent=2,sort_keys=True,allow_nan=False)+"\n").encode()
    def write_bytes(path,data):
        with path.open("xb") as handle:handle.write(data);handle.flush();os.fsync(handle.fileno())
        util.fsync_directory(path.parent)
    def write(path,v):write_bytes(path,encode(v))
    def bind(relative,expected):
        p=util.safe(ROOT,relative);expected={k:expected[k] for k in ("bytes","sha256")}
        require(identity(p)==expected,"Bound original/metadata changed: "+relative);inputs[relative]=expected;return p
    def usage():return {"CPU_s":time.process_time()-cpu_started,"wall_s":time.monotonic()-started,
                        "peak_RSS_bytes":int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)*1024}
    def limits():
        u=usage();require(u["CPU_s"]<=60 and u["wall_s"]<=90 and u["peak_RSS_bytes"]<=67108864,"Byte transport resource cap")
    event={"scope":"distribution_only","reported_by":"repository publication coordinator",
        "role":EXP+"/reporting001/trajectory.csv.gz","bytes":14400050,
        "observation":"Repository connector transport failed before a Git SHA was returned.",
        "smaller_successes_reported_bytes":[34608,4110769],
        "cause":"not_established","transport_limit":"not_established","scientific_status_changed":False}
    write(OUT/"reservation.json",{"schema":"mumble_live_anchor_transport_packaging_v1","packaging_invocations":1,
        "source_identities":sources,"original_roles":3,"unique_original_bytes":22968563,"chunk_max_bytes":LIMIT,
        "caps":{"CPU_s":60,"wall_s":90,"RSS_bytes":67108864,"closed_output_bytes":25165824},
        "distribution_event":event,"recompression_decompression_data_decoding_scientific_calls":0})
    try:
        metadata=[(EXP+"/reporting001/reporting_receipt.json",6851,"cf525bcf13d85365254b48b458f6fe93b5b730cc9d7c6e641c43f916efa63b0d"),
            (EXP+"/reporting_continuation001/receipt.json",8078,"2574084805c7793e21c28076982dabe17cb7e0ad70aa3a6ac1dc0bf62b5ae3a3"),
            (EXP+"/publication_selection.json",2724,"ac19d489d790bfaf8df19919f65715d51fa5ddc96b6c4a12b7b26efbd86cdc06"),
            (EXP+"/publication_assets_selection.json",3349,"2b5d28cb6aaf8bdb9cac0f0a71df35d924a212b61c5d134e0ef76cdedab2812c")]
        for path,size,digest in metadata:bind(path,{"bytes":size,"sha256":digest})
        (OUT/"chunks").mkdir();util.fsync_directory(OUT)
        for name,relative,size,digest in ORIGINALS:
            expected={"bytes":size,"sha256":digest};original=bind(relative,expected)
            ordered=[];whole,length=hashlib.sha256(),0
            with original.open("rb") as source:
                while block:=source.read(LIMIT):
                    length+=len(block);require(length<=size,"Original grew while splitting");whole.update(block)
                    part_id={"bytes":len(block),"sha256":hashlib.sha256(block).hexdigest()}
                    part_path=OUT/"chunks"/(part_id["sha256"]+".bin")
                    relative_part=part_path.relative_to(ROOT).as_posix()
                    if part_id["sha256"] not in parts:
                        write_bytes(part_path,block)
                        require(identity(part_path)==part_id,"New chunk differs")
                        parts[part_id["sha256"]]={"path":relative_part,**part_id}
                    else:
                        require(parts[part_id["sha256"]]=={"path":relative_part,**part_id} and identity(part_path)==part_id,
                                "Conflicting duplicate chunk")
                    ordered.append(dict(parts[part_id["sha256"]]));limits()
            require({"bytes":length,"sha256":whole.hexdigest()}==expected,"Split original identity differs")
            row={"role":name,"original_path":relative,"original_identity":expected,"parts":ordered}
            util.concatenate(ROOT,row)
            roles.append(row)
        require(len(roles)==3 and roles[1]["parts"]==roles[2]["parts"],"Identical trace roles were not deduplicated")
        manifest={"schema":"mumble_live_anchor_transport_manifest_v1","chunk_max_bytes":LIMIT,
            "roles":roles,"unique_parts":list(parts.values()),"distribution_event":event,
            "byte_order":"Concatenate each role's parts in listed order; no gzip processing.",
            "restoration":"Absent originals only; matching existing originals preserved; differing originals fail; no overwrite."}
        write(OUT/"manifest.json",manifest)
        ignores={"schema":"mumble_live_anchor_transport_ignore_proposal_v1","status":"proposal_only_no_git_changes",
            "paths":[r["original_path"] for r in roles],"root_anchored_gitignore_lines":["/"+r["original_path"] for r in roles],
            "scope":"Exactly three original gzip paths, in addition to the earlier twelve raw-asset exclusions.",
            "keep_tracked":"All chunks, manifests, helpers, PNGs, metadata and damaged export evidence.",
            "restoration_order":[EXP+"/publication_transport001/restore_transport.py",EXP+"/publication_assets_recovery001/restore_assets.py"]}
        require(len(ignores["paths"])==3,"Ignore proposal differs");write(OUT/"proposed_ignore_paths.json",ignores)
        for path,expected in {**sources,**inputs}.items():require(identity(ROOT/path)==expected,"Source/original changed at closure")
        for part in parts.values():require(identity(ROOT/part["path"])=={k:part[k] for k in ("bytes","sha256")},"Chunk changed at closure")
        limits()
    except Exception as error:errors.append({"type":type(error).__name__,"message":str(error)[:2048]})
    files={p.relative_to(OUT).as_posix():identity(p) for p in sorted(OUT.rglob("*")) if p.is_file()}
    receipt={"schema":"mumble_live_anchor_transport_packaging_v1","status":"failed" if errors else "completed",
        "packaging_invocations":1,"source_identities":sources,"input_identities":inputs,"roles":roles,
        "unique_chunks":len(parts),"unique_chunk_bytes":sum(p["bytes"] for p in parts.values()),
        "distribution_event":event,"errors":errors,"resources_before_final_receipt":usage(),"files":files,
        "restore_helper_identity":identity(OUT/"restore_transport.py"),
        "manifest_identity":identity(OUT/"manifest.json") if (OUT/"manifest.json").exists() else None,
        "closed_output_bytes_including_receipt":0,"recompression_decompression_data_decoding_scientific_calls":0,
        "original_files_changed":False,"closed_existing_receipts_changed":False,"git_mutations":0}
    for _ in range(24):
        size=sum(v["bytes"] for v in files.values())+len(encode(receipt))
        if size>25165824 and not any(e["message"]=="Closed transport output cap" for e in errors):
            errors.append({"type":"ResourceFailure","message":"Closed transport output cap"});receipt["status"]="failed"
        if receipt["closed_output_bytes_including_receipt"]==size:break
        receipt["closed_output_bytes_including_receipt"]=size
    else:raise ValueError("Transport receipt byte accounting did not stabilize")
    write(OUT/"receipt.json",receipt)
    print(encode({"status":receipt["status"],"receipt":{"path":str(OUT/"receipt.json"),**identity(OUT/"receipt.json")},
        "unique_chunks":receipt["unique_chunks"],"unique_chunk_bytes":receipt["unique_chunk_bytes"],
        "closed_bytes":receipt["closed_output_bytes_including_receipt"],"errors":errors}).decode(),end="")
    return 0 if receipt["status"]=="completed" else 1


if __name__=="__main__":raise SystemExit(main())
