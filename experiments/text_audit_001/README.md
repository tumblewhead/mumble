# Text size audit and restructuring plan

The smallest measured shared-math/48-bit-history numerical core has **17,100 B
of text**, **25,072 B static SRAM**, and **26,096 B including a provisional
1,024 B stack allowance**. All code and constants reside in SRAM. This is an
isolated audit on `experiment/text-audit-001`; estimator behavior and campaign
defaults have not changed.

The [function census](../../provenance/text_audit_001/CENSUS.md) lists every linked
function and its inline-aware attribution. The [machine-readable grouping](../../provenance/text_audit_001/groups.json)
and [independent review](../../provenance/text_audit_001/review_r1.json) record the
measurement and its limits. Source baseline: `c2cb9fc`.

## Where the code is

| Block | Attributed text | Responsibility and boundary | Tables / processing | Restructuring question |
|---|---:|---|---|---|
| Binary64 arithmetic | 4,772 B | Arithmetic, comparisons and conversions used throughout | Software IEEE arithmetic; no model LUT | Can a future whole-core representation remove entire helpers? Partial conversions retain both runtimes. |
| Model and endpoint evaluation | 4,008 B | Parameter chart + basis/state → coefficients, gradients, support result and transported endpoint | Cardinal spline map, reduced-map coefficients, exponentials, chain rule | Can feature evaluation and full-bank transport share one coefficient/derivative kernel? |
| Joint refit and scalar uncertainty | 2,674 B | History + original prior → fit/step and marginal variance | Rowwise Jacobians, triangular algebra, line search | Can forward/transposed triangular solves share a loop? Which evaluation/validation paths duplicate work? |
| Elementary math | 1,720 B | Bounded scalar inputs → exp/log/tanh/atanh/sqrt/hypot | Shared procedural Horner; range reduction; Newton sqrt | Share composite formulas only where linked text plus constants shrinks. This has already received one optimization pass. |
| Sample propagation | 1,450 B | Ordered sample and actual interval + carried state → next state and feature row | Fixed pole recurrences, hysteresis jets, charge integration | Can repeated state/jet updates use a small common loop without extra persistent arrays? |
| History / local QR | 1,128 B | New row + packed factor → updated factor or failure | Givens rotations; binary64 local factor; 48-bit history encoding | Can both factors share rotation logic with different storage access? |
| Memory runtime | 572 B | Source/destination spans → copied, moved or zeroed bytes | memcpy, memmove, memset | Would one narrow overlap-safe implementation or fixed-size loops cost less? |
| Ownership / interface checks | 510 B | Configuration and lease identity → validated access or rejection | Pointer/finite checks, generation counter, serialized scratch ownership | Can checks be shared while retaining failure behavior and preventing stale queries? |
| Entry / integer runtime | 266 B | Probe entry and integer support | Startup glue, count-leading-zero and switch helper | Keep probe-only and device integration costs distinguishable. |

These are disjoint **DWARF-attributed bytes**, including associated literals and
padding. They sum to 17,100 B. They are not predicted savings. In particular,
`reset` is the largest physical symbol at 3,856 B because the compiler inlined
estimator operations into it; its own source body accounts for only 182 B.

The physical union of compiler binary64 helpers is 4,746 B; with our subtraction
wrapper it is 4,762 B. Earlier extent summation included a 16 B overlapping tail.
This audit records the correction without altering earlier receipts. The 4,772 B
source attribution above uses a different boundary convention; do not add them.

## First experiments, in order

### T1: Share RC coefficient and derivative evaluation

`feature()` and `transported()` both compute ordered pole time constants,
log coordinates, spline values/derivatives and amplitude chain rules. Prototype
RC endpoint transport as a weighted sum of the existing full-bank feature rows,
or extract a shared primitive if that produces smaller code. Keep the likelihood
on the reduced basis and endpoint transport on all 13 poles. Hysteresis needs a
separate derivation; do not obtain it by dividing an H-weighted feature by H.

Use the existing derivative scratch only after proving its lifetime does not
overlap the output gradient or a local factor lease. A generic interface may
cause compiler specialization into two copies; inspect the final linked image.

