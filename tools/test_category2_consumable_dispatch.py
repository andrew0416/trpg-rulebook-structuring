"""Native producer tests for common use boundaries and dispatchers."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_item_stock as _fixture_test_category2_item_stock
from engine import Engine,Combatant,scenario
from builder import build_pokemon
import encounter,state_codec as CODEC,items as ITEMS


class ConsumableDispatchTests(unittest.TestCase):
    setUpClass=classmethod(_fixture_test_category2_item_stock.ItemStockTests.setUpClass.__func__)
    setUp=_fixture_test_category2_item_stock.ItemStockTests.setUp
    add=_fixture_test_category2_item_stock.ItemStockTests.add
    restored=_fixture_test_category2_item_stock.ItemStockTests.restored
    held=_fixture_test_category2_item_stock.ItemStockTests.held
    snap=_fixture_test_category2_item_stock.ItemStockTests.snap

    def test_quantity_drink_failure_rolls_back_time_stock_recipient_and_healing(self):
        original=Engine.heal
        def fail_after_heal(e,*args,**kwargs):
            original(e,*args,**kwargs)
            raise ValueError('injected post-healing error')
        for target_name in ('a','p'):
            self.setUp();target=getattr(self,target_name);target.hp=1
            self.a.spec['items']={'맛있는물':1};before=self.snap()
            with patch.object(Engine,'heal',new=fail_after_heal):
                with self.assertRaisesRegex(ValueError,'post-healing'):
                    self.e.use_item(self.a,'맛있는물',target,duration_minutes=1,duration_reason='observed intake')
            self.assertEqual(before,self.snap())
            result=self.e.use_item(self.a,'맛있는물',target,duration_minutes=1,duration_reason='observed intake')
            self.assertEqual((result['healed'],target.hp,self.a.spec['items']['맛있는물'],self.e.elapsed_seconds),(20,21,0,60))
            restored=self.restored();actual=next(c for c in restored.gm.everyone if c.entity_id==target.entity_id)
            self.assertEqual(actual.spec['drink_history'],target.spec['drink_history'])

    def test_quantity_food_failure_rolls_back_intake_and_does_not_leave_a_buff(self):
        import food_effects as F
        original=F.grant_buff
        def fail_after_grant(*args,**kwargs):
            original(*args,**kwargs)
            raise ValueError('injected post-buff error')
        self.a.spec['items']={'오랭열매':1};before=self.snap()
        with patch.object(F,'grant_buff',side_effect=fail_after_grant):
            with self.assertRaisesRegex(ValueError,'post-buff'):
                self.e.use_item(self.a,'오랭열매',self.p,duration_minutes=1,duration_reason='observed intake')
        self.assertEqual(self.snap(),before)
        self.e.use_item(self.a,'오랭열매',self.p,duration_minutes=1,duration_reason='observed intake')
        self.assertEqual(len(self.p.buffs),1);self.assertEqual(self.a.spec['items']['오랭열매'],0)

    def test_bandage_does_not_silently_accept_a_food_policy_or_cost_waiver(self):
        self.a.spec['items']={'붕대':1}
        for options in ({'free':True},{'food_policy':'book_xp20_level15'}):
            before=self.snap()
            with self.assertRaises(ValueError):self.e.use_item(self.a,'붕대',self.p,duration_minutes=1,duration_reason='observed application',**options)
            self.assertEqual(self.snap(),before)


class CapturePaymentTests(unittest.TestCase):
    setUpClass=classmethod(_fixture_test_category2_item_stock.ItemStockTests.setUpClass.__func__)
    add=_fixture_test_category2_item_stock.ItemStockTests.add
    restored=_fixture_test_category2_item_stock.ItemStockTests.restored

    def setUp(self):
        _fixture_test_category2_item_stock.ItemStockTests.setUp(self)
        self.p.side='wild';self.p.spec.update(side='wild',wild=True,evolutions_remaining=0)
        self.p.hp=1;self.p.pos=(1,0)
        self.e.everyone=self.e.gm.everyone=[self.a,self.p]

    def run_driver(self,stock,key,accuracy):
        self.setUp();self.a.spec['items']={key:stock}
        original=self.e.throw_ball
        def actual_throw(*args,**kwargs):return original(*args,**kwargs,fixed_accuracy=accuracy,fixed_capture=20)
        with patch.object(encounter,'load_encounter',return_value=(self.e,{'name':'payment','rounds':1},[self.a],[self.p])), \
             patch.object(self.e,'initiative',return_value=[self.a,self.p]), \
             patch.object(self.e,'throw_ball',side_effect=actual_throw):
            encounter.run_encounter(str(ROOT),'fixture.json',write=False)
        return self.a.spec.get('capture_attempts',{})

    def test_actual_encounter_spends_exactly_one_ball_for_miss_and_capture(self):
        for key in ('poke_ball','몬스터볼','item/몬스터볼'):
            for count in (1,2):
                for accuracy in (1,20):
                    with self.subTest(key=key,count=count,accuracy=accuracy):
                        attempts=self.run_driver(count,key,accuracy)
                        self.assertEqual(len(attempts),1)
                        self.assertEqual(self.a.spec['items'][key],count-1)
                        self.assertEqual(attempts['capture-1']['status'],'captured' if accuracy==20 else 'recoverable_on_ground')
                        restored=self.restored();a=next(c for c in restored.gm.everyone if c.entity_id==self.a.entity_id)
                        self.assertEqual(a.spec['capture_attempts'],attempts)
                        self.assertEqual(a.spec['items'][key],count-1)

    def test_unavailable_standard_action_never_pays_from_driver(self):
        self.a.spec['items']={'poke_ball':1}
        def no_standard(e,actor,rnd):
            if actor is self.a:actor.pending_action_loss={'standard':1}
        with patch.object(encounter,'load_encounter',return_value=(self.e,{'name':'payment','rounds':1},[self.a],[self.p])), \
             patch.object(self.e,'initiative',return_value=[self.a,self.p]):
            encounter.run_encounter(str(ROOT),'fixture.json',hook=no_standard,write=False)
        self.assertEqual(self.a.spec['items']['poke_ball'],1)
        self.assertFalse(self.a.spec.get('capture_attempts'))

    def test_scenario_caller_uses_the_last_ball_through_native_throw(self):
        original=Engine.throw_ball;captured=[]
        class StopAfterObservedThrow(Exception):pass
        def throwing(e,actor,target,*args,**kwargs):
            before=actor.spec['items']['poke_ball']
            original(e,actor,target,*args,**kwargs,fixed_accuracy=1)
            captured.append((before,actor.spec['items']['poke_ball'],deepcopy(actor.spec.get('capture_attempts',{}))))
            raise StopAfterObservedThrow()
        def hook(e,actor,rnd):
            import body_state as BODY
            for participant in e.gm.everyone:
                BODY.observe(e,participant,[(0,0)],reason='explicit one-cell scenario test observation')
            if actor.kind=='trainer':
                actor.spec['items']={'poke_ball':1}
                for c in e.gm.everyone:
                    if c.side=='wild':c.hp=1;c.pos=(actor.pos[0]+1,actor.pos[1]);c.spec['evolutions_remaining']=0
        with patch.object(Engine,'throw_ball',new=throwing), patch.object(Engine,'use_move_on',return_value=0):
            with self.assertRaises(StopAfterObservedThrow):
                scenario(str(ROOT),5,ruleset='core',rulings_path=str(ROOT/'tools/fixtures/initiative-gm-policy.json'),hook=hook)
        self.assertEqual(len(captured),1)
        before,after,attempts=captured[0]
        self.assertEqual((before,after),(1,0))
        self.assertEqual(attempts['capture-1']['status'],'recoverable_on_ground')
