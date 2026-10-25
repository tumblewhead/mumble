# Bounded Online 002: global stall removed; candidate not promoted

**Retain the component-wise gain as a demonstrated mechanism improvement. The complete candidate remains rejected.** It removes the observed all-coordinate stall, but two distinct failures remain: **17 rejected corrections after cold reset**, whose exact cause was not recorded, and **biased capacity estimates with misleadingly narrow local uncertainty**. The latter also occurs in the control arms, which reject no corrections. A numerical repair alone cannot qualify this learner. [Independent review](independent_review.json), [behavior review](behavior_review.json).

## What changed and what stayed fixed

The successor independently limits each measurement-gain coordinate to keep its proposed mean inside the inherited support. A nuisance parameter at a boundary can therefore stop its own correction while other coordinates continue learning. The same selected gain updates both the mean and the full Joseph covariance; two orthogonal rotation passes maintain a lower-triangular square factor in the existing 16-by-16 array. This is a feasible coordinate-wise update, with a local Gaussian belief. It does not solve an optimal constrained-posterior problem or provide calibrated support bounds. [Frozen plan](plan.json), [algebra and source review](design_review.json).

The public prior, physical model, parameter supports, observation noise, local-status thresholds and acceptance gates were frozen unchanged. Prediction preserves actual intervals and sample order, carries state and correlations, and retains no raw history. Each supplied voltage is considered once. Truth enters separate scoring after inference; it is absent from initialization, resets and corrections. [Plan](plan.json), [primary receipt](primary/receipt.json).

One primary ran the same two 2,100-second, 73,500-sample trajectories through uninterrupted control, fresh-process warm continuation, and cold reset at 900 seconds. It completed **378,000 deliveries across 12 processes**, with exact warm checkpoint/query parity and explicit cold-reset semantics. There were **zero additional primary runs and zero optimizer calls**. The recorded approximately 0.656-second process-wall total includes host I/O and persistence; it is not an isolated kernel or Cortex-M23 timing measurement. [Receipt](primary/receipt.json), [scoring audit](scoring_audit.json).

## Mechanism result and target accuracy

Cell B control changes from **71,928 global zero-gain updates in 001 to zero recorded all-zero selected gains in 002**. It still has 23,991 component-limited updates. At 68 saved queries, at least one active component is completely blocked while other components retain gain and the evidence position is current. At 460 seconds, for example, gamma-minus is blocked at its 1,200 upper bound while the current observation is assimilated. The new zero-gain counter also includes zero sensitivity, so its definition is broader than the old common-multiplier counter. [Behavior review](behavior_review.json), [comparison scores](scores.json).

Every arm records zero all-zero selected-gain corrections. Every post-initial saved query has current evidence, including after the cold-path failures. These approximately ten-second queries establish recovery by the next query; the rejection counters still record the intervening missed measurement corrections. [Behavior review](behavior_review.json).

| Criterion | 001 | 002 |
| --- | ---: | ---: |
| Lifecycle and fixed-object resource gates | Pass | Pass |
| SOC absolute error at most 10 percentage points | 16/16 | 16/16 |
| Capacity absolute relative error at most 5%; joint hard targets | 6/16 | 8/16 |
| Joint preferred region: 0.5 pp SOC and 0.5% capacity | 0/16 | 0/16 |
| Rejected corrections; 002 permits zero | 0 | 17: fail |
| No hard-limit breach among provisional saved queries | Fail | Fail |
| Promotion | No | No |

The 16 scheduled arm/checkpoint pairs include **six warm duplicates** of control results. There are ten distinct control/cold evaluation points, all drawn from two shared trajectories. Control/warm gates are at 900, 1,800 and 2,100 seconds; cold gates are at 1,800 and 2,100 seconds. [001 scores](../bounded_online_001/scores.json), [002 scores](scores.json), [independent review](independent_review.json).

### Final point errors at 2,100 seconds

Entries show **001 → 002**, with signed estimate-minus-truth errors. Warm results equal control and are omitted here.

| Cell and arm | Current SOC error, pp | Capacity error, relative % | Scaled current-vector RMS |
| --- | ---: | ---: | ---: |
| A control | −0.06998 → +0.02628 | −2.53130 → +1.02012 | 0.40574 → 0.13310 |
| A cold | −0.47819 → −0.33436 | −7.48501 → −0.66815 | 0.54972 → 0.33706 |
| B control | −0.37847 → −3.40821 | +9.38929 → −7.53789 | 0.89326 → 0.86258 |
| B cold | −0.49357 → +2.83198 | +3.17243 → −2.61836 | 0.16497 → 0.51395 |

The vector score is the RMS of all 16 coordinate errors divided by fixed engineering scales: 1 for log parameters, 0.2 ohm for resistances, 0.03 V for hysteresis amplitude and RC states, 0.1 for current SOC, and 1 for current hysteresis state. Both versions use the same current-state chart. This is a dimensionless point-error summary; it is not a percentage, a covariance-normalized distance or the M1 entering-state metric. Cell B cold's larger vector error shows why the capacity change alone cannot summarize overall belief quality. [001 scores](../bounded_online_001/scores.json), [002 selected vectors](scores.json), [trajectory figure](../../report/Bounded-Online-002.png).

