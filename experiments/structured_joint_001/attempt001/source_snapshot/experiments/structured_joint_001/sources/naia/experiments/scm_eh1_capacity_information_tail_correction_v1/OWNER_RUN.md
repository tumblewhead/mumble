# Owner handoff — draft only, do not execute yet

**This correction is local source preparation only. Publication and owner execution require separate authorization.** These commands are for the later published package, not permission to run now. No test/import/build/simulation occurred during preparation. Keep the old failed run and all successful A informative artifacts unchanged.

The selected plan audits saved A, then executes only **A control from its original prior, B informative, B control**. New full work is 122,850 estimator updates, three primary integrations/nine piecewise solver calls, plus one native build and the new correction checks. The original A control prefix (27,148 updates) is intentionally repeated rather than restored. There is no new benchmark or repeated primary/tighter reference campaign. See README for why source snapshots are not an approved resume interface.

## 0. Shell and interpreter safety

After publication/execution authorization, open a disposable child shell with this command alone:

```bash
bash || true
```

Activate the same `naia-env` inside the child, using the owner's normal activation command. Do not install into system Python or silently substitute an environment. Continue in that child so all variables survive; if it exits, preserve the printed path and report the failure rather than pasting later sections into the parent.

```bash
set -euo pipefail
unset PYTHONOPTIMIZE PYTHONPATH SCM_NATIVE_DISABLE
export PYTHONDONTWRITEBYTECODE=1
PYTHON=$(python3 -c 'import sys; print(sys.executable)')
[[ "$PYTHON" = /* && -x "$PYTHON" ]] || { echo 'STOP: absolute executable interpreter required'; exit 1; }
cd /home/easy/proj/naia-scm-run
REPO=$(pwd -P)
[ "$(git branch --show-current)" = SpanishCastleMagic ] || { echo 'STOP: wrong worktree'; exit 1; }
[ -z "$(git status --porcelain)" ] || { echo 'STOP: preserve dirty worktree'; exit 1; }
git pull --ff-only origin SpanishCastleMagic
# Fill these with the actual reviewed publication handoff; no such commit exists yet.
APPROVED_SOURCE_COMMIT='<approved published correction commit>'
APPROVED_MANIFEST_SHA256='<approved correction SOURCE_MANIFEST SHA-256>'
PKG="$REPO/experiments/scm_eh1_capacity_information_tail_correction_v1"
[ -f "$PKG/SOURCE_MANIFEST.json" ] || { echo 'STOP: correction has not been published'; exit 1; }
RUN_ID="owner_capacity_tail_$(date -u +%Y%m%dT%H%M%SZ)"
RUN=$(mktemp -d "${TMPDIR:-/tmp}/${RUN_ID}.XXXXXX")
printf 'Run: %s\nRun ID: %s\nPython: %s\n' "$RUN" "$RUN_ID" "$PYTHON"
"$PYTHON" -B "$PKG/owner_tools/prepare_run.py" --repository "$REPO" --run-root "$RUN" --run-id "$RUN_ID" --approved-source-commit "$APPROVED_SOURCE_COMMIT" --approved-manifest-sha256 "$APPROVED_MANIFEST_SHA256"
CORRECTION="$RUN/runtime/correction"
DEPENDENCY="$RUN/runtime/dependency"
export MPLCONFIGDIR="$RUN/cache/matplotlib"
export XDG_CACHE_HOME="$RUN/cache"
```

Preparation first requires the actual approved published commit and manifest pins (placeholders fail closed), then requires original interpreter executable/prefix/base-prefix/full version, verifies frozen source/evidence bytes and exact snapshots, and creates new source copies. No old run file is rewritten. Runtime inventories reject unlisted source files. Unsupported interpreter or source changes require review; do not edit locks to bypass them.

## 1. Execute new correction checks and read-only saved-data audit

```bash
CHECK_STATUS=0
"$PYTHON" -B "$CORRECTION/owner_tools/check_correction.py" --run-root "$RUN" > "$RUN/checks_stdout.log" 2>&1 || CHECK_STATUS=$?
cat "$RUN/checks_stdout.log"
printf 'Checks exit: %s\nPreserve: %s\n' "$CHECK_STATUS" "$RUN"
```

Inspect `CHECKS.json`, `audit/informative.json`, and `audit/zero_current.json`. These are owner-executed stdlib checks and saved-data arithmetic, **not** estimator updates or reference integration. The old A informative complete raw score summary must reproduce exactly. The failed control prefix must reproduce its raw point miss separately from the new analytic subset result. Its old arm/matrix status remains FAIL/incomplete. `CHECKS.json` must say `PASS` before continuing; otherwise skip to export and stop. No automatic retry or threshold adjustment.

The included executable checks cover certificate/scorer adversaries. Runner lifecycle is statically reviewed, not dynamically validated by this test suite; no complete correction run has yet been observed.

## 2. Explicit native build and provenance

Only after passing checks:

```bash
cd "$DEPENDENCY"
BUILD_STATUS=0
SCM_NATIVE_DISABLE=1 "$PYTHON" -B -m joint_estimator_v3.native_kernels --build > "$RUN/native_build.log" 2>&1 || BUILD_STATUS=$?
cat "$RUN/native_build.log"
printf 'Build exit: %s\n' "$BUILD_STATUS"
```

