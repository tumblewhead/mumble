# Boundary transaction diagnostic 001

## Decision

**The diagnostic is complete.** A minimal binary64 witness reproduces a
negative trial resistance in the production boundary limiter. The selected
remedy is a constant-work fallback: when the actual rounded proposed mean is
finite but outside its support, set only that coordinate's selected gain and
multiplier to zero. Use that final gain in both the mean and full Joseph
covariance. The diagnostic variant passes its declared checks while retaining
learning in another coordinate.

The production estimator source and the two frozen bounded candidates remain
unchanged. This is a tested remedy decision for a subsequent learner revision,
not a promoted third candidate. The original 17 cold-reset rejections still
lack their actual failed-stage/operand records, so this witness does not
attribute those historical events to this mechanism.

The separate [local uncertainty decision](../../plans/local_uncertainty_decision_001.json)
is frozen. The existing local covariance remains a local precision diagnostic;
application SOC/capacity accuracy remains unresolved for this learner, coverage
is unvalidated, and the local Gaussian supplies no hard support. The decision
is uniform across cells and does not change inference, raw research statuses,
original scores, point-error gates or useful-availability gates.

## Reproduced arithmetic

Let `u = 2^-1074`, the smallest positive binary64 subnormal. The frozen
production selector computes `change = gain * standard`, obtains a feasibility
multiplier, backs it off by `1 - 1e-9`, and then applies
`mean + (multiplier * gain) * standard`.

Under nearest-even rounding with gradual underflow:

| Operation | Rounded value |
| --- | --- |
| Entering mean | `u` |
| Normalized gain | `1` |
| Standardized innovation | `-1.5` |
| Unconstrained change | `-1.5` |
| Boundary multiplier, `u / 1.5` | `u` |
| Relative backoff, `u * (1 - 1e-9)` | `u` |
| Selected gain | `u` |
| Applied change, `u * -1.5` | `-2u` |
| Proposed mean | **`-u`**, outside the nonnegative support |

The scale division rounds upward, and the relative backoff cannot move the
subnormal multiplier. The final multiplication rounds the change to two
subnormal units. This establishes the representability failure; it does not
require attributing all of the effect to a change of multiplication order.
The [baseline result](primary/baseline.json) preserves hexadecimal operands.

The fixture also exercises the full production ingestion transaction with
the unchanged default `sigma_V = 0.001`. It constructs an API-valid rank-one
factor with `L[9,9] = 0.25`, `L[12,9] = -1`, and `R3 = 7u`; other means use
public initialization. One constructed observation gives standardized
innovation `-8`. The selected R3 gain rounds to `u`, so its proposed mean is
`7u - 8u = -u`. The captured failure is **`mean_domain`, coordinate 9 (R3)**.

This is a numerical fixture, not a physically reached battery history. In
particular its constructed voltage is negative and is admitted by the current
API's finite-voltage contract. No claim of battery-trajectory reachability
follows. It does not tune the production prior, noise or physical supports.

## Remedy and transaction checks

The [exact variant difference](primary/remedy.diff) moves the actual mean
feasibility check before selected-gain storage and gain diagnostics. A finite
out-of-domain trial selects `t = 0`, `lambda = 0`, and retains that coordinate's
predicted mean. Other coordinates keep their own selected gains. Nonfinite
failures and other rejection stages keep their existing rejection behavior.

This fallback is bounded: it adds no search or retry loop. Because the
committed predicted mean is already valid, the zero-gain coordinate remains
in support. It does not clip a mean after choosing a different covariance
gain. Gain masks and extrema are computed from the final selection, including
the zero fallback.

The full covariance check independently forms

\[
P^+ = (I-KH)P^-(I-KH)^T + K\,\sigma_V^2\,K^T,
\qquad K_i=t_i/s_d,
\]

using the actual selected gain and the committed prediction. It does not use
either production rotation pass or its `g-t` covariance identity. The maximum
element difference is **2.220446049250313e-16**, within the frozen
`3e-13 * max(1, abs(expected))` allowance. R3 retains its marginal variance,
while V1 still receives a correction and the observation advances the evidence
position. This finite check does not prove calibrated covariance or indefinite
floating-point stability.

