SCM-inspired C battery estimator — 35 Hz research reference
=========================================================

This package contains the reconstructed C99 estimator, synthetic data,
independent scoring code, numerical qualification, and the fresh 35 Hz study.
It specializes the electrical model to known 25 C operation. It is a research
reference for conditional learning and later Cortex-M23 work; the full fitting
path currently replays and caches history and is not bounded-memory firmware.

START HERE
----------
  make
  make test
  ./build/scm_estimator --data data/cell_a_35hz_s202610240.csv \
      --case cell_a_35hz_s202610240 --modes 3 --method full \
      --sigma .001 --starts 3 --max-iter 120 --prefix 31500

This fits the first 900 seconds (31,500 samples) and prints a JSON result. The
assessment field is produced in C and keeps unexcited/unresolved targets
explicit. It is not a calibrated posterior or a global identification proof.
The C executable requires only a C99 compiler and libm. No Python is involved
in its physical model, optimization, projections, or qualification.

For Python orchestration, scoring and plots, use the versions recorded in
requirements-reference.txt or compatible local versions. The included results
are sufficient to inspect the experiment without repeating all optimization.

REPRODUCING THE EXPERIMENT
-------------------------
  OPENBLAS_NUM_THREADS=1 python3 tools/generate_cases.py
  OPENBLAS_NUM_THREADS=1 python3 tools/run_streaming.py --workers 3
  OPENBLAS_NUM_THREADS=1 python3 tools/run_profiles.py --workers 3
  OPENBLAS_NUM_THREADS=1 python3 tools/refine_early.py
  OPENBLAS_NUM_THREADS=1 python3 tools/run_compression.py
  OPENBLAS_NUM_THREADS=1 python3 tests/compare_assess_c.py
  MPLCONFIGDIR=/tmp/scm35-mpl python3 tools/make_report.py

The fresh campaign has six cases: two different cells and three noise seeds.
The main 60 fits use the full observation objective at ten growing prefixes.
The prior prefix theta is an initial guess only. Every observation occurs once
in the objective; a previous posterior is not also inserted as a prior factor.
The last five minutes are weak 3 mA use. A separate tail-only control discards
earlier evidence. A supplemental comparison studies full, one-anchor tangent,
and five-anchor hybrid event-local projection on the complete histories.

The frozen campaign binary's SHA256 and source hashes are in the result
metadata. The final CLI additionally includes C assessment reporting; its
equivalence checks are in results/c_integration_review.json. Numerical outputs
can differ slightly with compiler, platform or library versions. The old
two-mode recovered-note results are not part of this fresh three-mode dataset.
Two Linux x86-64 executables are preserved under reference_binaries/ for exact
study provenance; build the source with make for your own host. The preserved
benchmark executable predates the C qualification output, while the final
executable includes it. Neither executable is an MCU image.

DATA CONTRACT
-------------
Input CSV header:
  sample_index,dt_s,current_A,voltage_V
Sample indices must be consecutive from zero. Each current is held constant
over its own dt_s interval, and voltage is a point sample at that interval's
END. Positive current discharges. Units are seconds, amperes, volts, ohms and
ampere-hours. Nominal sample interval is 1/35 s, but actual dt_s is supplied.
Current, time and voltage calibration must be handled before ingestion.
Never normalize measured current by a candidate capacity.

Optional measured 25 C OCV table:
  --ocv path/to/ocv.csv
Header: z,voltage
SOC is a fraction in [0,1]. Use a strictly increasing SOC axis and monotone
voltage values. The table must cover every candidate SOC along its whole path.
The code linearly interpolates, uses the right slope at interior knots, and
rejects extrapolation. Without a table it uses this explicitly illustrative
curve, not a supplied measured curve:
  U(z) = 3 + 1.15*z + 0.08*tanh(8*(z-0.5)) volts.

MODEL
-----
  z_next = z - I*dt/(3600*Q_Ah)
  v_i,next = exp(-dt/tau_i)*v_i + R_i*I*(1-exp(-dt/tau_i))
  h_next = exp(-gamma_sign*abs(I)*dt/3600)*h
           + (1-exp(-gamma_sign*abs(I)*dt/3600))*sign(I)
  V = U25(z) - R0*I - sum(v_i) - H*h

At zero current SOC and throughput hysteresis are unchanged while the RC
states relax. State is carried chronologically through event boundaries.
There are three RC modes in the main study; the core supports one to three.

Seven nonlinear coordinates (modes=3):
  theta = [log(tau1),log(tau2),log(tau3),log(gamma_plus),
           log(gamma_minus),z0,log(Q_Ah)]
Nine conditional linear amplitudes:
  alpha = [R0,R1,R2,R3,H,v10,v20,v30,u0], with u0=H*h0.
The inner solver enforces nonnegative R/H, bounded entering RC states, and
|u0|<=H within numerical solution tolerance. h0 must remain unavailable when
H is too small to identify a ratio. All 16 quantities are unknown to fitting.

Declared search supports:
  tau1: .015 to .15 s; tau2: .15 to 1.5 s; tau3: 1.5 to 30 s
  gamma_plus/minus: 5 to 1200 per Ah
  initial SOC: .2 to .95; capacity: .03 to .10 Ah
  R0/R_i: 0 to 1 ohm; H: 0 to .1 V
  v_i0: -.08 to .08 V; u0: -.1 to .1 V, coupled to H
These supports are assumptions, not estimates learned from the data.

ESTIMATION AND SELF-REPORTING
----------------------------
The reference uses variable projection: a constrained small linear QP inside
a nonlinear multiple-start damped projected Gauss-Newton/LM search. The outer
reduced matrix is a projected approximation; numerical convergence is not a
claim of a global optimum. Tiny solve regularization is not reported as data
information. objective_full always recomputes the uncompressed raw-voltage
negative log likelihood (without its parameter-independent constant).

