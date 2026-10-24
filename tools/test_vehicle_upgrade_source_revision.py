"""Source-classified upgrade caps and retained complete alloy definitions."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
import test_category2_vehicle_native as FIX
import native_scenario_fixture as SCENARIO
import vehicle_native as N
import special_entities as S
import control_vehicle as CONTROL
import crafting_recipes as Q
import world_entities as W
from engine import Rules
from state_codec import dump_engine, load_engine, StateCodecError


class VehicleUpgradeSourceRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.poly = Rules(str(ROOT), ruleset='polygon')

    trainer = FIX.NativeVehicleTests.trainer
    setUp = FIX.NativeVehicleTests.setUp
    register = FIX.NativeVehicleTests.register
    snap = FIX.NativeVehicleTests.snap
    breach = FIX.NativeVehicleTests.breach
    hit = FIX.NativeVehicleTests.hit
    start = FIX.NativeVehicleTests.start
    move = FIX.NativeVehicleTests.move
    policy = FIX.NativeVehicleTests.policy

    def purchase(self, upgrade, identity='car', ordinal=1, choice=None):
        return N.acquire_upgrade(self.e, self.a, identity, upgrade,
            request_id=upgrade + '/' + str(ordinal), reason='actual sourced upgrade purchase',
            source_choice=choice)

    def choice(self, variant):
        prepared = N.reinforced_alloys_choices(self.e)
        return {'value': variant, 'reason': 'explicit selection of this complete source definition',
                'scope': prepared['decision_scope']}

    def test_actual_size_prices_caps_and_replay_reject_before_any_payment(self):
        for template, prices in (
            ('personal', (1500, 5000, 3000, 500)),
            ('basic', (2250, 7500, 4000, 750)),
            ('large', (3000, 10000, 5000, 1000)),
        ):
            row = self.register(template, template, occupied=False)
            original_speed = row['overland']
            for (upgrade, cap), price in zip((('breach_resistance', 1), ('reinforced_alloys', 1),
                                             ('shield_generator', 1), ('vehicle_speed', 2)), prices):
                for ordinal in range(1, cap + 1):
                    money = self.a.spec['money']
                    result = self.purchase(upgrade, template, ordinal)
                    self.assertEqual((result['count'], result['cost'], money - self.a.spec['money']),
                                     (ordinal, price, price))
                before = self.snap()
                with patch.object(Q, 'prepare_materials', side_effect=AssertionError('payment reached')):
                    self.assertEqual(result, self.purchase(upgrade, template, cap))
                    SCENARIO.assert_rejected_unchanged(self.e,
                        lambda: self.purchase(upgrade, template, cap + 1),
                        reason_pattern='exceeds sourced rank or single-purchase limit')
                self.assertEqual(before, self.snap())
            self.assertEqual(row['overland'], original_speed + 2)
            self.assertEqual((row['breach_security'], row['breach_capacity']),
                             {'personal': (2, 5), 'basic': (3, 6), 'large': (4, 8)}[template])
            self.assertEqual(N.begin_scene(self.e, self.a, template)['temporary_hp'],
                             {'personal': 20, 'basic': 40, 'large': 60}[template])

    def test_second_speed_rank_reaches_all_modes_and_paid_native_control(self):
        quotes = [dict(id='mode/' + mode, kind='movement', operation='add', mode=mode,
                       cost=1000, reason='actual movement customization')
                  for mode in ('swim', 'levitate', 'sky')]
        row = self.register(modifications=quotes)
        self.purchase('vehicle_speed', ordinal=1); self.purchase('vehicle_speed', ordinal=2)
        self.assertEqual(CONTROL.body_view(row)['machine_movement'],
                         {'land': 9, 'swim': 9, 'levitate': 9, 'sky': 9})
        self.start(); result = self.move()
        self.assertEqual((result['remaining'], row['location']['cell'], self.a.pos, self.a.budget['standard']),
                         (7, (3, 1), (3, 1), 0))

    def test_native_config_admission_rejects_every_over_cap_count_unchanged(self):
        row = self.register(occupied=False)
        for upgrade, cap in (('structural_integrity', 3), ('armored_plating', 2),
                             ('breach_resistance', 1), ('reinforced_alloys', 1),
                             ('shield_generator', 1), ('vehicle_speed', 2)):
            proposed = deepcopy(row); config = proposed['native_vehicle']['config']
            config['upgrades'][upgrade] = cap + 1
            proposed['native_vehicle']['config'] = N._sign({k: v for k, v in config.items() if k != 'sha256'})
            SCENARIO.assert_rejected_unchanged(self.e,
                lambda: S.observe(self.e, proposed, reason='attempted over-cap native configuration'),
                reason_pattern='exceeds sourced rank or single-purchase limit')

    def test_legacy_over_cap_paid_record_requires_reconstruction_without_coercion_or_refund(self):
        row = self.register(template='personal', occupied=False)
        self.purchase('shield_generator')
        native = row['native_vehicle']
        # Model a pre-fix saved second purchase, including the actual old payment.
        receipt = deepcopy(native['upgrades']['shield_generator/1'])
        receipt['result']['count'] = 2
        native['upgrades']['shield_generator/2'] = N._sign({k: v for k, v in receipt.items() if k != 'sha256'})
        config = native['config']; config['upgrades']['shield_generator'] = 2
        native['config'] = N._sign({k: v for k, v in config.items() if k != 'sha256'})
        self.a.spec['money'] -= 3000
        before = (deepcopy(self.e._physical_objects), deepcopy(self.a.spec), self.e.rng.getstate())
        with self.assertRaisesRegex(ValueError, 'over-cap legacy records require explicit reconstruction'):
            N.validate_record(self.e, row)
        with self.assertRaises(StateCodecError):
            dump_engine(self.e)
        self.assertEqual(before, (self.e._physical_objects, self.a.spec, self.e.rng.getstate()))
        self.assertEqual(native['config']['upgrades']['shield_generator'], 2)
        self.assertEqual(self.a.spec['money'], 94000)

    def test_both_complete_alloy_definitions_and_legacy_default_survive_restore_and_replay(self):
        choices = {'legacy': None, 'korean': self.choice('korean_ground'), 'english': self.choice('english_grass')}
        results = {}
        for identity, choice in choices.items():
            row = self.register(identity, 'personal', occupied=False)
            results[identity] = self.purchase('reinforced_alloys', identity, choice=choice)
            self.assertEqual(results[identity]['cost'], 5000)
            expected_types = [('노말', [1, 2]), ('격투', [1, 2]), ('얼음', [1, 2]), ('바위', [1, 2]),
                              ('땅', [3, 2] if identity == 'english' else [1, 1]),
                              ('풀', [1, 2] if identity == 'english' else [1, 1]), ('독', [0, 1])]
            for kind, multiplier in expected_types:
                result = self.hit(8, identity=identity, kind=kind, event=kind)
                self.assertEqual(result['type_multiplier'], multiplier, (identity, kind))
            self.assertEqual(row['hp'], 48)
        self.assertNotIn('source_policy', results['legacy'])
        self.assertEqual(results['english']['definition_clause_id'], 'do-porygon:1450')
        saved = self.snap(); self.e.gm.snapshot('alloy-sources')
        self.e.gm.set_hp(self.a, value=1, reason='later actor damage'); self.e.gm.restore('alloy-sources')
        for engine in (self.e, load_engine(self.poly, json.loads(json.dumps(saved, ensure_ascii=False)))):
            actor = W.actor_index(engine)[self.a.entity_id]
            for identity, choice in choices.items():
                before = dump_engine(engine)
                result = N.acquire_upgrade(engine, actor, identity, 'reinforced_alloys',
                    request_id='reinforced_alloys/1', reason='actual sourced upgrade purchase', source_choice=choice)
                self.assertEqual(result, results[identity]); self.assertEqual(before, dump_engine(engine))
                replay = N.hit(engine, actor, identity, move_type='독', after_defense=8,
                    passenger_after_defense={}, event_id='독', reason='actual typed attack resolved against vehicle',
                    breach_policy=self.breach())
                self.assertEqual(replay['type_multiplier'], [0, 1]); self.assertEqual(before, dump_engine(engine))

    def test_source_choice_is_scoped_and_atomic_and_cannot_change_completed_intent(self):
        row = self.register(template='personal', occupied=False)
        choice = self.choice('english_grass'); changed = deepcopy(choice)
        changed['scope']['definition_hash'] = 'changed'
        SCENARIO.assert_rejected_unchanged(self.e,
            lambda: self.purchase('reinforced_alloys', choice=changed), reason_pattern='GM decision scope changed')
        SCENARIO.assert_rejected_unchanged(self.e,
            lambda: self.purchase('shield_generator', choice=choice), reason_pattern='only Reinforced Alloys')
        original = Q.pay_materials; before = self.snap()
        def late_failure(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError('late alloy payment failure')
        with patch.object(Q, 'pay_materials', side_effect=late_failure):
            with self.assertRaisesRegex(RuntimeError, 'late alloy payment failure'):
                self.purchase('reinforced_alloys', choice=choice)
        self.assertEqual(before, self.snap())
        self.purchase('reinforced_alloys', choice=choice)
        SCENARIO.assert_rejected_unchanged(self.e,
            lambda: self.purchase('reinforced_alloys', choice=self.choice('korean_ground')),
            reason_pattern='request changed intent')
        receipt = row['native_vehicle']['upgrades']['reinforced_alloys/1']
        receipt['result']['source_policy']['values']['definitions']['english_grass']['resist'] = ['땅']
        row['native_vehicle']['upgrades']['reinforced_alloys/1'] = N._sign({k: v for k, v in receipt.items() if k != 'sha256'})
        with self.assertRaisesRegex(ValueError, 'retained Reinforced Alloys source decision changed'):
            N.validate_record(self.e, row)


if __name__ == '__main__':
    unittest.main()
