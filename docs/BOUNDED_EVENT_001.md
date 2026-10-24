# Bounded event evidence: first design and falsification

## Outcome

A new allocation-free C component preserves the complete **fixed local affine
voltage likelihood** while consuming samples chronologically and retaining no
raw sample history or explicit projection basis. It preserves useful earlier
SOC/capacity information through the tested quiet tail and keeps unsupported
quantities unresolved. It is a bounded evidence representation, **not yet an
autonomous bounded nonlinear estimator**.

The corrected four-run experiment passes all 72 declared executable checks.
The original failed run is also retained: it exposed a subnormal-arithmetic
defect in QR rotations, which was repaired without changing tolerances.

| Evidence | Location |
| --- | --- |
| Plan committed before execution | [plan.json](../experiments/bounded_event_001/plan.json) |
| Corrected receipt and gate results | [receipt.json](../experiments/bounded_event_001/receipt_scaled_givens/receipt.json) |
| Original failed receipt | [first receipt](../experiments/bounded_event_001/receipt/receipt.json) |
| Complete host storage/stack accounting | [memory_accounting.json](../experiments/bounded_event_001/memory_accounting.json) |
| Public interface | [scm_evidence.h](../include/scm_evidence.h) |
| C implementation | [scm_evidence.c](../src/scm_evidence.c) |
| Focused correctness and regression tests | [test_evidence.c](../tests/test_evidence.c) |
| Host replay audit | [evidence_probe.c](../tools/evidence_probe.c) |
| Reproduction and independent scoring | [run_bounded_event.py](../tools/run_bounded_event.py) |

The retained-history reference was fetched clean at
`0fd443b126579c625aea8c3772ddc28668aa242b`. Numerical reference sources, original
data, original results and their provenance are unchanged. The corrected
experiment records source revision `2ee068f` and exact source/binary/input
hashes; subsequent documentation commits do not redefine its source identity.

Publication through the connected GitHub app assigns different commit metadata
while preserving each tree exactly. The canonical corrected-source commit is
`82cfc121bd69f8615c62d66d68f6f9dcd07def88`, whose tree equals the recorded local
`2ee068f` tree. The [publication map](../provenance/bounded_event_001_publication.json)
records every correspondence. A verified
[development bundle](../provenance/bounded_event_001_development.bundle)
preserves the exact original commit objects, so receipt provenance remains
recoverable without rewriting any frozen result.

## What the code inspection established

For three RC modes the host reference caches 80 doubles for every sample:
one OCV value, nine linear-amplitude columns, seven OCV derivatives and 63
amplitude-column derivatives. At 73,500 samples the cached rows alone cost
47,040,000 bytes. Its accounted retained allocation is

\[
2072+N(24+8+640)=49{,}394{,}072\text{ bytes}.
\]

The 24-byte term is the input sample, the 8-byte term is the copied voltage,
and the 640-byte term is the cached model row. Solver stack and caller-owned
qualification objects are additional.

The original one-anchor projection reduces the voltage payload to 723
features, but keeps the entire input history, a per-sample centering vector,
explicit event bases and projected derivative rows. Its accounted retained
allocation is 9,001,296 bytes. The five-anchor version uses 24,436,808 bytes.
Those figures are preserved in `results/compression_results.json`.

There is another scaling problem: an event ends whenever current **or actual
dt** changes. With arbitrary clock jitter, each sample can become its own
event. In that limit the explicit projection can cost more memory than the
full method. The new accumulator permits this partition while retaining only
one historical aggregate and one active event. CPU cost can still increase
because short events require more merges.

## The representation and its exact claim

Let the original joint coordinates be

\[
x=(\theta,\alpha)\in\mathbb R^{16},\qquad
x=\bar x+S\delta,
\]

where \(\bar x\) is a declared fixed anchor and \(S\) contains the reference's
coordinate scales. The theta coordinates include original initial SOC and
log capacity; alpha includes entering RC states and \(u_0=Hh_0\). None is
reset when an event ends.

At each observed endpoint, propagate the model at the anchor using the actual
interval and measured current. Form

\[
a_i=\frac{J_i(\bar x)S}{\sigma},\qquad
b_i=\frac{V_i-\mu_i(\bar x)}{\sigma}.
\]

The frozen affine objective is

\[
L_{\rm affine}(\delta)=\frac12\sum_i(a_i\delta-b_i)^2.
\]

