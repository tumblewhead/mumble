# Optimization lemmas

Status: handwritten conditional proofs. Implementation correspondence, target
bounds and concrete error budgets must be supplied for each optimization.
Finite exact examples in `check_contracts.py` test some identities and expose
counterexamples; they are not a formal verification of optimized C.

## K0. Exact trace refinement

Let R and C be reference and candidate transition systems. Inputs include samples,
queries, reset and admitted faults. Public observations include consumed/published
prefixes, estimates, joint uncertainty, query authorization, statuses and externally
observable side effects. Internal memory layout is not itself a public observation.

Assume a relation S between states such that initial states are related and, for
every admitted input and related pair, each candidate operation terminates within
its budget, produces the same public observation as R, and ends in related states.
Then every finite admitted trace has identical observations: the base is the
initial relation, and the transition premise is the induction step. Bounded
internal stuttering is permitted only when it preserves the declared deadline.
Thus trace safety and established availability properties transfer from R to C.

For concurrency or faults, S must cover all admitted interleavings/failure points,
not just the successful sequential path. If C can choose nondeterministic actions,
every choice needs the relation or a separate allowed-behavior contract. Proving
equality of mathematical objectives is weaker than this claim: stopping rules,
rounding, supports and recovery may differ. Bitwise implementation equivalence
additionally requires a specified arithmetic environment and observable ABI.

Guard removal is permitted only if its predicate is proved for all reachable
states at that program point in the admitted domain. A private kernel can inherit
an invariant from a checked entry point only if every caller establishes it and
no intervening mutation breaks it. Reset, bad input, overflow and error branches
belong in that argument. Finite testing does not prove unreachable branches.

## K1. Numerical perturbation and decision preservation

For a common input stream, let the reference update be T_k and candidate defect
be at most e_k in a declared norm. If T_k is L_k-Lipschitz throughout the needed
region, and states differ by at most b_k, the triangle inequality gives

    b_(k+1) <= L_k b_k + e_k.

For query f with Lipschitz constant L_f and candidate query-evaluation defect eta,
the output difference is at most L_f b_k+eta. Domain membership and numerical
evaluation of the bound need their own proof. An integrator cannot use a strict
contraction bound. Discontinuous branches require a margin argument or a bound
covering all possible successor branches; differentiability on one path is not
a global premise. E4/E5 supply separate joint-width and center bounds.

For a decision margin g, authorize when g>=0. Suppose |g_C-g_R|<=delta.
Using g_C>=delta guarantees g_R>=0. If g_R>=2delta, this conservative candidate
also authorizes. Proof: subtract/add delta in the two inequalities. Thus the
ambiguous band has an explicit size; it is not silently treated as equivalence.
Outside |g_R|<=delta, unguarded signs agree, but the conservative rule can refuse
some additional safe reference decisions. Availability must budget this refusal
or use a qualified reference fallback. Other decision conventions require their
own boundary treatment.

Example: margins +epsilon and -epsilon differ by only 2epsilon but choose opposite
loads. Small numerical error alone never proves identical decisions at a threshold.
Thresholds include support guards, solver termination, refresh triggers and trust
status, not only brownout decisions. Reference authorization must itself be sound;
copying or conservatively approximating an unqualified decision is not a proof
against physical truth.

Early solver termination can use E5 only after certifying the reference gradient
residual, Hessian lower bound and query derivative bound in the required region.
A small candidate gradient or fixed iteration cap alone supplies no such guarantee.
The cap bounds execution; reaching it may require unresolved status. Removing
constant objective terms can change an absolute-cost stopping criterion even
when normalized posterior mathematics is unchanged.

## K2. Successive optimizations consume a cumulative budget

All comparisons here are at a common prefix, parameter domain and coordinate
system. For objectives F_0,...,F_m with osc(F_i-F_(i-1))<=omega_i,

    osc(F_m-F_0) <= sum_i omega_i.

Proof: telescope the objective differences and apply the triangle inequality
to their values at any two domain points. E2 then gives the posterior bound
tanh(sum_i omega_i/4), under its normalizer/support premises. This is not by
itself a lifetime coverage statement or a bound on physical model error.

For SPD precisions with

    (1-epsilon_i) P_(i-1) <= P_i <= (1+epsilon_i) P_(i-1),
    0<=epsilon_i<1,

