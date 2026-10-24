# Working instructions

## Read first

Read `README.md`, `PROJECT_STATE.json`, and the relevant linked specification or
receipt before changing implementation or interpreting results. Use selective
file reads; large raw result files are evidence, not required default context.

## Project goals

- Estimate quantities only when the available stimulus supports them.
- Carry earlier evidence and uncertainty through weak or repetitive use.
- Keep unexcited, unresolved and provisional estimates explicit.
- Treat 35 Hz as the nominal stream rate; preserve actual intervals and sample order.
- Work toward bounded memory on Cortex-M23. Do not call the current replay solver firmware-ready.
- Prioritize useful battery state estimates; do not require every nuisance parameter to be known.

## Scientific integrity

- Keep truth out of fit objectives, initial guesses, centering and state corrections.
- Distinguish point error, numerical convergence, local precision and validated coverage.
- Preserve source identities, chronology and carried physical state across event boundaries.
- Do not count replayed observations and a posterior derived from them as independent evidence.
- Unfinished high-cost searches do not prove physical exclusion.
- Distinguish local likelihood diagnostics, solver curvature and any proposed scalar potential.
  Do not describe this conventional reference as a proof of SCM, NAIA or a D2/D2E method.
- Preserve original results and their hashes when revising summaries or implementation.
  Record adaptations and new experiments separately.

## Development workflow

- Inspect repository status and current instructions before edits; preserve unrelated work.
- Use a work branch for new experiments. Do not force-push shared history.
- Build and use meaningful targeted tests for changed behavior. Do not rerun long sweeps by default.
- Keep source revision, assumptions, commands, statuses and uncertainty limits with new evidence.
- Machine-to-machine handoffs should be compact JSON or YAML.
- Keep human explanations in plain language, with links to source evidence.
- Never change repository visibility or publish to another destination implicitly.
