"""Exact native tuple-result assertion semantics; unknown objects remain rejected."""
import unittest

from effect_contracts import BatchResult
from test_reference_connection_equivalence import _assertion_value


class ReferenceAssertionValueTests(unittest.TestCase):
    def test_native_batch_counts_keep_original_tuple_assertion_semantics(self):
        for counts in ((0,0),(1,0),(0,1),(3,2)):
            with self.subTest(counts=counts):
                result=BatchResult(*counts)
                self.assertEqual(result,counts)
                self.assertEqual(_assertion_value(result),_assertion_value(counts))
                self.assertEqual(_assertion_value({'result':result}),_assertion_value({'result':counts}))

    def test_tuple_subclasses_opaque_values_and_nonfinite_numbers_remain_rejected(self):
        class OtherTuple(tuple):pass
        class OtherBatch(BatchResult):pass
        for value in (OtherTuple((1,0)),OtherBatch(1,0),object(),b'opaque',float('nan'),float('inf')):
            with self.subTest(kind=type(value).__name__):
                with self.assertRaisesRegex(AssertionError,'unsupported reference assertion value'):
                    _assertion_value(value)


if __name__=='__main__':unittest.main()
