"""One real paid wait crosses both GM and fresh-Rules restore boundaries."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
import test_category2_priority_actions as P
import passive_events as PASSIVE
import move_completion as COMPLETE
from state_codec import dump_engine


class PriorityPendingRestoreTests(unittest.TestCase):
    setUpClass = classmethod(P.PriorityActionTests.setUpClass.__func__)
    setUp = P.PriorityActionTests.setUp
    actor = P.PriorityActionTests.actor
    close = P.PriorityActionTests.close
    fresh = P.PriorityActionTests.fresh
    complete_round = P.PriorityActionTests.complete_round

    def test_actual_paid_wait_gm_rollback_then_cold_resume_never_repeats_move_or_slot(self):
        self.foe.spec['abilities'] = self.foe.abilities = ['테라셸']
        self.e.register_abilities(self.foe)
        self.e.watch_ability_interrupt(self.foe, 'ability/테라셸', reason='actual recipient requests type choice')
        hp = self.foe.hp
        with self.assertRaises(PASSIVE.PassiveEventPending):
            self.e.use_priority_move(self.p, self.foe, P.QUICK)
        event = self.e._passive_pending
        self.e.gm.snapshot('paid-native-priority-wait')
        declined = self.e.choose_ability_interrupt(event, self.foe, use=False,
                                                  reason='native recipient declines')
        self.assertIsNone(self.e._passive_pending)
        declined_damage = hp - self.foe.hp
        self.assertGreater(declined_damage, 0)
        self.e.finish_initiative_reaction()
        self.e.gm.restore('paid-native-priority-wait')
        self.assertEqual(self.e._passive_pending, event)
        self.assertEqual(self.foe.hp, hp)
        self.assertEqual(self.p.move_uses[P.QUICK], 1)
        self.assertIs(self.e._active_turn_actor, self.p)
        self.fresh()
        accepted = self.e.choose_ability_interrupt(event, self.foe, use=True,
            options={'chosen_type': '강철'}, reason='restored actual recipient chooses Steel')
        self.assertIsInstance(declined, int)
        self.assertIsInstance(accepted, int)
        self.assertGreater(hp - self.foe.hp, 0)
        self.assertLess(hp - self.foe.hp, declined_damage)
        self.assertEqual(self.p.move_uses[P.QUICK], 1)
        self.assertEqual(len(self.e.initiative_reaction_status()['owed_turns']), 1)
        returned = COMPLETE.require_returned_event(self.e, event)
        self.assertTrue(returned)
        before = dump_engine(self.e)
        with self.assertRaises(ValueError):
            self.e.choose_ability_interrupt(event, self.foe, use=True,
                options={'chosen_type': '강철'}, reason='completed choice replay refused')
        self.assertEqual(before, dump_engine(self.e))
        self.complete_round()
        self.assertEqual(self.p.custom_conditions['combat_turn_serial'], 1)
        self.assertFalse(self.e.initiative_reaction_status()['owed_turns'])


if __name__ == '__main__':
    unittest.main()
