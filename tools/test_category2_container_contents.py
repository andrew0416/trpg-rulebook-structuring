"""Actual shell intake/removal and reusable bottle bodies across actor kinds."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import unittest,sys,json
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_item_maturation as _fixture_test_category2_item_maturation
import item_maturation as M,item_containers as J,item_stock as S,state_codec as CODEC,world_entities as W

class ContainerContentsTests(unittest.TestCase):
    setUpClass=classmethod(_fixture_test_category2_item_maturation.ItemMaturationTests.setUpClass.__func__)
    def setUp(self):
        _fixture_test_category2_item_maturation.ItemMaturationTests.setUp(self)
        from builder import build_pokemon
        self.other=self.add(build_pokemon(self.r,'이브이',20,moves=[],abilities=[],extra={'trainer_id':self.a.entity_id}))
    add=_fixture_test_category2_item_maturation.ItemMaturationTests.add
    held=_fixture_test_category2_item_maturation.ItemMaturationTests.held
    restored=_fixture_test_category2_item_maturation.ItemMaturationTests.restored
    row=_fixture_test_category2_item_maturation.ItemMaturationTests.row
    snap=_fixture_test_category2_item_maturation.ItemMaturationTests.snap

    def jar(self):
        self.held(self.a,'item/빈병','jar')
        self.e.gm.observe_empty_container(self.a,container_selection='jar',reason='actual glass jar inspected empty')

    def bottle(self):
        return self.e.pokemon_activity(self.a,'collect_matured_item',target=self.p,batch_id=self.key,container_selection='jar',reason='one actual juice portion transferred')

    def drink(self,target):
        return self.e.use_item(self.a,'item/나무열매쥬스',target,container_selection='jar',duration_minutes=1,duration_reason='actual bottled refreshment intake')

    def valid(self):
        result=self.e.validate_state();self.assertTrue(result['valid'],result)

    def test_shell_snack_crosses_candy_deadline_without_becoming_a_drink_or_candy(self):
        self.e.advance_time(1295970);self.p.hp=max(1,self.p.max_hp-40);hp=self.p.hp
        out=self.e.use_item(self.p,'item/나무열매쥬스',shell_batch_id=self.key,duration_minutes=1,duration_reason='actual shell Snack intake')
        self.assertEqual(out['status'],'digestion_buff_gained');self.assertEqual(self.p.hp,hp)
        self.assertEqual(self.row()['stage'],'consumed');self.assertEqual(self.row()['removal']['at'],1295970)
        self.assertNotIn('drink_history',self.p.spec);self.assertNotIn('candy_at',self.row())
        self.valid()
        self.e.consume_food_buff(self.p,buff_id=out['buff_id'],action_kind='swift',action_reason='GM sourced Snack exchange')
        self.assertEqual(self.p.hp,min(self.p.max_hp,hp+30));self.assertFalse(self.p.buffs)
        self.assertEqual(self.p.spec['food_consumption_receipts'][-1]['item_stock']['product_id'],self.row()['product']['id'])
        self.e.advance_time(1209600);self.assertEqual(self.row()['stage'],'consumed')
        self.e.gm.restore(self.e.gm.snapshot());self.assertTrue(self.restored().validate_state()['valid']);self.valid()
        before=self.snap()
        with self.assertRaises(ValueError):self.e.use_item(self.p,'item/나무열매쥬스',shell_batch_id=self.key,duration_minutes=1,duration_reason='duplicate')
        self.assertEqual(before,self.snap())

    def test_bottled_juice_stops_shell_aging_and_heals_both_actor_kinds_leaving_body(self):
        for recipient in ('trainer','pokemon'):
            with self.subTest(recipient=recipient):
                self.setUp();self.jar();self.e.advance_time(1295999);self.bottle()
                self.assertEqual(self.row()['stage'],'bottled');self.assertEqual(self.row()['product']['location'],'container')
                self.e.advance_time(1209601)
                target=self.a if recipient=='trainer' else self.other
                target.hp=max(1,target.max_hp-35);hp=target.hp
                out=self.drink(target);self.assertEqual(out['healed'],min(30,target.max_hp-hp));self.assertEqual(target.hp,min(target.max_hp,hp+30))
                jar=self.e._physical_objects['jar'];self.assertNotIn('consumed',jar);self.assertEqual(jar['equipped_by'],self.a.entity_id)
                self.assertIsNone(jar[J.KEY]['current']);portion=next(iter(jar[J.KEY]['portions'].values()))
                self.assertEqual(portion['status'],'consumed');self.assertEqual(portion['item_id'],'item/나무열매쥬스')
                self.assertEqual(target.spec['drink_history'][-1]['item_stock']['content_id'],self.row()['product']['id'])
                self.assertNotIn('candy_at',self.row());self.valid()
                before=self.snap()
                with self.assertRaises(ValueError):self.drink(target)
                self.assertEqual(before,self.snap())

    def test_same_container_loads_honey_and_milk_from_existing_stock_with_ordinary_food_rules(self):
        self.jar();self.a.spec['items'].update({'꿀':2,'튼튼밀크':1})
        self.e.load_container(self.a,container_selection='jar',item_name='꿀',reason='actual Honey poured into jar')
        self.assertEqual(self.a.spec['items']['꿀'],1)
        before=self.snap()
        with self.assertRaises(ValueError):self.e.load_container(self.a,container_selection='jar',item_name='튼튼밀크',reason='occupied jar')
        self.assertEqual(before,self.snap())
        out=self.e.use_item(self.a,'꿀',self.other,container_selection='jar',duration_minutes=1,duration_reason='one actual Honey Snack')
        self.assertEqual(out['status'],'digestion_buff_gained');self.assertEqual(self.other.buffs[-1]['effect'],{'kind':'heal','amount':5})
        self.e.load_container(self.a,container_selection='jar',item_name='튼튼밀크',reason='same emptied jar reused')
        self.assertEqual(self.a.spec['items']['튼튼밀크'],0)
        self.a.hp=1;out=self.e.use_item(self.a,'튼튼밀크',container_selection='jar',duration_minutes=1,duration_reason='actual milk')
        self.assertEqual(out['healed'],min(80,self.a.max_hp-1));state=self.e._physical_objects['jar'][J.KEY]
        self.assertEqual(len(state['portions']),2);self.assertIsNone(state['current']);self.valid()
        with self.assertRaises(ValueError):self.e.gm.observe_empty_container(self.a,container_selection='jar',reason='attempt to erase history')
        self.assertTrue(self.restored().validate_state()['valid'])

    def test_missing_empty_observation_foreign_shell_and_refused_or_full_snack_do_not_spend(self):
        self.held(self.a,'item/빈병','jar');self.e.advance_time(86400);before=self.snap()
        with self.assertRaises(ValueError):self.bottle()
        self.assertEqual(before,self.snap())
        with self.assertRaises(ValueError):self.e.use_item(self.p,'item/나무열매쥬스',self.a,shell_batch_id=self.key,duration_minutes=1,duration_reason='foreign Snack')
        self.assertEqual(before,self.snap())
        with self.assertRaises(ValueError):self.e.use_item(self.a,'item/나무열매쥬스',shell_batch_id=self.key,duration_minutes=1,duration_reason='foreign batch')
        self.assertEqual(before,self.snap())
        self.e.use_item(self.p,'item/나무열매쥬스',shell_batch_id=self.key,accepted=False)
        self.assertEqual(self.row()['stage'],'juice');self.assertEqual(self.e.elapsed_seconds,86400)
        self.e.use_item(self.p,'오랭열매',duration_minutes=1,duration_reason='existing full Snack capacity')
        before=self.snap()
        with self.assertRaises(ValueError):self.e.use_item(self.p,'item/나무열매쥬스',shell_batch_id=self.key,duration_minutes=1,duration_reason='full buff capacity')
        self.assertEqual(before,self.snap());self.valid()

    def test_bottle_intake_keeps_drink_limit_and_exact_stock_selection_without_spending_early(self):
        self.jar();self.e.advance_time(86400);self.bottle();self.a.hp=1;self.drink(self.a)
        self.a.spec['items']['item/나무열매쥬스']=1
        self.e.load_container(self.a,container_selection='jar',item_name='item/나무열매쥬스',reason='another actual portion')
        before=self.snap()
        with self.assertRaises(ValueError):self.drink(self.a)
        self.assertEqual(before,self.snap())
        with self.assertRaises(ValueError):self.e.use_item(self.a,'item/나무열매쥬스',held_selection='jar',container_selection='jar',duration_minutes=1,duration_reason='ambiguous stock')
        self.assertEqual(before,self.snap())
        self.e.advance_time(3540);self.drink(self.a)
        self.assertEqual(len(self.a.spec['drink_history']),2)
        self.assertEqual(self.a.spec['drink_history'][1]['at']-self.a.spec['drink_history'][0]['at'],3600)
        self.assertEqual(len(self.e._physical_objects['jar'][J.KEY]['portions']),2);self.valid()

    def test_both_restore_paths_keep_bottle_identity_history_and_one_use_only(self):
        self.jar();self.e.advance_time(86400);self.bottle();saved=self.e.gm.snapshot();loaded=self.restored()
        self.a.hp=1;self.drink(self.a);self.e.gm.restore(saved)
        for e in (self.e,loaded):
            a=next(x for x in e.gm.everyone if x.entity_id==self.a.entity_id);a.hp=1
            e.use_item(a,'item/나무열매쥬스',container_selection='jar',duration_minutes=1,duration_reason='after restore')
            self.assertEqual(a.hp,31);self.assertIsNone(e._physical_objects['jar'][J.KEY]['current'])
            with self.assertRaises(ValueError):e.use_item(a,'item/나무열매쥬스',container_selection='jar',duration_minutes=1,duration_reason='second use')
            self.assertTrue(e.validate_state()['valid'])

    def test_corrupt_content_and_shell_links_fail_before_mutation_and_on_both_restore_paths(self):
        self.jar();self.e.advance_time(86400);self.bottle();state=self.e._physical_objects['jar'][J.KEY];key=state['current'];valid=deepcopy(state)
        state['portions'][key]['count']=True;before=self.snap()
        with self.assertRaises(ValueError):self.drink(self.a)
        self.assertEqual(before,self.snap())
        with self.assertRaises(ValueError):CODEC.dump_engine(self.e)
        with self.assertRaises(ValueError):self.e.gm.snapshot()
        with patch.object(J,'validate_world',return_value=True):
            payload=json.loads(json.dumps(CODEC.dump_engine(self.e)));bad=self.e.gm.snapshot('bad-contents')
        self.e._physical_objects['jar'][J.KEY]=valid;before=self.snap()
        with self.assertRaises(ValueError):CODEC.load_engine(self.r,payload)
        with self.assertRaises(ValueError):self.e.gm.restore(bad)
        self.assertEqual(before,self.snap())
        self.row()['removal']['container_id']='missing'
        self.assertFalse(self.e.validate_state()['valid'])
        with self.assertRaises(ValueError):self.e.gm.snapshot()

    def test_native_buff_transfer_preserves_shell_origin_across_current_holders_and_restore(self):
        self.e.advance_time(86400)
        out=self.e.use_item(self.p,'item/나무열매쥬스',shell_batch_id=self.key,duration_minutes=1,duration_reason='actual shell Snack')
        self.e.apply_effect(self.other,self.p,{'type':'steal_buff'},20,True,0,'move/벌레먹기')
        self.assertFalse(self.p.buffs);self.assertEqual(self.other.buffs[0]['id'],out['buff_id'])
        self.valid();self.e.gm.restore(self.e.gm.snapshot());self.assertTrue(self.restored().validate_state()['valid'])
        self.other.hp=1
        self.e.consume_food_buff(self.other,buff_id=out['buff_id'],action_kind='swift',action_reason='actual transferred Snack')
        self.assertEqual(self.other.hp,min(31,self.other.max_hp));self.valid()

    def test_failed_native_bottling_and_snack_keep_actual_material_time_and_history(self):
        self.jar();self.e.advance_time(1295970);before=self.snap();native=J.deposit
        def broken(*args,**kw):native(*args,**kw);raise ValueError('after actual deposit')
        with patch.object(J,'deposit',side_effect=broken):
            with self.assertRaises(ValueError):self.bottle()
        self.assertEqual(before,self.snap())
        import food_effects as F
        native_grant=F.grant_buff
        def broken_grant(*args,**kw):native_grant(*args,**kw);raise ValueError('after acquired Snack')
        with patch.object(F,'grant_buff',side_effect=broken_grant):
            with self.assertRaises(ValueError):self.e.use_item(self.p,'item/나무열매쥬스',shell_batch_id=self.key,duration_minutes=1,duration_reason='actual intake')
        self.assertEqual(before,self.snap());self.valid()
        self.bottle();self.assertEqual(self.row()['stage'],'bottled')

if __name__=='__main__':unittest.main()
