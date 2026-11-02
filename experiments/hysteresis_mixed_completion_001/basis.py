"""Study-only H4 mixed-term completion, using unchanged native response and joint QR."""
import numpy as np
from experiments.response_basis_attribution_001.basis import BasisField


class CompletedField(BasisField):
    def __init__(self, config, center, binary, completion, source='fixture'):
        if completion not in ('c22', 'tensor'):
            raise ValueError('completion must be c22 or tensor')
        super().__init__(config, center, binary, 2, 'log', source)
        self.completion = completion
        self.pairs = (self.pairs + [(2, 2)] if completion == 'c22'
                      else [(i, j) for i in range(3) for j in range(3)])
        # Discrete orthogonality makes these the retained projection rows (H4).
        full = np.kron(self.p1, self.p1)
        self.p2 = np.ascontiguousarray(full[[3*i+j for i, j in self.pairs]])
        self.b = len(self.pairs)
        self.width = 4 + 6*self.n + 2*self.b
        self.root = np.zeros((self.width, self.width))

    def storage(self):
        result = super().storage()
        result['hysteresis_completion'] = self.completion
        return result
