"""Modern Paralysis through real save, action, damage, clock and restore owners."""
from pathlib import Path
from copy import deepcopy
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Engine, Combatant
from builder import build_trainer, build_pokemon
from grid import Grid
from state_codec import dump_engine, load_engine
from native_scenario_fixture import prepare_body, assert_rejected_unchanged
import action_metadata as META
import combat_timing as CLOCK
import paralysis_state as PARALYSIS
import turn as TURN
import world_entities as WORLD


class ParalysisFailedActionSourceRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(ROOT, ruleset='core')

    def scene(self, role='trainer'):
        e = Engine(self.r, seed=1)
        e.grid = Grid(16, 10)
        owner = Combatant(self.r, build_trainer(
            self.r, 'actual trainer', 20, dict.fromkeys(('hp', 'atk', 'def', 'spa', 'spd', 'spe'), 20),
            moves=['move/몸통박치기'], abilities=[], pos=(3, 2), extra={'size': '중형'}))
        e.gm.add_combatant(owner)
        if role == 'pokemon':
            owner.pos = (0, 0)
            a = Combatant(self.r, build_pokemon(
                self.r, '이브이', 20, moves=['move/몸통박치기'], abilities=[], pos=(3, 2),
                extra={'trainer_id': owner.entity_id}))
            e.gm.add_combatant(a)
            e.gm.observe_loyalty(a, 6, reason='actual known obedience before native attack')
        else:
            a = owner
        b = Combatant(self.r, build_trainer(
            self.r, 'actual target', 20, dict.fromkeys(('hp', 'atk', 'def', 'spa', 'spd', 'spe'), 20),
            moves=['move/몸통박치기'], abilities=[], pos=(4, 2), side='opponent', extra={'size': '중형'}))
        e.gm.add_combatant(b)
        for actor in (a, b):
            prepare_body(e, actor, size=actor.spec['size'], offsets=[(0, 0)],
                         reason='observed complete native small or medium participant body')
        return e, a, b

    def begin(self, e, a, *, face=10):
        e.apply_status(a, '마비')
        e.start_round(e.everyone)
        with patch.object(Engine, 'd20', return_value=face) as rolled:
            e.start_of_turn(a, initiative_count=20)
        self.assertEqual(rolled.call_count, 1)

    def resources(self, e, a, b):
        return deepcopy((a.budget, a.hp, b.hp, a.move_uses, e.rng.getstate(),
                         getattr(a, '_restricted_action_taken', False), a._action_history))

    def test_swift_free_survive_both_selected_actions_with_real_move_and_shift_controls(self):
        for role in ('trainer', 'pokemon'):
            for choice in ('standard', 'shift'):
                with self.subTest(role=role, choice=choice):
                    e, a, b = self.scene(role)
                    if choice == 'shift':
                        b.pos = (10, 2)
                    self.begin(e, a)
                    self.assertTrue(TURN.spend(e, a, 'free', 'actual ordinary Free action component'))
                    self.assertFalse(a._restricted_action_taken)
                    if choice == 'standard':
                        self.assertTrue(TURN.spend(e, a, 'swift', 'actual ordinary Swift component before the choice'))
                        self.assertFalse(a._restricted_action_taken)
                        hp = b.hp
                        with patch.object(Engine, 'd20', return_value=18):
                            damage = e.use_move(a, b, 'move/몸통박치기', set_damage=True)
                        self.assertGreater(damage, 0)
                        self.assertEqual((b.hp, a.move_uses['move/몸통박치기']), (hp - damage, 1))
                        other = 'shift'
                    else:
                        position = a.pos
                        e.approach(a, b, movement_mode='land')
                        self.assertNotEqual(a.pos, position)
                        self.assertEqual(a.budget['shift'], 0)
                        self.assertTrue(TURN.spend(e, a, 'swift', 'actual ordinary Swift component after the choice'))
                        other = 'standard'
                    self.assertTrue(a._restricted_action_taken)
                    self.assertTrue(TURN.spend(e, a, 'free', 'actual ordinary Free component after the choice'))
                    self.assertTrue(TURN.spend(e, a, 'free', 'another actual ordinary Free component'))
                    before = self.resources(e, a, b)
                    self.assertFalse(TURN.spend(e, a, other, 'failed save excludes the other actual action'))
                    self.assertEqual(self.resources(e, a, b), before)
                    self.assertFalse(TURN.spend(e, b, 'free', 'actor does not own this open turn'))

    def test_one_restricted_component_plus_swift_is_legal_but_full_and_both_components_are_not(self):
        for choice in ('standard', 'shift'):
            with self.subTest(choice=choice):
                e, a, b = self.scene()
                self.begin(e, a)
                for cost in ('full', META.ActionCost(('standard', 'shift')),
                             META.ActionCost(('standard', 'shift', 'swift'))):
                    before = self.resources(e, a, b)
                    self.assertFalse(TURN.spend(e, a, cost, 'both restricted components remain forbidden'))
                    self.assertEqual(self.resources(e, a, b), before)
                cost = META.ActionCost((choice, 'swift'))
                self.assertTrue(TURN.spend(e, a, cost, 'actual conjunctive native payment'))
                self.assertEqual(a.budget[choice], 0)
                self.assertEqual(a.budget['swift'], 0)
                self.assertTrue(a._restricted_action_taken)
                self.assertEqual(a._action_history, [{'kind': 'compound', 'components': [choice, 'swift']}])
                self.assertTrue(TURN.spend(e, a, 'free', 'Free after a paid compound'))
                self.assertFalse(TURN.spend(e, a, 'shift' if choice == 'standard' else 'standard'))
                self.assertEqual(a.took_standard, choice == 'standard')
                e.apply_status(a, '화상')
                hp, loss = a.hp, e.tick(a)
                e.end_of_turn(a)
                self.assertEqual(a.hp, hp - loss)  # Actual Standard or actual choice of Shift makes the source tick.
        e, a, _ = self.scene()
        self.begin(e, a)
        e.apply_status(a, '화상')
        self.assertTrue(TURN.spend(e, a, 'swift'))
        self.assertTrue(TURN.spend(e, a, 'free'))
        self.assertFalse(a._restricted_action_taken)
        hp = a.hp
        e.end_of_turn(a)
        self.assertEqual(a.hp, hp)  # Voluntary nonselection is not inability to use Standard.

    def test_full_round_children_survive_actual_paralysis_cure_and_expire_at_exact_next_count(self):
        for role in ('trainer', 'pokemon'):
            with self.subTest(role=role):
                e, a, _ = self.scene(role)
                evasion = [a.evasion(kind, engine=e) for kind in ('물리', '특수', '변화')]
                self.assertTrue(any(evasion))
                self.begin(e, a)
                timed = next(row for row in CLOCK.records(a) if 'paralysis_failed_save' in row)
                self.assertEqual(tuple(timed['count_deadline']), (e.round_no + 1, 20))
                self.assertEqual(timed['paralysis_failed_save']['check']['passed'], False)
                self.assertEqual(timed['paralysis_failed_save']['source'], PARALYSIS.SOURCE)
                self.assertIn('취약', a.conditions)
                self.assertEqual([a.evasion(kind, engine=e) for kind in ('물리', '특수', '변화')], [0, 0, 0])
                e.cure_status(a, '마비')
                self.assertNotIn('마비', a.conditions)
                self.assertFalse(TURN.can_aoo(e, a))
                e.end_of_turn(a)
                e.end_round()
                e.start_round(e.everyone)
                CLOCK.at_count(e, 21)
                self.assertIn('취약', a.conditions)
                self.assertFalse(TURN.can_aoo(e, a))
                CLOCK.at_count(e, 20)
                self.assertNotIn('취약', a.conditions)
                self.assertFalse(CLOCK.records(a))
                self.assertTrue(TURN.can_aoo(e, a))
                self.assertEqual([a.evasion(kind, engine=e) for kind in ('물리', '특수', '변화')], evasion)
        e, a, _ = self.scene()
        self.begin(e, a, face=11)
        self.assertFalse(CLOCK.records(a))
        self.assertNotIn('취약', a.conditions)
        self.assertFalse(TURN.can_aoo(e, a))  # The separate while-Paralyzed rule still applies.
        self.assertTrue(TURN.spend(e, a, 'standard'))
        self.assertTrue(TURN.spend(e, a, 'shift'))
        e.cure_status(a, '마비')
        self.assertTrue(TURN.can_aoo(e, a))

    def test_gm_and_json_restore_keep_real_save_choice_and_independent_vulnerability(self):
        for restoration, role in (('gm', 'trainer'), ('json', 'pokemon')):
            with self.subTest(restoration=restoration):
                e, a, b = self.scene(role)
                e.apply_status(a, '취약')
                self.begin(e, a)
                self.assertTrue(TURN.spend(e, a, 'swift'))
                self.assertFalse(a._restricted_action_taken)
                original = deepcopy(next(row for row in CLOCK.records(a) if 'paralysis_failed_save' in row))
                identity = a.entity_id
                if restoration == 'gm':
                    e.gm.snapshot('actual failed Paralysis save plus Swift')
                    self.assertTrue(TURN.spend(e, a, 'standard'))
                    e.gm.restore('actual failed Paralysis save plus Swift')
                else:
                    e = load_engine(self.r, dump_engine(e))
                a = WORLD.actor_index(e)[identity]
                self.assertEqual(next(row for row in CLOCK.records(a) if 'paralysis_failed_save' in row), original)
                self.assertFalse(a._restricted_action_taken)
                self.assertTrue(TURN.spend(e, a, 'shift'))
                self.assertFalse(TURN.spend(e, a, 'standard'))
                e.cure_status(a, '마비')
                e.end_of_turn(a)
                e.end_round()
                e.start_round(e.everyone)
                CLOCK.at_count(e, 20)
                self.assertIn('취약', a.conditions)  # The timer did not own this independent condition.
                self.assertTrue(TURN.can_aoo(e, a))
                self.assertFalse(CLOCK.records(a))

    def test_missing_count_changed_source_and_late_child_failure_roll_back_real_turn_and_rng(self):
        e, a, _ = self.scene()
        e.apply_status(a, '마비')
        e.start_round(e.everyone)
        with patch.object(Engine, 'd20', return_value=10) as rolled:
            assert_rejected_unchanged(e, lambda: e.start_of_turn(a), reason_pattern='current explicit initiative count')
        self.assertEqual(rolled.call_count, 0)
        with patch.dict(PARALYSIS.SOURCE, {'sha256': '0' * 64}), \
             patch.object(Engine, 'd20', return_value=10) as rolled:
            assert_rejected_unchanged(e, lambda: e.start_of_turn(a, initiative_count=20),
                                      reason_pattern='source changed; review required')
        self.assertEqual(rolled.call_count, 0)
        observed = []
        install = CLOCK.install
        def fail_after_native_install(engine, actor, record):
            result = install(engine, actor, record)
            observed.append((deepcopy(result), '취약' in actor.conditions, engine.rng.getstate()))
            raise ValueError('late actual Paralysis child installation failure')
        rng = e.rng.getstate()
        with patch.object(CLOCK, 'install', side_effect=fail_after_native_install):
            assert_rejected_unchanged(e, lambda: e.start_of_turn(a, initiative_count=20),
                                      reason_pattern='late actual Paralysis child installation failure')
        self.assertEqual(len(observed), 1)
        self.assertFalse(observed[0][0]['paralysis_failed_save']['check']['passed'])
        self.assertTrue(observed[0][1])
        self.assertNotEqual(observed[0][2], rng)
        self.assertFalse(CLOCK.records(a))
        self.assertNotIn('취약', a.conditions)
        self.assertIsNone(e._active_turn_actor)


if __name__ == '__main__':
    unittest.main()
