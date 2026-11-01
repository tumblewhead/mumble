# Streaming H7 tangent campaign integration

Work branch `implementation/h7-campaign-001` integrates the qualified RC5/H7
likelihood and transport into the fused native original-origin tangent backend.
The existing default is unchanged. `--history tangent-h7` selects H7 alone;
`--history compare-h7` compares H5 tangent (`tangent64`) with H7 tangent
(`tangent_h7`) on the same samples. Physical parameters stay continuous.

[Plan](plan.json), [qualification](../../provenance/h7_campaign_001/qualification.json),
and the prior [offline refinement](../hysteresis_refinement_001/README.md).

The shared C kernel builds with separate hysteresis dimensions while keeping RC
degree5. H5 retains its previous arithmetic, and a comparison with the frozen
preintegration native kernel is bitwise exact on the tested stream. H7's joint
projection, update and nonlinear state/covariance transport agree with independent
mixed-field calculations. The outgoing Gaussian is still only a readout.

New binary dimension queries and distinct checkpoint magic reject accidental
H5/H7 ABI or native-state mixing. Compact checkpoints bind both H7 binaries and
all relevant source files. There is no reconstruction of discarded H7 coefficients
from an H5 checkpoint: start a new campaign for this representation.

Full/compact output parity, pending-history checkpoint replay, partial-window
buffer overflow, refresh rejection, original-origin feedback ownership, plot
rendering and checkpoint sizing are tested. The existing individual plots,
all-case overlays and parameter-error comparison pages include H7. The H5 and H7
arms have distinct labels and colors.

## 72-hour comparison

The registered run has eight cases: cellsA/B, embedded and CC/CV charge-discharge
loads, noise seeds1100/1103 at2mV, embedded load seed7. Both arms see the same
50Hz stream, with the same prior and60second nominal refresh cadence. Actual
sample intervals and chronological state transport are preserved.

```bash
cd /home/easy/proj/mumble/.worktrees/h7-campaign

python3 -B -m experiments.foster_campaign_001.run \
  --history compare-h7 --hours 72 --jobs 4 --sample-rate-hz 50 \
  --cells A B --loads embedded charge-discharge \
  --seeds 1100 1103 --load-seeds 7 --noise-v 0.002 \
  --recording compact --checkpoint-hours 3 --summary-bins 2000
```

The default output path is unique. The registered execution uses
`--out experiments/h7_campaign_001/run72_001`; do not reuse an existing path.
Results are in `summary.json`, with all-case plots in `case_summary/` and
per-case plots alongside `case_*/result.json`. Errors and rejected refreshes
remain in the results. No raw stream CSV is written.

## Resource limits

The H7 packed likelihood factor is50,624B (49.4KiB), plus1,336B live collocation
state. The native tangent context is1,376B and explicit native scratch is
6,280+3,808=10,088B. These are separate components, not total SRAM.
The desktop adapter also retains a100,352B dense field root, a163,840B raw batch
buffer, projection tables, prior, carrier and Python/solver workspace.
It remains a desktop reference, not firmware ready for10KiB SRAM at16MHz.

Compact recording bounds plot storage; checkpoint storage grows with the number
of scheduled snapshots. Its planning estimate now accounts for H7's larger root
and live state. Generated campaign data stay ignored by Git.

Run source and binaries must remain unchanged while generating or replaying
this campaign. The earlier field-comparison and archived replay worktrees are
preserved. Any repair after inspecting this run should get a separate result
path and retain this evidence.
