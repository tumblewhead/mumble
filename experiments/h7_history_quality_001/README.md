# H7 history-quality desktop experiments

Read the [contract and proofs](../../specifications/h7_history_quality_001/README.md)
before interpreting results. The tools leave the estimator unchanged. Output
directories must not already exist. Small source/receipt files are tracked;
raw experiment results and plots remain local.

History replay requires the existing reference NumPy/Matplotlib environment:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
python3 -B -m experiments.h7_history_quality_001.history \
  --out experiments/h7_history_quality_001/local_history \
  --prefix-seconds 60 600 3600 --loads rest multiscale embedded \
  --noise-v .0002 .002
```

Larger prefixes, for example3600,28800,259200seconds, regenerate the prefix for
each direct probe without writing a raw history file. Runtime scales with every
replayed sample and probe. These experiments run cases serially. A failed arm
is recorded as unresolved; other cases continue. `--refit` adds expensive local
direct refits and is optional. Use a new output path for every adaptation.

The certificate experiment additionally needs SciPy. For a separate environment:

```sh
python3 -m venv --system-site-packages /tmp/mumble-h7-quality-venv
/tmp/mumble-h7-quality-venv/bin/python -m pip install scipy==1.18.1
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
/tmp/mumble-h7-quality-venv/bin/python -B -m experiments.h7_history_quality_001.certificate_run \
  --out experiments/h7_history_quality_001/local_certificate \
  --prefix-seconds 60 600 1800 3600 --rate-radii 0 .01
```

This second fixture has hard bounded voltage error and explicitly characterized
response-rate support. Its authorization is conditional on those assumptions;
it does not certify the Gaussian-noise history runs above. Its selected-constraint
storage grows with duration, so begin with the small pilot.

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
/tmp/mumble-h7-quality-venv/bin/python -B -m unittest \
  experiments.h7_history_quality_001.test_quality -v
```

`history_errors.png` shows sampled likelihood shape, gradient and projected
query discrepancies. `certificate_enclosures.png` shows conditional SOC/Q
enclosures, H7 points and scoring-only truth. Read `summary.json` for unresolved
cases, failed assumptions and actual selected prefixes. Exact rational bounds
and endpoint tests are authoritative; plots are only visual summaries.