transitivity of matrix order gives

    product_i(1-epsilon_i) P_0 <= P_m <= product_i(1+epsilon_i) P_0.

Inversion gives the corresponding reciprocal covariance bounds. The proof is
induction using positive scalar multiplication; the matrices need not commute.
Replacing the products by 1 +/- sum epsilon_i is generally incorrect. If query
Jacobians or linearization points also change, bound those separately. A local
quadratic claim cannot silently become a nonlinear posterior claim.

Point-error bounds add only in a common output/norm with compatible comparison
points. Through sequential kernels, downstream Lipschitz factors multiply earlier
errors, as in K1. Root-sum-square is not justified for coherent deterministic
errors. Numerical budget consumption is not independent sensor noise and does
not automatically spend statistical alpha; use the appropriate transfer theorem.

The immutable-anchor ledger therefore persists across commits. A candidate can
be close to every parent while drifting unacceptably far from the anchor.

## K3. Graph scheduling and memoization

Let a graph node evaluate a deterministic pure kernel y=f(x,c), where x contains
all numerical dependencies and c contains every relevant configuration/arithmetic
dependency. A cache hit is exact if its key implies equality of (x,c), its value
is the unmodified result from that kernel version, and the value remains valid.
Proof: identical arguments to the same deterministic function have identical
results. A topological reordering of pure independent nodes preserves graph
outputs by induction over the dependency order.

Mutable state writes, source consumption, counters, error reporting, rounding
environment and other side effects require explicit edges and once-only semantics.
They cannot be omitted merely because the numerical output is cached. A phase
or pointer address alone is not a complete key. Depending on the kernel, include
dt/sample-rate configuration, temperature, physical parameters, anchor/chart/prior
versions, coefficient versions and source boundary. Hash-only keys need collision
handling or a separately qualified error model; a hash match is not logical equality.
Version wrap and concurrent invalidation require range/synchronization proofs.

Quantized keys are an approximation: if f is L-Lipschitz over each key bucket
of diameter d, a cached representative has error <=Ld. Propagate that defect by
K1/K2, including derivative outputs and reuse at every step. Quantizing a cache
key does not authorize quantizing the physical parameter space into a battery
codebook. Approximate temperature or rate reuse needs the same proof.

Do not cache unresolved solver results as validated outputs. A memory read fault
is an extra fault path of the cached implementation and needs the declared fault
contract. Eliminating computation may preserve successful arithmetic while changing
failure behavior; K0 covers the latter separately.

## K4. Lifetime-based storage reuse

For each logical object define the interval from its first write through its
last possible reader. Include normal use, trial computations, rollback, retries,
serialization, interrupts and concurrent accesses. Two objects can share a byte
range only if their live intervals do not overlap, or a stronger in-place
dependence proof shows that every old value is read before being overwritten.

Proof for disjoint lifetimes: order the writes/readers by the established
happens-before relation. No write for the next occupant can occur before the last
reader of the previous occupant. Induction therefore preserves every required
value. A liveness graph omitting failure readers proves only a weaker program.
In particular, aliasing a trial object with the rollback copy invalidates a
compute-then-commit transaction even when all ordinary successful runs agree.

The allocation also requires adequate capacity/alignment, valid C object/type
and aliasing rules, no dangling retained pointers, and a proven concurrency model.
The interval argument alone is not a full C memory-safety proof. Registry metadata,
guards, backing storage and stacks all count toward target memory.

## K5. Cost and memory bounds, including cold and exceptional paths

Suppose proved kernel upper costs are C_s per sample, C_b per block, C_r per
refresh and C_f per recovery attempt, with fixed setup C_0. If N samples, B-block
grouping and proved counts n_r,n_f apply, then a sequential execution has

    C_total <= C_0 + N C_s + ceil(N/B) C_b + n_r C_r + n_f C_f + C_other.

This follows by adding each executed operation's upper bound. C_other includes
executive, cache, certificate, diagnostics and specified interference costs.
Counts and cost bounds must include admitted worst inputs and faults. Mean
profiling time or the largest observed run is not a proof of a worst-case bound.

Under a contract permitting at most one refresh and r recovery attempts per
block, a sufficient block cost bound is

    C_block <= B C_s + C_b + C_r + r C_f + C_other,block.

