# Readout-only endpoint SOC width supplement

Integration review found that the primary runner reported Q widths, SOC centres
and future voltage widths but omitted the promised endpoint SOC width comparison.
Preserve the original full001/rc001 receipts and compact summary. This supplement
uses their saved selected origin fits/full covariance roots and factor snapshots;
no optimization, centering, domain, objective or source observations are changed.

At each selected fit, direct C evaluates the complete original-prefix state map F
and full joint GN precision P with the original prior. Report endpoint SOC SDs:

- direct C transport of the candidate's saved full covariance;
- compressed transport D of the same covariance, when physical support permits;
- direct C transport of the direct-objective local covariance at that same anchor;
- the direct fitted reference's endpoint SD, only when that reference converged.

The standard deviation for a transport row j and covariance root C is ||j*C||.
All coordinates/cross terms are retained. Report raw SDs in SOC percentage points
and labeled ratios; no diagonalization or uncertainty inflation. Prior-supported
widths under rest do not establish stimulus information or calibrated coverage.
Unresolved fits remain labeled; fit-to-fit ratios require both fits converged.
Check source, input recipe, observation, saved-fit and factor identities. This is
a separate, outcome-informed readout receipt completing the registered diagnostic.
