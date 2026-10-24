"""Native grounded Ground composition; prepared for the final combined run."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

STAGE = Path(__file__).resolve().parents[1]
ROOT = STAGE if (STAGE / 'data/core-rules.json').exists() else Path(os.environ.get(
    'PTK_CANONICAL_ROOT', r'D:/trpg-rulebook-structuring/work/public-actions-20261023/repository'))
sys.path[:0] = [str(STAGE / 'engine'), str(ROOT / 'engine'), str(ROOT / 'tools')]

from builder import build_pokemon, build_trainer
from engine import Combatant, Engine, Rules
from grid import Grid
import blessing_effects as BLESSINGS
import body_state as BODY
import catalog_move_states as CATALOG
import coat_effects as COATS
import combat_timing as TIMING
import csv_item_physical_contracts as PHYSICAL
import event_trace as TRACE
import items as ITEMS
import movement_actions as MOVEMENT
import world_entities as WORLD

ARROWS = 'move/사우전드애로'
SMACK = 'move/떨어뜨리기'
GROUND = 'move/대지의힘'
FIRE = 'move/불꽃세례'


class GroundedEffectivenessNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset='core')

    def setUp(self):
        self.e = Engine(self.rules, seed=407750)
        self.e.grid = Grid(8, 8)
        self.a = Combatant(self.rules, build_trainer(self.rules, 'grounding attacker', 30,
            {'hp': 40, 'atk': 20, 'def': 20, 'spa': 20, 'spd': 20, 'spe': 20},
            moves=[ARROWS, SMACK, GROUND, FIRE, 'move/타르샷', 'move/몸통박치기'],
            pos=(1, 1), abilities=[], extra={'movement': {'land': 6}}))
        self.t = Combatant(self.rules, build_pokemon(self.rules, '피카츄', 50,
            name='grounded recipient', wild=True, moves=['move/빛의장막'], abilities=[],
            pos=(2, 1), extra={'movement': {'land': 6, 'sky': 6, 'levitate': 4},
                             'movement_basis': 'current'}))
        for actor in (self.a, self.t):
            self.e.gm.add_combatant(actor)
            BODY.observe(self.e, actor, [(0, 0)], reason='actual observed one-cell body')
        TRACE.enable(self.e)
        # Rules.rulings is shared between Engines; every temporary answer is scoped.
        self.answers = deepcopy(self.rules.rulings.answers)
        self.addCleanup(setattr, self.rules.rulings, 'answers', self.answers)

    def begin(self, actor):
        if self.e._active_turn_actor is not None:
            self.e.end_of_turn(self.e._active_turn_actor)
        self.e.start_round(self.e.gm.everyone)
        self.e.start_of_turn(actor, initiative_count=20)

    def use(self, move, *, actor=None, target=None):
        actor, target = actor or self.a, target or self.t
        self.begin(actor)
        with patch.object(Engine, 'd20', return_value=18):
            return self.e.use_move(actor, target, move, set_damage=True, situational=100)

    def ground(self, source, types=('강철', '비행')):
        self.e.gm.set_types(self.t, list(types), reason='actual observed defensive types')
        self.begin(self.t)
        self.e.aerial_move(self.t, self.t.pos, mode='sky', altitude=1,
            gm_distance=1, reason_text='actual one-metre vertical flight')
        self.assertTrue(self.t.airborne)
        self.use(source)
        self.assertTrue(CATALOG.grounded(self.t))
        self.assertEqual((self.t.airborne, self.t.spec['_movement_altitude']), (False, 0))
        self.assertEqual((MOVEMENT.capabilities(self.e, self.t, environment=False)['sky'],
                          MOVEMENT.capabilities(self.e, self.t, environment=False)['levitate']), (0, 0))
        records = [r for r in TIMING.records(self.t) if 'catalog_grounding' in r]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['source'], source)

    def hit(self, move=GROUND, *, expected, actual_type=None):
        previous = len(TRACE.records(self.e))
        self.e.gm.set_hp(self.t, value=self.t.max_hp, reason='recipient is healthy before the measured attack')
        before = self.t.hp
        dealt = self.use(move)
        calculations = [facts for row in TRACE.records(self.e)[previous:]
                        for facts in row['calculations']
                        if facts.get('source') == move and 'after_defense' in facts]
        self.assertTrue(calculations)
        facts = calculations[-1]
        self.assertEqual(facts['type_multiplier'], expected)
        self.assertEqual(facts['damage_type'], actual_type or self.rules.move(move)['type'])
        self.assertGreater(dealt, 0)
        self.assertEqual(before - self.t.hp, dealt)
        self.assertEqual(self.a.budget['standard'], 0)
        return facts

    def restore(self):
        identities = self.a.entity_id, self.t.entity_id
        self.e = Engine.import_state(self.rules, json.loads(json.dumps(self.e.export_state())))
        actors = WORLD.actor_index(self.e)
        self.a, self.t = (actors[uid] for uid in identities)
        TRACE.enable(self.e)

    def expire(self):
        for remaining in (2, 1, 0):
            self.begin(self.t)
            self.assertTrue(CATALOG.grounded(self.t))
            self.e.end_of_turn(self.t)
            self.assertEqual(CATALOG.grounded(self.t), remaining > 0)
        self.assertEqual(MOVEMENT.capabilities(self.e, self.t, environment=False)['sky'], 6)

    def equip_balloon(self, uid):
        WORLD.register_object(self.e, uid, location={'kind': 'unknown'}, reason='actual held Balloon',
            kind='item_instance', item_rule_id='item/풍선', owner_id=self.t.entity_id)
        ITEMS.register_item(self.e, self.t, 'item/풍선', source_instance_id=uid, as_held=True)

    def test_both_native_grounding_sources_preserve_steel_and_bug_components(self):
        for source in (ARROWS, SMACK):
            for types, expected in ((('강철', '비행'), 1.5), (('벌레', '비행'), .5)):
                with self.subTest(source=source, types=types):
                    self.setUp()
                    self.ground(source, types)
                    self.assertEqual(self.e.type_multiplier('땅', self.t)[0], expected)
                    self.hit(expected=expected)
                    self.assertTrue(self.e.validate_state()['valid'])

    def test_levitate_grounding_restore_three_target_turns_and_expiry(self):
        for source in (ARROWS, SMACK):
            for types in (('강철', '비행'), ('강철',)):
                with self.subTest(source=source, types=types):
                    self.setUp()
                    self.e.gm.set_types(self.t, list(types), reason='actual Levitate recipient typing')
                    self.e.gm.set_ability(self.t, '부유', reason='actual Levitate ability')
                    before = self.t.hp
                    self.assertEqual(self.use(GROUND), 0)
                    self.assertEqual(self.t.hp, before)
                    self.ground(source, types)
                    self.restore()
                    self.hit(expected=1.5)
                    self.expire()
                    self.restore()
                    before = self.t.hp
                    self.assertEqual(self.use(GROUND), 0)
                    self.assertEqual(self.t.hp, before)
                    self.assertIn('부유', self.t.abilities)
                    self.assertFalse(CATALOG.grounded(self.t))
                    self.assertTrue(self.e.validate_state()['valid'])

    def test_actual_type_selection_preserves_printed_move_and_non_ground_matchups(self):
        for move, actual, expected in ((FIRE, '땅', .5), (GROUND, '불꽃', 1.5)):
            with self.subTest(move=move, actual=actual):
                self.setUp()
                self.ground(SMACK, ('벌레', '비행'))
                printed = self.rules.move(move)['type']
                self.a.type_override_next = actual
                self.restore()
                self.hit(move, expected=expected, actual_type=actual)
                self.assertIsNone(self.a.type_override_next)
                self.assertEqual(self.rules.move(move)['type'], printed)

    def test_registered_effectiveness_step_survives_ground_component_resolution(self):
        self.ground(SMACK)
        # An external registered +1 step is an input to a real native attack.
        self.a.registry.append({'type': 'type_effectiveness_override', 'steps': '+1'})
        self.hit(expected=2.0)

    def test_native_light_screen_keeps_ground_resistance_choice(self):
        self.ground(SMACK)
        self.use('move/빛의장막', actor=self.t, target=self.t)
        blessing = next(r for r in BLESSINGS.live(self.t) if r['source'] == 'move/빛의장막')
        self.rules.rulings.add_answer('team_blessing', True, reason='actual beneficiary chooses resistance')
        self.hit(expected=1.5)
        self.assertEqual(BLESSINGS.remaining(blessing), 1)
        self.assertEqual((blessing['decisions'][-1]['multiplier_before'],
                          blessing['decisions'][-1]['multiplier_after']), (1.5, 1.0))

    def test_native_tar_coat_is_preserved_by_ground_then_consumed_by_actual_fire(self):
        self.ground(SMACK, ('벌레', '비행'))
        self.use('move/타르샷')
        coat = next(r for r in COATS.live(self.t) if r['source'] == 'move/타르샷')
        self.hit(expected=.5)
        self.assertIn(coat, COATS.live(self.t))
        self.a.type_override_next = '불꽃'
        self.hit(GROUND, expected=2.0, actual_type='불꽃')
        self.assertFalse(COATS.live(self.t))

    def test_adopted_ground_flying_resistance_and_source_final_chart_keep_authority(self):
        self.e.configure_ground_flight_option(dict(enabled=True, gm_id='observed-gm',
            reason='explicit adoption of selected Ground/Flying optional paragraph'))
        self.ground(SMACK)
        self.hit(expected=1.0)
        self.e.gm.set_types(self.t, ['유리', '땅'], reason='selected source-owned final defense chart')
        source_value = self.e.type_multiplier('땅', self.t)
        self.assertIn('이로치-포켓몬의-예시', source_value[1])
        self.expire()
        self.assertEqual(self.e.type_multiplier('땅', self.t), source_value)

    def test_grounding_does_not_remove_other_type_or_wonder_guard_immunity(self):
        self.ground(SMACK, ('고스트', '비행'))
        before = self.t.hp
        self.assertEqual(self.use('move/몸통박치기'), 0)
        self.assertEqual(self.t.hp, before)
        self.e.gm.set_types(self.t, ['벌레', '비행'], reason='actual resisted Ground recipient')
        self.e.gm.set_ability(self.t, '불가사의부적', reason='independent actual Wonder Guard')
        self.assertEqual(self.use(GROUND), 0)
        self.assertEqual(self.t.hp, before)

    def test_balloon_newly_equipped_after_grounding_is_suppressed_and_actual_hit_destroys_it(self):
        for source in (ARROWS, SMACK):
            with self.subTest(source=source):
                self.setUp()
                self.ground(source)
                self.equip_balloon('grounded-new-balloon')
                self.assertFalse(PHYSICAL.ground_immunity(self.e, self.t, self.rules.move(GROUND)))
                self.restore()
                self.hit(expected=1.5)
                self.assertIn('destroyed', self.e._physical_objects['grounded-new-balloon'])

    def test_balloon_grounding_hit_destruction_and_unhit_expiry_are_distinct(self):
        self.equip_balloon('before-grounding')
        self.ground(SMACK)
        self.assertIn('destroyed', self.e._physical_objects['before-grounding'])
        self.equip_balloon('unhit-after-grounding')
        self.assertFalse(PHYSICAL.ground_immunity(self.e, self.t, self.rules.move(GROUND)))
        self.expire()
        self.restore()
        self.assertTrue(PHYSICAL.ground_immunity(self.e, self.t, self.rules.move(GROUND)))
        self.assertNotIn('destroyed', self.e._physical_objects['unhit-after-grounding'])
        before = self.t.hp
        self.assertEqual(self.use(GROUND), 0)
        self.assertEqual(self.t.hp, before)


if __name__ == '__main__':
    unittest.main()
