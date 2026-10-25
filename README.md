# mumble

C research reference for battery estimation from a 35 Hz voltage/current stream.

The goal is to **estimate what the available stimulus supports, retain earlier
evidence, and explicitly report what remains unknown**. The longer-term target
is a streaming Cortex-M23 implementation. The original nonlinear fitting path
retains and replays history. A new bounded event component preserves a fixed
local affine likelihood. A bounded nonlinear-remainder component now checks
trial moves against a declared analytic error budget. Cold-start learning,
historical relinearization and validated floating-point bounds remain open.
These components are host references, without Cortex-M23 qualification.
Numerical stability for indefinite runtime is an explicit proof gate. A new
conditional battery provider now combines exact integer charge, outward RC and
OCV enclosures, fixed capacity bins with contracting initial-SOC intervals,
and outward current-SOC/capacity queries. Eight reviewed arguments establish
containment, evidence retention and whole-observation transactions. For the
declared static model, capacity domain and admitted physical trajectory, a
composed proof establishes successful operation at every finite prefix without
age-driven range failure or loss of true support.

The small frozen experiment learns capacity, retains it through quiet use and
learns further after renewed excitation. It passes 45,408 top-level checks and
7,615 nested assertions, with overlapping summary gates disclosed. Its complete
owned objects and loose own-source stack total 3,248 host bytes. These results
assume known fixed RC/OCV, exact represented current/time and supplied hard
voltage bounds. Physical error validation, the original sixteen-unknown
estimator, drift/recovery and complete Cortex-M23 qualification remain open.

## Start here

| Resource | Contents |
| --- | --- |
| [Conditional battery provider](docs/BATTERY_CERTIFICATE_003.md) | Composed all-prefix proof, retained SOC/capacity learning, comparison and complete owned-memory accounting |
| [Current provider contract](proofs/indefinite_stability_003/contract.json) | Restricted model, integer units, ranges, observation semantics and open gates |
| [Provider lemma ledger](proofs/indefinite_stability_003/lemmas.json) | Eight arguments plus composed conditional availability |
| [Provider audit receipt](experiments/indefinite_stability_003/receipt.json) | Frozen short experiment, exact oracle, boundary canaries, retained-history comparison and resources |
| [Implemented stability contract and lemmas](docs/STABILITY_CONTRACT_002.md) | Exact integer kernels, all-prefix induction arguments, conditional finite evidence semantics and scoped host memory |
| [Inherited arithmetic contract](proofs/indefinite_stability_002/contract.json) | Concrete inputs, arithmetic, retention semantics and historical integration gates |
| [Arithmetic lemma ledger](proofs/indefinite_stability_002/lemmas.json) | Six claims, premises, source correspondence and limits |
| [Integer audit receipt](experiments/indefinite_stability_002/receipt.json) | 3,588 passing exact-reference checks; finite falsification, not an endurance proof |
| [Indefinite numerical stability](docs/INDEFINITE_NUMERICAL_STABILITY_001.md) | Lifetime proof contract, conditional invariants, finite-state limitations and seven small counterexamples |
| [Earlier proof contract](proofs/indefinite_stability_001/contract.json) | Preserved initial acceptance gates and evidence/arithmetic questions |
| [Nonlinear remainder experiment](docs/BOUNDED_EVENT_002.md) | Sparse joint-parameter bound, useful conditional tail trial, conservative region failure, preserved arithmetic failures and full memory costs |
| [Remainder receipt](experiments/bounded_event_002/receipt/receipt.json) | 654/672 unchanged checks pass; 18 near-roundoff prediction-norm failures retained and diagnosed separately |
| [Bounded event experiment](docs/BOUNDED_EVENT_001.md) | Fixed-memory C evidence design, complete host memory accounting, successful local carry and explicit failure witnesses |
| [Corrected bounded receipt](experiments/bounded_event_001/receipt_scaled_givens/receipt.json) | 72 passing checks; original failed receipt retained separately |
| [Implementation guide](README.txt) | Model, units, constraints, interfaces, assumptions and reproduction commands |
| [Study report](report/SCM-35Hz-Results.html) | Self-contained HTML report; download and open locally |
| [Convergence figure](report/SCM-35Hz-Convergence.png) | Stimulus and six-run error versus elapsed physical time |
| [Knowledge figure](report/SCM-35Hz-Knowledge.png) | Per-target unexcited, unresolved and provisional statuses |
| [Project state](PROJECT_STATE.json) | Compact machine-readable checkpoint and next work |
| [Continuation handoff](handoff/CONTINUE.json) | Repository-based instructions and context for the next agent |
| [Study specification](specification.json) | Experiment contract |
| [Input manifest](data/manifest.json) | Six traces, truth for scoring, stimulus and input hashes |
| [Results](results/) | Frozen fit outputs, profiles, compression comparison and verification receipts |
| [Import provenance](provenance/) | Original release hashes and repository portability checks |

