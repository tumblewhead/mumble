# A gallery that retains evidence rather than event records

Two histories are predictively equivalent under a fixed admitted model if
they imply the same distribution of requested future quantities for every
admitted future input sequence. A history message represents that equivalence
class to a declared tolerance. Raw events can disappear when their effect on
this class is preserved. Repetition alone does not prove equivalence.

Use three logically separate objects:

1. **An immutable physical dictionary.** A gallery describes stimulus/response
   functions or chronological transition/evidence operators. Templates include
   the domain of initial fast state, health, input duration/profile, temperature
   and noise assumptions. Two equal current pulses at different SOC or health
   need not have the same likelihood function. Exact parameter/state transport
   can establish equivalence; visual similarity cannot.
2. **An accumulated boundary belief and evidence coefficients.** Counts,
   residual sums, full mixed coefficients and uncertainty update once per new
   owned observation interval. A template is stored once while its evidence
   weight can grow. Old boundary states are eliminated using an admitted aging
   transition, preserving correlations and normalization. Gaussian Schur
   elimination is a closed base case; the actual battery closure remains open.
3. **A proof/error ledger.** The message records source ownership, model/domain
   identity, exact-versus-approximate operations and cumulative defect bounds.
   Bounds cannot be renewed merely by declaring a new epoch or discarding an
   old object. If composition leaves the proved domain, availability/precision
   must change explicitly rather than continuing with a false certificate.

A minimal proposed rolling token is a prior-free incremental operator with:

```
schema/model/noise versions
source_id and disjoint observation interval
entering/leaving boundary identities and physical transition relation
actual time, signed charge and absolute-throughput exposure
likelihood coefficients or a callable conditional likelihood with its domain
carried uncertainty, cross terms and normalization/branch-mass semantics
certified approximation and arithmetic defect, or explicit unresolved status
```

This is an interface specification, not implemented byte layout. An entire
rolling-window posterior is not automatically a valid token. If windows
overlap, the shared evidence must remain owned once. The initial prior remains
owned once. Known stimulus repetitions do not create independent state resets.

The dictionary can be organized by physical mechanisms already supported by
the experiments: OCV/charge response, RC relaxation/forcing, directional
hysteresis, and health transport. Those are function partitions; the probability
message must still retain their cross dependence. In particular,
`E[r_i F_i]` and `E[r_i r_j F_i F_j]` cannot be reconstructed from independent
rate and amplitude marginals. A node's stimulus profile is not its uncertainty.

For aging, keep the invariant response law/template separate from the current
health coefficients and their transition uncertainty. A cell changing R,Q,C
does not necessarily need a new dictionary entry for every event. It may need
new coefficients or a broader boundary belief. Whether this stays within a
fixed finite gallery requires the closure proof in P3; it is not assumed.

The user's ranges provide useful proposed compact domains. They do not yet
specify an aging kernel, a rate/variation bound, temperature/sensor effects or
how initial-reference uncertainty enters the relative factors. The wider
0.5–1.5envelope and likely0.7–1.3range must not silently become hard support or
validated probability. Directional trends can be tested as separate monotone
assumptions, including the resulting one-sided persistence of old constraints.

**Storage estimates:** the current combined-information research message uses
2544numeric bytes. A16dimensional Gaussian boundary mean and packed covariance
uses `(16+16*17/2)*8=1216bytes`; this proves a base-case storage count, not that
one Gaussian is adequate for the battery. A scalar repeated-response group
needs24bytes for64bit n,S,T, excluding descriptors, noise constants and context.
Ksuch groups need24Kbytes before dictionary/ownership/health/workspace costs.
A16dimensional quadratic information summary with constant and count needs
1232bytes. No gallery size or complete<=10240byte implementation is certified.
Exact real-arithmetic closure alone does not bound numerical precision, work,
stack, queues, retained domain certificates or transient factorization buffers.

The next implementation is the incremental token and exact elimination
reference. Its purpose is to test ownership, repeated-event sufficiency,
chronology and aging transport before adding another posterior approximation.
