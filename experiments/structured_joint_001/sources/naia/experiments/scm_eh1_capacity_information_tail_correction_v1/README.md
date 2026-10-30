# SCM Q reference-tail correction — local static candidate

**Not published, imported, tested, built, or executed during preparation.** No corrected matrix result exists. The original failed run and all frozen sources are unchanged.

## What changes

A small additive scorer wrapper uses a source-derived sign-preserving real-ODE enclosure for sufficiently tiny polarization tails of the **entire zero-current arm**. Both frozen cells are supported. The exact source-index gates are p1 at frame 2,688 and p2 at frame 26,875; p3 never reaches this conservative gate within the fixed 40,950 frames. A complete analytic enclosure must be contained in the unchanged estimator interval. Overlap is inconclusive, not a pass. There is no numerical epsilon, truth-centering, reference snapping, or estimator-bound adjustment.

Raw DOP853 points, public observations, bounds, source order and original point-outside counts stay intact. Every eligible tail coordinate uses the policy prospectively, even if its raw point already lies inside. Other coordinates and informative arms retain the original **numerical point-consistency** check, not a validated whole-trajectory claim. New summaries explicitly distinguish raw misses, certified subset/disjoint decisions, and reference-limited overlaps. Diagnostic JSONL files are capped at 256 events per chunk; canonical raw trajectory chunks remain unchanged.

See [TAIL_CERTIFICATE.md](TAIL_CERTIFICATE.md) for the signed-boundary thermal invariant, compact upper invariant/existence argument, rational tau and exponential bounds, exact binary64 representation threshold, full source premises, and limitations.

## Economical, conservative completion

1. Verify immutable original probe/dependency and all 156 published evidence files plus the original evidence manifest. Verify complete source snapshots, prior receipt chains and original failure.
2. Owner runs the new stdlib correction tests and saved-data audit. Reproduce the complete frozen score summaries, then rescore saved A informative and the failed A control prefix without an estimator/reference call.
3. Import A informative's complete 40,950-frame result as **historical owner evidence, newly read-only audited**. Do not rerun it or retroactively relabel the old matrix.
4. Rebuild the same native binary on the original interpreter/environment, checking exact hash/flags and a fresh runtime floating-environment guard. Reuse the exact old structural/reference/benchmark receipts only through explicit old-to-new compatibility checks. These old receipts are historical readiness/numerical consistency, not validation of the new scorer; the new CHECKS receipt supplies that separate check.
5. Execute **A zero-current from the original prior**, then B informative, then B zero-current. No snapshot restore, continuation splice, hidden retry, extra benchmark, threshold search, or stimulus change. Stop after any invalid/incomplete/inconclusive arm.
6. Each fresh arm regenerates its complete numerical primary trajectory and must match the original reference receipt's state-array hash before the first estimator step. A control's first 27,148 complete raw rows (including all estimator fields) must additionally match the old prefix bit-for-bit.
7. Only if all imported/new gates and final source/native/input checks pass may the new summary say `PASS_COMPOSITE_EXECUTION`. It separately reports the Q research outcome. Neither that status nor an analytic tail subset closes N03 or physical/indefinite/M23 qualification.

### Cost and tradeoff

- Read-only audits: **0** new estimator updates or reference integrations.
- Three new complete arms: **122,850** estimator updates and **3** primary reference integrations (**9** piecewise solver calls; **122,850** postinitial reference frames).
- Of those updates, **27,148** repeat the failed A control prefix. Its remaining 13,802 frames and both B arms contribute 95,702 previously unexecuted updates.
- A informative's 40,950 successful updates and the eight old primary/tighter reference integrations are not repeated. No 100-frame benchmark is added.
- One explicit owner native build plus correction unit/adversarial checks. Runtime is not promised.

The failed control snapshot records a committed step and nontrivial retained rows/pairs, counters and thermodynamic transport state. The frozen `restore()` has integrity checks, but the old `run_arm()` is not a resume interface. Splicing a scorer, reference trajectory, chunk history and milestone state would create a new unvalidated recovery workflow. A fresh control-only rerun is deliberately less economical than resume, but materially simpler and preserves the successful informative result.

## Source shape and verification scope

`run_completion.py` invokes the exact locked frozen `run_arm()` and injects only a per-arm Scores factory; a transparent integrate wrapper counts calls without changing arguments/results. `scoring.py` composes the untouched raw scorer and a separate effective decision map. `saved_point_scores.py` copies only the frozen Scores class to enable stdlib read-only audit without importing NumPy/SciPy/estimator/plant code; the owner checks its text equality. Complete case/protocol hashes reject unsupported changes before any normal nonapplicability fallback.

`INPUT_LOCK.json` binds historical sources/evidence. `SOURCE_MANIFEST.json` binds this new package. `owner_tools/prepare_run.py` copies all three source trees into separate runtime and archived snapshots. No old receipt is edited to spoof a new manifest hash. An environment/source/native mismatch stops the workflow and requires a new review, not silent receipt reuse.

The included owner checks cover oracle arithmetic, applicability, source-byte tampering, both signs, zero/subnormal semantics, thresholds, overlap/disjoint/subset, wrong current/rate/index, altered initial/boundary/physical parameters, unchanged raw rows, and preserved raw misses. Runner lifecycle gates (interpreter/native/receipt mismatch, existing-output refusal, stop-after-arm-failure and composite accounting) have **static review only** in this candidate; no end-to-end or stub lifecycle test execution is claimed. Owner tests and the new experiment remain pending.

Use [OWNER_RUN.md](OWNER_RUN.md) only after source publication and execution are separately authorized. Preparation of this candidate is not that authorization.
