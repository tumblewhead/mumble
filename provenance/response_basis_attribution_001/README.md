# Hysteresis dominates the small response-basis error; more degree is not a free repair

The signed attribution identifies joint directional hysteresis as the largest
group on302of306active-load public probes. Four earlier-prefix active-load probes instead
rank RC3 first. The basis intervention confirms a tradeoff: degree3 in log-rate
coordinates reduces the worst gradient defects, but costs more memory and worsens
many individual probes. Linear-rate coordinates are not a general improvement.
No estimator, default or target kernel is promoted.

See the [protocol](../../specifications/response_basis_attribution_001/README.md),
[compact results](summary.json), and [replay check](replay_check.json).
The local raw studies are experiments/response_basis_attribution_001/attribution001,
basis001 and basis002. Each uses the previous three stimuli, three prefixes through
one hour at35Hz, and51public queries. Input hashes match the prior study, including
the embedded35520sample failure prefix. Truth never enters the attribution or fit
basis; these are unfitted model-query comparisons, not cell population estimates.

## What creates the gradient defect

For whitened reference residual r and Jacobian J, response and sensitivity errors
give `dg = J^T dr + dJ^T r + dJ^T dr`. We split these signed vectors into RC1,
RC2,RC3 and joint hysteresis, retaining all pair interactions. Norms are not
additive and are not percentages of posterior uncertainty. Both directional rates
remain in the same hysteresis group; their derivative channels are reported
separately. The reconstruction closes to9.07e-10 and the QR comparison to6.80e-10
in the normalized gradient metric over the sampled prefixes. This checks the
diagnostic against the independent direct C model; it is not a uniform error bound.

At one hour, maxima across the51public probes are:

| Load | Largest H-only relative gradient defect | Largest RC-only defect | H voltage-defect RMS, maximum across probes |
|---|---:|---:|---:|
| Multiscale | 0.57679 | 0.003043, RC3 | 0.3675mV |
| Embedded | 0.06312 | 0.0001196, RC3 | 0.1490mV |

The first term, exact sensitivity acting on voltage-response error, is much larger
than the sensitivity-error term at the worst one-hour query in each active load.
Thus improving only derivatives would miss the main mechanism at those queries.
Rest instead exposes RC initial-state sensitivity error even though these public
amplitudes have zero initial RC voltages and hence zero RC voltage-response defect.
All groups/interactions and the four non-H-dominant exceptions remain in the report.

## Paired intervention

RC stays degree2. H varies between total degrees2/3 and log/linear rate coordinates.
The same physical rate support is used in every arm. Linear coordinates map
`[center/e,center*e]` to[-1,1], with the correct log-rate chain derivative. No prior
or probability mass is transformed or reweighted: these are response bases.
Every arm retains one joint QR factor and all amplitude cross terms.

Worst one-hour relative joint-gradient defects over the public probes:

| H basis | Multiscale | Embedded | Packed likelihood factor | Factor + live response + domain/scalars |
|---|---:|---:|---:|---:|
| degree2, log | 0.57559 | 0.06312 | 4760B | 5168B |
| degree3, log | 0.32205 | 0.02673 | 7224B | 7744B |
| degree2, linear rate | 1.34624 | 0.40208 | 4760B | 5168B |
| degree3, linear rate | 0.21906 | 0.08518 | 7224B | 7744B |

The degree3 log arm improves those worst one-hour values by1.79x/2.36x. Across
all active prefixes, however, it improves191of306probe gradient norms and
worsens115. In embedded alone,62improve and91worsen; the worst defect across all
embedded prefixes drops only from0.06312 to0.04203 (about1.50x). Linear-rate
degree2 worsens all153embedded probes; linear-rate degree3 worsens142of153.
The more favorable multiscale result for degree3 linear rate does not make it
a robust winner across these stimuli.

These defects are **not relative errors in Q, SOC or voltage**. They are scaled
joint amplitude/shape likelihood-gradient differences relative to the direct
gradient. No parameter fitting or physical coverage test was performed. The
baseline and interventions have different response spaces/node grids, so the
degree change includes the associated projection-grid change. No claim that
raising degree monotonically improves each query. Rest differences among H arms
are at rounding scale; the informative comparison is kept separate.

For reference, the worst one-hour H*h endpoint discrepancies drop from0.5181 to
0.1109mV in multiscale and0.2809 to0.1074mV in embedded for degree3 log. These
transport improvements do not guarantee that a fitted estimate is improved. All
out-of-box diagnostic queries remain refused; no domain enlargement or migration
has been demonstrated. The attribution pass itself inherits the domain refusal
evidence; the basis intervention reruns it explicitly.

## Resource tradeoff and next step

The degree3 factor costs2464B more; live response state grows312to424B, giving
2576B additional numeric payload in the table. That leaves2496B of the10KiB goal
before calibration/projection/rate tables, prior, optimizer, metadata, transaction
backup, temporary buffers and stack/ISR. It is not a complete-memory design.
Actual retained NumPy arrays are10400B/16240B for degree2/3 before scratch and
Python overhead. Update/query scratch is itemized in summary.json. A single host
run suggests roughly1.36–1.41times the update CPU for log-degree3 on active loads;
this excludes solver/query/system costs and is not an M23 benchmark.

Do not simply add more global polynomial degree or select linear-rate coordinates
from one favorable load. Preserve the log-degree2 baseline and log-degree3 control
for the next **short fitted-query comparison** against direct history and H7.
Measure SOC/Q shifts, joint uncertainty/readout limitations and proposed-load
voltage predictions at common supported prefixes. Use the existing development
targets (SOC0.5percentage point,Q1%) to judge practical return on added memory;
keep forecast accuracy distinct from safety authorization until voltage/fallback
requirements and physical bounds are supplied. The present unfitted gradient
probes cannot decide whether an extra2576B is worthwhile in application terms.
This is the next test, not a request for a long campaign or a promotion decision.

## Validation and adaptation

Six new targeted tests cover the signed expansion, legacy parity, both coordinate
derivatives, same-domain behavior, source/order and invalid update atomicity,
regrouping/storage counts and inherited chart-helper consistency. The attribution
review independently checked random-vector algebra, direct transport chaining and
log-shape finite differences as well as the seven previous control tests.

The original attribution protocol and first basis implementation remain archived.
basis002 adds coordinate-consistent inherited chart helpers so residual/NLL/output
helpers cannot accidentally use log coordinates in the linear-rate arm. This
does not change the study's evaluate/update arithmetic:1872query-arm records and
all stream hashes match basis001 exactly. The earlier summary is reproduced
separately as summary_basis001.json; original raw results remain unchanged.

Independent review covers the conditional attribution identity separately from
the new basis code and outcome interpretation. All physical/aging/calibration,
uniform approximation, support migration, unattended availability and target
resource qualifications remain open.
