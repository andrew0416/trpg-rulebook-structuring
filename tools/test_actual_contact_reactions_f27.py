"""F27: current contact classification belongs to the actual native recipient."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]

from builder import build_pokemon
from engine import Combatant, Engine
from grid import Grid
import move_defense_reactions as DEFENSE
import passive_events as PASSIVE
import reactive_ability_events as REACTIVE
import state_grants as GRANTS
import test_category2_equipment_variant_contracts as FIXTURE
import world_entities as WORLD


class ActualContactReactionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        FIXTURE.EquipmentVariantContractTests.setUpClass()
        cls.r = FIXTURE.EquipmentVariantContractTests.r

    def fixture(self, glove, *, move='move/몸통박치기'):
        fixture = FIXTURE.EquipmentVariantContractTests()
        fixture.r = self.r
        engine, attacker, spare = fixture.fixture(moves=(move,))
        GRANTS.replace_baseline(engine, attacker, 'abilities', ['인분'])
        if glove:
            fixture.equip(engine, attacker, 'item/펀치글러브', 'actual-contact')
        return engine, attacker, spare

    def target(self, engine, name, *, aroma=True, pos=None, intercept=False):
        extra = {'side': 'wild'}
        if pos is not None:
            extra['pos'] = pos
        if intercept:
            extra.update(loyalty=6, skills={'육상': 5}, movement={'land': 8},
                         movement_basis='current')
        target = Combatant(self.r, build_pokemon(
            self.r, '이상해씨', 30, name=name, moves=['move/몸통박치기'],
            abilities=['가시지않는향기'] if aroma else [], extra=extra))
        engine.gm.add_combatant(target)
        return target

    def choose(self, engine, target):
        engine.choose_reactive_ability(target, 'ability/가시지않는향기',
            reason='actual recipient chooses its next native contact reaction')

    def assert_outcome_and_restore(self, engine, attacker, target, glove):
        row = list(engine._move_completions.values())[-1]
        self.assertEqual(row['phase'], 'complete')
        self.assertIn('근접', row['move']['range'])
        evidence = row[REACTIVE.TAG]
        self.assertEqual(evidence['hits'][target.entity_id], {'hit_prevented': False})
        self.assertEqual(len(evidence['applications']), 0 if glove else 1)
        self.assertEqual(attacker.abilities, ['인분'] if glove else ['가시지않는향기'])
        self.assertTrue(engine.validate_state()['valid'])
        restored = Engine.import_state(self.r,
            json.loads(json.dumps(engine.export_state(), ensure_ascii=False)))
        restored_attacker = WORLD.actor_index(restored)[attacker.entity_id]
        self.assertEqual(restored_attacker.abilities, attacker.abilities)
        self.assertTrue(restored.validate_state()['valid'])
        return restored

    def test_native_single_hit_uses_current_contact_and_keeps_historical_validation(self):
        for glove in (False, True):
            with self.subTest(glove=glove):
                engine, attacker, spare = self.fixture(glove)
                target = self.target(engine, 'aroma-single')
                engine.start_round([attacker, spare, target])
                engine.start_of_turn(attacker, initiative_count=20)
                self.choose(engine, target)
                with patch.object(type(engine), 'd20', new=lambda e: 20):
                    engine.use_move(attacker, target, 'move/몸통박치기', set_damage=True)
                row = list(engine._move_completions.values())[-1]
                self.assertEqual(set(row['results']), {target.entity_id})
                self.assertTrue(row['results'][target.entity_id]['hit'])
                restored = self.assert_outcome_and_restore(engine, attacker, target, glove)
                if not glove:
                    historical = list(restored._move_completions.values())[-1]['move']
                    original_range = historical['range']
                    historical['range'] = '비접촉'
                    with self.assertRaisesRegex(ValueError, 'reactive handoff requires actual melee hit'):
                        REACTIVE.validate_world(restored, WORLD.actor_index(restored))
                    historical['range'] = original_range
                    self.assertTrue(restored.validate_state()['valid'])

    def test_line_move_classifies_each_of_two_actual_recipients(self):
        for chosen_index in (0, 1):
            for glove in (False, True):
                with self.subTest(chosen_index=chosen_index, glove=glove):
                    engine, attacker, spare = self.fixture(glove, move='move/드래곤해머')
                    engine.grid = Grid(20, 20)
                    attacker.pos = (2, 2)
                    spare.pos = (15, 15)
                    targets = [self.target(engine, 'aroma-line-' + str(index),
                        aroma=index == chosen_index, pos=pos)
                        for index, pos in enumerate(((3, 2), (4, 2)))]
                    target = targets[chosen_index]
                    engine.start_round([attacker, spare, *targets])
                    engine.start_of_turn(attacker, initiative_count=20)
                    self.choose(engine, target)
                    with patch.object(type(engine), 'd20', new=lambda e: 20):
                        engine.use_move_on(attacker, targets[0], 'move/드래곤해머',
                                           engine.everyone, set_damage=True)
                    row = list(engine._move_completions.values())[-1]
                    self.assertEqual(set(row['results']), {actor.entity_id for actor in targets})
                    self.assertTrue(all(result['hit'] for result in row['results'].values()))
                    self.assert_outcome_and_restore(engine, attacker, target, glove)

    def test_paid_intercept_classifies_the_actual_recipient_and_restores(self):
        for glove in (False, True):
            with self.subTest(glove=glove):
                engine, attacker, spare = self.fixture(glove)
                engine.grid = Grid(20, 20)
                attacker.pos = (3, 0)
                spare.pos = (10, 10)
                original = self.target(engine, 'original', aroma=False, pos=(4, 0))
                interceptor = self.target(engine, 'aroma-interceptor', pos=(4, 3), intercept=True)
                engine.start_round([attacker, spare, original, interceptor])
                engine.start_of_turn(attacker, initiative_count=20)
                self.choose(engine, interceptor)
                engine.watch_move_defense(original, [{
                    'actor_id': interceptor.entity_id, 'source': DEFENSE.MELEE}],
                    reason='physical melee attack has an actual Intercept recipient')
                with patch.object(type(engine), 'd20', new=lambda e: 20):
                    with self.assertRaises(PASSIVE.PassiveEventPending):
                        engine.use_move(attacker, original, 'move/몸통박치기', set_damage=True)
                    engine.choose_move_defense(engine._passive_pending, interceptor, use=True,
                        options={'path': [(4, 3), (4, 2), (4, 1), (4, 0)],
                                 'skill': '육상', 'mode': 'land',
                                 'roll_options': {'fixed': [6] * 5},
                                 'shove_destination': [5, 0]},
                        reason='pay for native Intercept and shove')
                row = list(engine._move_completions.values())[-1]
                self.assertEqual(set(row['received']), {interceptor.entity_id})
                self.assertTrue(row['received'][interceptor.entity_id]['hit'])
                self.assertNotIn(original.entity_id, row[REACTIVE.TAG]['hits'])
                self.assert_outcome_and_restore(engine, attacker, interceptor, glove)


if __name__ == '__main__':
    unittest.main()
