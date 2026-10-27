"""Printed Pester Ball identity and Pickup categories through native actions."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

import test_core_pester_balls as PESTER_FIX
import test_category2_csv_remaining_item_contracts as CSV_FIX
import csv_item_capability_contracts as CAP
import csv_item_physical_contracts as PHYSICAL
import pester_balls as PESTER
import native_scenario_fixture as NATIVE
import state_codec as CODEC
import common_checks as C
import resolution_transaction as TX
import world_entities as WORLD
import items as ITEMS


class CannonItemIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        PESTER_FIX.Tests.setUpClass()

    def scene(self, *, loaded=True, source='item/오물탄-잠듦'):
        f=PESTER_FIX.Tests();f.setUp();f.ready(source)
        f.held(f.a,source,'cannon/pester')
        equipment=CSV_FIX.RemainingCsvItemContractTests()
        equipment.equip(f.e,f.a,'cannon/body','item/몬스터볼-캐논',held=False)
        f.t.pos=(16,3)
        if loaded:
            before=f.a.budget['shift']
            self.assertTrue(PHYSICAL.load_cannon(f.e,f.a,'cannon/body','cannon/pester')['loaded'])
            self.assertEqual(f.a.budget['shift'],before-1)
        return f

    def test_loaded_pester_native_accuracy_range_damage_payment_and_hour(self):
        f=self.scene();before=f.t.hp;quantity=f.a.spec['items']['item/오물탄-잠듦']
        with patch.object(type(f.e),'accuracy_check',autospec=True,
                          side_effect=type(f.e).accuracy_check) as accuracy:
            result=f.use(held_selection='cannon/pester')
        self.assertTrue(result['hit'])
        self.assertEqual(accuracy.call_count,1)
        staged,user,target=accuracy.call_args.args[:3]
        self.assertIsNot(staged,f.e)
        self.assertEqual((user.entity_id,target.entity_id),(f.a.entity_id,f.t.entity_id))
        self.assertEqual(accuracy.call_args.kwargs['situational'],1)
        cannon=result['cannon']
        self.assertEqual((cannon['range_m'],cannon['fixed_damage']),(15,'2d6'))
        self.assertEqual(before-f.t.hp,cannon['damage']['requested'])
        self.assertEqual(sum(cannon['damage']['faces']),cannon['damage']['requested'])
        self.assertEqual(len(cannon['damage']['faces']),2)
        self.assertEqual(result['payment']['instance_id'],'cannon/pester')
        self.assertEqual(f.a.spec['items']['item/오물탄-잠듦'],quantity)
        self.assertIn('consumed',f.e._physical_objects['cannon/pester'])
        self.assertIsNone(f.e._physical_objects['cannon/body'][PHYSICAL.OBJECT_STATE]['loaded_ball_instance_id'])
        self.assertEqual(f.a.budget['standard'],0)
        self.assertTrue(result['status_applied']);self.assertTrue(PESTER.projection(f.e,f.t)['immune'])
        restored=CODEC.load_engine(f.r,json.loads(json.dumps(CODEC.dump_engine(f.e))))
        target=WORLD.actor_index(restored)[f.t.entity_id]
        self.assertTrue(PESTER.projection(restored,target)['immune'])

    def test_unloaded_or_withdrawn_cannon_does_not_extend_hand_throw(self):
        f=self.scene(loaded=False)
        NATIVE.assert_rejected_unchanged(f.e,lambda:f.use(held_selection='cannon/pester'),
                                       reason_pattern='throwing range')
        PHYSICAL.load_cannon(f.e,f.a,'cannon/body','cannon/pester')
        ITEMS.unregister_item(f.e,f.a,'item/몬스터볼-캐논')
        NATIVE.assert_rejected_unchanged(f.e,lambda:f.use(held_selection='cannon/pester'),
                                       reason_pattern='equipped Pokeball Cannon')

    def test_loaded_pester_rejects_beyond_fifteen_metres_before_payment(self):
        f=self.scene();f.t.pos=(17,3)
        NATIVE.assert_rejected_unchanged(f.e,lambda:f.use(held_selection='cannon/pester'),
                                       reason_pattern='throwing range')

    def test_miss_consumes_loaded_pester_once_without_damage_or_immunity(self):
        f=self.scene();before=f.t.hp
        result=f.use(natural=1,held_selection='cannon/pester')
        self.assertFalse(result['hit']);self.assertEqual(f.t.hp,before)
        self.assertNotIn('damage',result['cannon']);self.assertFalse(result['immunity_started'])
        self.assertIn('consumed',f.e._physical_objects['cannon/pester'])
        self.assertIsNone(f.e._physical_objects['cannon/body'][PHYSICAL.OBJECT_STATE]['loaded_ball_instance_id'])

    def test_exact_loaded_source_and_single_loading_reject_before_payment(self):
        f=self.scene();equipment=CSV_FIX.RemainingCsvItemContractTests()
        equipment.physical(f.e,f.a,'cannon/not-ball','item/몬스터볼-캐논')
        NATIVE.assert_rejected_unchanged(f.e,
            lambda:PHYSICAL.load_cannon(f.e,f.a,'cannon/body','cannon/not-ball'),reason_pattern='only an actual selected')
        NATIVE.assert_rejected_unchanged(f.e,
            lambda:PHYSICAL.cannon_profile(f.e,f.a,'cannon/body',projectile='sludge_bomb'),reason_pattern='only Poke Ball and Pester Ball')
        NATIVE.assert_rejected_unchanged(f.e,
            lambda:f.use('item/오물탄-독',held_selection='cannon/pester'),reason_pattern='another rule')
        # Loading is tied to this physical body, rather than its name or inventory count.
        NATIVE.assert_rejected_unchanged(f.e,
            lambda:PHYSICAL.load_cannon(f.e,f.a,'cannon/body','cannon/pester'),reason_pattern='two Cannons')

    def test_equipped_cannon_generated_weapon_is_source_admitted_before_first_read(self):
        f=self.scene()
        keys=[row['struggle_id'] for row in f.a.custom_conditions['equipped_weapons'].values()]
        self.assertTrue(keys)
        self.assertTrue(all(key in f.r.selection.units for key in keys))
        before=CODEC.rules_fingerprint(f.r)
        for key in keys:
            self.assertEqual(f.r.move(key)['id'],key)
            self.assertEqual(f.r.selection.dependencies[key],('combat/struggle','ch09-equipment/장비/무기'))
        self.assertEqual(CODEC.rules_fingerprint(f.r),before)

    def test_generated_weapon_catalog_and_graph_rollback_after_local_and_outer_late_failure(self):
        import turn as TURN, state_grants as GRANTS, optional_weapon_framework as FRAMEWORK
        for route in ('local','outer'):
            with self.subTest(route=route):
                f=self.scene(loaded=False)
                weapon={'name':'late published foot weapon','kind':'발 무기','grade':'조잡','moves':[]}
                before=f.e.export_state()
                before_keys=(set(f.r.moves),set(f.r.moves_mech),set(f.r.selection.units))
                if route=='local':
                    original=FRAMEWORK.on_equip
                    def fail(*args,**kwargs):
                        original(*args,**kwargs)
                        raise ValueError('late generated weapon receiver')
                    with patch.object(FRAMEWORK,'on_equip',side_effect=fail):
                        with self.assertRaisesRegex(ValueError,'late generated weapon receiver'):
                            TURN.equip_weapon(f.e,f.a,weapon)
                else:
                    def fail(staged,actor):
                        key=TURN.equip_weapon(staged,actor,weapon)
                        self.assertIn(key,staged.r.selection.units)
                        raise ValueError('late outer weapon publication')
                    with self.assertRaisesRegex(ValueError,'late outer weapon publication'):
                        GRANTS.transition(f.e,f.a,fail)
                self.assertEqual(f.e.export_state(),before)
                self.assertEqual((set(f.r.moves),set(f.r.moves_mech),set(f.r.selection.units)),before_keys)

    def test_late_native_damage_failure_restores_load_stock_action_and_rng(self):
        f=self.scene()
        def selected_policy():
            omitted={'root','rulings','ruleset','selection','_source_context_reads','_coordinator_contest_reader'}
            values={key:value for key,value in vars(f.r).items() if key not in omitted}
            values['selected_profile']=vars(f.r.ruleset)
            values['selection']={key:value for key,value in vars(f.r.selection).items() if key not in ('filter','dependencies')}
            return deepcopy(CODEC._plain(values))
        with patch.object(type(f.e),'take_damage',autospec=True,side_effect=ValueError('actual Cannon damage failed')) as damage:
            before=f.e.export_state()
            before_policy=selected_policy()
            try:
                with self.assertRaisesRegex(ValueError,'Cannon damage failed'):
                    f.use(held_selection='cannon/pester')
            finally:
                self.maxDiff=None
                after=f.e.export_state()
                after_policy=selected_policy()
                changed={key:{'before':repr(before_policy.get(key))[:2000],
                              'after':repr(after_policy.get(key))[:2000]}
                         for key in before_policy.keys() | after_policy.keys()
                         if before_policy.get(key)!=after_policy.get(key)}
                self.assertEqual(after,before,msg='Changed selected rule fields: '+repr(changed))
        self.assertEqual(damage.call_count,1)
        self.assertIsNot(damage.call_args.args[0],f.e)
        self.assertEqual(damage.call_args.args[1].entity_id,f.t.entity_id)
        self.assertEqual(f.e._physical_objects['cannon/body'][PHYSICAL.OBJECT_STATE]['loaded_ball_instance_id'],'cannon/pester')


class PickupSourceCategoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        CSV_FIX.RemainingCsvItemContractTests.setUpClass()

    def search(self, face):
        f=CSV_FIX.RemainingCsvItemContractTests()
        actor=f.pokemon('pickup-'+str(face),capabilities=('청소부',))
        engine=f.fixture(actor)
        before=deepcopy(actor.spec.get('items',{}))
        result=engine.scavenge(actor,fixed_d20=face,duration_minutes=5,
                               duration_reason='GM observed actual five-minute search')
        self.assertEqual(actor.spec.get('items',{}),before)
        self.assertEqual(engine.elapsed_seconds,300)
        return engine,actor,result

    def test_all_printed_d20_ranges_record_category_without_inventing_item(self):
        source_ranges=((1,5,'none'),(6,7,'x_item'),(8,10,'berry'),(11,13,'poke_ball'),
                       (14,16,'status_healing'),(17,17,'evolution_stone'),
                       (18,18,'vitamin'),(19,19,'held_item'),(20,20,'tm'))
        for lower,upper,category in source_ranges:
            for face in range(lower,upper+1):
                with self.subTest(face=face):
                    engine,actor,result=self.search(face)
                    self.assertEqual((result['d20'],result['category'],result['item_id']),(face,category,None))
                    self.assertIsNone(result['gm_selection'])
                    self.assertEqual(result['pickup_source']['file'],'input/ch10-index-reference.md')
                    self.assertEqual(actor.spec[CAP.STATE]['scavenger_days'],[result['day']])

    def test_gm_selects_real_eligible_items_for_each_nonempty_category(self):
        for face,item_id in ((6,'item/플러스파워'),(8,'item/오랭열매'),(11,'item/몬스터볼-2'),
                             (14,'item/상처약'),(17,'item/불꽃의돌'),(18,'item/타우린'),
                             (19,'item/선제공격손톱'),(19,'item/예리한손톱'),(20,'TM1')):
            with self.subTest(face=face,item=item_id):
                engine,actor,result=self.search(face)
                awarded=CAP.resolve_scavenge_reward(engine,actor,day=result['day'],item_id=item_id,
                                                    reason='GM selected this actual found item')
                self.assertEqual(awarded['item_id'],item_id)
                self.assertEqual(actor.spec['items'][item_id],1)
                self.assertEqual(awarded['gm_selection']['reason'],'GM selected this actual found item')
                self.assertEqual(engine.elapsed_seconds,300)

    def test_pending_category_restores_then_gm_awards_once_without_reroll(self):
        engine,actor,result=self.search(20);identity=actor.entity_id
        engine=CODEC.load_engine(engine.r,json.loads(json.dumps(CODEC.dump_engine(engine))))
        actor=WORLD.actor_index(engine)[identity]
        snapshot=engine.gm.snapshot();engine.gm.restore(snapshot)
        actor=WORLD.actor_index(engine)[identity];rng=engine.rng.getstate()
        CAP.resolve_scavenge_reward(engine,actor,day=result['day'],item_id='TM1',reason='GM actual found TM')
        self.assertEqual(engine.rng.getstate(),rng)
        NATIVE.assert_rejected_unchanged(engine,lambda:CAP.resolve_scavenge_reward(engine,actor,
            day=result['day'],item_id='TM1',reason='duplicate reward'),reason_pattern='already selected')
        NATIVE.assert_rejected_unchanged(engine,lambda:engine.scavenge(actor,duration_minutes=5,
            duration_reason='attempt to reroll pending category'),reason_pattern='daily use')

    def test_legacy_reward_restores_stock_unchanged_and_requires_reconciliation(self):
        engine,actor,result=self.search(20)
        # Reconstruct the exact old receipt schema and its historical automatic award.
        legacy={key:deepcopy(result[key]) for key in
                ('kind','day','d20','during','activity','actor_id')}
        legacy['item_id']='item/이상한사탕'
        legacy['sha256']=TX.request_fingerprint(legacy)
        actor.spec[CAP.STATE]['receipts'][-1]=legacy
        actor.spec.setdefault('items',{})[legacy['item_id']]=1
        identity=actor.entity_id
        engine=CODEC.load_engine(engine.r,json.loads(json.dumps(CODEC.dump_engine(engine))))
        actor=WORLD.actor_index(engine)[identity]
        snapshot=engine.gm.snapshot();engine.gm.restore(snapshot)
        actor=WORLD.actor_index(engine)[identity]
        self.assertEqual(actor.spec[CAP.STATE]['receipts'][-1],legacy)
        self.assertEqual(actor.spec['items'][legacy['item_id']],1)
        before=engine.export_state()
        decision=CAP.resolve_scavenge_reward(engine,actor,day=result['day'],item_id='TM1',
                                            reason='request reconciliation of historical loot')
        self.assertIsInstance(decision,C.PendingDecision)
        self.assertEqual(decision.basis['original_receipt'],legacy)
        self.assertEqual(decision.basis['printed_category'],'tm')
        self.assertFalse(decision.basis['automatic_inventory_adjustment'])
        self.assertEqual(engine.export_state(),before)
        self.assertEqual(actor.spec[CAP.STATE]['scavenger_days'],[result['day']])
        NATIVE.assert_rejected_unchanged(engine,lambda:engine.scavenge(actor,duration_minutes=5,
            duration_reason='legacy day cannot grant another roll'),reason_pattern='daily use')
        actor.spec[CAP.STATE]['receipts'][-1]['item_id']='item/상처약'
        with self.assertRaises(CODEC.StateCodecError):CODEC.dump_engine(engine)
        actor.spec[CAP.STATE]['receipts'][-1]=deepcopy(legacy)
        self.assertEqual(engine.export_state(),before)

    def test_none_wrong_category_non_tm_and_missing_gm_reason_reject_unchanged(self):
        engine,actor,result=self.search(3)
        NATIVE.assert_rejected_unchanged(engine,lambda:CAP.resolve_scavenge_reward(engine,actor,
            day=result['day'],item_id='item/상처약',reason='cannot override nothing'),reason_pattern='finds nothing')
        for face,item_id in ((6,'item/상처약'),(17,'item/업그레이드'),(18,'item/이상한사탕'),
                             (19,'item/불꽃의돌'),(19,'item/업그레이드'),
                             (20,'item/상처약'),(20,'HM1'),(20,'TM999')):
            with self.subTest(face=face,item=item_id):
                engine,actor,result=self.search(face)
                NATIVE.assert_rejected_unchanged(engine,lambda:CAP.resolve_scavenge_reward(engine,actor,
                    day=result['day'],item_id=item_id,reason='invalid GM item'),reason_pattern='outside|actual selected TM')
        engine,actor,result=self.search(12)
        NATIVE.assert_rejected_unchanged(engine,lambda:CAP.resolve_scavenge_reward(engine,actor,
            day=result['day'],item_id='item/몬스터볼-2',reason=''),reason_pattern='selection reason')


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(loader.loadTestsFromTestCase(case)
                              for case in (CannonItemIdentityTests,PickupSourceCategoryTests))