## Current roadmap

| Milestone | Status and next boundary |
| --- | --- |
| Retained-history 35 Hz reference | Completed and preserved; sixteen unknown quantities, synthetic matched-model evidence |
| Bounded Gaussian event summaries | Fixed affine evidence and conditional nonlinear remainder implemented; historical relinearization and floating-point validation remain open |
| Indefinite-runtime arithmetic contract | Integer charge, attenuation and state enclosures proved under declared inputs; finite-state limitations recorded |
| Conditional battery certificate provider | Implemented and reviewed; retained capacity learning, outward queries and composed conditional availability demonstrated |
| Bounded model uncertainty | Next: one uncertain RC mode with a fixed R/tau box, sound forcing/coefficient bounds and a useful all-prefix width recurrence |
| Complete deployment | Full unknown model, input-error validity, drift, delivery/recovery and target resources remain open |

## Build and run

The C executable needs a C99 compiler, `make` and `libm`. Python is only needed
for the combined test target, orchestration, independent validation and plots.
The separate integer provider test, `make test-certificate`, links without
libm and is also included in `make test`.

```bash
git clone https://github.com/tumblewhead/mumble.git
cd mumble
make

python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements-reference.txt
make test

./build/scm_estimator \
  --data data/cell_a_35hz_s202610240.csv \
  --case cell_a_35hz_s202610240 \
  --modes 3 --method full --sigma 0.001 \
  --starts 3 --max-iter 120 --prefix 31500
```

The example fits the first 900 seconds and prints estimates and uncertainty
qualification as JSON. Sample index is the ordering authority, with an explicit
interval in seconds. Positive current discharges; current is measured in A and
voltage is sampled at the end of each constant-current interval.

Use `--ocv path/to/ocv.csv` for a measured 25 C curve with columns `z,voltage`.
The included benchmark uses a known illustrative curve because the numerical
measured curve was not supplied. It must not be described as real-cell validation.

## Completed 35 Hz study

The main campaign contains two synthetic cells, three noise seeds per cell,
73,500 samples per trace, and ten chronological prefixes: **60 fits**. All
sixteen model quantities, including entering states, are unknown to fitting.
Truth enters independent scoring only.

| Result across six runs | Observation |
| --- | --- |
| Current SOC error below 0.5 percentage points | From the 600 s checkpoint onward |
| Capacity error below 0.5% | From the 900 s checkpoint onward |
| Every resistance and RC time constant below 10% point error | By the 220 s checkpoint |
| Worst final current-SOC error | 0.00350642 percentage points |
| Worst final capacity error | 0.0163354% |
| Numerical stopping status | 50 converged; 10 iteration limits |

“From” means the first tested checkpoint passing the threshold at that and every
remaining tested checkpoint. These are stimulus-specific results under a matched
25 C model, exact current/time, known OCV, and independent 1 mV Gaussian noise.
Local precision and truth accuracy are reported separately. Some R0 and fastest
pole estimates remain unresolved despite useful SOC/capacity estimates.

![35 Hz convergence](report/SCM-35Hz-Convergence.png)

The supplemental event-local comparison retains 723 one-anchor features or
1,442 five-anchor features from 73,500 voltage samples, across 106 event blocks.
Both preserve close fits in the two tested traces. Explicit basis storage still
costs megabytes and increases CPU time. Small feature payload is not complete
firmware memory consumption.

The final quiet-window control shows why earlier evidence matters. A complete
history fit retains useful SOC/capacity estimates; a fit to the last weak-use
window alone remains unresolved despite a similar voltage RMSE.

## Reproduce or inspect

Included results can be inspected without repeating optimization. To regenerate
the study, see [README.txt](README.txt). These commands overwrite their named
generated outputs, so use a work branch when making a new campaign:

```bash
git pull --ff-only
git switch -c experiment/my-next-study
make
make test
OPENBLAS_NUM_THREADS=1 python3 tools/run_streaming.py --workers 3
OPENBLAS_NUM_THREADS=1 python3 tools/run_profiles.py --workers 3
OPENBLAS_NUM_THREADS=1 python3 tools/run_compression.py
MPLCONFIGDIR=/tmp/mumble-mpl python3 tools/make_report.py
git status --short
```

Record the source revision, commands, assumptions and validation before committing
new results. Keep machine-to-machine handoffs compact JSON. Source and evidence
belong in this repository; chat summaries are supporting context.

## Implementation map

- `src/scm_model.c`, `include/scm_model.h`: chronological state propagation and sensitivities.
- `src/scm_features.c`, `include/scm_features.h`: orthogonal projections.
- `src/scm_estimator.c`, `include/scm_estimator.h`: host variable-projection estimator.
- `src/scm_assess.c`, `include/scm_assess.h`: fixed-workspace per-target qualification.
- `src/scm_evidence.c`, `include/scm_evidence.h`: bounded fixed-chart event evidence and guards.
- `src/scm_remainder.c`, `include/scm_remainder.h`: paired chronological ingestion and sparse analytic nonlinear-remainder budget checks.
- `src/scm_stable.c`, `include/scm_stable.h`: proved integer charge, attenuation, scalar-state and finite-mask kernels.
- `src/scm_certificate.c`, `include/scm_certificate.h`: conditional battery certificates, contracting SOC0 intervals and outward SOC/capacity queries.
- `src/main.c`: CSV/JSON host CLI.
- `tests/`: model, estimator, projection, constraint and qualification checks.
- `tools/`: data generation, runners, independent scoring and report construction.
- `reference_binaries/`: preserved Linux x86-64 executables for exact study provenance;
  build the source for your own host. These are not MCU images.

## Next work and limits

The current priority is extending the [conditional provider](docs/BATTERY_CERTIFICATE_003.md)
to one fixed uncertain RC mode. Its R/tau box needs outward forcing and
coefficient bounds, a width recurrence valid for every finite prefix, and a
small test that exposes any loss of SOC/capacity precision. The present provider
already supplies sound target queries, retained conditional learning and an
in-memory observation transaction under its known-parameter and hard-error
contract. Physical justification of those premises, full-model composition,
chronology/delivery, recovery and chart/parameter transport remain open.

Finite certified constraints do not claim Gaussian likelihood equivalence.
The Gaussian reference and earlier local evidence remain unchanged. A finite
replay or memory bound cannot replace proof obligations; no lifetime horizon
is substituted for indefinite operation.
Subsequent experiments should cover measured OCV, sensor
offsets, filtered/correlated noise, model mismatch and parameter drift. The current
study does not validate aging, temperature variation, EOD prediction, or Cortex-M23
latency, SRAM, flash or power. The requested 35 Hz operating point was tested;
20 Hz and 1 kHz comparisons remain separate work.

## Indefinite-runtime stability proof gate

The initial review separates numerical safety, fidelity, earlier-evidence
retention and conditional usefulness. It proves conditional time-uniform
error lemmas for dissipative states and bounded exact quantized charge,
and finite-state obstructions to unrestricted all-history likelihood
and empirical-mean accuracy. The existing Gaussian C/libm estimator remains
outside a full lifetime proof.

A preregistered small experiment reproduces seven mechanisms, including
absorbed increments in the production QR and remainder updates and atomic
rejection at the counter limit. These are scalar or deliberately constructed
API boundary states; no deployed-lifetime or physical-history reachability
claim is made. All seven reproduced mechanisms are counterexample evidence,
not a passing indefinite-stability result.

Read the [proof report](docs/INDEFINITE_NUMERICAL_STABILITY_001.md) and
[claim ledger](proofs/indefinite_stability_001/claims.json).
The [second checkpoint](docs/STABILITY_CONTRACT_002.md) selects a concrete
finite-certificate research contract and implements libm-free integer kernels.
Its source-level proofs cover exact bounded charge, outward attenuation,
invariant scalar-state enclosures, conditional uniform interval width, exact
historical cell retention and conditional eventual refinement. The audit checks
these against exact rational/integer references. Written proofs are independently
reviewed, without a machine-checked C or compiler-correctness claim.