scm_assess() consumes the undamped joint likelihood Gram matrix in the fit's
scaled coordinate chart. It computes finite local two-sigma ranges only when
the target has no material component in the numerical null space. It retains
full declared support when that computation is unavailable or untrusted.
Current SOC includes the z0/logQ cross-covariance. h0 uses H/u0 covariance.
Ranges are not clipped to physical bounds to make them appear precise.

Statuses:
  unexcited: a supported structural test finds absent stimulus for this target
  unresolved: null-space, imprecision, numerical, constraint or chart issue
  provisional: finite local range passes the declared precision screen

Default screens are 10% relative two-sigma half-width for ordinary positive
physical parameters and .05 absolute SOC fraction (5 percentage points) for
SOC. These are configurable engineering screens, not calibrated probabilities.
Nuisance entering states have no automatic precision screen. Even provisional
results still need nonlinear/model-mismatch validation. No 'known' or
'validated' status is invented. The entire output remains useful to an
application that decides what precision each downstream task requires.

Numerical null detection depends on stated scaling and tolerances. A poorly
finished overall fit conservatively withholds local intervals; this can defer
some useful targets even when their point estimates are already accurate.

Profiles constrain Q, current SOC, selected poles, hysteresis or R0 and re-fit
all other admitted coordinates. A fixed endpoint SOC uses z0=z_end+D/Q and its
correct derivative. Its transformed Gram must NOT be treated as unrestricted
SOC covariance. Finite grid profiles are not global confidence sets. A low-cost
feasible candidate is a witness; a high-cost unfinished optimization is not
evidence that a target is impossible. Summary policy v2 enforces this rule.

REPRESENTATION AND MEMORY
-------------------------
The full method retains every voltage. Tangent and hybrid methods use disjoint
event-local blocks, split when current or dt changes. They project centered
voltage onto constants, amplitude columns, and sensitivity directions. Tangent
uses one fixed prior anchor; hybrid uses five anchors and their mean-response
differences. The carried physical state is never reset at a block boundary.
The prototype stores explicit Q bases and replays the current history. Feature
count or payload compression is NOT the total-memory reduction. Per-result
data_bytes, basis_bytes, payload_bytes, workspace_bytes and retained_bytes make
those costs visible. Setup peak is separately reported.

With 73,500 samples the full reference accounts for 49,394,072 retained bytes,
including 47,040,000 bytes of cached design/sensitivity rows. The allocation-free
physical state is 280 bytes and a model row is 648 bytes on this host. The
allocation-free C assessment has a 4,224-byte workspace, 2,488-byte output and
56-byte options on this host. Those sizes are not a complete firmware SRAM
budget or stack watermark. No Cortex-M23 cycles, flash or power measurements
were made. Bounded replay, sufficient-statistic retention, target-aware update
scheduling, fixed workspaces and numeric precision remain porting work.

PUBLIC C LAYERS
---------------
  include/scm_model.h: chronological fixed-size physical propagation,
      OCV lookup, affine observation rows and analytic sensitivities
  include/scm_features.h: rank-revealing orthogonal projections
  include/scm_estimator.h: host fitting API, supports, profile constraints
  include/scm_assess.h: caller-owned fixed-size uncertainty qualification
  src/main.c: CSV and JSON host CLI

The caller owns samples and OCV arrays for the lifetime of scm_problem. Call
scm_problem_create(), scm_fit_options_default(), scm_fit(), scm_assess(), then
scm_problem_destroy(). For a fixed-current-SOC fit set the assessment option
linked_current_soc_chart; the CLI does this automatically. Sample-by-sample
model propagation is available through scm_model_step(), but the public fit
API currently operates on a retained array, not an online evidence bank.

WHAT THE BENCHMARK ESTABLISHES
-----------------------------
All six matched synthetic runs had <.5 percentage-point current SOC error
at the 600 s checkpoint and all later requested checkpoints. All six had
<.5% capacity error at 900 s and later checkpoints. Every resistance and RC
time constant was within 10% by 220 s and later checkpoints. These are physical
elapsed times under this particular stimulus, not universal convergence times.

At 2100 s, worst capacity error was .0163354% and worst current SOC error was
.00350642 percentage points. Fastest-pole error was still as large as 8.4230%.
The ordinary local screen still withheld the first-cell R0/fastest pole at the
end. Low voltage RMSE alone is insufficient evidence of parameter accuracy.

All 60 fits returned results: 50 met numerical stopping criteria, 10 reached
the iteration limit. One same-prefix profile found a better 220 s minimum;
the supplemental refinement preserves that finding without rewriting the
frozen campaign. The complete report explains these limits and profile gaps.

ASSUMPTIONS AND OPEN WORK
-------------------------
Both cells have constant parameters, exact current/time, known OCV, fixed 25 C,
independent 1 mV Gaussian voltage noise and an exactly matched electrical model.
The initial states are unknown and fitted. The stimulus moves roughly 21–23
percentage points of SOC. Six runs are not a population robustness study.
The data do not test thermal change, aging, ADC filtering/aliasing, offset or
current bias, correlated noise, OCV uncertainty, or model mismatch. The35Hz
rate is the requested operating point; 20 Hz degradation and 1 kHz diminishing
returns reported from SCM were not independently tested here.

Next work should retain qualified evidence across weak use while allowing
explicit staleness/inconsistency detection, compress bounded event history,
and assess uncertainty under measured OCV/current/voltage imperfections.
Unknown parameters must stay unknown until stimulus supplies the missing
directions. A small point error in synthetic truth scoring is not a substitute.

The current input schedule is a numerical experiment, not a prescription for
injecting these currents into a real device. Hardware load and charge limits
remain external to this package.
