# Proof-driven dependency and exact-reuse experiment

Read the [architecture contracts](../../specifications/architecture_reuse_001/README.md)
and [findings](../../provenance/architecture_reuse_001/README.md). This experiment
stays on `experiment/conditional-architecture-001`; campaign defaults and existing
response kernels are unchanged. The candidate is H7-only and shares eight
directional exp/expm1 coefficient pairs within each observation.

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -B -m unittest \
  experiments.architecture_reuse_001.test_reuse \
  experiments.architecture_reuse_001.test_gate -v

OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -B -m \
  experiments.architecture_reuse_001.run \
  --out experiments/architecture_reuse_001/local_qualification

python3 -B -m experiments.architecture_reuse_001.gate
```

Use a fresh output directory. The runner builds both versions, checks response
parity, counts expensive calls in separately instrumented binaries, measures
normal-build host timings, and compares two complete backends including the
preserved35520record domain failure. JSON summaries include timings and storage;
build receipts contain compiler settings, source/binary hashes and stack reports.
No raw observation files are retained.

The final command checks source/proof/review/test/evidence version bindings from
the committed manifest. A changed file invalidates its prior acceptance receipt.
This is not a theorem prover, a digital signature, or a substitute for re-running
tests and independent review. Do not update hashes alone to bless a change.
The graph is a static dependency/lifetime plan; persistent memoization and a
runtime graph executive have not been implemented.