An independent failure fixture advances nonzero current through a positive
interval and then rejects at `innovation_sd`, column 0, after the trial factor
has already changed. Both variants preserve the advanced prediction exactly,
consume the known input once, retain the old evidence position and reject a
duplicate delivery without changing state. The next distinct known interval
advances once. A separate all-zero-gain control preserves predicted mean and
factor bytes, including signed zero, without creating observation evidence.

## Execution and resources

Source was committed at `cded053a4160a9b5f3726062235d7a200009ab6f` before
execution, with a clean working tree. One invocation built and ran two
variants of the same fixed fixture:

| Variant | Scalar cases | Assertions | Failed assertions | Boundary transaction |
| --- | ---: | ---: | ---: | --- |
| Instrumented production baseline | 14 | 105 | 0 | Expected mean-domain defect reproduced |
| Diagnostic finite-coordinate fallback | 14 | 520 | 0 | Accepted; other coordinates still learn |

The successful baseline test result means the declared defect was reproduced.
It does not change the failed estimator numerical-health gate. Each variant
made nine ingestion API calls, of which seven consumed constructed fixture
inputs and two refused duplicates. There were **zero cell-trace deliveries,
optimizer calls or new two-cell primary runs**.

The runner checks the frozen production source hash, applies uniquely matched
instrumentation edits, and extracts the scalar loop directly from each
generated variant. The generated sources, exact difference, source hashes,
compiler commands and outputs are preserved in the
[receipt](primary/receipt.json). The fixture checks binary64, nearest-even
rounding, gradual underflow and evaluation at declared precision. Compilation
disables fast-math and contraction. The test is specific to this host/compiler;
Cortex-M23 arithmetic behavior remains unqualified.

| Storage scope | Bytes |
| --- | ---: |
| Existing persistent state | 2,424 |
| Existing workspace | 2,936 |
| Existing query result | 536 |
| Existing core subtotal | 5,896 |
| One caller-owned diagnostic capture record | 80 |
| Maximum two named capture records in one transaction fixture | 160 |
| Added production state/workspace/query storage | **0** |
| Added checkpoint storage | **0** |

The capture record, extra test states and dense oracle matrices belong only to
the host fixture. They are not linked into the production estimator and are
not a complete fixture-process memory account. The proposed zero-gain fallback
reuses existing coordinate scalars. Any later live capture or target integration
needs an explicit simultaneous-memory and stack account. The inherited 7,064
bytes of named host objects and 8,184-byte partial host-plus-own-stack total
remain partial accounts, not complete 10,240-byte Cortex-M23 qualification.

## Remaining blocker and next work

Cell B control in bounded_online_002 has zero rejected corrections, but ends
with capacity **0.05982298523 Ah** against scoring truth **0.0647 Ah**, or
**-7.5378899062%**. Its local two-SD interval is
`[0.05980280083, 0.05984317645] Ah`, while innovation EWMA is about `1.0235`.
These frozen facts are in the
[behavior review](../bounded_online_002/behavior_review.json) and
[independent review](../bounded_online_002/independent_review.json).
Repairing the constructed numerical defect does not explain that separate
wrong narrow belief.

The diagnostic stops here. The next substantive task is one narrowly scoped
design decision on bounded nonlinear evidence: choose a mechanism that can
address the capacity-bias/qualification failure, define its retained-evidence
semantics and complete resource cost, and freeze one discriminating small test
or identify the missing datum. Neither this numerical remedy nor withholding
application qualification constitutes a capacity-accuracy improvement. A new
two-cell primary, duration campaign, or target qualification remains gated.

To identify the original 17 failures, the missing datum is an actual rejected
step's stage, coordinate/column, entering predicted mean/factor, input and
gain/innovation operands. Saved query endpoints do not supply that record.
The current diagnostic does not request another trajectory replay to obtain it.

## Reproduction

Inspect the frozen evidence without running inference. To repeat this small
fixture deliberately, choose a new output path; the runner refuses existing
directories:

```bash
python3 tools/run_boundary_transaction_diagnostic.py \
  --output-dir experiments/boundary_transaction_diagnostic_001/my_new_receipt
```

The [plan](plan.json), [summary](summary.json),
[numerical remedy decision](decision.json), and
[independent audit](independent_review.json) keep the source, outcome and claim
boundaries together. Both earlier candidates and their publication provenance
remain unchanged.
