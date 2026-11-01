# H7 assurance before deep optimization

Use both empirical validation and conditional proofs. The completed
[late-SOC diagnostic](../../provenance/h7_late_soc_001/README.md) found no material
native-update, SOC-transport or local-solver explanation for the selected small
3SD crossings. It does not establish population coverage.

- [Monte Carlo plan](MONTE_CARLO.md): independent statistical units, crossed
  exploration, frozen confirmation, sensor/model mismatch, practical outcomes,
  coverage, power, missing/failing trials and recording budgets.
- [Proof foundation](PROOFS.md): physical recurrences, exact likelihood ownership
  and QR algebra, local positive precision, joint SOC transport, perturbation
  budgets, calibration assumptions and finite-horizon resource obligations.
- [Power calculations](power.json) and [calculator](sample_size.py): reproducible
  standard-library calculations with targeted checks.
- [Machine-readable plan](plan.json): current decisions and unresolved premises.

The ArghtOS pattern is useful: each optimization names the invariant authorizing
it, preserves a frozen control, measures the same target/harness, and records
accepted, neutral and rejected experiments. No whole-estimator accuracy or
coverage theorem has been proved here. Mathematical lemmas are handwritten and
conditional; implementation refinement and error-budget obligations remain open.

Do not launch a large campaign before the scenario distribution, acceptance
objectives and telemetry are frozen. Existing A/B runs are development evidence;
they must not become the supposedly independent holdout used to choose a sparse
basis or quantizer. No large Monte Carlo campaign has been executed in this step.