If the build failed, export and stop. If successful:

```bash
HOST_STATUS=0
"$PYTHON" -B "$DEPENDENCY/owner_tools/record_host.py" --output "$RUN" > "$RUN/host_stdout.log" 2>&1 || HOST_STATUS=$?
cat "$RUN/host_stdout.log"
printf 'Host receipt exit: %s\n' "$HOST_STATUS"
```

If the host receipt failed, export and stop. The exact old native source/binary/flags are required, with a fresh native environment guard. NumPy/SciPy must match the original used runtime; full interpreter identity remains pinned. Current host/kernel are recorded, not required identical. Matplotlib is unused by the runner and its old version is provenance, not a scientific compatibility gate; the inherited host-recording utility still imports it. Missing optional tooling is a reported setup blocker, not permission to install/change environments or weaken the reuse contract.

## 3. Execute only the three missing complete arms

After reviewing successful checks and native provenance, this is the **separate explicit scientific execution command**:

```bash
COMPLETE_STATUS=0
"$PYTHON" -B -u "$CORRECTION/run_completion.py" --run-root "$RUN" > "$RUN/completion_stdout.log" 2>&1 || COMPLETE_STATUS=$?
tail -n 30 "$RUN/completion_stdout.log"
printf 'Completion exit: %s\nPreserve run: %s\n' "$COMPLETE_STATUS" "$RUN"
```

The order is A zero-current, B informative, B zero-current. Each uses the unchanged frozen `run_arm()` and starts from the original prior. The full regenerated primary reference must match its original recorded array hash **before** the first estimator step. A control's first 27,148 complete raw rows must also match the prior prefix bitwise, including reference, public measurements, estimator intervals/status, and diagnostics.

The new scorer applies whole-enclosure containment at every eligible tail, not only at a point miss. `REFERENCE_LIMITED_OVERLAP` stops as inconclusive; `CERTIFIED_DISJOINT` stops as a model-conditional exclusion. Neither is repaired with an epsilon. An invalid arm stops later arms. Existing output/check directories refuse overwrite. Interruptions preserve snapshots/chunks and record unknown update totals when a result did not return, rather than pretending zero work occurred. No resume/retry is supplied.

Inspect `completion/SUMMARY.json` and each `CORRECTED_SUMMARY.json`. `PASS_COMPOSITE_EXECUTION` requires complete audited inherited A informative, all three new full arms and all original integrity/domain/control/witness/nonwidening gates, source/native/input stability, plus the added prefix-continuity gate. Q research success is a separate field. A valid no-Q-information result is scientifically inconclusive, not a reason to repeat the run. The original matrix remains `INVALID_OR_INCOMPLETE_RUN` regardless of the new outcome.

## 4. Export locally, including failures; no automatic publication

This export does not stage, commit, push, delete, or replace anything. It includes all new output/failure/log/native/source-snapshot files, excludes redundant runtime/caches, and records stored/logical CSV hashes. Inherited evidence is bound to its immutable published commit and manifest rather than duplicated. A failed run is just as exportable as a successful one once preparation wrote its marker.

```bash
EXPORT="${RUN}-export"
"$PYTHON" -B "$CORRECTION/owner_tools/export_run.py" --run-root "$RUN" --export-root "$EXPORT"
printf 'Local evidence export: %s\n' "$EXPORT"
```

Send the export location and completion/check status for review, or use the separately authorized selective publication route below. Do not reuse the old experiment's export/stage helper against this new schema. If preparation failed before its marker, preserve the scratch directory and terminal output and report the exact failure. Do not rerun commands to overwrite evidence or choose a different reference/threshold until a reviewed plan exists.

## 5. Optional authorized evidence publication — draft commands, not executed now

If the later source/run authorization includes returning the evidence by commit/push, use this section in the same child shell after export. This is the complete selective stage–audit–commit–push route; it does not require another preparation round. Without publication authorization, stop at the local export above. Failed evidence may be published for review without calling it a pass.

The helper requires clean tracked/staged state on `SpanishCastleMagic`, verifies the fresh remote ref equals local HEAD, refuses an existing destination, copies only the verified export into this correction package's new `owner_evidence/<run_id>` directory, stages only individually enumerated manifest files, and checks every staged byte. It does not run the estimator, commit or push.

```bash
cd "$REPO"
"$PYTHON" -B "$CORRECTION/owner_tools/stage_evidence.py" --repository "$REPO" --export-root "$EXPORT"
"$PYTHON" -B "$CORRECTION/owner_tools/stage_evidence.py" --repository "$REPO" --export-root "$EXPORT" --audit
git -C "$REPO" diff --cached --stat
git -C "$REPO" commit -m "Record SCM Q tail correction evidence $RUN_ID"
git -C "$REPO" push origin HEAD:SpanishCastleMagic
git -C "$REPO" rev-parse HEAD
```

If a command fails or push is rejected, preserve the export/staged state/local commit and report the exact error. Never force-push, reset, clean, broadly add a directory, or rebase unrelated work to make it go through. Send the resulting commit SHA for independent saved-data review. Publication and successful process exit are not scientific acceptance; every raw miss, failed arm and qualification limit remains visible.
