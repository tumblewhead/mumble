# Focused field comparison and parameter errors

`--history compare-tangent` now runs only field64 and tangent64. Both use float64
arithmetic; the removed comparison arm was the original rolling estimator named
`float64`. The default estimator remains joint-field. Original rolling controls
remain available explicitly; historical evidence is preserved.

Offline plots automatically focus on the two field arms when both are available.
`--arms` overrides that selection, and summary `--cases` selects case directories.
All individual and aggregate plots gain `parameter_errors.png/pdf`: signed
reference-parameter error `100*(estimate/truth-1)` for all 11 parameters. This affine
transform preserves compact-bin means and extrema for positive stationary truth.
Truth is used only for reporting. The±1%linear region of signed symlog axes is a display
choice, not a physical acceptance threshold.

A field comparison also produces `parameter_error_comparison/`: one parameter
per page, one case per panel, up to 16 cases per page. Green solid means field64;
purple dashed means tangent64. Case labels identify cell, load, noise and seeds.
Panels have independent limits, explicitly labeled. This avoids32overlaid curves
when comparing16cases.

The owner's 72-hour campaign has been rerendered into new directories within its
original worktree:

- `run_20261101_005759_788073/field_comparison/`
- `run_20261101_005759_788073/field_comparison_case0006_48_56h/`

The first includes the Q, H, gamma and allRCparameter comparison pages. The
second isolates the late noisy case. The earlier full-resolution diagnostic
figures remain in `experiments/field_tangent_native_001/review72h001/` in the
`uncertainty-weak-stimulus` worktree.

All original review-bound input/result/summary hashes and archived replay-source
hashes were rechecked unchanged. Code changes live separately in
`/home/easy/proj/mumble/.worktrees/field-comparison-plots` on
`implementation/field-comparison-plots-001`, preserving the owner's replay setup.
48 targeted tests pass: selected arms, numerical mean/range transformation,
full/compact agreement, facets, default selection and checkpoint replay.
See the [receipt](receipt.json) for exact paths and identities.

For another offline view, from the new worktree:

```sh
python3 -B -m experiments.foster_campaign_001.plot /absolute/path/to/run \
  --summary --arms field64 tangent64 --cases case_0006 case_0014 \
  --start-hour 48 --end-hour 56 --out /tmp/new_field_error_view
```

Use a fresh output path. Compact plots cannot resolve dynamics inside their
stored bins; replay in the original bound environment remains necessary for
that. No simulation, original artifacts, numerical kernel or estimator default
was changed by this plotting work.
