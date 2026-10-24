"""Q23 real Pickup selection, producing interpretation and physical lifecycle."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'engine'))
from engine import Rules, Engine
from tools import test_category2_pickup_item_copy as BASE
import pickup_item_copy as PICKUP
import held_equipment as HELD
import items as ITEMS
import world_entities as WORLD
import effects_ext


class PickupSourceInterpretationRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        BASE.PickupItemCopyTests.setUpClass()

    def setUp(self):
        self.base = BASE.PickupItemCopyTests()

    def state(self, engine, user, target):
        return deepcopy((user.spec, ('budget' in vars(user), vars(user).get('budget')),
                         target.spec, ('budget' in vars(target), vars(target).get('budget')),
                         engine._physical_objects, engine.log_lines, engine.rng.getstate()))

    def decision(self, engine, user, target, interpretation, selection='original', destination_slot=None):
        query = engine.pickup_source_choices(user, target, held_selection=selection,
                                              destination_slot=destination_slot)
        self.assertEqual(query['status'], 'PolicyInputsRequired')
        return {'value': interpretation, 'reason': 'actual current Q23 consumption-subject ruling',
                'scope': query['decision_scope']}

    def dual(self, ability='배달부', user_abilities=('픽업',)):
        engine, user, target = self.base.fixture(item=None, user_abilities=user_abilities,
                                                target_abilities=(ability,))
        self.base.add(engine, target, '예리한손톱', 'first', 'held:1')
        self.base.add(engine, target, '상처약', 'second', 'held:2')
        return engine, user, target

    def consume(self, engine, user, copy_id):
        user.hp -= 10
        injured = user.hp
        self.assertTrue(engine.use_item(user, '상처약', target=user, held_selection=copy_id))
        self.assertGreater(user.hp, injured)
        self.assertEqual(engine._physical_objects[copy_id]['consumed']['source'], 'item/상처약')
        self.assertEqual((user.budget['standard'], user.budget['shift']), (0, 0))

    def test_real_consumed_copy_distinguishes_both_scoped_readings_and_current_protection(self):
        for interpretation, explicit, sticky in [('copy_unconsumed', False, False),
                ('copy_unconsumed', True, False), ('original_unconsumed', True, False),
                ('original_unconsumed', True, True)]:
            with self.subTest(interpretation=interpretation, explicit=explicit, sticky=sticky):
                engine, user, target = self.base.fixture(item='상처약',
                    target_abilities=('점착',) if sticky else ())
                choice = self.decision(engine, user, target, interpretation) if explicit else None
                receipt = engine.activate_ability(user, '픽업', target, pickup_expiry_choice=choice)
                self.assertEqual(receipt['expiry_decision']['interpretation'], interpretation)
                self.assertEqual(user.budget['swift'], 0)
                self.consume(engine, user, receipt['copy_instance_id'])
                original = deepcopy(engine._physical_objects['original'])
                engine.end_encounter([user, target])
                history = user.spec[PICKUP.HISTORY][0]
                if interpretation == 'original_unconsumed' and not sticky:
                    self.assertIn('destroyed', engine._physical_objects['original'])
                    self.assertEqual(history['original_terminal'], 'destroyed')
                else:
                    self.assertEqual(engine._physical_objects['original'], original)
                    self.assertEqual(history['original_terminal'],
                        'retained_protected' if sticky else 'retained_copy_consumed')
                self.assertEqual(history['copy_terminal'], 'consumed')
                self.base.valid(engine)

    def test_actual_two_held_owner_selects_before_one_payment_even_with_user_supplied_id(self):
        for ability in ('배달부', '배달새'):
            with self.subTest(ability=ability):
                engine, user, target = self.dual(ability)
                before_objects = deepcopy(engine._physical_objects)
                before_budget = deepcopy(user.budget)
                before_frequency = deepcopy(user.spec.get('frequency_state'))
                pending = engine.activate_ability(user, '픽업', target, held_selection='first')
                choice_id = pending.basis['choice_id']
                self.assertEqual(pending.basis['chooser_id'], target.entity_id)
                self.assertEqual(engine._physical_objects, before_objects)
                self.assertEqual(user.budget, before_budget)
                self.assertEqual(user.spec.get('frequency_state'), before_frequency)
                self.assertNotIn(PICKUP.ACTIVE, user.spec)
                before = self.state(engine, user, target)
                with self.assertRaisesRegex(ValueError, 'owner must choose'):
                    engine.resolve_pickup_choice(user, choice_id, selection='first')
                self.assertEqual(self.state(engine, user, target), before)
                result = engine.resolve_pickup_choice(target, choice_id, selection='second')
                self.assertEqual(result['original_instance_id'], 'second')
                self.assertEqual(engine._physical_objects[result['copy_instance_id']]['item_rule_id'], 'item/상처약')
                self.assertEqual({row['instance_id'] for row in HELD.entries(target)}, {'first', 'second'})
                self.assertEqual(user.budget['swift'], before_budget['swift'] - 1)
                self.assertEqual(user.spec['frequency_state']['activations']['ability:픽업']['used'], 1)
                paid = self.state(engine, user, target)
                self.assertEqual(engine.resolve_pickup_choice(target, choice_id, selection='second'), result)
                self.assertEqual(self.state(engine, user, target), paid)
                with self.assertRaisesRegex(ValueError, 'cannot change'):
                    engine.resolve_pickup_choice(target, choice_id, selection='first')
                self.assertEqual(self.state(engine, user, target), paid)
                self.base.valid(engine)

    def test_stale_held_request_and_late_copy_failure_preserve_unpaid_state_then_settle(self):
        engine, user, target = self.dual()
        old = engine.activate_ability(user, '픽업', target)
        ITEMS.drop_item(engine, target, selection='first')
        before = self.state(engine, user, target)
        with self.assertRaisesRegex(ValueError, 'stale'):
            engine.resolve_pickup_choice(target, old.basis['choice_id'], selection='second')
        self.assertEqual(self.state(engine, user, target), before)
        engine.cancel_pickup_choice(user, old.basis['choice_id'])
        self.base.add(engine, target, '선제공격손톱', 'replacement', 'held:1')
        current = engine.activate_ability(user, '픽업', target)
        self.assertNotEqual(current.basis['choice_id'], old.basis['choice_id'])
        before = self.state(engine, user, target)
        with self.assertRaisesRegex(ValueError, 'request required'):
            engine.resolve_pickup_choice(target, old.basis['choice_id'], selection='second')
        self.assertEqual(self.state(engine, user, target), before)
        real = effects_ext.h_copy_item
        def fail_after_native_copy(*args, **kwargs):
            real(*args, **kwargs)
            raise ValueError('actual late copy registration witness')
        with patch.object(effects_ext, 'h_copy_item', side_effect=fail_after_native_copy):
            with self.assertRaisesRegex(ValueError, 'late copy registration'):
                engine.resolve_pickup_choice(target, current.basis['choice_id'], selection='second')
        self.assertEqual(self.state(engine, user, target), before)
        self.assertEqual(user.spec[PICKUP.CHOICE]['status'], 'awaiting_input')
        result = engine.resolve_pickup_choice(target, current.basis['choice_id'], selection='second')
        self.assertEqual(result['original_instance_id'], 'second')
        self.assertEqual(user.spec['frequency_state']['activations']['ability:픽업']['used'], 1)
        self.base.valid(engine)

    def test_pending_holder_and_producing_scope_survive_gm_and_fresh_rules_restore(self):
        engine, user, target = self.dual(user_abilities=('픽업', '배달부'))
        self.base.add(engine, user, '선제공격손톱', 'own-existing', 'held:1')
        choice = self.decision(engine, user, target, 'original_unconsumed', 'second', 'held:2')
        pending = engine.activate_ability(user, '픽업', target, destination_slot='held:2',
                                          pickup_expiry_choice=choice)
        engine.gm.snapshot('q23-unpaid-holder')
        engine.resolve_pickup_choice(target, pending.basis['choice_id'], selection='second')
        engine.gm.restore('q23-unpaid-holder', reason='actual unpaid Pickup decision rewind')
        fresh = Rules(ROOT, ruleset='core')
        loaded = Engine.import_state(fresh, json.loads(json.dumps(engine.export_state())))
        index = WORLD.actor_index(loaded)
        actual_user, actual_target = index[user.entity_id], index[target.entity_id]
        self.assertEqual(loaded.pending_pickup_choices()[0].basis['chooser_id'], actual_target.entity_id)
        result = loaded.resolve_pickup_choice(actual_target, pending.basis['choice_id'], selection='second')
        self.assertEqual(result['destination_slot'], 'held:2')
        self.assertEqual(result['expiry_decision']['choice'], choice)
        # An unrelated current profile annotation cannot rewrite the original producing scope.
        loaded.r.ruleset.profile['q23_history_annotation'] = 'unrelated current campaign note'
        self.base.valid(loaded)
        self.assertEqual(result['expiry_decision']['choice']['scope'], choice['scope'])
        self.consume(loaded, actual_user, result['copy_instance_id'])
        loaded.end_encounter(list(index.values()))
        self.assertIn('destroyed', loaded._physical_objects['second'])
        history_rules = Rules(ROOT, ruleset='core')
        history_rules.ruleset.profile['q23_history_annotation'] = 'unrelated current campaign note'
        restored = Engine.import_state(history_rules, json.loads(json.dumps(loaded.export_state())))
        saved = WORLD.actor_index(restored)[user.entity_id].spec[PICKUP.HISTORY][0]
        self.assertEqual(saved['expiry_decision'], result['expiry_decision'])
        self.assertEqual(saved['original_terminal'], 'destroyed')
        self.base.valid(restored)

    def test_source_scope_refusal_and_exact_legacy_optional_shape_keep_old_copy_history(self):
        engine, user, target = self.base.fixture(item='상처약')
        choice = self.decision(engine, user, target, 'original_unconsumed')
        wrong = deepcopy(choice)
        wrong['scope']['definition_hash'] = 'different actual original/copy scope'
        before = self.state(engine, user, target)
        with self.assertRaisesRegex(ValueError, 'scope changed'):
            engine.activate_ability(user, '픽업', target, pickup_expiry_choice=wrong)
        self.assertEqual(self.state(engine, user, target), before)
        receipt = engine.activate_ability(user, '픽업', target)
        copy_id = receipt['copy_instance_id']
        # Exact older producer shape: both real linked records lacked this new optional field.
        del user.spec[PICKUP.ACTIVE][0]['expiry_decision']
        del engine._physical_objects[copy_id]['pickup_copy']['expiry_decision']
        loaded = Engine.import_state(Rules(ROOT, ruleset='core'), json.loads(json.dumps(engine.export_state())))
        index = WORLD.actor_index(loaded)
        actual_user = index[user.entity_id]
        self.assertNotIn('expiry_decision', actual_user.spec[PICKUP.ACTIVE][0])
        self.consume(loaded, actual_user, copy_id)
        loaded.end_encounter(list(index.values()))
        self.assertNotIn('destroyed', loaded._physical_objects['original'])
        old = actual_user.spec[PICKUP.HISTORY][0]
        self.assertNotIn('expiry_decision', old)
        self.assertEqual(old['original_terminal'], 'retained_copy_consumed')
        completed = Engine.import_state(Rules(ROOT, ruleset='core'), json.loads(json.dumps(loaded.export_state())))
        self.assertEqual(WORLD.actor_index(completed)[user.entity_id].spec[PICKUP.HISTORY][0], old)
        self.base.valid(completed)


if __name__ == '__main__':
    unittest.main()
