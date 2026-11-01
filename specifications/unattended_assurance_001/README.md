# Assurance case for unattended battery estimation

Status: deployment requirements and conditional proof contracts, not a release
certificate. The supported target is approximately ten years of autonomous
operation on a baseline 16 MHz Cortex-M23 with about 10 KiB SRAM. H7 is the
desktop fidelity reference; its current implementation does not meet this case.
The [previous proofs](../h7_proofs_001/README.md) remain valid within their stated
scope. This case adds lifetime decisions, availability and autonomous recovery.

The top-level claim is: within a declared physical and fault envelope, the
device only authorizes uses justified by its current evidence and error bounds;
it remains bounded in resources; and it autonomously regains useful estimates
when sufficiently informative admissible observations return. Failure to prove
one of these clauses blocks the corresponding deployment claim.

## What trusted means

Trust belongs to a particular quantity or proposed action, at a particular
consumed prefix, under explicit assumptions. It is not one flag on the entire
battery. SOC can be useful while individual RC parameters remain unresolved;
a proposed load may be admissible even when its separate nuisance parameters
are poorly identified. Conversely, good Q accuracy does not authorize a load.

Separate these output fields:

- Execution state: acquiring, tracking, degraded, recovering, or quarantined.
- Numerical validity and evidence identity, including current source prefix.
- Query enclosure, units, error requirement, and physical horizon of validity.
- Guarantee type: bounded-error, simultaneous statistical coverage, or merely
  provisional local precision. A local H7 Gaussian is in the last category until
  the necessary calibration/approximation proof is supplied.
- Query authorization: certified for the stated requirement, unresolved, or
  outside the admitted domain. Unresolved does not mean that the point is wrong.
- Reasons and required recovery conditions, with bounded counters/telemetry.

A residual monitor not firing is not proof of model validity. A recent successful
solve does not renew a stale certificate. Never silently present a previous good
estimate as current after an update, sensor gap, reset or failed recovery.

