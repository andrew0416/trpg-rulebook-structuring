"""Reject copied Fashion issuances while preserving native and legacy lifetimes."""
from copy import copy, deepcopy
from pathlib import Path
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Engine, Combatant
from builder import build_pokemon
import condition_recovery as RECOVERY
import equipment_protection as PROTECTION
import fashion_items as FASHION
import frequency as FREQUENCY
import held_equipment as HELD
import items as ITEMS
import capability_actions as CAP
import state_codec as CODEC
import world_entities as WORLD
import test_category2_fashion_item_contracts as _fashion_fixture
import test_manual_equipment as _manual_fixture
import test_category2_csv_item_transfers as _transfer_fixture


class FashionSaveReceiptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.homebrew = Rules(ROOT, ruleset='homebrew')
        cls.core = Rules(ROOT, ruleset='core')

    def private_rules(self, source):
        rules = copy(source)
        rules.rulings = deepcopy(source.rulings)
        return rules

    def fashion(self):
        fixture = _fashion_fixture.FashionItemContractTests()
        fixture.rules = self.private_rules(self.homebrew)
        fixture.setUp()
        item = 'item/근사한-패션-1'
        instance_id = fixture.make(item)
        fixture.combat(fixture.p, fixture.a, fixture.q)
        issued = fixture.e.activate_fashion_item(fixture.p, item, instance_id=instance_id)
        self.assertIs(fixture.e.rulings, fixture.e.r.rulings)
        self.assertEqual(fixture.p.spec['fashion_next_save']['activation_receipt'], issued)
        self.assertEqual(fixture.e._physical_objects[instance_id][FASHION.STATE]['history'], [issued])
        self.assertNotIn('fashion_next_save', fixture.q.spec)
        return fixture, instance_id, issued

    @staticmethod
    def spec_items(payload, actor_id):
        actor = next(node for node in payload['nodes'].values()
                     if node['kind'] == 'actor' and node['entity_id'] == actor_id)
        attrs = payload['nodes'][actor['attrs']['$ref']]['items']
        spec = next(value for key, value in attrs if key == 'spec')
        return payload['nodes'][spec['$ref']]['items']

    def test_valid_cool_fashion_lingers_after_unequip_and_consumes_once(self):
        fixture, instance_id, issued = self.fashion()
        ITEMS.unregister_item(fixture.e, fixture.p, 'item/근사한-패션-1')
        loaded = Engine.import_state(fixture.rules, json.loads(json.dumps(fixture.e.export_state())))
        wearer = WORLD.actor_index(loaded)[fixture.p.entity_id]
        self.assertNotIn('equipped_by', loaded._physical_objects[instance_id])
        self.assertEqual(loaded._physical_objects[instance_id][FASHION.STATE]['history'], [issued])
        self.assertEqual(RECOVERY.saving_check(loaded, wearer, None, 8, fixed=5)['fashion_bonus'], 4)
        self.assertEqual(RECOVERY.saving_check(loaded, wearer, None, 8, fixed=5)['fashion_bonus'], 0)

    def test_codec_rejects_copied_activation_for_a_different_save_recipient(self):
        fixture, instance_id, issued = self.fashion()
        payload = json.loads(json.dumps(fixture.e.export_state()))
        original = deepcopy(payload)
        wearer_spec = self.spec_items(payload, fixture.p.entity_id)
        other_spec = self.spec_items(payload, fixture.q.entity_id)
        actual_pending = next(value for key, value in wearer_spec if key == 'fashion_next_save')
        self.assertFalse(any(key == 'fashion_next_save' for key, _ in other_spec))
        other_spec.append(['fashion_next_save', deepcopy(actual_pending)])
        with self.assertRaisesRegex(ValueError, 'Fashion save activation'):
            Engine.import_state(fixture.rules, payload)
        self.assertEqual(fixture.e.export_state(), original)

    def test_gm_restore_rejects_copied_activation_without_live_state_change(self):
        fixture, instance_id, issued = self.fashion()
        fixture.e.gm.snapshot('one-native-fashion-activation')
        snapshot = fixture.e.gm.snapshots['one-native-fashion-activation']
        source_spec = snapshot['combatants'][id(fixture.p)]['spec']
        receiver_spec = snapshot['combatants'][id(fixture.q)]['spec']
        self.assertNotIn('fashion_next_save', receiver_spec)
        receiver_spec['fashion_next_save'] = deepcopy(source_spec['fashion_next_save'])
        before = CODEC.dump_engine(fixture.e)
        with self.assertRaisesRegex(ValueError, 'Fashion save activation'):
            fixture.e.gm.restore('one-native-fashion-activation', reason='reject inconsistent derived receipt')
        self.assertEqual(CODEC.dump_engine(fixture.e), before)

    def test_native_save_benefit_stays_with_original_wearer_after_item_transfer(self):
        fixture, instance_id, issued = self.fashion()
        ITEMS.transfer_equipment(fixture.e, fixture.p, fixture.q, instance_id, consent_by=(fixture.p,))
        loaded = Engine.import_state(fixture.rules, json.loads(json.dumps(fixture.e.export_state())))
        index = WORLD.actor_index(loaded)
        self.assertEqual(loaded._physical_objects[instance_id]['equipped_by'], fixture.q.entity_id)
        self.assertEqual(RECOVERY.saving_check(loaded, index[fixture.q.entity_id], None, 8, fixed=5)['fashion_bonus'], 0)
        self.assertEqual(RECOVERY.saving_check(loaded, index[fixture.p.entity_id], None, 8, fixed=5)['fashion_bonus'], 4)
        self.assertEqual(RECOVERY.saving_check(loaded, index[fixture.p.entity_id], None, 8, fixed=5)['fashion_bonus'], 0)

    def test_consumed_activation_cannot_be_rearmed_on_its_original_wearer(self):
        fixture, instance_id, issued = self.fashion()
        pending = deepcopy(fixture.p.spec['fashion_next_save'])
        self.assertEqual(RECOVERY.saving_check(fixture.e, fixture.p, None, 8, fixed=5)['fashion_bonus'], 4)
        fixture.p.spec['fashion_next_save'] = deepcopy(pending)
        before = deepcopy(fixture.p.spec['fashion_next_save'])
        with self.assertRaisesRegex(ValueError, 'already consumed'):
            FASHION.consume_save_bonus(fixture.e, fixture.p)
        self.assertEqual(fixture.p.spec['fashion_next_save'], before)
        with self.assertRaisesRegex(ValueError, 'already consumed'):
            fixture.e.export_state()
        self.assertEqual(len(fixture.p.spec['fashion_save_history']), 1)

    def test_embedded_activation_edits_cannot_replace_original_issuance(self):
        fixture, instance_id, issued = self.fashion()
        original = deepcopy(fixture.p.spec['fashion_next_save'])
        for field, value in (('wearer_id', fixture.q.entity_id), ('instance_id', 'unrelated-item'),
                             ('clause_id', 'unrelated-clause'), ('maker_id', fixture.q.entity_id)):
            with self.subTest(field=field):
                changed = deepcopy(original)
                changed['activation_receipt'][field] = value
                fixture.p.spec['fashion_next_save'] = changed
                with self.assertRaisesRegex(ValueError, 'Fashion save'):
                    FASHION.consume_save_bonus(fixture.e, fixture.p)
                self.assertEqual(fixture.p.spec['fashion_next_save'], changed)
        fixture.p.spec['fashion_next_save'] = original
        self.assertEqual(fixture.e._physical_objects[instance_id][FASHION.STATE]['history'], [issued])
        self.assertEqual(RECOVERY.saving_check(fixture.e, fixture.p, None, 8, fixed=5)['fashion_bonus'], 4)

    def core_fashion(self):
        fixture = _transfer_fixture.Tests()
        fixture.r = self.private_rules(self.core)
        engine, wearer, other, _ = fixture.fixture(held=(None, None))
        item = 'item/기막힌-패션'; instance_id = 'core-save-fashion'
        WORLD.register_object(engine, instance_id, kind='item_instance', item_rule_id=item,
            owner_id=wearer.entity_id, location={'kind': 'unknown'}, reason='actual Core Fashion')
        ITEMS.register_item(engine, wearer, item, source_instance_id=instance_id)
        engine.start_round([wearer, other]); engine.start_of_turn(wearer, initiative_count=20)
        engine.activate_fashion_item(wearer, item, instance_id=instance_id)
        ITEMS.unregister_item(engine, wearer, item)
        return engine, wearer, other

    def test_core_issuance_survives_revoked_registration_and_restore(self):
        engine, wearer, other = self.core_fashion()
        pending = wearer.spec['fashion_next_save']
        self.assertIn('activation_id', pending['activation_receipt'])
        self.assertEqual(wearer.spec[FASHION.STATE]['history'], [pending['activation_receipt']])
        loaded = Engine.import_state(engine.r, json.loads(json.dumps(engine.export_state())))
        saved = WORLD.actor_index(loaded)[wearer.entity_id]
        self.assertEqual(RECOVERY.saving_check(loaded, saved, None, 8, fixed=5)['fashion_bonus'], 4)
        self.assertEqual(RECOVERY.saving_check(loaded, saved, None, 8, fixed=5)['fashion_bonus'], 0)

    def test_new_core_receipt_cannot_downgrade_to_legacy_by_removing_issuance_id(self):
        engine, wearer, _ = self.core_fashion()
        wearer.spec['fashion_next_save']['activation_receipt'].pop('activation_id')
        with self.assertRaisesRegex(ValueError, 'retained activation identity'):
            FASHION.consume_save_bonus(engine, wearer)
        with self.assertRaisesRegex(ValueError, 'retained activation identity'):
            engine.export_state()

    def test_legacy_unequipped_core_keeps_issuer_identity_without_invented_history(self):
        engine, wearer, other = self.core_fashion()
        # Reproduce the exact old writer schema: source metadata was revoked,
        # but its embedded native wearer/instance receipt survived unequipping.
        wearer.spec['fashion_next_save']['activation_receipt'].pop('activation_id')
        wearer.spec.pop(FASHION.STATE)
        payload = json.loads(json.dumps(engine.export_state()))
        copied = deepcopy(payload)
        actual = next(value for key, value in self.spec_items(copied, wearer.entity_id)
                      if key == 'fashion_next_save')
        self.spec_items(copied, other.entity_id).append(['fashion_next_save', deepcopy(actual)])
        with self.assertRaisesRegex(ValueError, 'actual wearer'):
            Engine.import_state(engine.r, copied)
        loaded = Engine.import_state(engine.r, payload)
        saved = WORLD.actor_index(loaded)[wearer.entity_id]
        self.assertNotIn(FASHION.STATE, saved.spec)
        self.assertEqual(RECOVERY.saving_check(loaded, saved, None, 8, fixed=5)['fashion_bonus'], 4)
        self.assertNotIn(FASHION.STATE, saved.spec)

    def test_legacy_homebrew_still_requires_original_physical_history(self):
        fixture, instance_id, _ = self.fashion()
        fixture.p.spec['fashion_next_save']['activation_receipt'].pop('activation_id')
        fixture.p.spec.pop(FASHION.STATE)
        state = fixture.e._physical_objects[instance_id][FASHION.STATE]
        state['scene_activation'].pop('activation_id')
        state['history'][0].pop('activation_id')
        loaded = Engine.import_state(fixture.rules, json.loads(json.dumps(fixture.e.export_state())))
        saved = WORLD.actor_index(loaded)[fixture.p.entity_id]
        self.assertEqual(RECOVERY.saving_check(loaded, saved, None, 8, fixed=5)['fashion_bonus'], 4)
        fixture.e._physical_objects[instance_id][FASHION.STATE]['history'][0]['wearer_id'] = fixture.q.entity_id
        with self.assertRaisesRegex(ValueError, 'original physical history'):
            fixture.e.export_state()

    def test_compound_host_handoff_requires_selection_but_accepts_protected_leek_replacement(self):
        transfer = _transfer_fixture.Tests()
        transfer.r = self.private_rules(self.core)
        manual = _manual_fixture.Tests()
        manual.f = transfer
        engine, giver, controller, incoming_id = manual.fixture()
        pokemon = Combatant(engine.r, build_pokemon(engine.r, '파오리', 20,
            moves=[], abilities=[], pos=(0, 1), extra={'trainer_id': controller.entity_id,
                'movement': {'land': 6, 'power': 4}, 'power_basis': 'current'}))
        engine.gm.add_combatant(pokemon, side='foe', reason='actual other-controller recipient')
        engine.gm.set_ability(pokemon, '대파의달인', reason='actual native Leek holder source')
        old_id = 'candidate05/leek'
        WORLD.register_object(engine, old_id, kind='item_instance', item_rule_id='item/대파',
            owner_id=pokemon.entity_id, weight_kg=1, location={'kind': 'unknown'},
            reason='actual protected Leek')
        CAP.set_carried(engine, pokemon, [{'id': old_id, 'weight_kg': 1}], 'actual Leek possession')
        ITEMS.register_item(engine, pokemon, '대파', source_instance_id=old_id, as_held=True)
        selected = ITEMS.selected_equipment(pokemon, old_id, ('held',))
        self.assertEqual(PROTECTION.status(engine, pokemon, selected, 'drop')['status'], 'needs_consent')
        with self.assertRaises(PROTECTION.EquipmentConsentRequired):
            PROTECTION.require(engine, pokemon, selected, 'drop', (giver,))
        before = CODEC.dump_engine(engine)
        with self.assertRaises(ValueError):
            engine.give_equipment(giver, pokemon, incoming_id)
        self.assertEqual(CODEC.dump_engine(engine), before)
        result = engine.give_equipment(giver, pokemon, incoming_id, replace_selection=old_id)
        self.assertTrue(result['equipped'])
        self.assertEqual(giver.budget['standard'], 0)
        self.assertEqual(HELD.entries(pokemon)[0]['instance_id'], incoming_id)
        old = engine._physical_objects[old_id]
        self.assertEqual((old['owner_id'], old['carrier_id']), (pokemon.entity_id, pokemon.entity_id))
        self.assertNotIn('equipped_by', old)
        self.assertEqual(engine._physical_objects[incoming_id]['owner_id'], giver.entity_id)
        print('OE_01_HOST_CONTRACT_OBSERVATION', json.dumps({
            'explicit_replace_selection': old_id, 'different_controller': controller.entity_id,
            'receiver_consent_input': 'not separately represented',
            'interpretation': 'compound trusted-host selection; no unwilling-player claim'}))


if __name__ == '__main__':
    unittest.main()
