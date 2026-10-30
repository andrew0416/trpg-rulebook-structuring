"""IMPL-01: blinded paid steps use the actual Living Weapon round pool.

Source-authored; not executed locally. Pending fixtures use actual Overwatch,
native defense choices and the real codec, never invented pending receipts.
"""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import os
import sys
import unittest

ROOT = Path(os.environ.get('PTK_EXPERIMENT_ROOT') or Path(__file__).resolve().parents[1]).resolve()
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Engine, Combatant
from builder import build_pokemon
import living_weapon as LIVING
import effects_ext as EXT
import marksman as MARKSMAN
import move_defense_reactions as DEFENSE
import native_scenario_fixture as NATIVE
import world_entities as WORLD


class BlindedLivingWeaponMovementTests(unittest.TestCase):
    def options(self, *, faces=(3, 3, 3, 3)):
        return {'movement_id': 'living-blinded-shift',
                'frequency': 'once_per_shift',
                'reason': 'one actual continuous rough or slow path, DC10',
                'check_options': [{'skill': '곡예', 'fixed': list(faces)}]}

    def world(self, *, slow=False):
        import test_living_weapon_movement_noguard_source_revision as FIXTURE
        case = FIXTURE.LivingWeaponMovementNoGuardSourceRevisionTests('runTest')
        case.world(holder='trainer')
        case.e.gm.set_skill(case.a, '곡예', 4, reason='actual Adept Acrobatics observation')
        case.e.gm.set_position(case.t, (6, 2), reason='actual three-cell straight approach goal')
        case.e.grid.blocking.update((x, y) for x in range(25) for y in range(12) if y != 2)
        (case.e.grid.slow if slow else case.e.grid.rough).add((3, 2))
        case.e.equip_living_weapon(case.a, case.p, consent=True)
        self.assertTrue(case.e.apply_status(case.a, '실명', parameters={'cause': 'external'}))
        case.turn(case.a)
        return case

    def restore(self, engine, *actors):
        ids = [actor.entity_id for actor in actors]
        rng = engine.rng.getstate()
        restored = Engine.import_state(engine.r, json.loads(json.dumps(engine.export_state())))
        self.assertEqual(restored.rng.getstate(), rng)
        index = WORLD.actor_index(restored)
        return (restored, *(index[identity] for identity in ids))

    def test_rough_and_slow_costs_share_both_turns_and_survive_restore(self):
        for slow, spent, final_position in ((False, 3, (8, 2)), (True, 4, (7, 2))):
            with self.subTest(slow=slow):
                case = self.world(slow=slow)
                case.e.approach(case.a, case.t, blindness_options=self.options())
                self.assertEqual((case.a.pos, case.p.pos), ((5, 2), (5, 2)))
                self.assertEqual(case.p.spec[LIVING.MOVEMENT]['distance'], spent)
                row = case.a.spec['_survivalist_shift']
                self.assertEqual((row['spent'], row['moved'], row['finished']), (spent, 3, True))
                self.assertEqual(case.a._action_history.count('shift'), 1)
                self.assertNotIn('넘어짐', case.a.conditions)
                case.e.gm.snapshot('blind-pool')
                case.e.gm.restore('blind-pool')
                case.restore()
                self.assertEqual(LIVING.movement_remaining(case.e, case.p), 6-spent)
                case.e.gm.set_position(case.t, (20, 2), reason='actual second-turn distant goal')
                case.turn(case.p)
                result = case.e.approach(case.p, case.t)
                self.assertEqual(result['distance'], 6-spent)
                self.assertEqual((case.a.pos, case.p.pos), (final_position, final_position))
                self.assertEqual(case.p.spec[LIVING.MOVEMENT]['distance'], 6)
                self.assertEqual((case.a.budget['shift'], case.p.budget['shift']), (0, 0))
                self.assertTrue(case.e.validate_state()['valid'])

    def test_bad_blindness_declaration_rejects_before_action_or_distance(self):
        case = self.world()
        bad = self.options()
        bad.pop('frequency')
        NATIVE.assert_rejected_unchanged(
            case.e, lambda: case.e.approach(case.a, case.t, blindness_options=bad),
            reason_pattern='GM must settle unspecified blinded-check repetition')
        self.assertNotIn(LIVING.MOVEMENT, case.p.spec)
        self.assertNotIn('_survivalist_shift', case.a.spec)
        self.assertEqual(case.a.budget['shift'], 1)
        case.e.approach(case.a, case.t, blindness_options=self.options())
        self.assertEqual(case.p.spec[LIVING.MOVEMENT]['distance'], 3)

    def test_failed_check_charges_only_the_actual_entered_slow_cell(self):
        case = self.world(slow=True)
        case.e.approach(case.a, case.t, blindness_options=self.options(faces=(1, 1, 1, 1)))
        self.assertEqual((case.a.pos, case.p.pos), ((3, 2), (3, 2)))
        self.assertIn('넘어짐', case.a.conditions)
        row = case.a.spec['_survivalist_shift']
        self.assertEqual((row['spent'], row['moved'], len(row['checks'])), (2, 1, 1))
        self.assertFalse(row['checks'][0]['result'].passed)
        self.assertEqual(case.p.spec[LIVING.MOVEMENT]['distance'], 2)
        self.assertEqual(case.a.budget['shift'], 0)
        case.restore()
        self.assertEqual(LIVING.movement_remaining(case.e, case.p), 4)
        self.assertTrue(case.e.validate_state()['valid'])

    def test_entry_failure_rolls_back_position_pool_shift_and_rng(self):
        case = self.world()
        with patch.object(EXT, 'on_enter_cell', side_effect=ValueError('IMPL-01 actual entry failure')):
            NATIVE.assert_rejected_unchanged(
                case.e, lambda: case.e.approach(case.a, case.t, blindness_options=self.options()),
                reason_pattern='IMPL-01 actual entry failure')
        self.assertEqual((case.a.pos, case.p.pos), ((2, 2), (2, 2)))
        self.assertNotIn(LIVING.MOVEMENT, case.p.spec)
        self.assertNotIn('_survivalist_shift', case.a.spec)
        self.assertEqual(case.a.budget['shift'], 1)

    def overwatch_world(self, *, speed, goal):
        import test_book_marksman_full as FIXTURE
        case = FIXTURE.MarksmanFullTests('runTest')
        case.rules = Rules(ROOT, ruleset='all')
        case.base_rulings = deepcopy(case.rules.rulings)
        case.scene(features=(MARKSMAN.WATCH,), positions=((2, 4), (8, 5), goal))
        engine, holder, target = case.e, case.b, case.c
        engine.gm.set_skill(holder, '곡예', 4, reason='actual Adept Acrobatics observation')
        engine.gm.set_movement_capabilities(
            holder, {'land': speed, 'power': 3}, basis='current',
            reason='actual Living Weapon wielder round movement speed')
        weapon = Combatant(case.rules, build_pokemon(
            case.rules, '단칼빙', 40, moves=['move/몸통박치기'], abilities=[],
            pos=(9, 5), side='foe', wild=True))
        engine.gm.add_combatant(weapon)
        NATIVE.prepare_body(engine, weapon, size=weapon.spec['size'], offsets=[(0, 0)],
                            reason='actual observed equipped Honedge body')
        engine.equip_living_weapon(holder, weapon, consent=True)
        self.assertTrue(engine.apply_status(holder, '실명', parameters={'cause': 'external'}))
        engine.grid.rough.add((9, 4))
        case.weapon()
        case.combat()
        MARKSMAN.watch(engine, case.a, case.key, direction=(1, 0), blast_center=(8, 4))
        engine.end_of_turn(case.a)
        engine.start_of_turn(holder, initiative_count=15)
        engine.watch_move_defense(
            holder, [{'actor_id': target.entity_id, 'source': DEFENSE.RANGED}],
            reason='actual Overwatch ranged-intercept decision')
        engine.rulings.add_answer('marksman_overwatch', {'weapon_id': case.key, 'move_id': case.mid},
                                 reason='actual equipped Overwatch weapon attack')
        return engine, holder, weapon, target

    def open_pending(self, engine, holder, weapon, target):
        with patch.object(Engine, 'd20', return_value=18):
            engine.approach(holder, target, blindness_options=self.options())
        event = engine._passive_pending
        self.assertIsNotNone(event, 'actual native Overwatch defense wait must be reached')
        self.assertIn(event, engine._passive_events)
        self.assertEqual((holder.pos, weapon.pos), ((9, 4), (9, 4)))
        self.assertEqual(weapon.spec[LIVING.MOVEMENT]['distance'], 1)
        row = holder.spec['_survivalist_shift']
        self.assertEqual((row['next_index'], row['spent'], row['entry_progress']['phase']),
                         (1, 1, 'entry_pending'))
        self.assertFalse(row['finished'])
        return event

    def test_actual_entry_pending_restore_resumes_once_including_zero_remaining(self):
        # Diagonal accounting is independently fixed: first step costs 1, second costs 2.
        for speed, goal, destination, distance in (
                (1, (10, 3), (9, 4), 1), (3, (11, 2), (10, 3), 3)):
            with self.subTest(speed=speed):
                engine, holder, weapon, target = self.overwatch_world(speed=speed, goal=goal)
                event = self.open_pending(engine, holder, weapon, target)
                engine, holder, weapon, target = self.restore(engine, holder, weapon, target)
                with patch.object(Engine, 'd20', side_effect=AssertionError('paid attack must not reroll')):
                    engine.choose_move_defense(event, target, use=False,
                                               reason='decline the actual observed intercept')
                changed = self.options()
                changed['movement_id'] = 'replacement-is-not-a-resume'
                NATIVE.assert_rejected_unchanged(
                    engine, lambda: engine.approach(holder, target, blindness_options=changed),
                    reason_pattern='cannot change an observed blinded Shift policy')
                with patch.object(Engine, 'skill_roll', side_effect=AssertionError('paid check must not reroll')):
                    engine.approach(holder, target, blindness_options=self.options())
                self.assertEqual((holder.pos, weapon.pos), (destination, destination))
                self.assertEqual(weapon.spec[LIVING.MOVEMENT]['distance'], distance)
                self.assertTrue(holder.spec['_survivalist_shift']['finished'])
                self.assertEqual(holder._action_history.count('shift'), 1)
                self.assertEqual(len(holder.spec['_survivalist_shift']['checks']), 1)
                engine, holder, weapon, target = self.restore(engine, holder, weapon, target)
                before = engine.export_state()
                engine.approach(holder, target, blindness_options=self.options())
                self.assertEqual(engine.export_state(), before)
                self.assertTrue(engine.validate_state()['valid'])

    def test_returned_entry_with_exhausted_live_pool_stops_before_the_next_cell(self):
        engine, holder, weapon, target = self.overwatch_world(speed=3, goal=(11, 2))
        event = self.open_pending(engine, holder, weapon, target)
        engine.choose_move_defense(event, target, use=False, reason='decline actual intercept')
        engine.gm.set_movement_capabilities(
            holder, {'land': 1, 'power': 3}, basis='current',
            reason='actual current speed falls to the already shifted distance')
        engine, holder, weapon, target = self.restore(engine, holder, weapon, target)
        with patch.object(Engine, 'skill_roll', side_effect=AssertionError('unreached cell cannot roll')):
            engine.approach(holder, target, blindness_options=self.options())
        self.assertEqual((holder.pos, weapon.pos), ((9, 4), (9, 4)))
        self.assertEqual(weapon.spec[LIVING.MOVEMENT]['distance'], 1)
        row = holder.spec['_survivalist_shift']
        self.assertEqual((row['spent'], row['moved'], row['finished']), (1, 1, True))
        self.assertEqual(holder._action_history.count('shift'), 1)
        self.assertTrue(engine.validate_state()['valid'])


if __name__ == '__main__':
    unittest.main()