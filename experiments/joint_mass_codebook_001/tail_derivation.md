# Tail-preserving probability coordinates

The primary and supplemental receipts are separate. No initial successful
result is overwritten after discovering a stronger uncertainty requirement.
The initial unit-sphere rounding bug is preserved in `development001`, the
relative-amplitude study in `attempt001`, the tail audit/log12 study in
`tails001`, and the16-bit precision follow-up in `log16_001`.

## Why absolute-mass accuracy is insufficient for retained history

For the declared finite probability vector p=(1-1e-12,1e-12), the12-bit linear
relative-amplitude code retains positive support but represents the small mass
as about5.96e-8. Its TV error is only about5.96e-8. A later likelihood
L=(1e-10,1) changes the true rare-state posterior to about0.009901; the encoded
posterior becomes about0.998326. Thus the later TV error is about0.988425.

No observations are replayed and no numerical solver fails in this example.
The initial geometric error is small in absolute probability and large in
relative probability at a rare state. Future data can make that state relevant.
Exact support preservation prevents false zero exclusion, but it does not
control the relative weight of small positive probabilities.

In the coarse finite-state battery fixtures the same issue is visible in
uncertainty: linear12bit amplitude encoding inflates SOC standard deviation by
up to118.37times while its worst mean difference is only0.000117SOC percentage
points. The extremely narrow reference distribution is itself a discrete-grid
artifact, not validated physical precision. Nevertheless the codebook must
preserve its declared target rather than being judged only on its mean.

## Log-amplitude quantization controls the relevant projective error

Retain the unit-sphere interpretation but encode

    l_i = log2(sqrt(p_i)/max_j sqrt(p_j)).

Each positive coordinate is in a declared interval[-S,0]. Zero has its own code;
it is not approximated by a small positive value. With B=2^bits-1, reserve code0
for zero, and let codes1...B represent[-S,0] with spacing

    Delta=S/(B-1).

Decode positive weights w_i=2^(2*lhat_i), then q_i=w_i/sum_j w_j. The maximum
code B fixes the amplitude scale. Re-encoding a decoded distribution recovers
the same integer vector in real arithmetic; finite idempotence checks pass.
The exact same span512 is used in12bit and16bit comparisons. Ratios outside
the declared range reject; no silent tail clipping or precision adaptation is
used. This encoding uses exponentials to decode probabilities, not to forget
history or model physical aging.

If |l_i-lhat_i|<=Delta/2, unnormalized log-probability error is bounded by
ln(2)*Delta. Normalization adds a common scalar, so the **oscillation** satisfies

    D(p,q) = max_i log(p_i/q_i)-min_i log(p_i/q_i)
           <= 2*ln(2)*Delta.

The usual sharp normalized-density bound yields

    TV(p,q) <= tanh(D(p,q)/4).

For completeness, if r=p/q ranges over[m,M], normalization gives E_q r=1.
The largest TV for fixed extrema is achieved by a two-point distribution on
m,M. Maximizing that value at fixed M/m=exp(D) gives
(sqrt(M/m)-1)/(sqrt(M/m)+1)=tanh(D/4). This is a relation between complete
probability measures; point errors, local Hessians and marginal boxes do not
replace its premises.

## Composition lemma

For any common strictly positive likelihood L,

    log(Bayes_L(p)_i/Bayes_L(q)_i)
       = log(p_i/q_i) + a common normalization constant,

so D is unchanged. For a common stochastic transition K, the output ratio at
each reachable state is a q-weighted average of incoming ratios. It lies
between their previous extrema, so D cannot increase. Identical zeros are
treated through the common reachable support; these statements do not license
discarding a positive state or changing a transition model.

If each codebook operation contributes local oscillation d_k, triangle
inequality gives

    D_k <= D_(k-1) + d_k,
    TV_k <= tanh((D_0+sum_j d_j)/4).

This avoids the likelihood amplification coefficient needed by a purely TV
ledger. Finite tests check common-likelihood invariance, Markov nonexpansion,
local quantization bounds, accumulated bounds and corresponding joint-event/
covariance queries. Floating arithmetic is still not outward-certified.

For the fixed span512, the worst per-encoding real-arithmetic D increment is
about0.17337 at12bits and0.010831 at16bits. These are representation bounds,
not chosen acceptance thresholds. The measured16bit cumulative TV bound is
at most0.02157 after the eight-event controls, with observed TV at most0.003844.

## What the16bit follow-up changes

The same rare-state example gives posterior probability about0.0099183 with
log16 encoding, versus0.0099010 uncompressed. TV error is about1.73e-5.
Across the six declared short fixture/rate combinations, log16 has worst Q
mean distortion about0.0296% and SOC mean distortion0.001743percentage points.
Its SOC standard-deviation ratio stays within approximately0.99807–1.00255;
these are preservation measurements relative to the finite-state reference,
not coverage or physical accuracy results.

For4,131 joint masses, log16 costs8,262B of actual packed payload. The span,
grid/basis/source descriptors and all update workspace are extra. This is a
useful uncertainty-preserving diagnostic reference, not a complete10KiB
firmware solution. The implicit codebook has no huge prototype table; evaluating
and updating its4,131-coordinate probability shape is still substantial work.

Finally, an additive D ledger is not an indefinite stability theorem. The
worst sum can grow with every genuinely changed encoding. Static uncertainty
coordinates need not contract under physical aging. Re-encoding idempotence
removes drift from unchanged storage only. To support ten years we still need
a bounded cumulative distortion argument, a justified contraction/query-bound
argument, or a representation whose repeated physical updates are exact within
the required class. No such premise is silently assumed here.
