#!/usr/bin/env python3
"""One authorized SVG recompression; reuse eleven intact publication roles."""
import gzip
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
OLD=ROOT/EXP/"publication_assets001"
OUT=ROOT/EXP/"publication_assets_recovery001"
BAD=EXP+"/publication_assets001/svg/reporting001/all16_parameters.svg.gz"
RAW=EXP+"/reporting001/all16_parameters.svg"
RAW_ID={"bytes":12704586,"sha256":"3480052b471a5e8a48bd085fb67510c9b2cbe52cdc57f2189f8d295da99e2161"}
GZIP_ID={"bytes":4110769,"sha256":"198aaf920083e8f01dbf1226ff827f7c1197d53ce1d99ac696710835f73df6bc"}
BAD_ID={"bytes":3391936,"sha256":"01551d83a81fca47da3d4bd907c3bf599a8e031d55031363f60e556a02e7742c"}
OLD_RECEIPT={"bytes":20684,"sha256":"61d413fa28ed158a01ba6c2be8a8925d9f5953396c4702310e4bcd1c01e5a597"}
RESTORER_SHA="d629e2f750f56e3b1f17aa6c04199b6d159f5cfbccc2ffbefed3724be470706d"
SCHEMA="mumble_live_anchor_asset_publication_recovery_v1"