Incremental Givens rotations reduce the augmented rows \([a_i,b_i]\) to a
17-by-17 upper triangular factor \(R\). No explicit orthogonal basis is kept.
In exact arithmetic,

\[
L_{\rm affine}(\delta)
=\frac12\left\|R\begin{bmatrix}\delta\\-1\end{bmatrix}\right\|^2
\]

for every displacement. The packed factor contains 153 doubles, or 1,224
numeric bytes. The final augmented diagonal retains residual energy
orthogonal to the parameter Jacobian. Omitting that energy would preserve an
optimizer while corrupting likelihood values and residual checks.

This identity preserves the joint undamped Gram matrix, gradient and constant
term. Consequently it also preserves the local null space and the couplings
between useful targets and nuisance parameters. It does not convert an absent
direction into information. Repeating observations increases information in
existing directions; it cannot create a structurally missing direction.

This is an affine-likelihood identity. It is not a theorem that the nonlinear
battery likelihood is globally sufficient in 153 numbers. It establishes no
SCM, NAIA, D2/D2E or scalar-potential result.

## Event lifecycle and provenance

The live bank holds a historical factor, an active-event factor, the fixed
chart/configuration, carried model state and sensitivities, a 256-bit
caller-provided source identity, contiguous sample counters and bounded
monitoring metadata. Events close when current or dt changes, when 256 samples
have arrived, or when the caller explicitly seals an event.

Closing an event stacks its factor onto the historical factor and performs
another QR reduction. The active factor is then cleared. QR factor rows are
never counted as additional voltage observations. The bank's sample count is
the count of original source samples. There is no additional previous-posterior
factor, and no replay of a sample into a bank that already represents it.

Pushes require exactly the next source index and the same source identity.
Duplicate, reordered, skipped and wrong-source observations fail without
changing the bank. State propagation, QR and metadata changes are staged in a
caller-owned workspace so failures after partial work are also atomic.
The caller must keep the live chart and OCV arrays unchanged. These checks
provide an in-process ingestion contract; durable restart/serialization and
cryptographic authenticity are not implemented.

Current SOC remains

\[
z_k=z_0-D_k/Q,
\]

where \(D_k\) is cumulative charge in Ah. Its local variance uses both the
initial-SOC and log-capacity directions, including their cross-covariance.
The code never substitutes current SOC for the original chart coordinate.

## Guards and unresolved states

Candidate checks enforce declared per-coordinate radii, original physical
supports, the coupled \(|u_0|\le H\) constraint, and the OCV domain along the
complete historical SOC path. Retained minimum/maximum cumulative charge
are sufficient for the latter check because capacity is a positive constant
within a candidate. A candidate is never silently clipped or adopted as a
new chart. A radius failure is reported as `relinearization_required`.

Every sealed event also reports anchor-residual RMS in units of the supplied
voltage sigma. The experiment declares an RMS limit of 4 sigma. Exceeding it
sets a diagnostic flag; it does not delete measurements, reset physical state,
inflate noise, or absorb unexplained error into a new parameter.
This is an engineering alarm without calibrated false-alarm coverage. A
parameter error can itself cause a flag, which is useful evidence that this
anchor is inadequate rather than permission to discard the observations.

Neither a radius pass nor a residual-monitor pass bounds the nonlinear error
of discarded history. The API has no reanchor operation. Translating the
stored polynomial to another origin would not recompute historical nonlinear
Jacobians or reconstruct a changed physical trajectory.

The host probe uses the existing assessment eigendecomposition with an
explicit unfinished-nonlinear-fit status. It reports its own ranges as
`fixed_chart_local_only`, uses the same null-projection rule, and never labels
the quadratic solve as nonlinear convergence. Unsupported target ranges are
withheld. Coverage remains unvalidated.

## Small experiment

Only `cell_a_35hz_s202610240` is used. The plan's model, noise assumptions,
candidate vectors, radii and acceptance tolerances were committed before
execution. The reference fits supply anchors; synthetic truth is supplied only
to scoring after the C processes finish. No new nonlinear fit or long campaign
was run.

| Check | Anchor and observations | Result |
| --- | --- | --- |
| Unexcited prefix | Frozen 400 s fit; 14,000 original samples | Numerical rank 14; gamma-minus unexcited; Q and current SOC unresolved |
| Informative prefix | Frozen 900 s fit; 31,500 samples | Rank 16; Q and SOC local precision agrees with the original reference |
| Earlier evidence through weak use | Frozen 1800 s fit; compress samples 0–62,999, then consume 63,000–73,499 once | Useful local Q/SOC information retained; small affine update closely matches the full nonlinear reference |
| Nominal-model falsification | Declared nominal anchor; first 31,500 samples | Large residual flags and an out-of-radius update; bounded cold start is not demonstrated |

