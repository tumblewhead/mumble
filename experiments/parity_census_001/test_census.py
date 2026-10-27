import csv
import gzip
import json
import math
from pathlib import Path
import struct
import tempfile
import unittest

import census


class CensusTests(unittest.TestCase):
    def test_adjacent_positive_and_negative(self):
        for x in (1.,-1.,.001,-.001):
            self.assertEqual(census.difference(math.nextafter(x,math.inf),x)[3],1)

    def test_zero_and_subnormal(self):
        self.assertEqual(census.difference(-0.,0.)[3],0)
        tiny=math.nextafter(0.,1.)
        self.assertEqual(census.difference(-tiny,tiny)[3],2)

    def test_relative_error_near_zero(self):
        signed,absolute,relative,_=census.difference(1e-300,0.)
        self.assertEqual(absolute,1e-300);self.assertEqual(relative,1.)

    def test_nonfinite_is_not_a_tolerated_mismatch(self):
        for x in (math.inf,-math.inf,math.nan):
            with self.assertRaises(ValueError):census.difference(x,0.)

    def test_histogram_boundaries(self):
        self.assertEqual([census.bin_name(x) for x in (0,1,2,4,5,16,17,256,257,4096,4097)],
                         ['signed_zero','1','2_to_4','2_to_4','5_to_16','5_to_16','17_to_256','17_to_256','257_to_4096','257_to_4096','above_4096'])

    def test_inventory_every_field_and_late_large_difference(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);expected=[];actual=[]
            for i in range(4):
                values=[1.]*27;values[16]=i*16/35
                e=[i*16,*values,100,200,1];a=e.copy()
                if i in (0,1):a[18]=math.nextafter(e[18],math.inf)
                if i==0:a[17]=-0.
                if i==3:a[22]=e[22]+.001;a[28]^=4;a[20]+=1000.
                expected.append(census.RECORD.pack(*e));actual.append(census.RECORD.pack(*a))
            (root/'expected').write_bytes(b''.join(expected));(root/'actual').write_bytes(b''.join(actual))
            summary=census.analyze(root/'actual',root/'expected',root,planned_snapshots=4)
            self.assertEqual(summary['snapshots'],4);self.assertEqual(summary['mismatch_snapshots'],3)
            self.assertEqual(summary['floating_mismatches'],5);self.assertEqual(summary['integer_mismatches'],1)
            self.assertEqual(summary['fields']['likelihood_cost']['longest_consecutive_snapshot_run'],2)
            self.assertEqual(summary['fields']['elapsed_s']['ULP_histogram']['signed_zero'],1)
            self.assertEqual(summary['fields']['total_cost']['max_absolute_difference'],1000.)
            with gzip.open(root/'mismatches.csv.gz','rt') as f:rows=list(csv.DictReader(f))
            self.assertEqual(len(rows),6);self.assertEqual(rows[-1]['field'],'flags')
            self.assertFalse(summary['tolerance_pass_claimed'])

    def test_partial_inventory_explicit(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);row=census.RECORD.pack(0,*([0.]*27),0,0,1)
            (root/'expected').write_bytes(row);(root/'actual').write_bytes(row)
            result=census.analyze(root/'actual',root/'expected',root,planned_snapshots=2)
            self.assertEqual(result['status'],'partial_inventory');self.assertFalse(result['strict_bitwise_parity'])

    def test_truncated_record_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            path=Path(name)/'input';path.write_bytes(b'123')
            with self.assertRaises(ValueError):list(census.records(path))


if __name__=='__main__':unittest.main()
