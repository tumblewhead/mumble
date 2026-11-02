# Bounded representation comparison: small coefficients are not sufficient

The three entrywise likelihood-coefficient candidates are rejected for promotion.
They preserve every cross entry and reduce coefficient storage, but interpolation
can destroy the positive-semidefinite conditional likelihood. The existing
low-degree square-root response controls preserve the sum-of-squares structure
yet still have substantial gradient error on this public domain. No candidate
is promoted; no production or campaign estimator changes.

See the [registered protocol](../../specifications/partitioned_coefficients_001/README.md),
[compact results](summary.json), [resource audit](resources.json), and
[physical-domain curvature witness](curvature_witness.json).
Local untracked raw results are experiments/partitioned_coefficients_001/pilot001
and followup002. The latter repeats all original arms and adds the existing
response degree1/2 controls; original-arm metrics and observation hashes match
exactly across36arm/prefix comparisons. It is a paired adaptation, not independent
confirmation. Original source/plan snapshots remain in versions/.

## What was measured

Three stimuli (rest, multiscale and embedded), three prefixes (21008,35520,
126000samples at35Hz; about10min,17min,1h),51 public amplitude/shape queries
per prefix, and the separately labeled known domain-exit candidate. The latter
is outcome-selected, not a training point. The embedded35520sample digest matches
the earlier failure exactly; all candidate/control representations refuse the
out-of-box query while the direct model supports its physical path.

These are fixed, mostly unfitted common queries over the original public log-rate
box, not inferred parameter trajectories. Point errors, Q/SOC convergence, calibrated
coverage and lifetime behavior were not measured. All public queries in these
cases were supported and compared. No repeated prefix/probe is counted as an
independent cell. A finite probe can expose a failure; passing it is not a uniform
bound. H7 is a fidelity control, not exact truth.

| Representation | Likelihood coefficient/factor bytes | Largest relative joint-gradient defect on active-load probes | Conditional curvature |
|---|---:|---:|---|
| Entrywise linear | 2112 | 13.64 | Material negative directions |
| Entrywise quadratic | 5120 | 0.882 | Material negative directions |
| Entrywise sparse quadratic | 2936 | 0.578 | Material negative directions |
| Square-root response degree1 | 2024 | 13.60 | No material negative direction observed |
| Square-root response degree2 | 4760 | 0.576 | No material negative direction observed |
| H7 control | 50624 | 0.001095 | No material negative direction observed |

The gradient statistic is the norm of the amplitude-scaled joint amplitude/shape
gradient difference divided by max(1, reference scaled-gradient norm). It is **not
relative error in Q, SOC, or voltage**. The maxima range over all public active-load
probes/prefixes, so the table does not rank fitted estimator accuracy. Polynomial
spaces also differ: products of interpolated responses contain higher degrees
than independently truncated Gram entries. No equal-approximation-space claim.

At one hour, quadratic entrywise RC endpoint error is at most0.0675mV in multiscale
and0.0104mV in embedded. Small endpoint errors coexist with large likelihood and
gradient defects. SOC transport here has the same exact signed-charge dependence;
this is not evidence that an estimator fitted to the wrong likelihood would retain
good SOC/Q estimates. The amplitude precision has spurious negative directions
even though the direct conditional response is affine in amplitudes.

The replayed quadratic witness finds a physically admitted amplitude direction
with curvature -1141492.75 versus direct +429781.25; a symmetric finite difference
gives -1141492.90. Both perturbed candidate paths remain admitted. This local
direction rules out interpreting the failure as only roundoff or an unobservable
direction. It is not an estimate of eventual fitted bias.

## Interpretation and the next architecture decision

The recurrence/index controls agree with direct C at interpolation nodes. The
defect appears when combining values between nodes: polynomial interpolation
weights can be negative, and independently represented quadratic entries do not
automatically retain a common sum-of-squares representation. Removing polynomial
terms for sparse storage supplies no PSD guarantee either. Keeping all cross
entries is necessary for joint information but is not sufficient for its validity.
The followup's square-root representation avoids that structural failure while
leaving response approximation error visible. Higher fidelity still costs space.

Do not repair this by clipping eigenvalues, arbitrarily inflating uncertainty or
letting a long simulation average the defect away. Those change the inference
object without supplying the needed error argument. Do not fit these three
entrywise candidates and interpret a solver's ability to stop as success.

Carry forward **a response/factor representation that preserves sum-of-squares
structure**, with all amplitude cross terms, as the next feasibility direction.
Before another campaign, attribute response/gradient defects to the individual
RC and directional-hysteresis basis functions, then compare physically specialized
or sparse response bases within an explicit complete-memory budget. This study
does not select a new basis, prove that it fits, or establish support migration.
H7 remains the reference rather than the embedded target. Any later approximation
or optimization still requires independent review and A6 error accounting.

## Resource limits and timing

Entrywise likelihood+live response+domain+scalar numeric subtotals are2392/5528/
3344B. Equivalent square-root factor+live response+domain+scalar subtotals are
2304/5168B for degrees1/2. All exclude calibration/rate/projection/index tables,
prior, solver, registry, error ledger, transaction/temporary storage, stacks/ISR
and overhead. These are lower payload subtotals, not complete-memory designs.

Actual retained NumPy arrays for entrywise schemes are7264/17440/15256B, before
Python overhead or scratch. The prototype forms1024row chunks and dense Gram/QR
scratch, so its live working memory is far above10KiB. The supplementary resource
audit enumerates the response controls' arrays and major scratch categories too.
Potential future lifetime reuse or procedural index generation is not credited
as already implemented savings. No target SRAM or WCET success is claimed.

For embedded one-hour data the single host run spends about0.164CPU seconds on
quadratic entrywise updates,0.0935 on response-degree2, and0.766 on H7. These are
isolated update timings, excluding queries, stimulus, solver and qualification;
they mix Python contractions, BLAS QR and native response generation. They are
feasibility observations, not robust benchmarks or M23 cycle estimates.

## Checks and review boundary

Seven targeted tests cover node parity against independent C, exact dependency
counts, chunk regrouping/sparse retained-term semantics, shape derivatives,
rest-null inverse-capacity information, domain refusal, update atomicity and
control/reference derivative transport. The original independent method reviewer
also enumerated275tensor-node probes with relative NLL defect<=6.61e-13 and
endpoint defect<=3.56e-15. Those checks do not establish between-node fidelity.

Review receipts bind the original method separately from the adaptive followup
and results. An initial curvature-report attempt failed while hashing a string
path; correcting that reporting type and rerunning produced the preserved witness.
No numerical algorithm or original run was changed by that correction.
No new physical/aging/risk/availability or whole-target requirement is closed.
