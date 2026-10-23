"""Actual attack type reaches physical/ability immunity and final Essence matchup."""
import json
import unittest
from unittest.mock import patch

from builder import build_pokemon
from engine import Combatant, Engine
import class_passive_combat as CLASS
import csv_item_physical_contracts as PHYSICAL
import effects_ext as EXT
import equipment_suppression as SUPPRESSION
import field_effects as FIELD
import items as ITEMS
import state_grants as GRANTS
import world_entities as WORLD
import test_category2_ability_transitions as ABILITY_FIXTURE
import test_category2_csv_remaining_item_contracts as ITEM_FIXTURE
import test_completed_table18_item_boundaries as ESSENCE_FIXTURE
import test_equipment_suppression_sources as SUPPRESSION_FIXTURE


TYPE_CASES = (
    ('move/땅고르기', None, True),
    ('move/불꽃세례', None, False),
    ('move/땅고르기', '불꽃', False),
    ('move/불꽃세례', '땅', True),
)


class ActualTypeEffectivenessNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ABILITY_FIXTURE.AbilityTransitionTests.setUpClass()
        ESSENCE_FIXTURE.Table18ItemBoundaries.setUpClass()
        cls.suppression_rules = SUPPRESSION_FIXTURE.SuppressionTests.selected_rules()

    def immunity_world(self, *, balloon=False, absent=False, selected_rules=False):
        case = ABILITY_FIXTURE.AbilityTransitionTests()
        if selected_rules:
            case.r = self.suppression_rules
        case.setUp()
        uid = 'actual-type/balloon'
        if balloon and not absent:
            item_case = ITEM_FIXTURE.RemainingCsvItemContractTests()
            item_case.r = case.r
            item_case.equip(case.e, case.t, uid, 'item/풍선')
        elif not balloon:
            case.e.gm.set_ability(case.t, '부유', reason='actual Levitate producer')
        if balloon and not absent:
            self.suppress_levitate(case)
            self.assertTrue(PHYSICAL.ground_immunity(case.e, case.t, case.r.move('move/땅고르기')))
        return case, uid

    def suppress_levitate(self, case):
        case.e.gm.choose_ability_transition(case.a, case.t, 'move/위액',
            ability='부유', reason='only the actual Levitate ability is suppressed')
        case.e.use_move(case.a, case.t, 'move/위액', situational=100)
        self.assertNotIn('부유', case.t.abilities)
        self.assertFalse(case.t.abilities_suppressed)

    def attacker(self, case, move_id):
        attacker = Combatant(case.r, build_pokemon(case.r, '피카츄', 20,
            name='Actual-type attack producer', moves=[move_id], abilities=[], side='party',
            extra={'trainer_id': case.a.entity_id, 'trainer': case.a.name}))
        case.e.gm.add_combatant(attacker, pos=(2, 3), side='party', reason='actual owned attacker')
        case.e.gm.observe_loyalty(attacker, 6, reason='actual Pokemon Move command')
        case.e.end_of_turn(case.a)
        case.e.start_of_turn(attacker, initiative_count=19)
        return attacker

    def hit(self, engine, attacker, target, move_id, override, immune):
        if override is not None:
            attacker.type_override_next = override
        printed_type = engine.r.move(move_id)['type']
        before = target.hp
        dealt = engine.use_move(attacker, target, move_id, situational=100, set_damage=True)
        self.assertIsNone(attacker.type_override_next)
        self.assertEqual(engine.r.move(move_id)['type'], printed_type)
        if immune:
            self.assertEqual((target.hp, dealt), (before, 0))
        else:
            self.assertGreater(dealt, 0)
            self.assertLess(target.hp, before)
        self.assertTrue(engine.validate_state()['valid'])

    def test_balloon_actual_type_table_with_only_levitate_suppressed(self):
        for move_id, override, immune in TYPE_CASES:
            with self.subTest(move=move_id, actual=override):
                case, _ = self.immunity_world(balloon=True)
                attacker = self.attacker(case, move_id)
                self.hit(case.e, attacker, case.t, move_id, override, immune)

    def test_levitate_actual_type_table(self):
        for move_id, override, immune in TYPE_CASES:
            with self.subTest(move=move_id, actual=override):
                case, _ = self.immunity_world()
                attacker = self.attacker(case, move_id)
                self.hit(case.e, attacker, case.t, move_id, override, immune)
                self.assertIn('부유', case.t.abilities)

    def test_balloon_inactive_item_states_do_not_restore_independent_immunity(self):
        for state in ('absent', 'klutz', 'magic_room_json', 'dropped', 'destroyed'):
            with self.subTest(state=state):
                case, uid = self.immunity_world(balloon=True, absent=state == 'absent', selected_rules=True)
                if state == 'klutz':
                    GRANTS.replace_baseline(case.e, case.t, 'abilities', [SUPPRESSION.KLUTZ_NAME])
                elif state == 'magic_room_json':
                    effect = next(e for e in case.r.move_mech('move/매직룸')[0]['effects_exec']
                                  if e.get('type') == 'field_effect')
                    FIELD.install(case.e, case.a, effect, 'move/매직룸')
                elif state == 'dropped':
                    ITEMS.drop_item(case.e, case.t, selection=uid)
                elif state == 'destroyed':
                    ITEMS.destroy_equipment(case.e, case.t, uid, reason='actual independent physical destruction')
                attacker = self.attacker(case, 'move/불꽃세례')
                if state == 'magic_room_json':
                    case.e = Engine.import_state(case.e.r, json.loads(json.dumps(case.e.export_state())))
                    index = WORLD.actor_index(case.e)
                    case.t, attacker = index[case.t.entity_id], index[attacker.entity_id]
                    self.assertEqual(case.e._physical_objects[uid]['equipped_by'], case.t.entity_id)
                self.assertFalse(PHYSICAL.ground_immunity(case.e, case.t, case.r.move('move/땅고르기')))
                self.hit(case.e, attacker, case.t, 'move/불꽃세례', '땅', False)

    def test_levitate_json_retains_actual_type_and_selected_suppression_boundary(self):
        for suppressed in (False, True):
            with self.subTest(suppressed=suppressed):
                case, _ = self.immunity_world()
                if suppressed:
                    self.suppress_levitate(case)
                attacker = self.attacker(case, 'move/불꽃세례')
                attacker.type_override_next = '땅'
                restored = Engine.import_state(case.e.r, json.loads(json.dumps(case.e.export_state())))
                index = WORLD.actor_index(restored)
                self.hit(restored, index[attacker.entity_id], index[case.t.entity_id],
                         'move/불꽃세례', None, not suppressed)

    def essence_world(self, *, wonder_guard=False, restored=False):
        fixture = ESSENCE_FIXTURE.Table18ItemBoundaries()
        fixture.setUp()
        engine, target = fixture.essence_fixture(2)
        if wonder_guard:
            engine.gm.set_ability(target, '불가사의부적', reason='actual native Wonder Guard')
        attacker = Combatant(engine.r, build_pokemon(engine.r, '이브이', 20,
            name='Essence attack producer', moves=['move/섀도볼'], abilities=[]))
        engine.gm.add_combatant(attacker)
        target.pos = (1, 0)
        if restored:
            engine = Engine.import_state(engine.r, json.loads(json.dumps(engine.export_state())))
            index = WORLD.actor_index(engine)
            attacker, target = index[attacker.entity_id], index[target.entity_id]
        return engine, attacker, target

    def test_essence_damage_and_preview_apply_one_step_for_actual_type(self):
        for override in (None, '불꽃'):
            with self.subTest(actual=override):
                engine, attacker, target = self.essence_world()
                move = engine.r.move('move/섀도볼')
                mm = engine.r.move_mech(move['id'])[0]
                if override is not None:
                    attacker.type_override_next = override
                self.assertEqual(engine.type_multiplier(override or '고스트', target)[0], 1.0)
                self.assertEqual(CLASS._effectiveness_preview(engine, attacker, target, move, mm), 1.0)
                self.assertEqual(attacker.type_override_next, override)
                engine.start_round([attacker, target])
                engine.start_of_turn(attacker, initiative_count=20)
                before = target.hp
                with patch.object(engine, 'd20', return_value=20):
                    dealt = engine.use_move(attacker, target, move['id'], set_damage=True)
                self.assertEqual((dealt, before - target.hp), (34, 34))
                self.assertIsNone(attacker.type_override_next)
                self.assertTrue(engine.validate_state()['valid'])

    def test_essence_neutral_preview_wonder_guard_and_json_agree(self):
        for restored in (False, True):
            with self.subTest(restored=restored):
                engine, attacker, target = self.essence_world(wonder_guard=True, restored=restored)
                move = engine.r.move('move/섀도볼')
                mm = engine.r.move_mech(move['id'])[0]
                self.assertEqual(target.spec['csv_essence_projection']['essence'], 2)
                self.assertEqual(CLASS._effectiveness_preview(engine, attacker, target, move, mm), 1.0)
                self.assertEqual(EXT.blocks_hit(engine, attacker, target, move, mm), 'ability/불가사의부적')
                engine.start_round([attacker, target])
                engine.start_of_turn(attacker, initiative_count=20)
                before = target.hp
                with patch.object(engine, 'd20', return_value=20):
                    dealt = engine.use_move(attacker, target, move['id'], set_damage=True)
                self.assertEqual((dealt, target.hp), (0, before))
                self.assertTrue(engine.validate_state()['valid'])


if __name__ == '__main__':
    unittest.main()
