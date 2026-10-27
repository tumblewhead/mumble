# Live bootstrap: selected design and qualified C primitives

## Outcome

The next bootstrap/anchor design is selected: **one older-history quartic bank,
sixteen retained raw samples and eight incoming samples**, starting from the
public prior. File playback and the saved archive are permitted host tools;
the new components have no file or archive dependency. The input contract now
preserves **12-bit V, I and T**, actual 64-bit duration ticks and chronology.

Three C prerequisites passed their finite fabricated qualifications: ADC
transport/calibration, a proposal that respects joint physical support, and
in-place translation of the represented history polynomial. The compiled phase
schema supports a **10,216-byte planning ledger**, leaving **24 bytes** to the
10,240-byte goal.

**This closes the design-and-primitives step, not the integrated rolling
estimator.** Current-block derivatives, boundary-state transport and the complete
record-once/prior-once transaction still need integration and qualification.
There was no new battery-data run, truth read or retry. SOC/capacity interval
coverage and M3 readiness remain open.

The [design](DESIGN.md), [machine decision](decision.json),
[frozen scope](../../plans/live_anchor_bootstrap_001.json),
[source/design review](review/source_and_design_review.json),
[saved-result review](review/primitive_result_review.json) and
[receipt review](qualification/receipt_review.json) define the exact scope.

## What changed and what passed

| Component | Qualification | Result |
|---|---|---|
| [ADC12 transport](adc12.h) | 8 cases, 657 assertions, 40 codec vectors | Passed one build and one test execution |
| [Support-aware proposal](support_step.h) | 14 fixed fabricated calls, 277 assertions | Passed one build and one finite suite |
| [History translation](history_translation.h) and [layout](live_layout.h) | 8 cases, 39,149 assertions, 255 query points | Passed one build and one test execution |
| **Total** | **30 cases; 40,083 assertions** | **Three builds; zero retries** |

Receipts are retained for [ADC12](qualification/adc12_attempt001/receipt.json),
[support](qualification/support_run001/receipt.json) and
[translation/layout](qualification/translation_attempt001/receipt.json).
All numerical inputs in this step are fabricated transport or algebra fixtures.
The previous completed history study and failed autonomous-anchor run are
unchanged.

### Input transport

The component retains all three channel codes in `0..4095`, including rail
codes, and never narrows the 64-bit duration. It enforces source identity and
sequence, handles FIFO wrap/full and counter exhaustion, rejects aliasing, and
leaves state and outputs unchanged after prevalidation rejection. Calibrated
take converts before consuming so an invalid conversion does not lose a queued
sample. Tests include nonfinite/overflow calibration failures.

A native raw packet is 16 bytes; a decoded reading containing duration, V, I
and T is 32 bytes. Explicit calibration is 56 bytes. The optional five-byte
codec contains the 36 channel bits only. Source, chronology and time remain
separate requirements.

The qualified standalone FIFO is 304 bytes. It is separate from the proposed
408-byte integrated input store. Its receipt also preserves an earlier
hypothetical integrated layout with 64 metadata bytes; the compiled schema now
uses 24 because source identity and committed cursor already live in the bank.
The standalone FIFO's own sizes and qualifications are unchanged.

### The active-bound search obstruction

The proposal uses the complete joint gradient and a conservative diagonal
majorizer derived from all entries of the full scaled metric. It solves the
coupled reciprocal-capacity/SOC constraints over a finite polygon and checks
the returned point in original support. It adds no damping ridge, does not clip
a rejected point, and does not treat the metric as posterior precision.

In the fabricated witness matching the old obstruction, entering hysteresis
stayed exactly at `h0 = -1`, while another coordinate moved by `-0.05`. The
original-gradient descent measure was `0.010000000000000002`. An outward
hysteresis gradient therefore did not prevent a usable supported move elsewhere.

Both SOC-face witnesses required capacity and entering SOC to move together.
They returned `logQ = -0.6931471805599453`, `z0 = 0.5`, exact represented support
slack zero and descent `0.8614688793449419`. These are fabricated numerical
witnesses, not battery capacity estimates. Independent checks used an 80-digit
polygon reference, exact rational arithmetic checks and reconstruction of the
unmodified scaled Cholesky factor.

