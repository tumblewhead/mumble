# 96-hour35Hz campaign review

The run has four accurate Q/SOC completions, one persistent capacity-bias case,
and three early failures reproduced at the same records in C and Python.
`completed_with_failures` means all eight case tasks finished handling; only
five cases completed the requested96 simulated hours.

Source: `experiments/foster_campaign_001/run_20261030_174341_464520`.
Eight seeds1000–1007 use cellA,35Hz,20mV voltage noise and both encodings.
The CC–CV charge capability is2/1/1.5C, and discharge cycles through
0.2/0.01/0.45/0.08C. State, cell parameters and calibration are the same as the
earlier500Hz study. Compared with that run, only sampling rate, requested duration
and seeds change in the saved CLI configuration. Native source hashes match.
The different seeds and durations prevent a causal comparison of sampling rates.

## Outcomes

Binary64 results (binary32 closely agrees):

| Seed | Outcome | Final Q error,% | Final SOC error,percentage points |
|---|---|---:|---:|
|1000|Completed96h|−0.02715|−0.001203|
|1001|Rejected at15.543s|Prefix only|Prefix only|
|1002|Completed96h|−0.01264|−0.000117|
|1003|Completed96h|−0.01583|−0.000342|
|1004|Rejected at449.829s|Prefix only|Prefix only|
|1005|Completed96h|−0.01724|−0.002292|
|1006|Completed96h, Q target unmet|+0.61555|+0.001263|
|1007|Rejected at613.943s|Prefix only|Prefix only|

All completed arms retire12,096,000 observations,756,000 tokens and leave no
pending rows. Failed arms preserve the last committed message and16 pending
observations. Their preallocated telemetry beyond the valid prefix is excluded.

Across every reported boundary in hours24–96, Q error stays inside0.5% for
seeds1000/1002/1003/1005. Seed1006 remains outside throughout that interval:
its error ranges from+0.61551% to+0.92301%. Final SOC alone conceals its persistent
cycle-dependent SOC error. [review.png](review.png) distinguishes these cases;
long-run curves use approximately minute-spaced samples and are not extrema plots.
Full-run statistics and the complete late-Q scan are in [review.json](review.json).

## Reproduced early failure: bounded hysteresis and unbounded conditioning

The public error `C estimator status -4` means physical-model rejection, not
a numeric overflow or a specific raw-model error. The diagnostic reproduced
the three failed prefixes using the **original saved C library**, in both
encodings. Every final committed message is byte-identical to the saved run.
An independent Python-path replay fails at the same records and gives matching
out-of-domain candidates. These are short controls, at most614 simulated seconds;
the96-hour campaign was not rerun.

| Seed | Fitted endpoint h | History candidate h,binary64 | Required bound |
|---|---:|---:|---|
|1001|−0.995294|−1.124536|h≥−1|
|1004|−0.999992|−1.001241|h≥−1|
|1007|−0.999999|−1.000102|h≥−1|

Prior propagation and the fitted physical trajectory are valid in every control.
Candidate SOC is valid and all candidate coefficients are finite. The violation
appears after the likelihood is conditioned and its posterior transported through
the local linear state map. The producer's final domain guard rejects it before
commit. [failures.json](failures.json) and [python_failures.json](python_failures.json)
record the exact states and counters; the fitted anchors, candidates and pending
rows are saved separately. The diagnostic C bridge only reads context fields.

The generic history computes a Gaussian posterior and an affine transport;
neither operation enforces physical h support. A physically bounded fit point
does not guarantee the subsequent unconstrained Gaussian-conditioned point
remains in that domain. This is an exposed incompatibility between the bounded
producer and its local Gaussian evidence/transport representation. It is not
evidence of an arithmetic defect in generic Gaussian conditioning.

The failure is already present in binary64 and the Python reference. Its origin
therefore predates compact token precision and the C CPU optimizations. The
commit guard is doing its job; a repair must preserve valid states and joint
uncertainty through the producer/history contract while keeping the compressor
independent of battery truth and the test harness.

## Seed1006: hysteresis error survives long operation

Its gamma− estimate peaks at386.756 at3.810h, versus true9. H peaks near34.96mV
at4.464h, versus true15mV. It subsequently relaxes toward truth but finishes with:

| Reference-temperature parameter | Truth | Estimate |
|---|---:|---:|
| Q,Ah |0.060000|0.060369|
| H,V |0.015000|0.012873|
| gamma+ |6|7.5132|
| gamma− |9|13.9394|

Q error falls from0.9224% at24h to0.7672% at48h and0.6156% at96h, but the
available trajectory does not establish when or whether it will meet the target.
It is inside both Q/SOC bands at only0.629% of all reported boundaries. The
small endpoint SOC error is a favorable point in a recurring error cycle.

Uncertainty is especially misleading here: the final approximate three-SD Q
width is0.01906%, versus0.61555% observed error. Truth misses the nominal Q and
SOC intervals at98.92% and97.43% of its outputs. These are temporal diagnostics,
not independent coverage trials. The four accurate completions have much smaller
miss fractions, although seed1000 still misses both intervals about11.6% of the
time. Calibrated coverage remains unestablished.

There is no thousands-of-seconds pole runaway in these completed cases, but RC
estimates are not uniformly accurate. For example seed1003 ends with R0≈0.170ohm
and tau2≈1.722s, versus0.100ohm and0.500s. Good Q/SOC does not resolve every
nuisance parameter. The largest full-run encoding differences are0.08586%Q and
0.02161SOC points, both in seed1006.

## Next repair target

The short seed1001 failure is now a precise regression fixture for the next
design step: align the bounded physical-state coordinates/transport with joint
history conditioning. Candidate approaches need comparison for support, retained
cross-covariance, likelihood meaning, boundary saturation and CPU/memory cost.
Changing the physical bound or ignoring the rejection would not establish a
valid posterior. No bound relaxation or repair is included in this review.

Seed1006 should remain a separate sustained-bias control. Its cause has not been
isolated by the early-failure reproductions, and a bounded-state repair must not
be assumed to fix its Q/hysteresis bias automatically.

## Evidence handling

45 original small artifacts were checked against the run manifest, including
the compiled C library, configuration, results and final messages. The archived
C header was separately checked against the build receipt before reading the
native context. Large arrays were memory-mapped, valid rows only; their entire
hashes were not recomputed. Original evidence and production code are unchanged.

Commands:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -B -m experiments.foster_96h_review_001.failures
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -B -m experiments.foster_96h_review_001.python_failures
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MPLCONFIGDIR=/tmp/mumble-matplotlib \
  python3 -B -m experiments.foster_96h_review_001.review
```

Receipt writers refuse existing receipt files. The saved outputs are preserved;
use a separate experiment directory for adaptations and further experiments.