## Two remaining failures

### Rejected corrections after cold reset

| Cold arm | Suffix deliveries | Component-limited corrections | Rejected corrections | First interval containing a rejection |
| --- | ---: | ---: | ---: | --- |
| A | 42,000 | 5,981 | 7 | (960, 970] s |
| B | 42,000 | 7,343 | 10 | (980, 990] s |

These are suffix counts obtained by subtracting reset counters; cumulative counters survive reset. The implementation retains the valid physical prediction when a correction fails and reports the rejection. Both arms subsequently continue learning. The frozen gate permits zero rejected corrections, so numerical health fails. [Receipt](primary/receipt.json), [behavior review](behavior_review.json).

R3 is limited near zero around every recorded rejection interval, and selected saved means include extremely small positive values and exact zero. A plausible mechanism is rounding disagreement between the product used to calculate a feasible multiplier and the product used to apply it, particularly near subnormal distances where the relative backoff becomes ineffective. **This remains a hypothesis.** The output contains no failing stage, coordinate or prospective factor/gain, so the exact cause of the 17 events is unresolved. There is no recorded basis for attributing them to NaNs or loss of positive semidefiniteness. [Source/behavior diagnosis](behavior_review.json).

### Biased estimates with narrow local ranges

Cell B control finishes with capacity **0.05982299 Ah**, against **0.06470000 Ah** truth: **−7.53789%**, outside the 5% hard limit. It is nevertheless provisional and locally within the preferred precision screen, with a two-SD interval of **[0.05980280, 0.05984318] Ah**. Its innovation EWMA is approximately **1.0235**. Neither the narrow interval nor apparently nominal innovations establish accurate capacity. This arm has no rejected corrections or all-zero gains. [Independent review](independent_review.json).

There are 113 provisional capacity hard-limit breaches at saved A-control queries, 191 at B-control queries, and 26 after B's cold reset; warm results duplicate their controls. A cold has none. These finite, correlated queries demonstrate failed qualification; they do not estimate validated coverage. The 900-second control errors also remain outside the capacity limit: **+7.75395% for A and −22.52286% for B**. [Scores](scores.json), [scoring audit](scoring_audit.json).

## Verification and memory boundary

The strict build and focused AddressSanitizer/UndefinedBehaviorSanitizer runs pass **5,569 core checks and 76 checkpoint checks**. Fixtures include independently formed dense Joseph covariance, finite-difference prediction sensitivities, blocked nuisance coordinates with continued SOC/capacity updates, deficient and zero pivots, exact zero-gain behavior, and rollback after a partly modified trial factor. The maximum dense-Joseph covariance difference is approximately **1.33×10⁻¹⁵**. The focused sanitizer scope excludes a leak audit. [Build checks](build_checks.json), [test log](strict_build_test.log), [sanitizer log](focused_sanitizers.log).

The separate scoring/provenance/lifecycle audit passes **139 checks**. Those checks verify the evidence and preserve the failed numerical, accuracy and qualification gates. No extra inference or primary run was performed for review. [Scoring audit](scoring_audit.json).

| Host memory scope | Bytes | Included |
| --- | ---: | --- |
| Core objects | **5,896** | State 2,424; candidate/workspace 2,936; query 536 |
| Named fixed host objects | **7,064** | Core plus config, one sample, CSV buffers and checkpoint path/schedule |
| Named objects plus largest reviewed own-source call path | **8,184** | Above plus 1,120 bytes of reviewed stack frames |
| Serialized checkpoint | **2,456** | External record; no additional whole-record RAM buffer |

These are alternative accounting scopes, not amounts to add together. The 8,184-byte subtotal remains partial: library/runtime stack and allocations, acquisition, interrupts, target ABI/linker placement and embedded persistence costs are additional. Checkpoint version 2 rejects version 1 explicitly. Full Cortex-M23 memory, the 35 Hz deadline, and indefinite numerical availability remain unqualified. Fixed storage, square-factor algebra and this short test do not constitute an all-prefix stability or coverage proof. [Complete memory account](memory_accounting.json), [design review](design_review.json).

## Next action and stopping rule

Do **one small deterministic boundary/transaction diagnostic** with explicit failed-stage and coordinate capture, focused on zero, adjacent representable and subnormal support distances. Stop when a minimal reproducing witness identifies the numerical failure; preserve the same gain for the mean and Joseph update and the existing rollback contract. This diagnostic has not been run. [Independent decision](independent_review.json), [behavior review](behavior_review.json).

Do not launch a third trajectory candidate until a numerical fix and a separate decision addressing biased uncertainty have been frozen. Preserve 001 and 002, their first failures, public priors and acceptance thresholds. No parameter sweep, longer campaign or truth-based retuning follows automatically.

The frozen execution source is `4c59c2363bf8ebe81238b30af7b03d802a5e3e13`; source/result hashes are in the [receipt](primary/receipt.json) and [independent review](independent_review.json). The [canonical publication mapping](../../provenance/bounded_online_002_publication.json) records the published source/result identities without rewriting the experiment provenance.
