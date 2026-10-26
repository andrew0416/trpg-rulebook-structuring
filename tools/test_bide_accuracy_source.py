"""Bide retains its source-owned automatic release when accuracy rereads mechanics."""
import unittest
from unittest.mock import patch
import tools.test_category2_gmax_moves as FIX
from engine import Engine
import bide as BIDE

class BideAccuracySourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        FIX.GMaxMoveTests.setUpClass()

    def test_real_reaction_and_cold_release_succeed_on_natural_one_without_extra_payment(self):
        fixture=FIX.GMaxMoveTests();fixture.setUp()
        try:
            # The original first hit explicitly uses17, and G-Max uses1;
            # this fixes only the otherwise-free Bide declaration/release rolls.
            with patch.object(Engine,'d20',return_value=1):
                fixture.test_bide_pending_scope_counts_later_smite_without_turning_miss_into_hit()
        finally:
            fixture.doCleanups()

    def test_unmarked_bide_keeps_ordinary_accuracy_and_forged_projection_has_no_native_authority(self):
        fixture=FIX.GMaxMoveTests();fixture.setUp()
        try:
            engine,actor,target,base,move=fixture.world('C2CSV-MOVE-R1016')
            raw=engine.r.move(BIDE.SOURCE)
            self.assertNotIn('_retrospective_hp_loss',raw)
            before=engine.rng.getstate()
            self.assertFalse(engine.accuracy_check(actor,target,raw,fixed_roll=1)[0])
            with self.assertRaisesRegex(ValueError,'actual completed damaging hit Reaction'):
                engine.accuracy_check(actor,target,dict(raw,_retrospective_hp_loss=999),fixed_roll=1)
            self.assertEqual(engine.rng.getstate(),before)
            self.assertIsNone(BIDE.pending(actor))
        finally:
            fixture.doCleanups()
