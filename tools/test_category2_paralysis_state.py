"""Paralysis state through actual actors, shared initiative, action and storage owners."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
import test_category2_condition_recovery as RECOVERY
import initiative as INITIATIVE
import turn as TURN
from engine import Engine


class ParalysisStateTests(unittest.TestCase):
    setUpClass = classmethod(RECOVERY.ConditionRecoveryTests.setUpClass.__func__)
    setUp = RECOVERY.ConditionRecoveryTests.setUp
    add = RECOVERY.ConditionRecoveryTests.add
    restored = RECOVERY.ConditionRecoveryTests.restored

    def begin(self, actor, face):
        self.e.start_round(self.e.gm.everyone)
        with patch.object(Engine, 'd20', return_value=face) as roller:
            self.e.start_of_turn(actor, initiative_count=INITIATIVE.value(self.r, actor, engine=self.e).value)
        return roller.call_count

    def state(self, engine, actor):
        return deepcopy((actor.budget, actor.hp, actor.move_uses,
                         engine.rng.getstate()))

    def test_native_thunder_wave_applies_to_trainer_and_pokemon_without_changing_speed(self):
        for role in ('a', 'p'):
            with self.subTest(role=role):
                self.setUp()
                actor = getattr(self, role)
                attacker = self.add(RECOVERY.build_pokemon(
                    self.r, '잉어킹', 10, moves=[], abilities=[],
                    extra={'trainer_id': self.a.entity_id}))
                attacker.pos, actor.pos = (1, 1), (2, 1)
                self.e.gm.set_move(attacker, 'move/전기자석파', True, reason='observed actual Move')
                self.e.gm.observe_loyalty(attacker, 6, reason='actual Move participant')
                speed = actor.staged('spe')
                self.begin(attacker, 20)
                with patch.object(Engine, 'd20', return_value=20):
                    self.e.use_move(attacker, actor, 'move/전기자석파')
                self.assertIn('마비', actor.conditions)
                self.assertEqual(actor.staged('spe'), speed)
                self.assertEqual(INITIATIVE.value(self.r, actor, engine=self.e).value, speed // 2)
                self.assertEqual(attacker.move_uses['move/전기자석파'], 1)

    def test_failed_save_allows_either_first_action_but_never_both_for_both_kinds(self):
        for role in ('a', 'p'):
            for first, second in (('standard', 'shift'), ('shift', 'standard')):
                with self.subTest(role=role, first=first):
                    self.setUp()
                    actor = getattr(self, role)
                    self.assertTrue(self.e.apply_status(actor, '마비'))
                    self.assertEqual(self.begin(actor, 10), 1)
                    self.assertTrue(TURN.spend(self.e, actor, first, 'actual selected action'))
                    before = self.state(self.e, actor)
                    self.assertFalse(TURN.spend(self.e, actor, second, 'paralysis prevents second action'))
                    self.assertEqual(self.state(self.e, actor), before)
                    with patch.object(Engine, 'd20', return_value=20) as roller:
                        self.e.end_of_turn(actor)
                    self.assertEqual(roller.call_count, 0)
                    self.assertIn('마비', actor.conditions)

    def test_successful_save_allows_both_actions_without_cure_or_initiative_restore(self):
        for role in ('a', 'p'):
            with self.subTest(role=role):
                self.setUp()
                actor = getattr(self, role)
                self.assertTrue(self.e.apply_status(actor, '마비'))
                speed = actor.staged('spe')
                self.assertEqual(self.begin(actor, 11), 1)
                self.assertTrue(TURN.spend(self.e, actor, 'standard', 'actual Standard'))
                self.assertTrue(TURN.spend(self.e, actor, 'shift', 'actual Shift'))
                self.assertIn('마비', actor.conditions)
                self.assertEqual(INITIATIVE.value(self.r, actor, engine=self.e).value, speed // 2)

    def test_gm_and_json_restore_keep_the_same_active_actor_and_spent_restricted_choice(self):
        for role in ('a', 'p'):
            with self.subTest(role=role):
                self.setUp()
                actor = getattr(self, role)
                self.e.apply_status(actor, '마비')
                self.begin(actor, 10)
                self.assertTrue(TURN.spend(self.e, actor, 'shift', 'actual selected Shift'))
                self.e.gm.snapshot('paralysis-choice')
                loaded = self.restored()
                clone = next(c for c in loaded.gm.everyone if c.entity_id == actor.entity_id)
                for engine, actual in ((self.e, actor), (loaded, clone)):
                    self.assertIs(engine._active_turn_actor, actual)
                    before = self.state(engine, actual)
                    self.assertFalse(TURN.spend(engine, actual, 'standard', 'cannot repay after restore'))
                    self.assertEqual(self.state(engine, actual), before)
                    engine.end_of_turn(actual)
                    engine.start_round(engine.gm.everyone)
                    with patch.object(Engine, 'd20', return_value=11):
                        engine.start_of_turn(actual, initiative_count=INITIATIVE.value(self.r, actual, engine=engine).value)
                    self.assertTrue(TURN.spend(engine, actual, 'standard', 'next turn success'))
                    self.assertTrue(TURN.spend(engine, actual, 'shift', 'next turn success'))
                    self.assertIn('마비', actual.conditions)
                self.e.gm.restore('paralysis-choice')
                self.assertFalse(TURN.spend(self.e, actor, 'standard', 'snapshot keeps prior choice'))
                self.assertEqual(actor.budget['shift'], 0)


if __name__ == '__main__':
    unittest.main()

