"""Candidate observations: a PASS reproduces the named state, not a repaired guarantee."""
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


class CandidateReview05Tests(unittest.TestCase):
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

    def two_native_saves(self, engine, wearer_id, other_id, instance_id, issued):
        index = WORLD.actor_index(engine)
        wearer, other = index[wearer_id], index[other_id]
        physical_history = deepcopy(engine._physical_objects[instance_id][FASHION.STATE]['history'])
        self.assertEqual(physical_history, [issued])
        self.assertEqual(other.spec['fashion_next_save']['activation_receipt']['wearer_id'], wearer_id)
        before_uses = deepcopy(FREQUENCY.state(wearer)['activations'])
        foreign = RECOVERY.saving_check(engine, other, None, 8, fixed=5)
        original = RECOVERY.saving_check(engine, wearer, None, 8, fixed=5)
        self.assertEqual((foreign['fashion_bonus'], original['fashion_bonus']), (4, 4))
        self.assertTrue(foreign['passed'] and original['passed'])
        self.assertEqual(engine._physical_objects[instance_id][FASHION.STATE]['history'], physical_history)
        self.assertEqual(FREQUENCY.state(wearer)['activations'], before_uses)
        self.assertEqual(RECOVERY.saving_check(engine, other, None, 8, fixed=5)['fashion_bonus'], 0)
        self.assertEqual(RECOVERY.saving_check(engine, wearer, None, 8, fixed=5)['fashion_bonus'], 0)
        print('OE_C01_REPRODUCTION', json.dumps({'single_native_activation': len(physical_history),
            'native_bonus_consumers': [other_id, wearer_id], 'bonuses': [4, 4],
            'source_history_unchanged': True, 'purpose': 'defect confirmation, not repair acceptance'}))

    def test_valid_cool_fashion_lingers_after_unequip_and_consumes_once(self):
        fixture, instance_id, issued = self.fashion()
        ITEMS.unregister_item(fixture.e, fixture.p, 'item/근사한-패션-1')
        loaded = Engine.import_state(fixture.rules, json.loads(json.dumps(fixture.e.export_state())))
        wearer = WORLD.actor_index(loaded)[fixture.p.entity_id]
        self.assertNotIn('equipped_by', loaded._physical_objects[instance_id])
        self.assertEqual(loaded._physical_objects[instance_id][FASHION.STATE]['history'], [issued])
        self.assertEqual(RECOVERY.saving_check(loaded, wearer, None, 8, fixed=5)['fashion_bonus'], 4)
        self.assertEqual(RECOVERY.saving_check(loaded, wearer, None, 8, fixed=5)['fashion_bonus'], 0)

    def test_probe_codec_copies_one_native_activation_to_an_unrelated_save_recipient(self):
        fixture, instance_id, issued = self.fashion()
        payload = json.loads(json.dumps(fixture.e.export_state()))
        original = deepcopy(payload)
        wearer_spec = self.spec_items(payload, fixture.p.entity_id)
        other_spec = self.spec_items(payload, fixture.q.entity_id)
        actual_pending = next(value for key, value in wearer_spec if key == 'fashion_next_save')
        self.assertFalse(any(key == 'fashion_next_save' for key, _ in other_spec))
        other_spec.append(['fashion_next_save', deepcopy(actual_pending)])
        loaded = Engine.import_state(fixture.rules, payload)
        self.assertEqual(fixture.e.export_state(), original)
        self.two_native_saves(loaded, fixture.p.entity_id, fixture.q.entity_id, instance_id, issued)

    def test_probe_gm_checkpoint_copies_one_native_activation_to_an_unrelated_save_recipient(self):
        fixture, instance_id, issued = self.fashion()
        fixture.e.gm.snapshot('one-native-fashion-activation')
        snapshot = fixture.e.gm.snapshots['one-native-fashion-activation']
        source_spec = snapshot['combatants'][id(fixture.p)]['spec']
        receiver_spec = snapshot['combatants'][id(fixture.q)]['spec']
        self.assertNotIn('fashion_next_save', receiver_spec)
        receiver_spec['fashion_next_save'] = deepcopy(source_spec['fashion_next_save'])
        fixture.e.gm.restore('one-native-fashion-activation', reason='probe inconsistent derived receipt')
        self.two_native_saves(fixture.e, fixture.p.entity_id, fixture.q.entity_id, instance_id, issued)

    def test_probe_compound_host_handoff_requires_selection_but_accepts_protected_leek_replacement(self):
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
