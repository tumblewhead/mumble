#!/usr/bin/env python3
"""Fixed diagnostic queries from already retained public/configuration evidence.

No observation decoding, model/prior evaluation, optimization or truth reads.
This preparation is separate from the single canonical scientific invocation.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import resource
import time
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
EXP = Path("experiments/compact_nonlinear_history_001")
PLAN = Path("plans/compact_nonlinear_history_001.json")

def identity(p):
    b = p.read_bytes()
    return {"bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()}

def main():
    start = time.monotonic()
    plan = json.loads((ROOT / PLAN).read_bytes())
    pins = plan["input"]
    inputs = {}
    values = {}
    for key in ("public_configuration", "warm_generation", "warm_evaluator"):
        rel = pins[key]
        got = identity(ROOT / rel)
        if got["sha256"] != pins[key + "_sha256"]:
            raise ValueError("Pinned preparation input changed: " + rel)
        inputs[rel] = got
        values[key] = json.loads((ROOT / rel).read_bytes())
    prior = values["public_configuration"]["configuration"]["public_prior"]
    generation = values["warm_generation"]
    evaluator = values["warm_evaluator"]
    a7 = np.array(generation["x"], dtype=np.float64)
    if a7.tolist() != evaluator["x"] or generation["generation"] != 7:
        raise ValueError("Saved anchor/evaluator disagreement")
    D = np.array(prior["public_unsplit_sd"], dtype=np.float64)
    kernel_sd = np.array(prior["kernel_sd"], dtype=np.float64)
    gram = np.zeros((16, 16), dtype=np.float64)
    packed = evaluator["gram"]
    if len(packed) != 136:
        raise ValueError("Unexpected full Gram")
    for i in range(16):
        for j in range(i + 1):
            gram[i, j] = gram[j, i] = packed[i * (i + 1) // 2 + j]
    B = gram + np.diag(1.0 / kernel_sd**2)
    scaled = B * np.outer(D, D)
    L = np.linalg.cholesky(scaled)  # failure is final; no repair or fallback
    white = D[:, None] * np.linalg.solve(L.T, np.eye(16))
    nodes = [
        {"index": 0, "label": "public_mean", "x": prior["public_unsplit_mean"]},
        {"index": 1, "label": "autonomous_generation_7", "x": a7.tolist()},
    ]
    for j in range(16):
        for sign in (-1, 1):
            nodes.append({"index": len(nodes), "label": f"whitened_{j:02d}_{sign:+d}",
                          "kind": "full_joint_metric_whitened", "column": j,
                          "signed_distance": sign, "x": (a7 + sign * white[:, j]).tolist()})
    target_directions = {}
    for target in ("logQ", "endpoint_SOC_at_252000"):
        g = np.zeros(16)
        if target == "logQ":
            g[5] = 1.0
        else:
            g[5] = evaluator["charge_Ah"] / np.exp(a7[5])
            g[11] = 1.0
        solved = np.linalg.solve(L.T, np.linalg.solve(L, D * g))
        direction = D * solved / np.sqrt(np.dot(D * g, solved))
        target_directions[target] = {"gradient": g.tolist(), "direction": direction.tolist()}
        for step in (-2, -1, 1, 2):
            nodes.append({"index": len(nodes), "label": f"{target}_{step:+d}",
                          "kind": "full_joint_curvature_predicted", "target": target,
                          "signed_distance": step, "x": (a7 + step * direction).tolist()})
    low, high = np.array(prior["entering_lower"]), np.array(prior["entering_upper"])
    for node in nodes:
        x = np.array(node["x"])
        if not np.all(np.isfinite(x)):
            raise ValueError("Nonfinite fixed node")
        node["entering_box_feasible"] = bool(np.all(x >= low) and np.all(x <= high))
        node["historical_path_feasibility"] = "not evaluated in preparation"
    assert len(nodes) == 42
    output = ROOT / EXP / "prepared"
    output.mkdir(exist_ok=False)
    text = "".join(" ".join(format(v, ".17g") for v in n["x"]) + "\n" for n in nodes)
    query_path = output / "queries.txt"
    with query_path.open("x") as f:
        f.write(text)
    recovered = [[float(s) for s in line.split()] for line in text.splitlines()]
    if recovered != [n["x"] for n in nodes]:
        raise ValueError("Query serialization did not roundtrip")
    own = resource.getrusage(resource.RUSAGE_SELF)
    receipt = {
        "schema": "mumble_compact_nonlinear_history_preparation_v1", "status": "completed",
        "source_id": pins["source_id"], "plan": {"path": str(PLAN), **identity(ROOT / PLAN)},
        "preparation_source": {"path": str(EXP / "prepare_queries.py"), **identity(Path(__file__))},
        "inputs": inputs,
        "queries": {"path": str(query_path.relative_to(ROOT)), **identity(query_path),
                    "rows": 42, "columns": 16, "format": "17 significant decimal digits; exact binary64 roundtrip"},
        "nodes": nodes, "target_directions": target_directions,
        "metric": {"formula": "B=savedG+kernelprecision, scaledB=B*outer(PUBLIC_SD,PUBLIC_SD)",
                   "factorization": "unmodified numpy.linalg.cholesky",
                   "repairs": 0, "whitened_metric_max_identity_error": float(np.max(np.abs(white.T @ B @ white - np.eye(16)))),
                   "cholesky_relative_residual": float(np.linalg.norm(L @ L.T - scaled, ord=np.inf) / np.linalg.norm(scaled, ord=np.inf))},
        "counts": {"preparation_invocations": 1, "saved_anchor_reads": 1, "saved_evaluator_reads": 1,
                   "model_steps": 0, "prior_evaluations": 0, "optimizer_calls": 0,
                   "observation_decodes": 0, "truth_reads": 0},
        "interpretation": "Fixed full-joint metric diagnostics, not credible intervals/profile endpoints; unavailable nodes remain in the scientific output. Saved a7 affects only warm arm and external query design, never public-arm initialization or acceptance.",
        "resources": {"CPU_self_s": own.ru_utime + own.ru_stime,
                      "wall_s": time.monotonic() - start, "peak_RSS_bytes": 1024 * own.ru_maxrss},
        "numpy": np.__version__,
    }
    with (output / "receipt.json").open("x") as f:
        json.dump(receipt, f, sort_keys=True, separators=(",", ":"), allow_nan=False)
        f.write("\n")
    print(json.dumps({"status": "completed", "queries": receipt["queries"],
                      "receipt": identity(output / "receipt.json"), "metric": receipt["metric"]}))

if __name__ == "__main__":
    main()
