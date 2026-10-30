"""Follow-up acceptance candidates. Source declarations only; not locally run."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
import test_fling_native as BASE
import test_book_researcher_fields_crafting as CRAFT
import book_survivalist_fixture as FIX
import researcher_fields as R
import researcher_blend_contents as B
import item_containers as J
import items as I
import world_entities as W
import fling_move as FLING
import fling_consumables as F
import vitamin_moves as V
from engine import Rules, Engine, Combatant
from builder import build_trainer
from grid import Grid
from native_scenario_fixture import prepare_body
import glitch_bender as GLITCH
import trainer_feature_acquisition as T
import restorative_items as REST
import combat_timing as TIME


class FlingBlendFollowupTests(unittest.TestCase):
    setUpClass = classmethod(CRAFT.ResearcherFieldsCraftingTests.setUpClass.__func__)
    setup = CRAFT.ResearcherFieldsCraftingTests.setup
    trainer = CRAFT.ResearcherFieldsCraftingTests.trainer
    pokemon = CRAFT.ResearcherFieldsCraftingTests.pokemon
    hand = BASE.FlingNativeTests.hand
    cast = BASE.FlingNativeTests.cast
    launch = BASE.FlingNativeTests.launch

    def setUp(self):
        previous = self.rules.rulings
        self.rules.rulings = deepcopy(previous)
        self.addCleanup(setattr, self.rules, 'rulings', previous)
        self.setup(movement={'land': 5, 'power': 4}, movement_basis='current', power_basis='current')  # Fling hand observation needs an actual sheet Power
        self.a = self.t
        self.t = self.pokemon('이브이', 20, 'actual Blend recipient', pos=(2, 0), tutor_points=4)
        self.e.gm.set_move(self.a, FLING.SOURCE, reason='actual acquired Fling')

    def restore(self):
        self.e, index = FIX.restore(self.rules, self.e)
        self.a, self.t = index[self.a.entity_id], index[self.t.entity_id]

    def bottle(self, *, patch=False):
        self.a.spec['items'].update({'상처약': 1, '플러스파워': 1})
        first = '상처약'
        if patch:
            first = R.patch_cure(self.e, self.a, first, seconds=600, reason='actual Patch production')['patch']
        self.blend = R.medicinal_blend(self.e, self.a, first, '플러스파워',
                                      seconds=600, reason='actual native Blend production')['blend']
        uid = 'fixture/blend-bottle'
        W.register_object(self.e, uid, location=W.location_of(self.a), weight_kg=.1,
            reason='actual existing empty bottle', kind='item_instance', item_rule_id='item/빈병', owner_id=self.a.entity_id)
        I.equip_held(self.e, self.a, 'item/빈병', source_instance_id=uid)
        J.observe_empty(self.e, self.a, container_selection=uid, reason='actual emptiness inspected')
        self.portion = B.load(self.e, self.a, self.blend, container_selection=uid,
                              reason='actual crafted dose poured into bottle')['content_id']
        return uid

    def arm(self, uid):
        I.unregister_item(self.e, self.a, 'item/빈병')
        self.hand(uid=uid, rule='item/빈병')
        FIX.battle(self.e, self.a)

    def test_native_blend_hit_consumes_contents_and_preserves_carrier_for_landing(self):
        uid = self.bottle();self.restore();self.arm(uid)
        self.e.lose_hp(self.t, 30, source='gm/actual-fixture-injury')
        hp, stage = self.t.hp, self.t.stages['atk']
        actions = deepcopy((getattr(self.t, 'budget', None), getattr(self.t, '_action_history', None), getattr(self.t, 'pending_action_loss', None)))
        self.cast(uid)
        self.assertGreater(self.t.hp, hp)
        self.assertEqual(self.t.stages['atk'], min(6, stage + 2))
        self.assertEqual((getattr(self.t, 'budget', None), getattr(self.t, '_action_history', None), getattr(self.t, 'pending_action_loss', None)), actions)
        self.assertEqual(self.a.spec['items'][self.blend], 0)
        self.assertEqual(self.launch()['plan']['damage_base'], 0)
        self.assertEqual(self.launch()['consumer_result']['status'], 'consumed_contents')
        self.assertEqual(self.launch()['landing']['status'], 'pending')
        self.restore()
        obj = self.e._physical_objects[uid]
        self.assertEqual(obj['item_rule_id'], 'item/빈병')
        self.assertEqual(obj['owner_id'], self.a.entity_id)
        self.assertNotIn('consumed', obj)
        self.assertIsNone(obj[J.KEY]['current'])
        self.assertEqual(obj[J.KEY]['portions'][self.portion]['consumed_by'], self.t.entity_id)
        self.assertIsNone(B.profile(self.e, self.a, self.t, uid, {}))

    def test_miss_preserves_the_same_loaded_dose_and_native_quantity_receipt(self):
        uid = self.bottle();self.arm(uid)
        hp, stages = self.t.hp, deepcopy(self.t.stages)
        self.cast(uid, face=1);self.restore()
        obj = self.e._physical_objects[uid]
        self.assertEqual(obj[J.KEY]['current'], self.portion)
        self.assertEqual(obj[J.KEY]['portions'][self.portion]['status'], 'stored')
        self.assertEqual((self.t.hp, self.t.stages), (hp, stages))
        self.assertEqual(self.a.spec['items'][self.blend], 0)
        self.assertNotIn('consumer_result', self.launch())

    def test_patch_derived_blend_stays_extended_only_and_not_fling_intake(self):
        uid = self.bottle(patch=True)
        self.assertIsNone(F.profile(self.e, self.a, self.t, 'item/빈병', instance_id=uid))
        self.assertEqual(self.e._physical_objects[uid][J.KEY]['current'], self.portion)

    def test_duplicate_load_cannot_pay_with_a_recipe_or_empty_quantity(self):
        uid = self.bottle()
        before = deepcopy((self.a.spec, self.e._physical_objects))
        with self.assertRaisesRegex(ValueError, 'insufficient owned items'):
            B.load(self.e, self.a, self.blend, container_selection=uid, reason='no second produced dose')
        self.assertEqual(before, (self.a.spec, self.e._physical_objects))

    def test_unissued_blend_intake_cannot_spend_the_loaded_portion(self):
        uid = self.bottle();self.arm(uid)
        plan = F.profile(self.e, self.a, self.t, 'item/빈병', instance_id=uid)
        before = deepcopy((self.a.spec, self.t.spec, self.t.hp, self.e._physical_objects))
        with self.assertRaisesRegex(ValueError, 'unused Fling effect admission'):
            B.consume(self.e, self.a, self.t, 'unissued', plan)
        self.assertEqual(before, (self.a.spec, self.t.spec, self.t.hp, self.e._physical_objects))

    def test_removed_native_transfer_cannot_be_replaced_by_declared_contents(self):
        uid = self.bottle()
        self.a.spec[R.KEY]['blends'][self.blend]['bottled'].clear()
        with self.assertRaisesRegex(ValueError, 'actual native quantity transfer'):
            J.validate_world(self.e, W.actor_index(self.e))

    def test_declared_consumption_without_native_fling_cannot_survive_validation(self):
        uid = self.bottle()
        obj = self.e._physical_objects[uid]
        obj[J.KEY]['current'] = None
        obj[J.KEY]['portions'][self.portion].update(status='consumed',
            consumed_at=self.e.elapsed_seconds, consumed_by=self.t.entity_id)
        with self.assertRaisesRegex(ValueError, 'actual native Fling admission'):
            J.validate_world(self.e, W.actor_index(self.e))

    def test_saved_blend_recipient_cannot_be_rebound(self):
        uid = self.bottle();self.arm(uid);self.cast(uid);self.restore()
        self.e._physical_objects[uid][J.KEY]['portions'][self.portion]['fling']['target_id'] = self.a.entity_id
        with self.assertRaisesRegex(ValueError, 'actual native Fling admission|actual carrier/contents/recipient'):
            self.restore()

    def test_zero_stock_pp_up_returns_before_move_selection_and_changes_nothing(self):
        before = deepcopy((self.a.spec, self.t.spec, getattr(self.a, 'budget', None), self.e.rng.getstate()))
        self.assertEqual(V.consume(self.e, self.a, self.t, V.PP), (0, 0))
        self.assertEqual(before, (self.a.spec, self.t.spec, getattr(self.a, 'budget', None), self.e.rng.getstate()))

    def test_unbridged_battle_consumable_never_silently_becomes_other(self):
        for uid in ('item/꿈안개', 'item/벌레회피스프레이', 'item/연막탄'):
            with self.subTest(item=uid), self.assertRaisesRegex(ValueError, 'family native application'):
                F.profile(self.e, self.a, self.t, uid)


class FlingBlendCodeSuppressionTests(unittest.TestCase):
    """FLING-BLEND-CODE-1 regression. Source declaration only; not locally run.

    Core + Polygon profile so the Researcher crafting fixture and an actual Glitch
    Bender Code issuer share one scene. The recipient has an actual Object Not Found
    receipt when the native Blend lands: contents are paid, the Fling admission
    completes once, no heal/stage/X timing record is installed, and nothing becomes
    effective after Code expires inside the same encounter.
    """
    trainer = CRAFT.ResearcherFieldsCraftingTests.trainer
    pokemon = CRAFT.ResearcherFieldsCraftingTests.pokemon
    hand = BASE.FlingNativeTests.hand
    cast = BASE.FlingNativeTests.cast
    launch = BASE.FlingNativeTests.launch

    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset='polygon')

    def setUp(self):
        previous = self.rules.rulings
        self.rules.rulings = deepcopy(previous)
        self.addCleanup(setattr, self.rules, 'rulings', previous)
        self.e = Engine(self.rules, seed=20762128);self.e.grid = Grid(24, 16)
        self.a = self.trainer('actual Researcher', (0, 0), movement={'land': 5, 'power': 4}, movement_basis='current', power_basis='current')
        self.t = self.pokemon('이브이', 20, 'actual Blend recipient', pos=(2, 0), owner=self.a, tutor_points=4)
        self.e.gm.set_move(self.a, FLING.SOURCE, reason='actual acquired Fling')
        extra = {'movement': {'land': 6}, 'movement_basis': 'current', 'edges': ['feat/버그의-존재'], 'items': {}}
        self.g = Combatant(self.rules, build_trainer(self.rules, 'actual Code issuer', 40,
            {'hp': 300, 'atk': 20, 'def': 10, 'spa': 20, 'spd': 10, 'spe': 30}, moves=['move/몸통박치기'], abilities=[],
            pos=(2, 3), side='foes', skills={'집중': 6, '오컬트학': 6, '통찰': 6, '전투': 3, '육상': 3, '곡예': 3, '직감': 3}, extra=extra))
        self.e.gm.add_combatant(self.g)
        for actor in (self.a, self.t, self.g):
            prepare_body(self.e, actor, size=actor.spec.get('size') or '중형', offsets=[(0, 0)], reason='actual complete participant body')
        for feature in (GLITCH.CLASS, GLITCH.REALITY, GLITCH.CODE):
            choice = {'edition': 'supplement'}
            if feature == GLITCH.CLASS:choice['gm_permission'] = 'GM admits this actual campaign Glitch class'
            T.acquire_static(self.e, self.g, feature, acquisition_request_id=self.g.entity_id + '/' + feature, selection=choice)

    def restore(self):
        self.e, index = FIX.restore(self.rules, self.e)
        self.a, self.t, self.g = index[self.a.entity_id], index[self.t.entity_id], index[self.g.entity_id]

    def brew(self, first, x):
        self.a.spec['items'].update({first: 1, x: 1})
        self.blend = R.medicinal_blend(self.e, self.a, first, x, seconds=600, reason='actual native Blend production')['blend']
        uid = 'fixture/blend-bottle'
        W.register_object(self.e, uid, location=W.location_of(self.a), weight_kg=.1,
            reason='actual existing empty bottle', kind='item_instance', item_rule_id='item/빈병', owner_id=self.a.entity_id)
        I.equip_held(self.e, self.a, 'item/빈병', source_instance_id=uid)
        J.observe_empty(self.e, self.a, container_selection=uid, reason='actual emptiness inspected')
        self.portion = B.load(self.e, self.a, self.blend, container_selection=uid,
                              reason='actual crafted dose poured into bottle')['content_id']
        return uid

    def grip(self, uid):
        I.unregister_item(self.e, self.a, 'item/빈병')
        self.hand(uid=uid, rule='item/빈병')

    def code_then_fling(self, uid):
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.g, initiative_count=30)
        GLITCH.code_injection(self.e, self.g, self.t, 'object_not_found', fixed_accuracy=20)
        self.assertTrue(GLITCH.benefits_blocked(self.t))
        self.e.end_of_turn(self.g)
        self.e.start_of_turn(self.a, initiative_count=20)
        return self.cast(uid)

    def x_records(self):
        return [row for row in TIME.records(self.t) if row.get('x_item')]

    def valid(self):
        result = self.e.validate_state()
        self.assertTrue(result['valid'], result['issues'])

    def test_code_recipient_blend_pays_contents_without_present_or_deferred_x_benefit(self):
        cases = (('item/상처약', 'item/크리티컬-커터'), ('item/상처약', 'item/이펙트가드'), ('item/힘의가루', 'item/크리티컬-커터'))
        for n, (first, x) in enumerate(cases):
            with self.subTest(first=first, x=x):
                if n:self.setUp()
                uid = self.brew(first, x);self.restore();self.grip(uid)
                self.e.lose_hp(self.t, 30, source='gm/actual-fixture-injury')
                hp, stages = self.t.hp, deepcopy(self.t.stages)
                actions = deepcopy((getattr(self.t, 'budget', None), getattr(self.t, '_action_history', None), getattr(self.t, 'pending_action_loss', None)))
                self.code_then_fling(uid)
                # Contents paid once; the native Fling admission completed; bottle awaits landing.
                self.assertEqual(self.a.spec['items'][self.blend], 0)
                launch = self.launch();result = launch['consumer_result']
                self.assertEqual(result['status'], 'consumed_contents')
                self.assertEqual([list(row) for row in result['result']], [[0, 0], [0, 0]])
                self.assertEqual(launch['landing']['status'], 'pending')
                obj = self.e._physical_objects[uid];portion = obj[J.KEY]['portions'][self.portion]
                self.assertEqual(portion['status'], 'consumed');self.assertIsNone(obj[J.KEY]['current']);self.assertNotIn('consumed', obj)
                self.assertEqual(portion['benefit_suppression'], {'source': GLITCH.CODE, 'target_id': self.t.entity_id, 'at': portion['consumed_at']})
                # No benefit now: no heal, no stage change, no X timing record, no recipient debt.
                self.assertEqual((self.t.hp, self.t.stages), (hp, stages))
                self.assertEqual(self.x_records(), []);self.assertEqual(REST.crit_delta(self.t), 0)
                self.assertEqual((getattr(self.t, 'budget', None), getattr(self.t, '_action_history', None), getattr(self.t, 'pending_action_loss', None)), actions)
                if first == 'item/힘의가루':
                    herbal = self.t.spec['herbal_restoratives']
                    self.assertEqual(herbal['count'], 1);self.assertIsNone(herbal['uses'][-1]['buff_id'])
                # Restore while Code is active, then expire Code within the same encounter.
                self.restore();self.valid()
                self.assertTrue(GLITCH.code_rows(self.t, 'object_not_found'))
                self.e.end_of_turn(self.a);self.e.end_round();self.e.start_round(self.e.everyone);self.e.at_initiative_count(30)
                self.assertFalse(GLITCH.code_rows(self.t))
                # Nothing deferred becomes effective after expiry.
                self.assertEqual(self.x_records(), []);self.assertEqual(REST.crit_delta(self.t), 0)
                self.assertFalse(REST.blocks_stage_loss(self.e, self.t, -1))
                self.assertEqual((self.t.hp, self.t.stages), (hp, stages))
                self.restore();self.valid()

    def test_forged_suppression_recipient_cannot_survive_restore(self):
        uid = self.brew('item/상처약', 'item/크리티컬-커터');self.restore();self.grip(uid)
        self.code_then_fling(uid);self.restore()
        portion = self.e._physical_objects[uid][J.KEY]['portions'][self.portion]
        portion['benefit_suppression']['target_id'] = self.a.entity_id
        with self.assertRaisesRegex(ValueError, 'actual Object Not Found recipient'):
            self.restore()

    def test_blend_without_code_still_installs_its_actual_x_benefit(self):
        uid = self.brew('item/상처약', 'item/크리티컬-커터');self.restore();self.grip(uid)
        self.e.lose_hp(self.t, 30, source='gm/actual-fixture-injury');hp = self.t.hp
        self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a, initiative_count=20)
        self.cast(uid)
        self.assertGreater(self.t.hp, hp);self.assertEqual(REST.crit_delta(self.t), 2)
        self.assertEqual(len(self.x_records()), 1)
        portion = self.e._physical_objects[uid][J.KEY]['portions'][self.portion]
        self.assertNotIn('benefit_suppression', portion);self.restore();self.valid()


if __name__ == '__main__':unittest.main()