The 400 s and 900 s runs are retrospective representation checks. The 1800 s
bootstrap is also retrospective; only the subsequent 300 s tail extension is
causal relative to that anchor. A reference-derived anchor is not evidence
that the same anchor can be obtained from a one-pass bounded cold start.

After the QR repair, all 72 executable gates pass. Worst relative errors are
\(6.92\times10^{-14}\) for the Gram comparison,
\(4.58\times10^{-14}\) for affine objective comparisons, and
\(8.83\times10^{-11}\) for the normalized gradient comparison.

The local precision results below are conditional fixed-chart diagnostics,
not calibrated confidence intervals. The tail widths are evaluated in the
unchanged 1800 s chart, not relinearized at the proposed updated point.

| Checkpoint/chart | Q two-sigma relative half-width | Current-SOC two-sigma half-width |
| --- | ---: | ---: |
| 400 s | Withheld | Withheld |
| 900 s | 0.336063% | 0.0231659 percentage points |
| 1800 s before tail | 0.0543913% | 0.00859827 percentage points |
| 2100 s after tail, same chart | 0.0369014% | 0.00561122 percentage points |

### Weak-tail point comparison

At 2100 s the minimum-norm affine step produces
\(Q=60.00646756\) mAh and current SOC \(57.36901902\%\). Exact nonlinear
host replay at that point was performed only as an audit; it never corrects
the online bank's state or factor.

| Metric | Bounded affine step versus frozen full-history fit |
| --- | ---: |
| Relative capacity difference | −0.00000661590% |
| Current-SOC difference | −0.000000180400 percentage points |
| Excess exact nonlinear negative log likelihood | +0.0000130459 |
| RMS nonlinear-versus-affine predicted voltage difference | 0.00599439 microvolts |

Separately, against synthetic truth, the point capacity error is +0.0107793%
and current-SOC error is −0.00201273 percentage points. These truth errors are
not used to choose the chart, step, guards or qualification.

The original tail-only control remains an independent comparison: its
capacity and SOC errors were about 18.72% and 6.115 percentage points, with a
voltage RMSE near 0.995 mV and an iteration-limit status. It uses a different
entering-state problem and is not inserted into the new factor as evidence.
The comparison demonstrates why a good voltage fit during quiet use is
insufficient to reconstruct the knowledge contained in earlier excitation.

### What the falsification controls rule out

The nominal 900 s chart has a rank-16 local Gram and even finite, apparently
narrow local ranges. Nevertheless its anchor residual RMS is about 155.7
sigma and all 214 events trigger the declared RMS alarm. Its proposed step
is outside the chart. The affine objective at that step is about 15,747,
while exact nonlinear replay is about 3,305,313. The prediction mismatch is
14.45 mV RMS. Local rank and local precision therefore cannot qualify this
anchor or establish successful cold-start inference.

A second control is more subtle. The predetermined `inside_SOC_Q` probe
passes the parameter-radius restriction. At the final tail checkpoint its
nonlinear-versus-affine prediction error is only 1.74 microvolts RMS, but the
nonlinear negative log likelihood differs by approximately −134. This point
is far above the local optimum in likelihood cost; the observation does not
invalidate the successful small tail update. It does demonstrate that the
declared radius is **not a uniform likelihood-error certificate**, even under
the matched model. The next step must address this distinction explicitly.

## Numerical failure found and repaired

The first experiment failed 23 of 72 gates, despite passing the initial short
unit tests. The old rotation computed

\[
r=\operatorname{hypot}(a,b),\quad c=a/r,\quad s=b/r.
\]

Entering-state sensitivities decay through many orders of magnitude. If both
rotation inputs are subnormal, rounding \(r\) can leave very few significant
bits. For the smallest positive double with \(a=b\), the rounded hypotenuse
can equal \(a\), giving \(c=s=1\) and \(c^2+s^2=2\). That rotation also acts
on ordinary-size later columns and residuals, so a negligible pivot can
corrupt a material amount of residual energy.

The repair normalizes \(a,b\) by their maximum absolute magnitude before
forming \(c,s\), then rescales only the stored diagonal. It does not flush
small directions, drop evidence or relax tolerances. A 3,500-sample regression
now drives a physical entering-state column through the subnormal range while
retaining ordinary-size residuals. It fails before the repair and passes
after it. The original failure and corrected evidence have separate source
revisions, hashes and result directories.