Boundary contract: same continuous parameter chart, incoming/forced response,
physical support and derivative scaling. Compare values and gradients against
the unmodified evaluator at interior and boundary cases, then scalar uncertainty
and paired short streams. Reordering sums is a numerical change, not an exact
bitwise-equivalence claim. No parameter quantization or evidence change.

### T2: Share QR rotation/update logic

History insertion and local inference insertion both use Givens updates.
Compare a common rotation loop with specialized storage access against the two
current loops. Count dispatch/access code as well as any new descriptors.

Boundary contract: history still rounds on **every 48-bit write**; the local
factor remains binary64. Preserve row mutation order, nonfinite rejection,
invalid-state handling, packed indexing and exactly-once observation ownership.
Compare individual updates including extreme scales and zero pivots, failure
paths and short paired streams. Do not replace square roots with a Gram matrix.

### T3: Share triangular algebra

The step solves an upper triangular system; variance solves its transpose and
forms a squared norm. Test a direction/transpose-aware common loop with the
existing workspace. Keep output commitment and scratch lease semantics intact.

Boundary contract: original whitened prior, joint cross terms, sign convention,
transpose and marginal-variance meaning. Verify residuals, variances, rejected
invalid factors and resource use. Do not trade away uncertainty for a smaller
point-estimate-only solver.

### T4: Sample-update and runtime cleanup

Inspect repeated free/forced RC updates and hysteresis jet loops for common
serial kernels. Preserve actual dt, charge units, sample order, rest evolution
and carried physical state. Avoid a broad registry unless a measured descriptor
replaces more code than it adds. A fixed-pole exponential recurrence may save
CPU while retaining all exp code elsewhere; that is not automatically SRAM gain.

Memory routines and repeated support transformations are secondary candidates.
Never substitute memcpy for an overlapping move or remove finite/support checks
merely to make the image smaller.

### T5: Whole-core representation experiment

The arithmetic runtime is the largest single family. Changing a few operations
to float32 or fixed point can retain the double runtime and add another one.
Use a dependency inventory first: which operations, comparisons and conversions
must disappear before a helper is eliminated? Only then compare complete builds.
Any lower-precision candidate needs explicit rounding/error accumulation and
uncertainty obligations, especially for indefinite history. This is a separate
architectural change after the shared-operation experiments, not an assumed win.

## Why restructuring remains necessary

With data, constants, vectors and the provisional stack unchanged, only
**1,244 B** remains for text under a 10,240 B total budget:
`10240 - (6928 + 1016 + 28 + 1024)`.
This excludes additional platform code. Even eliminating the entire current
4,762 B arithmetic family would leave 21,334 B with the same stack allowance.
Therefore local deduplication is a useful learning phase, but is not yet a
credible complete route to 10 KiB. We must subsequently reduce both the solver
architecture and its writable storage, using the contracts above to constrain
changes. No savings from the proposed experiments have been established.

## Acceptance ledger for each candidate

1. Same compiler, target, baseline inputs and linked entry points; retain source
   revision and commands. Change one structural choice at a time.
2. Count text, constants, alignment, data and stack. Report stack observations
   separately from a proven bound. Include descriptors and scratch lifetimes.
3. Check the relevant algebra and failure contracts, then targeted numerical
   comparisons. Examine drift and uncertainty before longer runs where needed.
4. Independent fresh-context review; retain failed variants and explanations.
5. Accept only measured total-SRAM improvement with justified behavior. Keep
   campaign/mainline defaults unchanged until separately qualified.

## Reproduction

From this worktree (new output directories are required):

```bash
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.shared_math_001.target \
  --variant procedural_horner --history-bits 48 \
  --out experiments/text_audit_001/baseline001
python3 -B -m experiments.text_audit_001.audit \
  --measurement experiments/text_audit_001/baseline001/measurement.json \
  --out experiments/text_audit_001/audit001
python3 -B experiments/text_audit_001/summarize.py \
  --census experiments/text_audit_001/audit001/census.json \
  --measurement experiments/text_audit_001/baseline001/measurement.json \
  --out provenance/text_audit_001
```

The audit rebuilds with debug information and requires byte-identical allocated
code/data before attributing source lines. The reviewer independently verified
the complete ELF allocated-section set. The script's current address-window
section discovery is specific to this target layout; it is not a general ELF
auditor. Static call counts are not a CPU profile. Large build/debug artifacts
remain ignored; only tools, documentation and small receipts are tracked.