The desired combination is **soundness plus availability**. Soundness bounds
unsafe authorizations. Availability bounds unnecessary refusal and reacquisition
time on a specified informative class of use. An estimator that refuses forever
fails availability. Requiring zero false acceptance and zero false refusal for
all noisy, indistinguishable cells is impossible; [D0](THEOREMS.md#d0-limits-of-a-perfect-trust-classifier)
gives the reason. The practical replacement is quantified risk and a tested,
conditional recovery guarantee, rather than a binary claim of omniscience.

## Required collection of proofs

| ID | Deployment claim | Required evidence / present gap |
|---|---|---|
| A0 | Operating assumptions and requirements are explicit | Duration, rates/gaps, physical/thermal/aging bounds, sensor error and fault model, query tolerances, lifetime risk, availability target. Several values remain unqualified. |
| A1 | Every observation has one owner; chronology and carried state survive boundaries | Existing exact compaction/ownership proofs; complete C/Python refinement and gap handling remain open. |
| A2 | Arithmetic remains usable throughout the supported lifetime | Range, overflow/underflow, conditioning, cancellation, libm, QR, solve and recurrence error bounds; budget exhaustion revokes authorization. Five finite QR certificates are insufficient. |
| A3 | Approximation and aging errors cannot silently disappear from uncertainty | Uniform feature/derivative/transport bounds and valid evolution model; no repeated stationary evidence masquerading as current information after aging. |
| A4 | Authorized outputs meet their declared guarantee at all allowed decision times | Joint containment plus query certificate and total lifetime risk accounting; H7 local SD does not discharge this. |
| A5 | Useful outputs recover without technical intervention | Conditional acquisition/recovery time and false-refusal bounds under defined excitation/noise/drift. Always-unresolved fails this claim. |
| A6 | Proposed loads obey voltage/EOD requirements | Full joint trajectory enclosure, sensor/model/actuator margins, all times in the load horizon, explicit fallback action. Pointwise RC error is not enough. |
| A7 | Handled faults cannot publish partial or stale state | Transactional update or terminal quarantine, bounded automatic recovery, no retry duplication. Field QR fault witness currently blocks universal atomicity. |
| A8 | Reset and lost history cannot produce false confidence | Validate source/configuration/checkpoint identity; cold start with explicit uncertainty; preserve or conservatively account lifetime risk across boots. SRAM-only loss cannot reconstruct history. |
| A9 | Memory, execution and storage use stay bounded | Complete target SRAM/stack/flash, worst-case cycles, buffer/backpressure, counter ranges, retry limits and any persistence wear. H7 factor alone is 50,624 B. |
| A10 | Sensor/time faults have a defined containment response | Saturation, bias, missing/duplicate/out-of-order records, clock faults and corrupted state; define detectable and intrinsically indistinguishable faults separately. |
| A11 | Optimization preserves the assurance case | Immutable reference, proof dependency, target compiler/ABI, code-to-contract evidence, negative controls and matched hardware measurements per change. |

The machine-readable [claim/dependency ledger](case.json) distinguishes generic
lemmas from deployed guarantees. Every claim needs a statement, assumptions,
implementation location, evidence and expiry/recovery rule. A violated premise
must invalidate affected authorizations; an undetectable premise needs external
qualification, redundancy or a conservative envelope, not a fictitious monitor.

## Physical and lifetime boundaries to freeze

The ten-year mission and nominal 35 Hz are design targets. Configured rates and
actual intervals must remain consistent; integer cursors do not eliminate physical
time. The earlier 100 Hz counter example is a stress point, not a newly certified
maximum rate. Aging of reference-condition R, Q and branch C is separated from
reversible temperature response. Monotonicity and the proposed 0.5–1.5 relative
envelope do not give a drift-rate bound or ensure identifiability during quiet use.

Capacity manufacturing guidance is +/-3sigma=2.6–3.6 mAh about 60 mAh; it is not
hard support or an aging envelope. The application has discussed 0.5% as a useful
accuracy scale and about 1% Q as acceptable during development. Neither is yet
an approved safety requirement. SOC absolute points, Q relative error, voltage
margin and permitted false authorization must be specified separately.

No lifetime risk number or brownout voltage/margin is invented here. Record
alpha_life, the device's admissible fallback load policy, minimum useful service,
and the conditions/time allowed for reacquisition before release. No proof can
provide energy the battery does not have or maintain service under unrestricted
permanent sensor failure. Recovery availability is conditional on viable power,
working sensors and informative use returning.

## Trust must survive repetition and restart

A 95% interval at each checkpoint is not a 95% guarantee that every authorized
decision over ten years is correct. Use a joint guarantee over the decision
sequence, or a valid lifetime allocation of failure probability. Confidence
sequences are one established mathematical route to uniform-in-time coverage;
they still require a valid model and a practical implementation.
[Howard et al., Annals of Statistics, 2021](https://arxiv.org/abs/1810.08240v9).

The [new lemmas](THEOREMS.md) give sufficient contracts without selecting a large
new solver: containment under propagation, sound query authorization, sequential
risk composition, recovery from informative data, and bounded error accounting.
An independent conservative certificate may accompany the existing fast estimator;
whether a useful one fits M23 remains an engineering/proof obligation. It must
not count the estimator's output as independent evidence. It may share kernels
only with explicit common-cause failure analysis.

SRAM-only history implies that a cold reset loses evidence. Reacquire honestly
from a public initial set and measured inputs. Retaining a checkpoint is optional
and would require a separate persistence contract; this document does not add a
flash/FRAM history requirement. A statistical lifetime budget also cannot restart
from zero on every boot. Possible contracts are retained accounting, a qualified
maximum boot count with per-boot allocation, or a deterministic bounded-error
guarantee. None has been selected. A reset is not evidence that an aged cell is new.

## Proof and implementation order

1. Specify the query/status contract and prove transaction/quarantine transitions.
   Repair the observed flush gap; test failure at every commit/publication boundary.
2. Construct a conservative query certificate on a small admitted domain, with
   explicit physical, sensor, approximation and numerical bounds. Keep H7 as the
   point-estimation reference. Begin with SOC/Q and then load voltage trajectories.
3. Prove propagation through quiet periods, aging and missing inputs, plus a
   conditional reacquisition theorem. Test both false authorization and refusal
   on informative cases. Do not add arbitrary aging or covariance inflation.
4. Implement lifetime risk/reset semantics and bounded autonomous recovery.
   Qualify mismatch detection only for specified detectable fault classes.
5. Complete target numerical/range/resource proofs. Then optimize kernel by
   kernel, preserving these contracts and matched evidence.

The Monte Carlo plan supplies physical robustness and availability evidence;
formal proofs supply contracts over all admitted traces. Neither substitutes
for battery characterization, noise qualification or target execution evidence.
Hardware brownout protection and the system's fallback policy require their own
qualification; this algorithm's assurance case alone does not certify the device.

No estimator implementation or production status changed in this step. The
executable finite checks in this directory validate small theorem examples and
counterexamples; they are not an implemented H7 trust monitor.