For a single reserved execution budget rho*F_clk and block deadline D, require
C_block<=rho*F_clk*D with a proved scheduling/interference model. D=B/F_s applies
only to that fixed-rate block contract. Sample-service deadlines, nonpreemptible
sections, arrival jitter and maximum queue backlog require additional bounds.
A long-run utilization improvement can coexist with a deadline regression.

A cache replacing cost C_compute with hit cost C_hit and miss cost
C_compute+C_lookup+C_fill has expected cost determined by the qualified hit rate;
its worst path can exceed the original. No speedup follows from memoization alone.
Similarly, a graph executive must save more work than its dispatch/invalidation
overhead under the claimed workload. Cold start and recovery must be included.

For a concrete verified memory layout, total SRAM bounds include static storage,
allocated scratch/caches/buffers, maximum feasible call-chain stack and interrupt
nesting, metadata, alignment and allocator overhead if any. Nonoverlapping live
data may share storage by K4. Sum of live payload sizes is a lower requirement,
not automatically an upper bound for a real allocator with fragmentation.
Flash includes lookup tables and software arithmetic/runtime support. Measure
the final target link image and validate the layout/call graph used in the proof.

## K6. Cadence changes and closed-loop behavior

Different processing groups preserve the exact feature likelihood only if all
rows are generated chronologically from the same carried model state and every
observation is consumed exactly once. Different QR schedules have separate
roundoff obligations. Different nonlinear anchors or refresh schedules can
change the approximation and must meet K1/K2; exact algebraic additivity of the
underlying data does not make those approximations schedule-independent.

Deferring a readout can preserve a likelihood while changing externally visible
latency. A cached output requires transport to the requested physical boundary
with a certified error; a nonce is not a replacement for dt in physical dynamics.
Every dropped/merged observation requires its own evidence/noise-model argument.
Skipping apparently uninformative samples is not an exact implementation change.

Matched-input replay bounds do not alone prove closed-loop equivalence when
estimates affect the next load. K0 transfers closed-loop behavior for identical
observations under the same deterministic controller, by induction. For bounded
numerical changes, either prove controller decisions match using margins, or
include the controller/environment in a coupled error/reachability argument.
Robust load authorization may allow differing safe actions, but then availability
and future excitation must be requalified under the changed policy.

## K7. Basis changes, elimination and discarded modes

For invertible M, phi_new=M phi and A_new=A M^-1 preserve

    ||A_new phi_new||^2 = ||A phi||^2.

This follows by substitution. It permits exact coordinate preconditioning of
the likelihood. The physical parameter map, prior, state transport, derivatives,
support, error accounting and any density Jacobian under a parameter change must
be transformed consistently. A feature basis change alone is not a parameter
change. Conditioning and rounded evaluation still need K1.

For a full quadratic in retained x and eliminated y, with precision blocks
A,B,D and linear terms a,b, assume D SPD. Completing the square in y gives the
retained precision A-B D^-1 B' and linear term a-B D^-1 b. Gaussian integration
also contributes the determinant/normalization factor of D and the completed-
square constant. These can depend on remaining nonlinear coordinates. Dropping
them can change posterior mass even when the conditional optimizer is unchanged.
Replacing elimination by A alone discards correlation; it is not equivalent.

Explicitly, for F(x,y)=x'Ax/2+x'By+y'Dy/2+a'x+b'y+c and m eliminated
coordinates, integration over all y in R^m gives negative log marginal

    x'(A-B D^-1 B')x/2 + (a-B D^-1 b)'x + c
       - b'D^-1 b/2 + log(det D)/2 - m log(2pi)/2.

Substitute y+D^-1(B'x+b) to complete the square and use the Gaussian integral.
Constrained y support adds a domain-dependent mass term; this unconstrained
formula cannot silently replace a bounded-support elimination.

For omitted feature modes with residual error e and derivative error dJ, the
earlier identities Delta F=r'e+e'e/2 and Delta g=J'e+dJ'r+dJ'e give the starting
budget. A small omitted coefficient alone does not bound the accumulated
likelihood or its weakest joint directions. Any rank/basis reduction must preserve
the required joint errors and endpoint map on the declared domain and horizon.
Changing continuous parameter support requires a separate model contract.