## Complete memory accounting and remaining target work

All sizes below are this host's C ABI with double precision. The
[machine-readable accounting](../experiments/bounded_event_001/memory_accounting.json)
includes compiler flags, per-function stack reports, call-path estimates and
provenance checks. Object sizes are independent of sample count and event
count. Source counters fail closed on exhaustion; unlimited numerical lifetime
precision is not claimed.

| Item | Bytes | Scope |
| --- | ---: | --- |
| One numeric augmented QR factor | 1,224 | Payload only |
| One factor including dimension/count metadata | 1,240 | Snapshot or bank member |
| Persistent evidence bank | 3,336 | Two factors, chart, carried state, source and monitor metadata |
| Update workspace | 4,176 | Transactional staged bank, model row and QR scratch |
| Bank plus update workspace | **7,512** | Ingestion object subtotal |
| Bank, update workspace and snapshot | **8,752** | Snapshot subtotal |
| Existing fit/assessment adapter objects | 9,272 | Fit result, eigensolver workspace, assessment output and options |
| Local-step/target vectors | 384 | Three 16-double vectors |
| Simultaneous bank/update/snapshot/diagnostic/vector objects | **18,408** | No scratch reuse assumed |
| Retained separate input configuration, if kept | 472 | Already copied into the bank; the probe retains this duplicate |
| Incoming sample | 24 | Acquisition storage beyond the bank/workspace subtotal |
| All named static objects in the host probe | **31,485** | Includes replay arrays, candidate arrays, configuration and CSV buffer |

The embedded model state and row are already included in the bank/workspace
figures and must not be counted twice. The host has no OCV-table allocation
for the illustrative analytic curve. A double-precision measured curve would
require 16 bytes per knot for its two arrays if stored in RAM; placement in
flash is a separate implementation choice.

Compiler stack accounting adds project-owned call frames. Initialization and
streaming have different peaks, and the full host probe has different call
paths again. For this compiler, ingestion objects plus one sample plus the
reported project push call path total 8,192 bytes. The simultaneous diagnostic
objects plus the reported assessment path total 19,272 bytes. These are
partial live totals, not complete SRAM bounds. The largest listed complete
probe project call path is 1,408 bytes; its host linker data/BSS total is
32,720 bytes. External libm/libc stack, stdio buffers, application/interrupt
stack, acquisition buffering and target-specific alignment remain outside a
host `sizeof` calculation and are explicitly unmeasured. The full diagnostic
path already exceeds the approximately 10 KiB subsystem goal before those
costs. The 7,512-byte subtotal must not be presented as complete firmware SRAM.

No workspace overlay optimization is implemented. No Cortex-M23 compiler,
cycle count, SRAM/stack watermark, flash budget, numeric-format qualification
or power measurement was performed. Host file replay and its timing are not
35 Hz MCU latency measurements.

## Reproduce without overwriting evidence

From this work branch, use a new output directory each time:

```bash
make build/scm_evidence_probe test-evidence evidence-stack
OPENBLAS_NUM_THREADS=1 python3 tools/run_bounded_event.py \
  --output-dir experiments/bounded_event_001/my_new_receipt
python3 tools/measure_bounded_memory.py \
  --probe-result experiments/bounded_event_001/my_new_receipt/carry_1800_to_2100.json \
  --output experiments/bounded_event_001/my_new_memory.json
```

The runner refuses an existing output directory. It snapshots the executable,
checks data identity and records source hashes, all commands, gate outcomes,
guards and scoring. The original campaign and profiles need not be repeated.

## Next decision

Keep this component as the exact fixed-chart reference for bounded evidence.
Before broadening the campaign, construct a controlled validity mechanism for
nonlinear use: first measure and bound the likelihood remainder over the
region actually supported by the retained factor, then specify what bounded
information permits a chart change. The inside-radius counterexample must
remain a regression witness.

Cold-start acquisition of a useful chart is a separate unsolved requirement.
A bounded excitation window or a declared finite collection of model charts
could be evaluated next, but either must account for entering-state
uncertainty and preserve old evidence without replay/prior duplication. A
frozen quadratic must never silently become a globally valid or newly
relinearized history factor. Aging, model mismatch, sensor errors, measured
OCV, noise correlation and EOD validation remain subsequent work.
