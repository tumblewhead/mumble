# Focused late-SOC diagnostic

The two first-crossing intervals reproduce the original H5/H7 estimator contexts,
likelihood factors, transport states and physical stream exactly at the next
saved checkpoint. No production source or original run was changed. The selected
H7 SOC crossings are small, and the tested native update, SOC transport and
local solver controls do not explain them. No covariance inflation or repair
was applied.

[Receipt](receipt.json), [registration](../../experiments/h7_late_soc_001/registration.json),
[diagnostic plot](../../experiments/h7_late_soc_001/attempt002/diagnostic.png),
[Monte Carlo design](../../specifications/h7_assurance_001/MONTE_CARLO.md),
[proof foundation](../../specifications/h7_assurance_001/PROOFS.md).

## Reproduced observations

| Case, cell B charge cycles | Seed 1103 / case 0007 | Seed 1100 / case 0006 |
|---|---:|---:|
| Replay interval (hours) | 471.5861–474.5899 | 711.8848–714.8885 |
| H7 first crossing (hours) | 472.48907 | 711.90684 |
| H7 missed outputs / 33,792 | 68 | 5,084 |
| Maximum absolute standardized SOC error | 3.00361 | 3.09315 |
| Maximum absolute SOC error in interval | 0.0003696 pp | 0.0003263 pp |
| H7 misses on a fresh scheduled refresh | 0 | 27 |

Case 0007 crosses during -90 mA charging, at about 25.19–25.56 C. Case 0006
crosses during both charging and discharge, with refresh ages from zero to
59.84 seconds. Thus the second witness cannot be explained solely by a stale
between-refresh approximation. Counts are correlated outputs from selected
windows, not binomial coverage trials. The first-crossing selection itself is
outcome-dependent and remains diagnostic evidence only.

## Controls and their limits

Eight probes cover start, first crossing, maximum standardized error and end.
The refits use only the saved prior-free joint likelihood and original public
prior, initialized from the current estimator. Truth is used solely for scoring
and selecting diagnostic probes; it is never supplied to fitting.

- A dense same-anchor joint solve matches native SOC within 6.1e-10 local SD.
  Every final replayed estimator array matches the original checkpoint bitwise.
- The charge identity z=z0-A/Q and its full covariance, including the SOC–logQ
  cross term, reproduce native SOC and width to floating-point precision.
  The origin SOC–logQ correlation is approximately -0.694 in these probes.
- A fresh nonlinear fit of the entire H7 likelihood leaves the reported center
  unchanged under the existing stopping criterion. Recomputed SOC width changes
  by at most 1.32 parts per million. Because a stopping rule alone is not proof,
  the remaining explicit GN correction was also evaluated: its SOC projection
  is at most 2.38e-6 local SD.
- Exact moments for SOC transport of the *local jointly Gaussian* origin have a
  mean correction below 2.39e-6 local SD and a negligible width change. This
  checks nonlinear transport of that Gaussian, not Gaussianity of the posterior.
- Directional observed/GN curvature ratios from the compressed objective differ
  by at most 0.0182%, across three finite-difference step sizes. This is one
  query-relevant direction at selected points, not a full Hessian certificate.

These controls rule out a material implementation/transport/solver explanation
within the tested paths. They do not establish that the remaining misses are
statistically abnormal, nor distinguish finite-feature likelihood error, ADC
likelihood approximation, prior/model effects or ordinary correlated tail
realizations. The exact raw-data likelihood from sample zero was not rebuilt.
That would be a separate, more expensive diagnostic; a late compressed
checkpoint cannot substitute for an independent exact-history reference.

## Execution and next work

The diagnostic retains about 8.5 MB: compact per-output diagnostic traces,
selected joint snapshots, a plot and receipts. No full raw V/I/T log was saved.
Seven targeted tests pass, covering independent Gaussian quadrature, packed
native covariance, exact-binomial planning calculations and rejection boundaries.

Attempt 001 stopped at a strict physical-snapshot comparison after both estimator
arms already matched: the restored controller held a Python tuple whereas the
JSON checkpoint held the equivalent list. Attempt 002 normalizes that comparison
through JSON and uses a fresh output path. The original source and attempt are
preserved; no estimator or stimulus recurrence changed.

The next step is a reproducible Monte Carlo manifest and outcome reducer, with
independent scenario confirmation and separate crossed-factor exploration. It
should measure whether these tail patterns recur across populations before
changing the uncertainty model. The proof foundation states exact mathematical
invariants separately from open finite-precision, approximation and calibration
obligations. Use frozen H7 as the control for later storage/code optimization.
