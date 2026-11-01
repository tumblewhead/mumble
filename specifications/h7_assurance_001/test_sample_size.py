import unittest
import math
from .sample_size import zero_failure_upper,required_zero_failures,binomial_cdf,coverage_power

class SampleSizeTests(unittest.TestCase):
    def test_exact_zero_failure_inversion(self):
        for p in (.01,.001,.0001):
            n=required_zero_failures(p)
            self.assertLessEqual(zero_failure_upper(n),p)
            self.assertGreater(zero_failure_upper(n-1),p)
        self.assertEqual(required_zero_failures(.01),299)
        self.assertEqual(required_zero_failures(.001),2995)
    def test_familywise_allocation_increases_required_sample(self):
        self.assertGreater(required_zero_failures(.01,.05/4),required_zero_failures(.01))
    def test_invalid_input(self):
        for n in (0,-1,1.5,True):
            with self.assertRaises(ValueError):zero_failure_upper(n)
        for p in (0,1,-.1):
            with self.assertRaises(ValueError):required_zero_failures(p)
    def test_binomial_sum_against_direct_small_problem(self):
        for n in (5,20):
            for p in (.05,.4,.95):
                for k in range(n):
                    expected=sum(math.comb(n,i)*p**i*(1-p)**(n-i) for i in range(k+1))
                    self.assertAlmostEqual(binomial_cdf(k,n,p),expected,places=13)
        self.assertAlmostEqual(binomial_cdf(1,500,.01),.99**500+500*.01*.99**499,places=12)
    def test_coverage_rejection_boundary_and_power(self):
        r=coverage_power(500);k=r['max_misses_to_reject_null']
        self.assertLessEqual(r['type_I'],.025)
        self.assertGreater(binomial_cdf(k+1,500,.06),.025)
        self.assertAlmostEqual(r['power'],binomial_cdf(k,500,.05))

if __name__=='__main__':unittest.main()
