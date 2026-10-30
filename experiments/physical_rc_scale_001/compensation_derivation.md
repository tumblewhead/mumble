# Final registered adaptation: physical state compensation in the mean

The construction-only conditioning diagnostic integrates the slow conditional
analytically. At32records, after information-scale fitting, the carried-sum
variance discrepancy contains18.83mV² from its conditional fit and40.10mV²
from replacing construction prefixes by generated prefixes. This is an exact
finite moment decomposition using fixed construction and model latent labels;
it is not a causal attribution of the complete voltage variance.

Physical RC voltage contributions add as v1+v2+v3. If their local conditional
compensation is affine in physical voltages, expressing the slow response in
F coordinates requires terms `(a3/a1)*F1` and `(a3/a2)*F2`. The existing mean
has F1 and F2 with constant coefficients. Add just

```
F1*(a3/a1-1), F2*(a3/a2-1)
```

to the slow mean. Together with the original terms these span the physical
compensation directions. Subtracting1 is a fixed public feature change, not
a fitted center. Both coefficients may be zero, exactly recovering the last
model. Keep the combined precision law and refit only this slow conditional
using construction data. Prefix densities and every other conditional remain
unchanged, so any response change can be tied to this specified adaptation.

This enlarges the mean family; physical motivation does not guarantee a
better heldout fit or elimination of prefix-distribution error. All13probes
and the same finite source partitions remain visible. Reusing heldout sources
after earlier comparisons means this remains exploratory. No further family
tuning is planned within this experiment.

Two coefficients in each of two components add32bytes. Retained numeric
storage becomes2576bytes,80bytes above the original2496. These numbers exclude
metadata, workspace and complete subsystem SRAM. No physical aging or rolling
integration is implemented here.
