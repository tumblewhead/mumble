# Shared triangular solve

Candidate `shared` uses one loop for the fit step (descending upper solve) and
scalar variance (ascending transposed solve). It retains operand order, step
sign, per-step finite rejection, variance's final finite-total check, scratch
ownership and output commitment. No persistent memory or numerical approximation
is added. Direction dispatch adds control work; timing is unmeasured.

Compared with shared QR commit4d15640:

| Resource | Baseline | Candidate |
|---|---:|---:|
| Static SRAM | 24,680 B | 24,672 B |
| Observed stack | 664 B | 664 B |
| Static plus observed stack | 25,344 B | 25,336 B |
| With provisional 1 KiB stack allowance | 25,704 B | 25,696 B |

This is an **8 B measured saving**. Stack is an exercised watermark, not a bound;
M23 instructions run on an M33 emulator, not the final device. Mainline and
campaign defaults remain unchanged. No long-stream or lifetime qualification
is claimed for this step.

Direct controls cover1,000 paired solves, including20 matched failures. Outputs
and scratch compare equal on tested inputs; normalized equation residual is below
7.4e-16. Controls include zero and nonfinite diagonals. The target integration
probe completes with status0 and unchanged stack. Independent review is recorded
in provenance/triangular_sharing_001/review.json. This is limited experimental
acceptance, not firmware readiness or a universal floating-point proof.

Reproduce with fresh output directories:

```
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.triangular_sharing_001.target --variant shared --out experiments/triangular_sharing_001/new_target
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.triangular_sharing_001.target --variant shared --execute --out experiments/triangular_sharing_001/new_stack
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.triangular_sharing_001.check
```

The check command uses check001 and requires it not to exist. Source and small
receipts are tracked; generated builds remain ignored.
