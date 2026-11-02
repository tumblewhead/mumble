# Conditional architecture experiment

Work branch: `experiment/conditional-architecture-001`, based on reviewed H7
revision `ea3bd99`. Read the [stage-A contract](../../specifications/conditional_architecture_001/README.md)
and [findings](../../provenance/conditional_architecture_001/README.md).

This starts the architecture investigation with a paired domain-failure replay
and a packed fixed-shape likelihood baseline. It does not replace the local
campaign estimator or implement continuous unknown-rate inference.

From this worktree, choose fresh output paths:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -B -m \
  experiments.conditional_architecture_001.domain \
  --out experiments/conditional_architecture_001/local_domain

OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -B -m \
  experiments.conditional_architecture_001.run \
  --out experiments/conditional_architecture_001/local_representation \
  --prefix-seconds 600 3600 --loads rest multiscale embedded

OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -B -m unittest \
  experiments.conditional_architecture_001.test_architecture -v
```

The domain runner stops at35,520samples. It compiles an experiment-only native
copy with three distinct domain return codes and compares it with unchanged H7.
The longer solver control is diagnostic: it does not resume or publish the failed
arm. No source files in the existing estimator are modified.

The representation runner reports `summary.json` and per-case `result.json`.
It regenerates the same input for direct C queries without writing raw streams.
Three public shape probes each retain a separate conditional factor; these
probes are not a codebook of allowable batteries or a posterior mixture.
At600/3600seconds the actual boundaries are21,008/126,000samples. Defaults use
fixed25C,35Hz,cellB,noise1103/load7 and0.2mV noise. Host timing includes Python
response generation in the conditional control and native generation in H7;
it does not establish a target CPU advantage.

Rate changes require new evidence representation, not relabeling a fixed-rate
factor. The next stage must preserve continuous rate dependence and query-relevant
uncertainty before a resource/performance claim is possible.
