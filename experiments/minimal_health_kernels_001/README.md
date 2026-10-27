# Minimal aging-aware desktop kernels

The [specified model](../../specifications/minimal_health_model_001/model.json)
now has a Python/NumPy implementation of physical propagation, normalized
health-path density and analytic first derivatives. **301 checks in ten finite
cases pass.** This qualifies these kernels and small posterior controls; a
full aging posterior estimator remains to be implemented.

[The final receipt](qualification/development002/receipt.json) and
[all checks and numerical outputs](qualification/development002/checks.json)
are preserved alongside source snapshots and hashes. The first qualification
also passed (286 checks); [self-review](development_review.json) records the
subsequent underflow guard, derivative-allocation improvement and added tests.
There was no independent reviewer and no canonical battery-data run.

## Implemented behavior

- [kernel.py](kernel.py) applies the health-then-physics convention with
  continuous SOC and an explicit accessible-charge ledger. It preserves actual
  intervals, source order, RC states and hysteresis. Its immutable physical
  cursor commits only after a complete valid step.
- Bounded Gaussian health transitions retain their state-dependent normalizer
  and derivatives. A mode-scaled integral avoids subtracting nearly equal CDFs.
  Zero variance is an exact constraint; numerical underflow never silently
  converts positive diffusion into a deterministic transition.
- [path.py](path.py) combines the original capacity-mixture prior exactly once,
  all transitions and valid voltage likelihoods. It eliminates deterministic
  health coordinates and differentiates through the entire supplied path.
  It reports supplied-path density, with posterior uncertainty unresolved.
- [qualify.py](qualify.py) contains independent physical AD comparisons,
  high-precision tail controls and small marginal posterior calculations.
  These controls explicitly separate predicted changes, measurement corrections
  and changes in uncertainty.

The normalizer checks successive quadrature orders and bounds omitted Gaussian
tails. Those are finite numerical safeguards, not a rigorous interval-arithmetic
certificate over every possible parameter. Unresolved computations return an
explicit status. The physical cursor is not a posterior checkpoint or a complete
streaming estimator.

## Evidence and limits

| Check | Result |
| --- | --- |
| Stationary predictions versus independent physical equations | Maximum voltage gap 4.44e-16 V; original mixture prior and scaled gradients pass |
| Changing-capacity charge balance | Maximum ledger error 7.18e-18 Ah |
| Transition normalization | All seven cases within 1e-8, including 40/80-standard-deviation tails and variance 1e-14 |
| Tail reference | Separate 70-digit Decimal Simpson integration checks log normalizers and means |
| Supplied-path derivatives | Full 24-coordinate gradient plus partial deterministic-path controls pass registered scaled tolerances |
| Marginal versus profile | Centered log contrast 0.680651 versus approximately zero in the scalar control |
| Correlated weak observation | Health correction retained despite no direct health measurement |
| Rest then renewed load | Rest produces zero resistance measurement correction and growing uncertainty; renewed load corrects resistance and reduces uncertainty |
| Invalid input and mismatch | Atomic rejection, gap recovery, temperature flag and explicit residual mismatch; no automatic aging-rate inflation |

The rest/load fixture estimates **only R0**, conditional on declared public
values for every other parameter. Its rates are deliberately accelerated
engineering fixtures, with a distinct synthetic plant trend and noiseless
observations. The likelihood still uses 1 mV noise. It is not a realistic aging
trajectory, a full joint posterior, or a coverage study. The 48- and 96-node
posterior means/variances agree within 1e-6. After six rest records the R0
variance is 0.0119600 ohm²; after six loaded records it is 0.00135434 ohm².
Truth is used for plant generation and scoring after inference closes, never
passed to the inference function.

The final worker used about **0.504 CPU seconds**, **37.6 MB peak RSS**,
562 candidate physical steps, 15 independent AD steps and 149,059 posterior
quadrature evaluations. Its 79,456 inner normalizer nodes are counted separately.
These are fabricated qualification costs, not long-history performance or MCU
resource estimates. Both development attempts and their resource receipts are
retained; no long sweep was rerun.

## Use and next step

Run a new, exclusively named qualification directory from the repository root:

```sh
python3 -B experiments/minimal_health_kernels_001/run.py /tmp/mumble-health-check-new
```

The supervisor freezes source hashes, bounds resources, collects independent
case failures and refuses to overwrite an existing directory. The
[plan](plan.json) fixes fixtures, tolerances and budgets before execution.

Select and register a full-history posterior backend next, including convergence
and integration/sampling error diagnostics, then qualify it on these controls
and short joint-state fixtures. A path MAP or inverse solver curvature cannot
replace marginal uncertainty. Compression comparisons must use the same dynamic
marginal target. The complete Cortex-M23 target remains **10,240 bytes of SRAM**;
no deployment history archive is introduced. M2/M3 promotion, physical aging
calibration and the later cell/load/noise/duration campaign remain open.
