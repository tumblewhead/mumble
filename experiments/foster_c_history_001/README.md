# Structured history calculations and workspace reuse

The default smaller-workspace variant reduces host replay time by **8.0–9.3%**
against the previous optimized C version. It also lowers the rolling-path
context-plus-largest-own-frame memory bound from30,856B to **21,832B**.
All tested full replay outputs, including final joint messages and likelihood
normalization, remain **bit-identical** in both token formats.

A CPU-only variant is retained: it saves **9.2–11.0%** of host time but keeps the
larger stack workspace. The default favors the memory reduction needed for M23.
Neither variant meets the10,240B target or establishes16MHz timing.

## Structured arithmetic

[history.c](history.c) retains the generic Gaussian operation, without battery
assumptions, parameter thresholds or discarded covariance terms:

- The likelihood root is upper triangular, so `A*L` and residual re-centering skip
  its known zero entries.
- Only the lower triangle of `I+BᵀB` is constructed for Cholesky.
- Exact identity transport rows use direct root copies. Other rows retain dense
  multiplication, including arbitrary, mixed and singular transport maps.
- The seventeenth likelihood row is an orthogonal residual. It remains in the
  likelihood normalizer even though it contributes no parameter information.
- The endpoint/anchor offset remains present for identity rows. Identity transport
  does not imply that the encoded centers are identical.

Token formats, double arithmetic, the QR subnormal repair, physical model,
calibration, prior and fitting settings are unchanged.

## Workspace lifetimes

The final variant decodes one likelihood row at a time into `B` and the residual,
so it needs no full decoded likelihood matrix. It leaves transport encoded until
conditioning is complete, then decodes one transport row at a time.

After the fitted residual has contributed to log evidence, `B` is dead and its
storage becomes the posterior covariance root. The explicit history workspace
is **4744B**, versus the earlier collection of large local arrays.

| Phase | Reuse |
|---|---|
| Fit matrix construction and solve | `B` and precision share the trial-output buffer |
| Line search | Matrix work is finished; that same buffer receives trial physical output |
| Token serialization | Accepted physical output is still available; token is independent afterward |
| History conditioning/transport | Model/thermal/trial phase storage becomes history workspace |
| Outgoing-domain check | History output is complete; model scratch is reused for a zero-record check |

Committed history, staged output, encoded token and pending observations remain
separate from that shared workspace. Failure after fitting or history calculation
preserves committed history and pending input. Retry rebuilds transient values.
The zero-record domain check does not read the overwritten thermal cache.

The matrix preparation helper scopes its `restrict` promises to that phase.
They do not span subsequent writes through the overlapping trial-output member.
The generic history worker likewise requires nonoverlapping input, output, token
and workspace. The standalone `fb_history` adapter still allocates a local
workspace; the rolling path calls `fb_history_work` directly with context storage.

## Paired host timings and preservation

Three repetitions alternate stage order. Medians from the
[final benchmark](attempt002/summary.json):

| Case and token format | Previous version | Structured arithmetic only | Also workspace reuse, default |
|---|---:|---:|---:|
| Four-hour CC–CV, binary64 | 0.598s | 0.543s | **0.550s** |
| Four-hour CC–CV, binary32 | 0.581s | 0.522s | **0.533s** |
| Twelve-hour weak excitation, binary64 | 1.880s | 1.673s | **1.704s** |
| Twelve-hour weak excitation, binary32 | 1.809s | 1.615s | **1.654s** |

These are instrumented single-thread AMD Ryzen7 9800X3D host runs, excluding
initialization, file I/O, compilation, plant simulation, plots and scoring.
The12 case/encoding/stage combinations all complete; repeat hashes match. Both
new stages preserve trace outputs and final mean/root/normalizer bytes relative
to the previous version, not merely application-scale point accuracy.

The [first attempt](attempt001/summary.json) exposed an implementation tradeoff:
workspace reuse slowed matrix preparation enough to lose much of the CPU gain.
A separately scoped matrix helper made the nonaliasing assumptions explicit and
recovered most of that time. The original results and source snapshots remain
available; [development.json](development.json) records their mapping. The final
workspace variant remains about1–2% slower than the CPU-only variant on these
controls, while eliminating the large history stack allocation.

**Twenty-two targeted tests pass**, covering prior controls plus independent
Gaussian conditioning with identity/dense/singular transport, a residual-only
normalizer, poisoned workspace and boundary guards, post-history domain-failure
retry, and byte-equal partial-window comparisons. The inherited harness control
exercises the unchanged replay runner; changed estimator paths use the new library.
AddressSanitizer and UndefinedBehaviorSanitizer pass the standalone4097-record
control. LeakSanitizer remains disabled in this traced environment.

These results preserve the current estimator's behavior. They do not validate
Gaussian coverage, resolve weak-excitation bias, add aging, or qualify ten-year
history.

## M23 resource evidence

| Item | Previous version | Default variant |
|---|---:|---:|
| Context | 19,416B | 19,416B |
| Fitter own stack frame | 4,744B | **656B** |
| Integrated history own stack frame | 11,440B | **192B** |
| Largest own frame on rolling path | 11,440B | **2416B**, token encoding |
| Context + largest rolling-path own frame | 30,856B | **21,832B** |
| Linked accounting-probe text | 26,876B | 27,444B |
| Probe data + BSS, excluding stack | 22,400B | 22,400B |

The saved compiler `.su` files and
[rolling disassembly](build_m23_2/rolling.disassembly.txt) verify that retirement
calls `fb_history_work`, not the4760B-frame standalone adapter. That adapter is
still available to independent callers and must be budgeted if they use it.

Adding the known C frames along `fb_offer -> fb_flush -> fb_token -> fb_qr`
gives2680B, or **22,096B including context**, before called math/runtime frames,
external caller stack, acquisition and interrupts. The host replay entry adds48B.
These figures are partial source/compiler accounting, not a complete SRAM bound.
The linked probe also retains separate initialization buffers and library globals;
its static total is a different accounting scope from the context figures.

The soft-float M23 cross-build succeeds. The probe has no startup/vector table or
custom memory map and was not executed. Target cycle measurements remain open.
[qualification.json](qualification.json) records tests, commands and preservation
of all88 prior model-pass artifacts,98 first-CPU-pass artifacts,83 baseline
artifacts and68 original Foster artifacts.

## Use and rerun

Stage2 is the default workspace variant; stage1 selects structured arithmetic
only; stage0 rebuilds the previous version for comparison.

```bash
python3 -B -m experiments.foster_c_history_001.build
python3 -B -m experiments.foster_c_baseline_001.run \
  --binary experiments/foster_c_history_001/build_host_2/baseline.so \
  --case experiments/foster_cccv_stimulus_001/cycle001/case_0000 \
  --out experiments/foster_c_history_001/my_replay
```

Use a fresh output directory. The campaign runner's default backend is unchanged.
C callers must rebuild with this experiment's [baseline.h](baseline.h), since the
context members now include phase unions. The Python replay adapter uses the
context-size query and works with the new library.

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python3 -B -m experiments.foster_c_history_001.qualify
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python3 -B -m experiments.foster_c_history_001.benchmark \
    --out experiments/foster_c_history_001/my_benchmark --repeats 3
```

Next memory work should address persistent/evaluation payload sizes—particularly
full transport matrices and covariance-root storage—while preserving all cross
terms and verifying any required re-triangularization. Target cycle measurement
remains necessary; further host speed gains alone do not establish M23 readiness.
