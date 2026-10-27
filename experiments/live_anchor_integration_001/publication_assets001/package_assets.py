#!/usr/bin/env python3
"""One metadata-only packaging invocation for closed SVG and trace roles."""
import gzip
import hashlib
import importlib.util
import os
from pathlib import Path
import resource
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
EXP = "experiments/live_anchor_integration_001"
OUTPUT = ROOT / EXP / "publication_assets001"
PINNED = {
    EXP + "/reporting001/reporting_receipt.json": (6851, "cf525bcf13d85365254b48b458f6fe93b5b730cc9d7c6e641c43f916efa63b0d"),
    EXP + "/reporting_continuation001/receipt.json": (8078, "2574084805c7793e21c28076982dabe17cb7e0ad70aa3a6ac1dc0bf62b5ae3a3"),
    EXP + "/presentation/display_sources.json": (3245, "ff35e19b82e39f8f9d3547eac28ceaed50fd1056cc8217babffe2c853d80656e"),
    EXP + "/publication_selection.json": (2724, "ac19d489d790bfaf8df19919f65715d51fa5ddc96b6c4a12b7b26efbd86cdc06")}
SCHEMA = "mumble_live_anchor_asset_packaging_v1"


def main():
    helper_path = OUTPUT / "restore_assets.py"
    spec = importlib.util.spec_from_file_location("asset_restoration_byte_helpers", helper_path)
    util = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(util)
    require, identity = util.require, util.identity
    import json
    def encode(value):
        return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    def write(path, value):
        with path.open("xb") as handle:
            handle.write(encode(value));handle.flush();os.fsync(handle.fileno())
        util.fsync_directory(path.parent)
    def manifest(directory):
        rows = {}
        for path in sorted(directory.rglob("*")):
            require(not path.is_symlink(), "Symlink in package output")
            if path.is_file():rows[path.relative_to(directory).as_posix()] = identity(path)
        return rows
    require({p.name for p in OUTPUT.iterdir()} == {"package_assets.py", "restore_assets.py", "ARTIFACTS.md"},
            "Packaging directory is not the fresh source-only directory")
    started, cpu_started = time.monotonic(), time.process_time()
    sources = {p.relative_to(ROOT).as_posix(): identity(p) for p in OUTPUT.iterdir()}
    bindings, roles, errors = {}, [], []
    write(OUTPUT / "reservation.json", {"schema": SCHEMA, "packaging_invocations": 1,
        "source_identities": sources, "SVG_count": 10, "raw_SVG_bytes": 53162357,
        "compression": {"level": 6, "mtime": 0, "filename": ""},
        "caps": {"CPU_s": 120, "wall_s": 180, "RSS_bytes": 134217728, "closed_output_bytes": 67108864},
        "no_plot_data_or_scientific_value_decoding": True})
    def usage():
        return {"CPU_s": time.process_time()-cpu_started, "wall_s": time.monotonic()-started,
                "peak_RSS_bytes": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)*1024}
    def limits():
        u=usage();require(u["CPU_s"]<=120 and u["wall_s"]<=180 and u["peak_RSS_bytes"]<=134217728,
                         "Packaging resource cap")
    def bind(relative, expected):
        path=util.safe(ROOT,relative);expected={k:expected[k] for k in ("bytes","sha256")}
        require(identity(path)==expected,"Bound artifact changed: "+relative)
        require(relative not in bindings or bindings[relative]==expected,"Conflicting artifact binding")
        bindings[relative]=expected
        return path
    try:
        docs={}
        for name,(size,digest) in PINNED.items():
            docs[name]=util.read_json(bind(name,{"bytes":size,"sha256":digest}))
        report=docs[EXP+"/reporting001/reporting_receipt.json"]
        continuation=docs[EXP+"/reporting_continuation001/receipt.json"]
        display=docs[EXP+"/presentation/display_sources.json"]
        selection=docs[EXP+"/publication_selection.json"]
        require(report["status"]=="failed" and continuation["status"]==display["status"]=="completed",
                "Original reporting/continuation/display status differs")
        svg={}
        for dirname,receipt in (("reporting001",report),("reporting_continuation001",continuation)):
            directory=ROOT/EXP/dirname
            receipt_name="reporting_receipt.json" if dirname=="reporting001" else "receipt.json"
            actual=manifest(directory)
            require({k:v for k,v in actual.items() if k!=receipt_name}==receipt["files"],"Closed report manifest changed")
            require(sum(v["bytes"] for v in actual.values())==receipt["closed_output_bytes_including_receipt"],
                    "Closed report byte count changed")
            for name,expected in receipt["files"].items():
                relative=EXP+"/"+dirname+"/"+name;bind(relative,expected)
                if name.endswith(".svg"):svg[relative]=expected
        for row in display["files"]:
            bind(row["path"],row)
            if row["path"].endswith(".svg"):svg[row["path"]]={k:row[k] for k in ("bytes","sha256")}
        # Bind reporting code/configuration only, never raw truth inputs.
        for relative,receipt in (("tools/report_live_anchor_integration.py",report),
                                 ("tools/finish_live_anchor_report.py",continuation),
                                 (EXP+"/reporting_plan.json",report)):
            expected=next(r for r in receipt["inputs"] if Path(r["path"]).resolve()==ROOT/relative)
            require(not expected.get("truth_content",False),"Unexpected truth-content source")
            bind(relative,expected)
        bind("tools/make_live_anchor_update_figures.py",display["script"])
        require(len(svg)==10 and sum(v["bytes"] for v in svg.values())==53162357,"SVG inventory differs")
        for relative,expected in sorted(svg.items()):
            original=ROOT/relative
            target=OUTPUT/"svg"/Path(relative).relative_to(EXP)
            target=target.with_suffix(target.suffix+".gz");target.parent.mkdir(parents=True,exist_ok=True)
            digest,size=hashlib.sha256(),0
            with original.open("rb") as raw,target.open("xb") as sink:
                with gzip.GzipFile(filename="",mode="wb",fileobj=sink,compresslevel=6,mtime=0) as compressor:
                    while block:=raw.read(1048576):
                        size+=len(block);require(size<=expected["bytes"],"SVG grew during compression")
                        digest.update(block);compressor.write(block);limits()
                sink.flush();os.fsync(sink.fileno())
            util.fsync_directory(target.parent)
            require({"bytes":size,"sha256":digest.hexdigest()}==expected,"SVG compression input differs")
            compressed=identity(target);decompressed=util.decompressed_identity(target,expected)
            roles.append({"kind":"SVG","raw_path":relative,"raw_identity":expected,
                "gzip_path":target.relative_to(ROOT).as_posix(),"gzip_identity":compressed,
                "decompressed_identity":decompressed,"original_preserved":True})
        require(selection["status"]=="selected_after_explicit_recovery" and
                selection["original_packaging_integrity_status"]=="failed_postclosure", "Trace selection history differs")
        producer=EXP+"/attempt001/producer"
        commit=util.read_json(bind(producer+"/commit.json",selection["capture_commit_identity"]))
        for selected in selection["roles"]:
            role="original" if selected["role"]=="original" else "object"
            row=commit[role];raw_path=producer+"/"+row["path"]
            bind(raw_path,row);require({k:row[k] for k in ("bytes","sha256")}==selected["raw_identity"],"Trace raw selection differs")
            compressed=bind(selected["gzip_path"],selected["gzip_identity"])
            decoded=util.decompressed_identity(compressed,selected["raw_identity"])
            roles.append({"kind":"primary_raw_capture","capture_role":selected["role"],
                "raw_path":raw_path,"raw_identity":selected["raw_identity"],"gzip_path":selected["gzip_path"],
                "gzip_identity":selected["gzip_identity"],"decompressed_identity":decoded,
                "selection_manifest":EXP+"/publication_selection.json","original_preserved":True,
                "restore_to_separate_inode":True})
        require(len(roles)==12,"Restoration role count differs")
        trace_roles=[r for r in roles if r["kind"]=="primary_raw_capture"]
        stats=[(ROOT/r["raw_path"]).stat() for r in trace_roles]
        require((stats[0].st_dev,stats[0].st_ino)!=(stats[1].st_dev,stats[1].st_ino),"Raw trace roles share an inode")
        restoration={"schema":"mumble_live_anchor_restoration_manifest_v1","roles":roles,
            "selected_trace_manifest":{"path":EXP+"/publication_selection.json",**bindings[EXP+"/publication_selection.json"]},
            "original_reporting_status":"failed_preserved","original_package_integrity_status":"failed_postclosure_preserved",
            "restoration_policy":"Only absent targets; matching existing targets unchanged; different existing target aborts; trace targets require separate inodes."}
        write(OUTPUT/"restoration_manifest.json",restoration)
        ignores={"schema":"mumble_live_anchor_proposed_raw_ignores_v1","status":"proposal_only_no_git_changes",
            "paths":[r["raw_path"] for r in roles],"SVG_paths":sorted(svg),
            "primary_raw_trace_paths":[r["raw_path"] for r in trace_roles],
            "root_anchored_gitignore_lines":["/"+r["raw_path"] for r in roles],
            "keep_tracked":["PNG files","trajectory.csv.gz","metadata and receipts","all selected gzip packages",
                EXP+"/publication001/trace_independent_copy.jsonl.gz"],
            "preservation":"No deletion or ignore mutation performed; damaged old gzip remains tracked evidence."}
        require(len(ignores["paths"])==12 and len(ignores["primary_raw_trace_paths"])==2,"Ignore inventory differs")
        write(OUTPUT/"proposed_ignore_paths.json",ignores)
        for relative,expected in {**sources,**bindings}.items():require(identity(ROOT/relative)==expected,"Bound input/source changed at closure")
        for row in roles:require(identity(ROOT/row["gzip_path"])==row["gzip_identity"],"Packaged gzip changed before closure")
        limits()
    except Exception as error:
        errors.append({"type":type(error).__name__,"message":str(error)[:2048]})
    files=manifest(OUTPUT)
    receipt={"schema":SCHEMA,"status":"failed" if errors else "completed","packaging_invocations":1,
        "source_identities":sources,"input_identities":bindings,"roles":roles,"errors":errors,
        "restore_helper_identity":identity(helper_path),
        "restoration_manifest_identity":identity(OUTPUT/"restoration_manifest.json") if (OUTPUT/"restoration_manifest.json").exists() else None,
        "resources_before_final_receipt":usage(),"files":files,"closed_output_bytes_including_receipt":0,
        "SVG_files_compressed":sum(r["kind"]=="SVG" for r in roles),
        "trace_packages_referenced_separately":sum(r["kind"]=="primary_raw_capture" for r in roles),
        "plot_data_value_decodes":0,"model_prior_optimizer_truth_calls":0,"original_files_changed":False,
        "canonical_or_original_failure_status_changed":False}
    for _ in range(24):
        size=sum(v["bytes"] for v in files.values())+len(encode(receipt))
        if size>67108864 and not any(e["message"]=="Closed asset output cap" for e in errors):
            errors.append({"type":"ResourceFailure","message":"Closed asset output cap"});receipt["status"]="failed"
        if receipt["closed_output_bytes_including_receipt"]==size:break
        receipt["closed_output_bytes_including_receipt"]=size
    else:raise ValueError("Asset receipt byte accounting did not stabilize")
    write(OUTPUT/"receipt.json",receipt)
    print(encode({"status":receipt["status"],"receipt":{"path":str(OUTPUT/"receipt.json"),**identity(OUTPUT/"receipt.json")},
        "SVG_files":receipt["SVG_files_compressed"],"trace_roles":receipt["trace_packages_referenced_separately"],
        "closed_bytes":receipt["closed_output_bytes_including_receipt"],"errors":errors}).decode(),end="")
    return 0 if receipt["status"]=="completed" else 1


if __name__=="__main__":
    raise SystemExit(main())