A rounding-sensitive fixture remains unresolved: its represented reciprocal
constraint slack was `-5.551115123125783e-17`; support was not relaxed. A usable
proposal still needs the integrated nonlinear objective's finite cost-decrease
acceptance check.

### Preserving the stored polynomial during an anchor move

Quadratic-first feature ordering permits translation in the existing
5,624-byte factor. The implementation preflights all prospective coefficients,
updates each constant before its linear coefficients and retains explicit
failure semantics.

An independent dense long-double reference compared cost, all sixteen gradient
entries and all 136 Hessian entries at 255 points. It covered mixed shifts,
inverse/composed translations and all 37 pure basis terms. The largest error
divided by the frozen arithmetic allowance was `9.139007007159217e-06`.
Nonfinite, alias and overflowing translations were rejected without changing
the factor.

This checks algebra: an anchor-coordinate change preserves the approximation
already stored. It does not establish fidelity to the exact earlier battery
likelihood. Lost higher-order history is not recovered, and no interval width
follows from these results.

## How compact the retained history is

The factor retains older observations approximately; the small raw block is
reused. Its sixteen-record size is a memory and work choice that allows capacity
to continue learning later, not a claim about startup identifiability.

| Item | Bytes |
|---|---:|
| Older-evidence factor, included in the bank below | 5,624 |
| Complete bank, including factor, carried state and metadata | 6,368 |
| Core: bank + shared workspace + shared result | 8,088 |
| Sixteen retained native samples | 256 |
| Eight incoming native samples | 128 |
| Input metadata | 24 |
| Calibration, counted in RAM | 56 |
| Checkpoint codec reservation | 128 |
| Project stack reservation | 768 |
| Runtime/IRQ/caller reservation | 768 |
| **Complete planned total** | **10,216** |

The factor and bank are nested within the core, not added again. Objects occupy
8,680 bytes; the two stack/runtime reservations bring that to 10,216 bytes.
The layout qualification confirmed query state 224 bytes, decoded input 32,
workspace 1,600, result 120, core 8,088 and input store 408. Decoding reuses the
phase workspace. No second factor or standalone FIFO is also owned.

The support primitive's conservative reviewed host project call path is 584
bytes before caller, libm/libc and IRQ/runtime costs. The translation path is
152 bytes from emitted host frames. These component checks do not measure an
integrated Cortex-M23 stack. Complete reservations, target timing, interrupt
handling and checkpoint behavior remain unqualified.

The saved 8 MB history remains valid study material. It can feed a file producer
or provide an external reference. It is outside proposed operational memory
and must not select candidate anchors or supply replay inside the engine.

## What twelve bits establishes

Twelve bits establishes 4,096 codes per channel. Physical scale, offset, rail
meaning, sensor error and timing calibration remain explicit inputs. It does
not specify a noise law or accumulator width. The statistical representation
currently uses binary64; reducing that precision needs a separate error account.

Current-gain calibration matters directly to capacity. In the present model an
unknown current-gain scale can be traded against capacity, resistances and
hysteresis rates while preserving the predicted voltage. A capacity interval
must be conditional on calibration or include its uncertainty. The
[design](DESIGN.md#calibration-and-uncertainty-obligations) derives this model
symmetry. Arbitrary added voltage variance would not resolve the ambiguity.

Temperature is preserved by the interface. The existing 25-degree model does
not yet use it. No physical calibration values, thermal compensation or new
uncertainty thresholds were invented in this step.

## Where this leaves the path to M3

The prior handoff required a chosen causal representation, a supported joint
proposal, clear ownership of pre-origin evidence and a complete phase-liveness
ledger before the next finite experiment. Those decisions are now concrete,
and the three prerequisites have executable qualification evidence.

Next, integrate the rolling engine and qualify block derivatives, approximate
boundary transport, single-count evidence/prior transactions, fault behavior
and actual call chains. Then freeze one public-start chronological probe. The
archive may supply input and post-closure reference comparisons while the
candidate uses delivered samples and bounded owned state.

The scientific question is whether repeated causal transitions retain enough
nonlinear historical fidelity for useful SOC and capacity inference. Calibrated
joint intervals and actual near-10-KiB Cortex-M23 execution remain separate,
unfinished gates. The candidate is not promoted, and M2/M3 are not complete.
