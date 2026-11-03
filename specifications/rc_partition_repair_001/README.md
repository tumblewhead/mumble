# Partition the RC representation by free and forced response

Base 8ebf9b4, branch experiment/rc-free-forced-repair-001. This is a focused
representation study; no production default, prior, original centre, support,
start, stopping rule or physical model changes. Read the preceding joint-refit
report and P4 before implementation/results. Every proof and implementation change
requires fresh-context independent review.

The last rest discrepancy must originate in the free RC response: forced RC
responses and their shape derivatives vanish at identically zero current from
the retained origin. Initial RC voltages remain learned amplitudes. Richer free
decay can therefore target this failure without expanding every forced response.
This is a physical partition, not a test-rig mode: candidates always use the same
representation on every observation, including active loads and later rests.

Keep six-term Taylor H fixed in the candidate comparisons. Test fixed public
degree-three and degree-five Chebyshev free response with the original degree-two
Taylor forced response. Controls: existing TaylorRC/TaylorH2, matched TaylorRC/H7,
full degree-five RC with Taylor H, and the separate R5/H7 reference; plus direct.
One joint factor preserves all cross terms and original uncertainty. No resetting
at rest, adaptive basis selection, sample dropping, recentering or duplicated prior.

Six frozen cases: the same 21008 and 126000 records, three recipes each. Verify
observation/source identities and unchanged selected direct/TaylorRC_TaylorH2/
TaylorRC_H7/R5_H7 controls against the prior refit. Two common public starts and
unchanged 60-round solver. Report every attempt/status. Unresolved direct rest
continues to withhold fit-to-fit qualification. Separate same-anchor likelihood
precision and direct/compressed state-transport forecasts. Apply M1/P3 numerically
without incorrectly using Taylor P2 envelopes for collocation free response.

Also run a bounded public mechanism probe: irregular intervals, signed currents,
nonzero initial RC amplitudes, log-tau offsets [-1,-.9,-.7,-.13,0,.13,.7,.9,1].
Report free and forced response and slope error separately, including regressions.
No truth-based calibration or claim of uniform support fidelity from sampled probes.

Pre-implementation screening considered a Cayley coordinate w=tanh(log(tau/tauc)/2).
Scalar free-exponential sampled maxima at |log offset|=1 remained about .046–.064
at degree two, versus .066–.067 for log Taylor two; higher degrees reduce them but
expand both response families if used uniformly. This unregistered analytical
screen is not qualification evidence. The selected study instead targets the
demonstrated free-response defect and retains the proven forced recurrence.

Expected packed factors: baseline 4760 B; free3/forced2 5624 B; free5/forced2
7568 B; full RC5/TaylorH2 11024 B. The initial adapter retains padded native state,
so report actual state/table/NumPy and partial packed subtotals separately. No
complete M23 memory/CPU or lifetime assertion. Store only source and compact
reviewed provenance in Git; raw run artifacts and binaries stay local.

Tests: native free/forced row reproduction against old controls, zero-current
restriction, central derivative finite differences, shared physical support,
chronological chunking and atomic refusal, full joint covariance/transport.
Then execute this fixed study once, independently review/reproduce it, and decide
whether the free/forced partition earns its storage. Any substantive repair or
new experiment is separately recorded and reviewed.
