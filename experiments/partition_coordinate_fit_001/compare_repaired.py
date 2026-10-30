"""Run the same frozen factorial with one explicit arithmetic substitution.

The original driver/source/receipts are not edited. All injection is process
local and bound into the new reservation; the prior run stays reproducible.
"""
import json
import sys
from pathlib import Path
import numpy as np
from experiments.partition_coordinate_fit_001 import compare as driver
from experiments.partition_coordinate_fit_001 import stable_normalizer
from experiments.partition_coordinate_fit_001 import fitting

HERE = Path(__file__).resolve().parent
ORIGINAL_LOG_MASS = driver.c.v.log_mass


class RepairControls(driver.Controls):
    def test_normal_subnormal_transition(self):
        for a in [36., 37., 37.5, 38., 38.2, 38.4, 39., 40.]:
            for lo, hi in [(a, a+.1), (-a-.1, -a)]:
                mode = min(hi, max(lo, 0.))
                reference = driver.c.old.kernel.normalizer(-mode, 1., lo-mode, hi-mode).log_Z
                self.assertAlmostEqual(float(driver.c.v.log_mass(lo, hi)), reference, delta=5e-12)

    def test_objective_gradient_in_subnormal_tail(self):
        design = np.ones((128, 1))
        target = np.linspace(.001, .099, 128)
        lower, upper = np.zeros(128), np.full(128, .1)
        theta = np.array([-38.4, 0.])
        _, gradient = fitting.objective(theta, design, target, lower, upper)
        for j in range(2):
            delta = np.zeros(2)
            delta[j] = 1e-5
            actual = (fitting.objective(theta+delta, design, target, lower, upper)[0]
                      -fitting.objective(theta-delta, design, target, lower, upper)[0])/(2e-5)
            self.assertAlmostEqual(actual, gradient[j], delta=2e-6)


def main():
    if '--output' not in sys.argv:
        sys.argv += ['--output', str(HERE/'attempt002')]
    adaptation = json.loads((HERE/'numerical_adaptation.json').read_text())
    original_result = HERE/'attempt001/result.json'
    original_source_bindings = json.loads((HERE/'attempt001/reservation.json').read_text())['identities']
    for path, expected in original_source_bindings.items():
        driver.c.old.require(driver.base.identity(driver.ROOT/path) == expected, 'original source changed: '+path)
    tail_control = []
    for a in [36., 37., 37.5, 38., 38.2, 38.4, 39., 40.]:
        reference = driver.c.old.kernel.normalizer(-a, 1., 0., .1).log_Z
        tail_control.append(dict(lower=a, upper=a+.1,
            original_error=float(ORIGINAL_LOG_MASS(a, a+.1))-reference,
            repaired_error=float(stable_normalizer.log_mass(a, a+.1))-reference))
    real_write = driver.base.write

    def bind_write(path, value):
        if path.name == 'reservation.json':
            value['numerical_adaptation'] = adaptation
            value['original_result_identity'] = driver.base.identity(original_result)
            for extra in [Path(__file__), HERE/'stable_normalizer.py', HERE/'numerical_adaptation.json']:
                value['identities'][str(extra.relative_to(driver.ROOT))] = driver.base.identity(extra)
            real_write(path.parent/'tail_control.json', tail_control)
        return real_write(path, value)

    driver.base.write = bind_write
    driver.c.v.log_mass = stable_normalizer.log_mass
    driver.Controls = RepairControls
    driver.main()


if __name__ == '__main__':
    main()
