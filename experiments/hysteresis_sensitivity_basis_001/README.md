# Hysteresis sensitivity comparison

Run from this worktree, using unused build/output paths:

```sh
OPENBLAS_NUM_THREADS=1 python3 -B -m unittest experiments.hysteresis_sensitivity_basis_001.test_basis -v
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.hysteresis_sensitivity_basis_001.run --build-dir experiments/hysteresis_sensitivity_basis_001/new_build --out /tmp/mumble-h-sensitivity.json
OPENBLAS_NUM_THREADS=1 python3 -B -m experiments.hysteresis_sensitivity_basis_001.probe --build-dir experiments/hysteresis_sensitivity_basis_001/new_build --study /tmp/mumble-h-sensitivity.json --out /tmp/mumble-h-locality.json
```

The saved `rc_sensitivity_basis_001/pilot001` and `full001` assets and baseline
recipes are local prerequisites. Their registrations, manifests, sources, binaries,
snapshots and regenerated observations are verified. No raw observation logs are
needed. The runner does not refit, change priors or use plant truth in readouts.
`--runs`/`--loads` allow subsets; the qualification includes both runs/all loads.

`response.c` exposes a new entry point: collocation H and derivative H cannot be
interpreted through a legacy response-state ABI. `basis.py` binds the representation
to the kernel mode and preserves the reviewed Taylor RC layout. All principal H
arms share Taylor RC; the old R5_H7 reference remains separately labeled. The
prototype pads six H derivative slots to the existing nine-slot transport layout.

Six tests cover derivative/majorant identities, projection, centre and mixed
derivatives, rest/single-sign, legacy-binding rejection, chunking, full joint QR,
failure atomicity and transport chain rules. `reference.py` is an independent
Python derivative check and conservative H6 envelope. The separate 15-query public
probe exposes locality and does not train or recenter the candidate.

Native builds remain ignored. Commit only source and compact provenance. No
production/default change, CPU qualification or complete target-memory claim.
See the [plan](../../specifications/hysteresis_sensitivity_basis_001/README.md),
[H5/H6 proofs](../../specifications/hysteresis_sensitivity_basis_001/H5.md) and
[report](../../provenance/hysteresis_sensitivity_basis_001/README.md).
