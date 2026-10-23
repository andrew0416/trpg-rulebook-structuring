"""Keep Rollout's paid path mandatory through both actual native entry points."""
import unittest
from unittest.mock import patch
import test_category2_forced_move_chains as _fixture_test_category2_forced_move_chains


class Tests(unittest.TestCase):
    def test_rollout_direct_native_calls_cannot_bypass_paid_path(self):
        _fixture_test_category2_forced_move_chains.ForcedMoveChainTests.setUpClass()
        f = _fixture_test_category2_forced_move_chains.ForcedMoveChainTests()
        f.setUp()
        before = f.e.export_state()
        random_before = f.e.rng.getstate()
        for call in (lambda: f.e.use_move(f.a, f.b, f.rollout),
                     lambda: f.e.use_move_on(f.a, f.b, f.rollout, f.e.everyone)):
            with patch.object(f.e, 'd20') as rng:
                with self.assertRaisesRegex(ValueError, 'Pass Move requires use_pass_move'):
                    call()
            rng.assert_not_called()
            self.assertEqual(f.e.export_state(), before)
            self.assertEqual(f.e.rng.getstate(), random_before)