The [third checkpoint](docs/BATTERY_CERTIFICATE_003.md) supplies the restricted
battery producer and target query that were open at stability002. It composes
the integer kernels with immutable capacity bins and contracting SOC0 ranges,
proves whole-observation transactions, and closes conditional all-prefix
availability and containment for its declared static physical domain. A frozen
informative/quiet/renewed-excitation experiment demonstrates retained capacity
learning while keeping unexcited capacity explicitly unresolved.

The existing 35 Hz, B001 and B002 results and their interpretations remain
unchanged. Full-model uncertainty, physical premise validation, delivery and
recovery, coverage and Cortex-M23 qualification remain open. The historical
68-byte primitive subtotal is superseded for this provider by 2,128 bytes of
complete owned objects plus 1,120 bytes of loose own-source stack, still short
of a complete firmware memory account.

## Bounded event prototype

`scm_evidence` consumes each actual interval/current/voltage observation once,
carries model state and sensitivities across events, and merges event-local
augmented QR factors into one aggregate. It retains no sample history or
explicit Q basis. Source/index checks prevent duplicate ingestion in a live
bank. Parameter-radius, physical-domain and residual diagnostics expose
unsupported updates without deleting evidence.

The corrected small experiment preserves the reference's unresolved 400 s
SOC/capacity status, reproduces informative 900 s local precision and carries
earlier information through the final quiet tail. All 72 checks pass. The
nominal-chart control fails: local rank/precision alone cannot qualify a
poorly placed nonlinear model. A separate inside-radius witness shows that
the current radius is not a nonlinear likelihood-error certificate.

On this host, the persistent bank plus update workspace uses 7,512 bytes;
the simultaneous snapshot/diagnostic/solve objects bring that subtotal to
18,408 bytes before additional configuration, input, stack and runtime costs.
The complete approximately 10 KiB subsystem target is not achieved.

```bash
make build/scm_evidence_probe test-evidence evidence-stack
OPENBLAS_NUM_THREADS=1 python3 tools/run_bounded_event.py \
  --output-dir experiments/bounded_event_001/my_new_receipt
python3 tools/measure_bounded_memory.py \
  --probe-result experiments/bounded_event_001/my_new_receipt/carry_1800_to_2100.json \
  --output experiments/bounded_event_001/my_new_memory.json
```

Both helpers refuse existing outputs. The original 60-fit campaign is not
needed to reproduce this small experiment. Read the
[design and results](docs/BOUNDED_EVENT_001.md) before treating local evidence
as a nonlinear estimate.

## Nonlinear remainder prototype

`scm_remainder` retains 19 sparse Hessian-envelope norms and bounded propagation
state on the original joint chart. It advances through the same atomic paired
ingestion as the evidence bank. It supports the smooth illustrative OCV and
reports a real-arithmetic prediction/NLL error bound; ordinary double arithmetic
is explicitly unvalidated.

At the final quiet tail, the conditional SOC/capacity trial has an analytic
NLL-error bound of 0.0041192 and an upper-cost improvement of 0.1314269 under
the declared 0.1 budget. The full joint step and every whole-region guarantee
remain over budget. Earlier unresolved directions remain unresolved; the
nominal bad-chart control allows no update. No trial is applied or used to
reset the chart.

The four-run receipt retains 18 failed prediction-norm checks near machine
precision at already fitted anchors. Separate higher-precision diagnostics
investigate that floor without changing the original result or tolerances.
All original NLL-error gates pass. The paired ingestion objects use 9,912 bytes,
and the listed project stack plus input raises that partial total to 10,672
bytes before external costs. The full diagnostic object set uses 20,856 bytes.

```bash
make test-remainder build/scm_remainder_probe
python3 tools/run_remainder.py \
  --output-dir experiments/bounded_event_002/my_new_receipt
python3 tools/measure_remainder_memory.py \
  --probe-result experiments/bounded_event_002/my_new_receipt/carry_1800_to_2100.json \
  --output experiments/bounded_event_002/my_new_memory.json
```

The runner's nonzero exit records the preserved numerical failures on this
host. Read the [remainder report](docs/BOUNDED_EVENT_002.md) and selective
evidence links before interpreting an analytic-budget pass as qualified
machine arithmetic, nonlinear convergence, or validated coverage.

The original study release manifest is preserved in
[`provenance/study_release.json`](provenance/study_release.json). The original
import adapted documentation and verification-helper paths. The later bounded
prototype is recorded separately; original study outputs and numerical
reference sources remain preserved.
