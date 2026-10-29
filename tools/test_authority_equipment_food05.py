"""Equipment scope, food quota and saved-projection regression boundaries."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]

from engine import Engine, Rules
import csv_item_food_contracts as CSV_FOOD
import food_effects as FOOD
import items as ITEMS
import optional_physical_equipment as OPTIONAL
import state_codec as CODEC
import world_entities as WORLD
import test_category2_optional_physical_equipment as _equipment_fixture
import test_category2_csv_remaining_item_contracts as _food_fixture


class EquipmentFoodAuthorityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset='all')
        cls.core = Rules(ROOT, ruleset='core')
        cls.playtest = Rules(ROOT, ruleset='playtest')

    def setUp(self):
        self.equipment = _equipment_fixture.OptionalPhysicalEquipmentTests()
        self.equipment.r = self.rules
        for rules in (self.rules, self.core, self.playtest):
            previous = rules.rulings
            rules.rulings = deepcopy(previous)
            rules.rulings.answers.clear()
            rules.rulings.provider = None
            self.addCleanup(setattr, rules, 'rulings', previous)

    def place(self, engine, actor, map_id, cell):
        WORLD.observe_location(engine, actor,
            {'kind': 'grid', 'map_id': map_id, 'cell': cell},
            reason='observed independent map for equipment radius')

    def test_flute_rejects_remote_protection_and_does_not_cure_other_maps(self):
        engine, actor, ally, enemy = self.equipment.fixture()
        self.equipment.equip(engine, actor, 'crafted_item/따스한-플루트', 'map-flute')
        self.place(engine, actor, 'map-a', (2, 2))
        self.place(engine, ally, 'map-b', (2, 2))
        self.place(engine, enemy, 'map-b', (3, 2))
        for target in (actor, ally, enemy):
            engine.apply_status(target, '마비')
        engine.start_round(engine.everyone)
        engine.start_of_turn(actor, initiative_count=20)
        before = CODEC.dump_engine(engine)
        with self.assertRaisesRegex(ValueError, 'outside 20 metres'):
            OPTIONAL.activate_heartwarming_flute(engine, actor, protected_allies=(ally,))
        self.assertEqual(CODEC.dump_engine(engine), before)
        self.place(engine, ally, 'map-a', (4, 2))
        result = OPTIONAL.activate_heartwarming_flute(engine, actor, protected_allies=(actor, ally))
        self.assertTrue(result['activated'])
        self.assertEqual(set(result['protected']), {actor.entity_id, ally.entity_id})
        self.assertNotIn('마비', actor.conditions)
        self.assertNotIn('마비', ally.conditions)
        self.assertIn('마비', enemy.conditions)
        ghost = {'type': '고스트', 'class': '특수'}
        self.assertEqual(ITEMS.item_damage_reduction(ally, ghost, engine=engine), 5)
        self.assertEqual(ITEMS.item_damage_reduction(enemy, ghost, engine=engine), 0)

    def test_svalinn_uses_observed_map_and_two_metre_boundary(self):
        engine, wearer, target, _ = self.equipment.fixture()
        self.equipment.equip(engine, wearer, 'crafted_item/스-발린', 'map-svalinn')
        self.place(engine, wearer, 'map-a', (2, 2))
        self.place(engine, target, 'map-b', (2, 2))
        self.assertEqual(OPTIONAL.resistance_steps(engine, target, '불꽃'), 0)
        self.place(engine, target, 'map-a', (4, 2))
        self.assertEqual(OPTIONAL.resistance_steps(engine, target, '불꽃'), 1)
        self.assertEqual(OPTIONAL.resistance_steps(engine, target, '물'), 0)
        self.place(engine, target, 'map-a', (5, 2))
        self.assertEqual(OPTIONAL.resistance_steps(engine, target, '불꽃'), 0)

    def mirror_fixture(self, rules, count=1):
        fixture = _food_fixture.RemainingCsvItemContractTests()
        fixture.r = rules
        actor = fixture.pokemon('mirror-quota-holder', abilities=('Gluttony',),
                                items={'item/흉내허브': count + 1})
        source = fixture.pokemon('mirror-quota-source')
        engine = fixture.fixture(actor, source)
        for _ in range(count):
            self.intake_mirror(engine, actor)
        return engine, actor, source

    def intake_mirror(self, engine, actor):
        return engine.use_item(actor, 'item/흉내허브',
            food_policy=CSV_FOOD.definition(engine.r, 'item/흉내허브')['clause_id'],
            duration_minutes=1, duration_reason='observed actual Mirror Herb intake')

    def test_core_and_playtest_mirror_accept_or_decline_actual_stage(self):
        for rules in (self.core, self.playtest):
            for accept in (True, False):
                with self.subTest(profile=rules.ruleset.name, accept=accept):
                    engine, actor, source = self.mirror_fixture(rules)
                    engine.start_round([source, actor])
                    engine.start_of_turn(source, initiative_count=20)
                    engine.rulings.add_answer('mirror_herb', accept,
                        reason='actual holder accepts or declines this exchange')
                    engine.change_stage(source, 'atk', 2)
                    self.assertEqual(source.stages['atk'], 2)
                    self.assertEqual(actor.stages['atk'], 2 if accept else 0)
                    self.assertEqual(len(actor.buffs), 0 if accept else 1)
                    receipts = actor.spec.get('food_consumption_receipts', [])
                    self.assertEqual(len(receipts), int(accept))
                    if accept and rules is self.core:
                        self.assertEqual(FOOD._core_usage(engine, actor), (1, False))
                    restored = Engine.import_state(rules, json.loads(json.dumps(engine.export_state())))
                    self.assertTrue(restored.validate_state()['valid'])
                    rules.rulings.answers.clear()

    def test_core_mirror_stops_at_encounter_quota_without_cancelling_source_gain(self):
        engine, actor, source = self.mirror_fixture(self.core, count=4)
        engine.start_round([source, actor])
        engine.start_of_turn(source, initiative_count=20)
        engine.rulings.add_answer('mirror_herb', True, reason='actual holder exchanges eligible Herbs')
        engine.change_stage(source, 'atk', 1)
        self.assertEqual((source.stages['atk'], actor.stages['atk']), (1, 3))
        self.assertEqual(FOOD._core_usage(engine, actor), (3, False))
        self.assertEqual(len(actor.buffs), 1)
        engine.change_stage(source, 'def', 1)
        self.assertEqual((source.stages['def'], actor.stages['def']), (1, 0))
        self.assertFalse(FOOD.consumption_allowed(engine, actor, actor.buffs[0], optional=True))
        with self.assertRaisesRegex(ValueError, 'core Gluttony encounter'):
            FOOD.consumption_allowed(engine, actor, actor.buffs[0])

    def test_playtest_mirror_scene_quota_survives_later_actual_intake(self):
        engine, actor, source = self.mirror_fixture(self.playtest, count=3)
        engine.rulings.add_answer('mirror_herb', True, reason='actual holder exchanges eligible Herbs')
        engine.change_stage(source, 'atk', 1)
        self.assertEqual(actor.counters['lim:food_buff_consumed'], 3)
        self.intake_mirror(engine, actor)
        engine.change_stage(source, 'def', 1)
        self.assertEqual((source.stages['def'], actor.stages['def']), (1, 0))
        self.assertEqual(len(actor.buffs), 1)
        with self.assertRaisesRegex(ValueError, 'Gluttony scene'):
            FOOD.consumption_allowed(engine, actor, actor.buffs[0])

    def test_core_unknown_legacy_quota_skips_optional_mirror_but_retains_obligation(self):
        engine, actor, source = self.mirror_fixture(self.core)
        engine.rulings.add_answer('mirror_herb', True, reason='actual earlier Herb exchange')
        engine.change_stage(source, 'atk', 1)
        receipt = actor.spec['food_consumption_receipts'][0]
        receipt.pop(FOOD.ENCOUNTER_RECEIPT)
        self.intake_mirror(engine, actor)
        engine.start_round([source, actor])
        engine.start_of_turn(source, initiative_count=20)
        self.assertEqual(FOOD._core_usage(engine, actor), (0, True))
        engine.change_stage(source, 'def', 1)
        self.assertEqual((source.stages['def'], actor.stages['def']), (1, 0))
        self.assertEqual(len(actor.buffs), 1)
        self.assertEqual(len(actor.spec['food_consumption_receipts']), 1)
        with self.assertRaisesRegex(ValueError, 'quota observation required'):
            FOOD.consumption_allowed(engine, actor, actor.buffs[0])

    def test_optional_mirror_probe_does_not_swallow_malformed_consumption_history(self):
        engine, actor, source = self.mirror_fixture(self.core)
        engine.start_round([source, actor])
        engine.start_of_turn(source, initiative_count=20)
        actor.spec['food_consumption_receipts'] = 'not a history'
        with self.assertRaisesRegex(ValueError, 'actual food consumption receipts'):
            FOOD.consumption_allowed(engine, actor, actor.buffs[0], optional=True)
        self.assertEqual((source.stages['atk'], actor.stages['atk']), (0, 0))
        self.assertEqual(len(actor.buffs), 1)

    def test_optional_unnerved_probe_validates_history_without_consuming_or_weakening_default(self):
        import test_category2_ability_target_limits as limits_fixture
        case = limits_fixture.TargetLimitsTests()
        case.r = self.core
        case.setUp()
        buff_id = case.feed()
        case.begin()
        case.activate()
        buff = next(row for row in case.t.buffs if row['id'] == buff_id)
        self.assertFalse(FOOD.consumption_allowed(case.e, case.t, buff, optional=True))
        with self.assertRaisesRegex(ValueError, 'Unnerve'):
            FOOD.consumption_allowed(case.e, case.t, buff)
        original = deepcopy(case.t.spec.get('food_consumption_receipts', []))
        case.t.spec['food_consumption_receipts'] = 'not a history'
        before = deepcopy((case.t.spec, case.t.counters, case.t.buffs))
        with self.assertRaisesRegex(ValueError, 'actual food consumption receipts'):
            FOOD.consumption_allowed(case.e, case.t, buff, optional=True)
        with self.assertRaisesRegex(ValueError, 'Unnerve'):
            FOOD.consumption_allowed(case.e, case.t, buff)
        self.assertEqual((case.t.spec, case.t.counters, case.t.buffs), before)
        case.t.spec['food_consumption_receipts'] = original
        case.t.counters['food_buff_consumed'] = -1
        with self.assertRaisesRegex(ValueError, 'actual food consumption counter'):
            FOOD.consumption_allowed(case.e, case.t, buff, optional=True)
        self.assertEqual(case.t.counters['food_buff_consumed'], -1)
        self.assertIn(buff, case.t.buffs)

    def test_changed_equipment_projection_rejects_codec_and_gm_restore_atomically(self):
        cases = (('item/정신방패', 'mental_bonus', 60),
                 ('item/정신방패', 'iron_mind', True),
                 ('crafted_item/명금의-로브', 'save_bonus', 20),
                 ('crafted_item/명금의-로브', 'save_condition', '마비'),
                 ('crafted_item/명금의-로브', 'kind', 'mental_shield'))
        for item_id, field, changed in cases:
            with self.subTest(item=item_id, field=field):
                engine, actor, _, _ = self.equipment.fixture()
                uid = self.equipment.equip(engine, actor, item_id, 'projection')
                engine.gm.snapshot('intact')
                before = CODEC.dump_engine(engine)
                attrs = engine.gm.snapshots['intact']['combatants'][id(actor)]
                stored = next(row for row in attrs['registry']
                              if row.get('type') == 'optional_physical_equipment' and row.get('instance_id') == uid)
                stored[field] = changed
                with self.assertRaisesRegex(ValueError, 'projection differs from its selected definition'):
                    engine.gm.restore('intact', reason='reject inconsistent derived equipment')
                self.assertEqual(CODEC.dump_engine(engine), before)
                actual = next(row for row in actor.registry
                              if row.get('type') == 'optional_physical_equipment' and row.get('instance_id') == uid)
                original = deepcopy(actual)
                try:
                    actual[field] = changed
                    encoder = CODEC._Encoder(engine)
                    malformed = deepcopy(before)
                    malformed['root'] = encoder.value(engine)
                    malformed['nodes'] = encoder.nodes
                finally:
                    actual.clear()
                    actual.update(original)
                with self.assertRaisesRegex(ValueError, 'projection differs from its selected definition'):
                    Engine.import_state(self.rules, malformed)
                self.assertEqual(CODEC.dump_engine(engine), before)

    def test_native_iron_mind_suit_and_shadow_walker_configurations_roundtrip(self):
        for iron_mind in (False, True):
            with self.subTest(iron_mind=iron_mind):
                engine, actor, _, _ = self.equipment.fixture(
                    edges=('edge/강철의-정신',) if iron_mind else ())
                self.equipment.equip(engine, actor, 'item/정신방패', 'valid-mental')
                restored = self.equipment.restored(engine)
                current = WORLD.actor_index(restored)[actor.entity_id]
                self.assertEqual(OPTIONAL.mental_resistance_bonus(current), 0 if iron_mind else 6)
                self.assertTrue(restored.validate_state()['valid'])
        for variant in ('ordinary', 'robotic'):
            with self.subTest(suit=variant):
                engine, actor, _, _ = self.equipment.fixture()
                uid = 'optional-equipment/valid-suit'
                WORLD.register_object(engine, uid, kind='item_instance', item_rule_id='item/우주복',
                    owner_id=actor.entity_id, location={'kind': 'unknown'}, reason='actual suit variant')
                OPTIONAL.configure_space_suit(engine, actor, uid, variant, reason='observed manufactured suit')
                ITEMS.register_item(engine, actor, 'item/우주복', source_instance_id=uid)
                restored = self.equipment.restored(engine)
                current = WORLD.actor_index(restored)[actor.entity_id]
                projection = OPTIONAL._equipped(current, 'space_suit')
                self.assertEqual(projection['space_suit_variant'], variant)
                self.assertEqual(OPTIONAL.movement(current, {})['free_float'], 4)
                self.assertTrue(restored.validate_state()['valid'])
        engine, actor, _, _ = self.equipment.fixture()
        base = self.equipment.equip(engine, actor, 'crafted_item/경쟁-부츠', 'valid-base')
        shadow = self.equipment.equip(engine, actor, 'crafted_item/섀도우-워커', 'valid-shadow')
        restored = self.equipment.restored(engine)
        current = WORLD.actor_index(restored)[actor.entity_id]
        retained = OPTIONAL._equipped(current, 'shadow_walkers')['retained_base']
        self.assertEqual(retained['instance_id'], base)
        self.assertEqual(current._item_reg[retained['registration_key']]['retained_by_shadow_walkers'], shadow)
        self.assertTrue(restored.validate_state()['valid'])


if __name__ == '__main__':
    unittest.main()
