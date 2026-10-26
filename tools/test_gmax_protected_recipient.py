"""Gold Rush's area Confusion respects an actually prevented creature hit."""
from copy import deepcopy
from unittest.mock import patch
import unittest
import tools.test_category2_gmax_moves as FIX
from engine import Engine
import move_completion as COMPLETE

class GoldRushProtectedRecipientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        FIX.GMaxMoveTests.setUpClass()

    def test_substitute_receives_gold_rush_hit_without_new_confusion_or_lost_coins(self):
        for already_confused in (False, True):
            with self.subTest(already_confused=already_confused):
                fixture=FIX.GMaxMoveTests();fixture.setUp()
                try:
                    e,actor,(target,outside),base,move=fixture.mapped_world('C2CSV-MOVE-R1021',first='outside')
                    fixture.learn_retaliation(e,target,'move/대타출동','actual learned Substitute for Gold Rush recipient boundary')
                    e.gm.set_stage(actor,'atk',value=-6,reason='actual weak attack preserves the Substitute coat')
                    e.end_of_turn(outside);e.start_of_turn(target,initiative_count=15)
                    e.use_move(target,target,'move/대타출동')
                    coat=next(row for row in target.coats if row['source']=='move/대타출동')
                    if already_confused:
                        e.gm.add_condition(target,'혼란',reason='independent pre-existing confusion')
                    hp,coat_hp,conditions=target.hp,coat['hp'],deepcopy(target.conditions)
                    e.end_of_turn(target);e.start_of_turn(actor,initiative_count=10)
                    with patch.object(Engine,'d20',return_value=19):
                        e.use_gmax_move_on(actor,target,base,move,e.everyone,aim=(9,4),set_damage=True)
                    completion=next(row for row in e._move_completions.values() if row['move_id']==move)
                    result=COMPLETE.recipient_result(completion,target)
                    self.assertFalse(result['hit']);self.assertTrue(result['hit_prevented']);self.assertEqual(result['dealt'],0)
                    self.assertEqual(target.hp,hp);self.assertLess(coat['hp'],coat_hp);self.assertGreater(coat['hp'],0)
                    self.assertEqual(target.conditions,conditions)
                    self.assertEqual(e._gmax_payload_receipts[-1]['target_ids'],[])
                    self.assertNotIn('혼란',outside.conditions)
                    self.assertEqual(len(e._gmax_coin_rewards),1)
                    self.assertEqual(actor.move_uses[move],1)
                    self.assertTrue(e.validate_state()['valid'])
                finally:
                    fixture.doCleanups()
