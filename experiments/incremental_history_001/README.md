# Incremental history token and exact elimination reference

The first prior-free chronological token is implemented, with **1,289 finite
checks passing**. It compacts history exactly in real arithmetic for a declared
linear-Gaussian model, while preserving evidence ownership, covariance cross
terms and normalization. This advances P1/P2 of the
[ten-year roadmap](../../proofs/ten_year_history_001/roadmap.json); nonlinear
battery closure and integration into the C rolling solver remain open.

The [derivation](derivation.md) defines the operator and proves its composition
formula. [token.py](token.py) implements immutable tokens, read-only prior
queries and a fixed-capacity rolling retirement queue. The
[registered plan](plan.json), [passing receipt](attempt002/result.json) and
[summary](summary.json) record the scope and limitations.

Each token retains the likelihood of the interval's entering state and the
exit-state distribution conditional on those observations. This allows old
states to be integrated out. It does not turn a rolling point estimate or its
curvature into new evidence. The prior is supplied separately at query time.

Only adjacent intervals from the same immutable source/model/noise/calibration
contract can compose. Actual integer ticks, sequence order, signed charge and
absolute throughput are carried explicitly. A zero interval still advances the
sequence. The queue offers one new observation at a time and retires only a
prefix; failed operations preserve ownership. Queries combine retired history
and pending observations in scratch without advancing either cursor.

## What the finite tests establish

Twenty-four vector cases cover deterministic, rank-deficient and full-rank
process covariance. Their reference builds the entire joint Gaussian from
independent driving variables and conditions it in one batch; it does not use
the token composition routine. Sequential filtering provides another check.

| Comparison or control | Result |
| --- | --- |
| Composed token versus independent batch, mean/covariance/log evidence | Maximum absolute difference 8.53e-14 across these differently scaled quantities |
| Two chronological parenthesizations | Maximum coefficient difference 1.42e-14 |
| Overlapping rolling queries versus batch | Maximum absolute difference 8.53e-14 |
| 4,096 stationary repeated observations | Same summed information coefficients; evidence-constant roundoff 1.38e-10 |
| Duplicate evidence, source/model/noise/calibration mismatch, gaps and reversed order | Rejected |
| Query immutability and retirement failure after partial scratch work | Preserved ownership and state |
| Quiet unobserved direction | Retains uncertainty, adding only the supplied process covariance |
| Correlated, indirectly observed direction | Correction and covariance coupling retained |
| Deterministic or singular transition | No artificial process noise added |

The comparison tolerance `2e-10 + 2e-10*abs(reference)` is a finite host
regression allowance, not a battery accuracy threshold. The repeated-event
control uses zero elapsed ticks to isolate likelihood accumulation; it is not
a physical aging trajectory or a maximum-rate assumption. The suite took
approximately **1.16 CPU seconds**, with **53.9 MB peak host RSS**. These are
small qualification costs, not rolling-estimator or MCU throughput benchmarks.

The initial run retained **1,240 passes and one failed case**. Subtracting
nearly equal information matrices caused 2.13e-14 of asymmetry, beyond the
1.71e-14 arithmetic guard. An equivalent linear solve repairs the cancellation
without changing the guards or test tolerances. The original results, exact
source snapshots and diagnostic are preserved in [attempt001](attempt001/result.json)
and [development_review.json](development_review.json). This was self-review,
not an independent review.

## Aging and the error model

In this closed family, a quiet identity transition with uncertainty W changes
covariance P to P+W. Old information therefore becomes less precise about the
current state through an explicit transition. There is no history discount
factor. W and all transition matrices are supplied fixture assumptions; this
does not estimate or calibrate battery aging rates. Metadata exposure does not
automatically define W, and some algebraic fixtures allow positive W at zero
elapsed time. A physical aging producer will need its own interval-dependent
law and validation.

The admitted model's representation defect is zero in real arithmetic.
Floating-point error and discrepancy from a battery are explicitly unresolved.
In particular, on unbounded Gaussian support a small mean/covariance change
can have infinite log-density-oscillation distance. Moment comparisons cannot
be substituted for a lifetime bound in that strong metric. A battery domain
or alternative query metric needs a separate propagation proof.

## Storage and next gate

| Object | Numeric storage |
| --- | ---: |
| Packed 3-state token | 224 B |
| Packed 16-state token, including two-boundary transport and evidence | **4,488 B** |
| Packed 16-state Gaussian prior | 1,216 B |
| Packed token plus prior | **5,704 B** |
| Actual dense Python-array payload per 16-state token | 6,408 B |
| Five dense tokens: history plus capacity-4 pending queue | 32,040 B |

Metadata, query outputs, solves, temporary composition objects, Python overhead
and the existing rolling estimator are additional. The packed layout is an
estimate, not an implemented codec. The Python reference does not fit the
complete 10,240-B target. The earlier 2,544-B research posterior is a different
object and has not been replaced or combined with this token.

The next gate is **P3: derive closure for the partitioned battery operator**.
For each OCV, RC, hysteresis and health component, identify what remains exact
conditional on nonlinear parameters, which mixed terms must be retained, and
where elimination introduces functions outside the chosen representation.
Choose a supported domain/query-error definition before approximating those
functions. RC aging still needs an explicit state-continuity convention;
`C_i=tau_i/R_i` and the proposed 0.5–1.5 envelope do not supply it. The C token
producer, complete SRAM proof, calibrated aging model, long-duration behavior
and coverage are not qualified by this prototype.

To rerun into a new directory from the repository root:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -B -m experiments.incremental_history_001.qualify /tmp/mumble-incremental-new
```

The destination must not exist; the harness snapshots its sources, collects
failures across independent cases and exits unsuccessfully if any check fails.
