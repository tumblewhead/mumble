# What the system trials establish

All twelve estimator runs completed their four-hour sources. The encoding
comparison passes the preferred scales in every case, while useful capacity
estimation does not generalize to the new cell and gradual-aging cases.
These two findings must remain separate.

For capacity in absolute units, the decomposition is exact:

    Q32 − Qtrue = (Q32 − Q64) + (Q64 − Qtrue).

The first term includes encoding and its later effects on conditional moments.
The second includes finite health/nuisance support, moment projection, physical
model and aging assumptions, and the evidence actually supplied by the stream.
The largest relative binary32/binary64 capacity difference is 0.02813%, whereas
final point errors in the three mismatched cases are −10.053%, −5.761% and
−2.702%. Increasing encoding precision cannot repair the common reference error.

## Health support and false precision

At 25 °C, the history model permits Q values of 0.060, 0.051 and 0.042 Ah.
The between-nodes cell is a stationary 0.0567 Ah cell. Its true value is inside
the overall envelope but is absent from the latent support. A mixture of nodes
can have the correct *mean*; that does not make it a distribution over batteries
with the missing intermediate capacity or reproduce their charge trajectories.

The saved checkpoints show repeated switching between supported capacity levels
during excitation. At one hour, the estimate is approximately 0.051 Ah, and its
final value is 0.05099993 Ah with a reported SD of 0.00002579 Ah. The 0.00570007 Ah
error is about 221 of those reported standard deviations. During the rest phase,
the truth lies outside mean ±3 SD on 98.76% of samples. Across the full run this
fraction is 91.34%. Thus small reported local uncertainty cannot be treated as
reliable uncertainty about the real cell.

The controlled change from matched to between-nodes modifies only true Q/R0;
stimulus, nominal noise, prior and inference remain unchanged. This implicates
model support and its interaction with the inference machinery. It does not
separately identify the contribution of Q discretization, R discretization,
nuisance coupling, conditional Gaussian projection and the assumed aging kernel.
In particular, the final selected level is not simply the nearest Q node.
Calling the entire discrepancy a rounding error would be incorrect.

Gradual aging exposes the same issue along a trajectory. True Q moves from
0.060 to 0.054 Ah, passing through capacities the model cannot represent as
states. During weak use, Q error grows to 6.13%; after loading resumes the mean
moves towards a lower discrete level, with a transient error up to 24.23% and
a final error of −5.76%. The combined case also changes RC-branch R/C, thermal
response, load amplitude and noise; it is a system stress, not a clean causal
isolation of any single model defect.

Monotone *physical paths* do not require a monotone *posterior mean*. Updating
weights over paths can move a mean in either direction. The observed estimate
switching is therefore not, by itself, proof that the monotone transition code
violates its support. It is a symptom to investigate jointly with the missing
continuous health states and uncertainty.

## Why SOC and voltage can look good while Q is wrong

For fixed Q and charge throughput A(t) in Ah,

    z(t) = z(0) − A(t)/Q,
    delta_z(t) = A(t) * [1/Qtrue − 1/Qestimate]

when the entering SOC is shared. The SOC sensitivity to capacity scales with
net charge displacement, not the number of repeated samples. The nominal
70-second, 0.03 A pulse displaces only 0.0005833 Ah. Even the 0.0567 versus
0.051 Ah mismatch produces about 0.115 SOC percentage points of displacement
over that pulse. Balanced cycles then return the net charge near its previous
value. State corrections and nuisance compensation further change the actual
observed discrepancy; this calculation is explanatory, not a fitted error bound.

Accordingly, every history SOC estimate in all four trials stays within the
preferred 0.5-point scale, even while capacity is wrong. Saved-checkpoint
pre-update standardized voltage innovations have RMS about 0.90–1.08 across
the phases. Good voltage residuals and useful SOC alone are insufficient gates
for capacity accuracy or calibrated uncertainty. During zero current, no new
charge displacement is available to identify capacity change directly; earlier
evidence and the evolution model must preserve appropriate uncertainty.

## Practical significance and next repair

The matched control meets both preferred scales during rest. On renewed
excitation, four of 126,000 samples exceed the Q scale, peaking at 0.784%; SOC
remains well within its scale. Preserve this brief failure, but it is a lower
priority than the persistent multi-percent capacity bias and false precision
in the mismatched cases. No precision changes were made to chase it.

The immediate next step should be a focused health-representation comparison:
allow continuous Q/R variation within or instead of the coarse health nodes,
retain joint SOC/nuisance dependence, and compare against the frozen matched and
between-nodes streams before repeating the gradual-aging case. The earlier
centroid/trajectory idea is relevant, but its continuous residual and uncertainty
must accompany the centroid; a moving point alone is not history.

Use the unchanged binary32/binary64 pair to keep encoding separate from that
model repair. Require capacity accuracy only when excitation supports it, and
otherwise require honest unresolved status/uncertainty. Do not invent a
forgetting factor or inflate uncertainty merely to cover these particular
truths. Independent noise realizations and broader excitation will be needed
before making coverage claims. The original rolling solver remains an external
baseline until the [ownership boundary](boundary.md) can be integrated without
counting observations twice.

Storage and execution optimization should follow this behavior repair. The
results already show that extra codec accuracy is not the useful next target.