def main():
    helper=OLD/"restore_assets.py"
    if hashlib.sha256(helper.read_bytes()).hexdigest()!=RESTORER_SHA:raise ValueError("Reviewed restore source differs")
    spec=importlib.util.spec_from_file_location("verified_asset_byte_helpers",helper)
    util=importlib.util.module_from_spec(spec);spec.loader.exec_module(util)
    identity,require=util.identity,util.require
    require({p.name for p in OUT.iterdir()}=={"recover_assets.py"},"Recovery directory is not fresh")
    started,cpu_started=time.monotonic(),time.process_time()
    sources={EXP+"/publication_assets_recovery001/recover_assets.py":identity(Path(__file__))}
    inputs,roles,errors,facts={},[],[],{}
    def encode(v):return (json.dumps(v,sort_keys=True,indent=2,allow_nan=False)+"\n").encode()
    def write_bytes(p,data):
        with p.open("xb") as f:f.write(data);f.flush();os.fsync(f.fileno())
        util.fsync_directory(p.parent)
    def write(p,v):write_bytes(p,encode(v))
    def usage():return {"CPU_s":time.process_time()-cpu_started,"wall_s":time.monotonic()-started,
                        "peak_RSS_bytes":int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)*1024}
    def limits():
        u=usage();require(u["CPU_s"]<=60 and u["wall_s"]<=90 and u["peak_RSS_bytes"]<=134217728,"Recovery resource cap")
    def manifest(directory):
        result={}
        for p in sorted(directory.rglob("*")):
            require(not p.is_symlink(),"Symlink in preserved/closed package")
            if p.is_file():result[p.relative_to(directory).as_posix()]=identity(p)
        return result
    def bind(relative,expected):
        p=util.safe(ROOT,relative);expected={k:expected[k] for k in ("bytes","sha256")}
        require(identity(p)==expected,"Bound file changed: "+relative)
        require(relative not in inputs or inputs[relative]==expected,"Conflicting identity")
        inputs[relative]=expected;return p
    write(OUT/"reservation.json",{"schema":SCHEMA,"recovery_invocations":1,"SVG_recompressions_max":1,
        "source_identities":sources,"raw_path":RAW,"raw_identity":RAW_ID,"gzip_expected":GZIP_ID,
        "preserved_damaged_path":BAD,"preserved_damaged_identity":BAD_ID,
        "caps":{"CPU_s":60,"wall_s":90,"RSS_bytes":134217728,"closed_output_bytes":8388608},
        "science_plot_data_value_calls":0})
    history=[]
    try:
        old_receipt=util.read_json(bind(EXP+"/publication_assets001/receipt.json",OLD_RECEIPT))
        require(old_receipt["status"]=="failed" and old_receipt["packaging_invocations"]==1 and
                old_receipt["SVG_files_compressed"]==10 and old_receipt["trace_packages_referenced_separately"]==2,
                "Original asset failure changed")
        actual=manifest(OLD)
        require({k:v for k,v in actual.items() if k!="receipt.json"}==old_receipt["files"],"Preserved failed asset manifest changed")
        require(sum(v["bytes"] for v in actual.values())==old_receipt["closed_output_bytes_including_receipt"],
                "Preserved failed asset byte count changed")
        for relative,expected in {**old_receipt["source_identities"],**old_receipt["input_identities"]}.items():bind(relative,expected)
        for name in ("restoration_manifest.json","proposed_ignore_paths.json"):
            bind(EXP+"/publication_assets001/"+name,old_receipt["files"][name])
        damaged=bind(BAD,BAD_ID);original=bind(RAW,RAW_ID)
        st=damaged.stat();damaged_stat={"bytes":st.st_size,"inode":st.st_ino,"device":st.st_dev,
                                      "mtime_ns":st.st_mtime_ns,"ctime_ns":st.st_ctime_ns}
        old_manifest=util.read_json(OLD/"restoration_manifest.json")
        require(old_manifest["roles"]==old_receipt["roles"] and len(old_manifest["roles"])==12,"Preserved role manifest differs")
        bad_rows=[r for r in old_manifest["roles"] if r["gzip_path"]==BAD]
        require(len(bad_rows)==1 and bad_rows[0]["raw_path"]==RAW and bad_rows[0]["gzip_identity"]==GZIP_ID,
                "Unexpected repair selection")
        for row in old_manifest["roles"]:
            bind(row["raw_path"],row["raw_identity"])
            if row["gzip_path"]!=BAD:bind(row["gzip_path"],row["gzip_identity"])
        target=OUT/"all16_parameters.svg.gz"
        h,n=hashlib.sha256(),0
        with original.open("rb") as raw,target.open("xb") as sink:
            with gzip.GzipFile(filename="",mode="wb",fileobj=sink,compresslevel=6,mtime=0) as compressor:
                while block:=raw.read(1048576):
                    n+=len(block);require(n<=RAW_ID["bytes"],"Original SVG grew")
                    h.update(block);compressor.write(block);limits()
            sink.flush();os.fsync(sink.fileno())
        util.fsync_directory(OUT)
        require({"bytes":n,"sha256":h.hexdigest()}==RAW_ID,"Recompression source differs")
        require(identity(target)==GZIP_ID,"Recovered gzip differs from originally verified bytes")
        decoded=util.decompressed_identity(target,RAW_ID)
        prefix=True
        with damaged.open("rb") as a,target.open("rb") as b:
            while block:=a.read(1048576):
                if block!=b.read(len(block)):prefix=False;break
        for row in old_manifest["roles"]:
            selected=dict(row)
            if selected["gzip_path"]==BAD:
                selected["gzip_path"]=target.relative_to(ROOT).as_posix()
                selected["recovery_provenance"]="Exactly one recompression of the unchanged original SVG; failed original gzip preserved."
            roles.append(selected)
        trace_receipt_id={"bytes":4883,"sha256":"dcc6a97b8dd7926f268bab99370be3d17ed1274cc87abad9aecd5fd9c6e2373a"}
        trace_selection_id={"bytes":2724,"sha256":"ac19d489d790bfaf8df19919f65715d51fa5ddc96b6c4a12b7b26efbd86cdc06"}
        bind(EXP+"/publication001/receipt.json",trace_receipt_id)
        trace_selection=util.read_json(bind(EXP+"/publication_selection.json",trace_selection_id))
        require(trace_selection["original_packaging_integrity_status"]=="failed_postclosure","Trace export failure history changed")
        history=[{"kind":"trace_export","original_receipt":{"path":EXP+"/publication001/receipt.json",**trace_receipt_id},
            "integrity_status":"failed_postclosure_preserved","damaged_artifact":trace_selection["preserved_damaged_artifact"],
            "selected_recovery_manifest":{"path":EXP+"/publication_selection.json",**trace_selection_id},"cause":"unattributed"},
            {"kind":"SVG_export","original_receipt":{"path":EXP+"/publication_assets001/receipt.json",**OLD_RECEIPT},
             "status":"failed_preserved","damaged_artifact":{"path":BAD,**BAD_ID,"stat":damaged_stat},
             "originally_verified_identity":GZIP_ID,"exact_prefix_of_recovered_gzip":prefix,"cause":"unattributed"}]
        restored_manifest={**old_manifest,"roles":roles,"export_failure_history":history,
            "selected_asset_recovery":"publication_assets_recovery001; one SVG only; other11 roles reused byte-exact"}
        write(OUT/"restoration_manifest.json",restored_manifest)
        write_bytes(OUT/"restore_assets.py",helper.read_bytes())
        require(identity(OUT/"restore_assets.py")["sha256"]==RESTORER_SHA,"Copied reviewed helper differs")
        ignores=util.read_json(OLD/"proposed_ignore_paths.json")
        require(len(ignores["paths"])==12 and len(ignores["SVG_paths"])==10 and len(ignores["primary_raw_trace_paths"])==2,
                "Ignore proposal inventory differs")
        ignores["selected_restoration_manifest"]=EXP+"/publication_assets_recovery001/restoration_manifest.json"
        ignores["keep_tracked"].append(BAD)
        write(OUT/"proposed_ignore_paths.json",ignores)
        instructions="""# Selected lossless publication artifacts

This recovery preserves both failed export attempts. Exactly one SVG was
recompressed from its unchanged original; the other nine SVG packages and the
two separately selected trace packages are reused unchanged. Full provenance
is in `restoration_manifest.json` and this directory's receipt.

Verify packages and destinations without writes:

```sh
python -B experiments/live_anchor_integration_001/publication_assets_recovery001/restore_assets.py --verify-only
```

Restore only absent original paths:

```sh
python -B experiments/live_anchor_integration_001/publication_assets_recovery001/restore_assets.py
```

Use `--root /absolute/path/to/destination` for another existing directory.
Matching files stay unchanged. Different existing files cause failure; no
capture is repaired or overwritten. Both raw trace roles are installed as
separate files with distinct inodes. Validate the original capture metadata
after restoration before using those bytes as scientific evidence.

`proposed_ignore_paths.json` contains exactly ten original SVGs and two large
raw trace paths. No ignore rule is applied here. Keep PNGs, CSV gzip, metadata,
selected packages, and both damaged old gzip files tracked as evidence.
Packaging/restoration performs no model, fitting, prior or truth-value work
and changes no original success or failure status. Attribution of both export
truncations remains unknown.
"""
        write_bytes(OUT/"ARTIFACTS.md",instructions.encode())
        for relative,expected in {**sources,**inputs}.items():require(identity(ROOT/relative)==expected,"Input/source changed at closure")
        for row in roles:require(identity(ROOT/row["gzip_path"])==row["gzip_identity"],"Selected gzip changed at closure")
        require(manifest(OLD)==actual,"Failed original package changed during recovery")
        limits()
        facts={"SVG_recompressions":1,"other_exact_roles_reused":11,"recovered_identity":GZIP_ID,
               "decompressed_identity":decoded,"damaged_gzip_exact_prefix":prefix,"cause":"unattributed"}
    except Exception as error:errors.append({"type":type(error).__name__,"message":str(error)[:2048]})
    files=manifest(OUT)
    receipt={"schema":SCHEMA,"status":"failed" if errors else "completed","recovery_invocations":1,
        "source_identities":sources,"input_identities":inputs,"roles":roles,"facts":facts,
        "export_failure_history":history,"errors":errors,"resources_before_final_receipt":usage(),
        "files":files,"closed_output_bytes_including_receipt":0,
        "restore_helper_identity":identity(OUT/"restore_assets.py") if (OUT/"restore_assets.py").exists() else None,
        "restoration_manifest_identity":identity(OUT/"restoration_manifest.json") if (OUT/"restoration_manifest.json").exists() else None,
        "plot_data_value_decodes":0,"model_prior_optimizer_truth_calls":0,
        "original_files_changed":False,"original_failure_statuses_changed":False}
    for _ in range(24):
        size=sum(v["bytes"] for v in files.values())+len(encode(receipt))
        if size>8388608 and not any(e["message"]=="Recovery closed output cap" for e in errors):
            errors.append({"type":"ResourceFailure","message":"Recovery closed output cap"});receipt["status"]="failed"
        if receipt["closed_output_bytes_including_receipt"]==size:break
        receipt["closed_output_bytes_including_receipt"]=size
    else:raise ValueError("Recovery receipt byte accounting did not stabilize")
    write(OUT/"receipt.json",receipt)
    if receipt["status"]=="completed":
        selection={"schema":"mumble_live_anchor_asset_publication_selection_v1","status":"selected_after_narrow_byte_recovery",
            "receipt":{"path":(OUT/"receipt.json").relative_to(ROOT).as_posix(),**identity(OUT/"receipt.json")},
            "restoration_manifest":{"path":(OUT/"restoration_manifest.json").relative_to(ROOT).as_posix(),**identity(OUT/"restoration_manifest.json")},
            "restore_helper":{"path":(OUT/"restore_assets.py").relative_to(ROOT).as_posix(),**identity(OUT/"restore_assets.py")},
            "proposed_ignore_paths":{"path":(OUT/"proposed_ignore_paths.json").relative_to(ROOT).as_posix(),**identity(OUT/"proposed_ignore_paths.json")},
            "export_failure_history":history,"no_gitignore_or_original_file_changes":True,"scientific_calls":0}
        write(ROOT/EXP/"publication_assets_selection.json",selection)
    print(encode({"status":receipt["status"],"receipt":{"path":str(OUT/"receipt.json"),**identity(OUT/"receipt.json")},
        "facts":facts,"closed_bytes":receipt["closed_output_bytes_including_receipt"],"errors":errors}).decode(),end="")
    return 0 if receipt["status"]=="completed" else 1


if __name__=="__main__":raise SystemExit(main())
