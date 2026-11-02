# Outcome-informed RC fidelity control

The initial pilot001/full001 results are preserved. At one-hour multiscale,
H2/c22/tensor Q shifts versus the converged direct fit are +3.28/+4.68/+4.25%.
All three share low-degree RC response. H7 is closer but changes both RC and H,
so that comparison alone cannot attribute the difference. R1 already showed
central RC value exactness with nonzero derivative error.

Add R5_H2, R5_H2_c22 and R5_H2_tensor: only change the RC nodal degree from 2 to 5;
retain each H representation's identical 3x3 nodes, projection, physical box,
prior and joint-likelihood semantics. Run the three original streams at the
126000-record prefix, with the original arms/direct fit repeated as controls.
This is a separately registered follow-up, not independent confirmation or a
replacement for original failed candidate results. No truth, support, initialization,
convergence tolerance or forecast changes are allowed. Preserve unresolved cases.

Factor widths 52,54,58 give 11024,11880,13688 bytes; the response state is 456 B
and the lower domain/scalar allowance 96 B. These controls exceed the 10 KiB goal
before full overhead; they test attribution and do not nominate a deployable fix.
Independent class and experiment review is required. If higher RC fidelity helps,
seek a more efficient RC representation using the symbolic sensitivity findings;
do not promote a global degree increase on this control alone.
