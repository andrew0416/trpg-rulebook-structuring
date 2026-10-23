"""C09-047: real Portable Grower body consumed by native growth/harvest."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json,unittest
from engine import Rules,Engine
import test_category2_cultivation_state as fixture
import cultivation_growth as G,cultivation_state as P
import physical_planter as POT,world_entities as W,state_codec as CODEC
import capability_actions as C,state_grants as GRANTS,campaign_rewards as REWARDS
import common_checks as CHECKS,downtime as D

ROOT=Path(r'D:/trpg-rulebook-structuring/ptk-structure-experiment')


class PhysicalPlanterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')
    actor=fixture.CultivationStateTests.actor
    act=fixture.CultivationStateTests.act
    own=fixture.CultivationStateTests.own
    plant_setup=fixture.CultivationStateTests.plant_setup
    botany=fixture.CultivationStateTests.botany

    def setUp(self):
        fixture.CultivationStateTests.setUp(self);self.plant_setup()
        self.a.spec.setdefault('movement',{})['power']=2
        W.observe_location(self.e,self.a,{'kind':'grid','cell':[1,1]},reason='actual planter gardener')

    def box(self,identity='pot',slot=0,policy='book-literal',*,bind=True,item=P.PLANTER):
        W.register_object(self.e,identity,kind='item_instance',item_rule_id=item,owner_id=self.a.entity_id,
            location={'kind':'grid','cell':[1,1]},reason='observed individual Portable Grower')
        if bind:POT.bind(self.e,self.a,identity,slot=slot,planter_policy=policy,reason='actual owned tool unit and selected source')
        return self.e._physical_objects[identity]

    def native(self,pid='plant',species='버치열매',policy='book-literal',slot=0):
        return self.act('plant_berry',berry=species,plant_id=pid,planter_slot=slot,planter_policy=policy)

    def remove(self,pid='plant',**kw):
        return POT.remove(self.e,self.a,pid,soil_quality=kw.get('soil_quality',0),soft_soil=kw.get('soft_soil',False),
            allows_growth=kw.get('allows_growth',True),reason='actual same plant removed at this location')

    def snapshot(self):return CODEC.dump_engine(self.e)

    def assert_atomic(self,call):
        before=self.snapshot()
        with self.assertRaises(ValueError):call()
        self.assertEqual(self.snapshot(),before)

    def restore(self):
        identity=self.a.entity_id
        self.e=CODEC.load_engine(Rules(ROOT,ruleset='core'),json.loads(json.dumps(self.snapshot(),ensure_ascii=False)))
        self.a=W.actor_index(self.e)[identity]

    def test_native_book_actual_body_single_plant_real_price_seed_and_fertile_harvest(self):
        self.a.spec['items'].pop('나무열매플랜터');self.a.spec['money']=2000
        sale=REWARDS.purchase(self.e,self.a,event_id='actual-pot-sale',merchant='actual nursery',items={P.PLANTER:1},reason='actual Portable Grower purchase')
        self.assertEqual((sale['price'],sale['cash_spent'],self.a.spec['money']),(2000,2000,0))
        inventory_key=next(iter(sale['items']));self.box();self.native()
        plant=self.a.spec['plants']['plant'];body=self.e._physical_objects['pot']
        self.assertIs(plant,self.e._physical_objects['plant'])
        self.assertEqual((plant['growth']['site_id'],plant['growth']['slot']),('pot',0))
        self.assertEqual((self.a.spec['items'][inventory_key],self.a.spec['items']['버치열매']),(1,4))
        self.assertEqual(W.effective_location(self.e,plant)['cell'],(1,1))
        self.assert_atomic(lambda:self.native('second'))
        self.e.advance_time(172800,[self.a])
        out=self.act('harvest_berry',plant_id='plant',fixed=3,environment_allows_growth=False,soil_quality=-99)
        self.assertEqual((out['amount'],out['protected'],out['receipt']['soil_base'],out['receipt']['site_bonus']),(3,True,0,1))
        self.assertNotIn('mulch_applications',plant);self.assertNotIn('consumed',body)
        self.assertEqual(self.a.spec['items'][inventory_key],1)

    def test_herb_uses_same_actual_book_body_and_rejects_other_plant_kinds(self):
        self.a.spec['edges']=[];self.botany();self.a.spec['items']['멘탈허브']=2;self.box();self.native(species='멘탈허브')
        plant=self.a.spec['plants']['plant'];self.assertEqual(plant['crop']['kind'],'herb')
        self.assertEqual(self.a.spec['items']['멘탈허브'],1)
        self.e.advance_time(172800,[self.a]);out=self.act('harvest_berry',plant_id='plant',fixed=3,environment_allows_growth=False)
        self.assertEqual((out['amount'],out['protected']),(2,True))
        self.remove();value=deepcopy(plant['growth']['definition'])
        value.update(species='빨간규토리',seed={'item_id':P.SOURCE,'key':'빨간규토리','count':1});self.a.spec['items']['빨간규토리']=1
        self.assert_atomic(lambda:self.e.plant_growth(self.a,value,plant_id='apricorn',site_id='pot',slot=0,reason='book body permits Berries and herbs'))

    def test_sheet_four_plants_and_three_sessions_stay_distinct_from_book(self):
        self.e=Engine(self.rules,seed=18,session_frequency=True,defer_session_refresh=True);self.e.gm.everyone=[self.a,self.p,self.q]
        self.e.begin_session('s0',[self.a]);self.box(policy='sheet-current')
        for n in range(4):self.native(str(n),policy='sheet-current')
        self.assert_atomic(lambda:self.native('fifth',policy='sheet-current'))
        self.assert_atomic(lambda:self.native('book',policy='book-literal'))
        self.e.advance_time(172800,[self.a]);self.assertEqual(self.e.growth_status(self.a,'0')['remaining'],3)
        for n in (1,2,3):self.e.begin_session('s'+str(n),[self.a])
        self.assertTrue(self.e.growth_status(self.a,'0')['ready'])
        self.assertEqual(len([p for p in self.a.spec['plants'].values() if POT.contained(p)]),4)
        self.restore();self.assertEqual(self.e._physical_objects['pot']['growth_site']['capacity'],4)
        self.assertEqual(self.act('harvest_berry',plant_id='0',fixed=3,environment_allows_growth=False)['amount'],3)

    def test_same_plant_follows_actual_carried_body_and_access_survives_restore(self):
        self.box();self.native();plant=self.a.spec['plants']['plant']
        body=self.e._physical_objects['pot']
        self.assertFalse(POT.contained(body));self.assertTrue(POT.contained(plant))
        self.assertEqual(W.effective_location(self.e,body)['cell'],(1,1))
        self.assert_atomic(lambda:W.observe_location(self.e,plant,{'kind':'grid','cell':[8,8]},reason='cannot split contained organism'))
        self.assert_atomic(lambda:W.register_object(self.e,'plant',location={'kind':'grid','cell':[8,8]},owner_id=self.a.entity_id,reason='same contained organism cannot be independently replaced'))
        self.assert_atomic(lambda:C.set_carried(self.e,self.a,[{'id':'plant','weight_kg':1}],reason='cannot carry plant separately'))
        C.set_carried(self.e,self.a,[{'id':'pot','weight_kg':1}],reason='same actual pot lifted')
        W.observe_location(self.e,self.a,{'kind':'grid','cell':[8,8]},reason='gardener carried the pot')
        self.assertEqual(W.effective_location(self.e,body)['cell'],(8,8))
        self.assertEqual(W.effective_location(self.e,plant)['cell'],(8,8))
        self.restore();plant=self.a.spec['plants']['plant']
        self.assertEqual(W.effective_location(self.e,plant)['cell'],(8,8));self.assertIs(plant,self.e._physical_objects['plant'])
        C.set_carried(self.e,self.a,[],reason='pot released')
        W.observe_location(self.e,self.e._physical_objects['pot'],{'kind':'grid','cell':[8,8]},reason='actual ground location after release')
        self.assertEqual(W.effective_location(self.e,self.e._physical_objects['pot'])['cell'],(8,8))
        W.observe_location(self.e,self.a,{'kind':'grid','cell':[1,1]},reason='gardener walked away')
        self.e.advance_time(172800,[self.a]);self.assert_atomic(lambda:self.act('harvest_berry',plant_id='plant',fixed=3))
        self.assert_atomic(lambda:self.remove())
        W.observe_location(self.e,self.a,{'kind':'grid','cell':[8,8]},reason='gardener returned')
        self.assertEqual(self.act('harvest_berry',plant_id='plant',fixed=3)['amount'],3)

    def test_removal_keeps_clock_seed_body_and_old_harvest_but_ends_current_benefits(self):
        self.box();self.native();self.e.advance_time(172800,[self.a])
        first=self.act('harvest_berry',plant_id='plant',fixed=3,environment_allows_growth=False)
        plant=self.a.spec['plants']['plant'];origin=deepcopy(plant['growth']);receipt=deepcopy(plant['harvest_history'][0])
        seed_balance=self.a.spec['items']['버치열매'];removed=self.remove(soil_quality=-1,allows_growth=False)
        self.assertIs(plant,self.e._physical_objects['plant']);self.assertEqual(plant['growth'],origin)
        self.assertEqual(self.a.spec['items']['버치열매'],seed_balance);self.assertEqual(plant['harvest_history'][0],receipt)
        current=self.e.growth_status(self.a,'plant')
        self.assertEqual((current['mature'],current['protected'],current['site_bonus'],current['soil_base'],current['ready']),(True,False,0,-1,False))
        self.assertEqual(current['physical_planter_release'],removed['sha256'])
        self.native('replacement');self.assertEqual(plant['harvest_history'][0],receipt)
        self.e.gm.snapshot('removed');self.restore();plant=self.a.spec['plants']['plant']
        W.observe_location(self.e,self.e._physical_objects['pot'],{'kind':'grid','cell':[5,5]},reason='pot moved after old plant removed')
        self.assertEqual(W.effective_location(self.e,plant)['cell'],(1,1));self.assertEqual(plant['harvest_history'][0],receipt)
        D.new_day(self.a)
        pending=self.act('harvest_berry',plant_id='plant',fixed=3,environment_allows_growth=False)
        self.assertIsInstance(pending,CHECKS.PendingDecision)
        out=self.act('harvest_berry',plant_id='plant',fixed=3,environment_allows_growth=True,soil_quality=0)
        self.assertEqual((first['amount'],out['amount'],out['protected'],out['receipt']['site_bonus']),(3,2,False,0))
        self.assertEqual(plant['harvest_history'][0],receipt)
        self.restore();self.assertEqual(self.a.spec['plants']['plant']['harvest_history'][0],receipt)

    def test_empty_binding_requires_actual_identity_owned_slot_and_unmixed_source(self):
        self.box(bind=False);self.assert_atomic(lambda:POT.bind(self.e,self.a,'pot',slot=0,planter_policy=None,reason='no implicit book or sheet'))
        self.assert_atomic(lambda:POT.bind(self.e,self.a,'missing',slot=0,planter_policy='book-literal',reason='missing real body'))
        self.assert_atomic(lambda:POT.bind(self.e,self.a,'pot',slot=1,planter_policy='book-literal',reason='missing second inventory unit'))
        with patch.object(POT,'REFERENCE',dict(POT.REFERENCE,sha256='0'*64)):
            self.assert_atomic(lambda:POT.bind(self.e,self.a,'pot',slot=0,planter_policy='book-literal',reason='source hash changed'))
        POT.bind(self.e,self.a,'pot',slot=0,planter_policy='book-literal',reason='same actual counted tool')
        self.box('duplicate',bind=False)
        self.assert_atomic(lambda:POT.bind(self.e,self.a,'duplicate',slot=0,planter_policy='book-literal',reason='one counted tool cannot create another actual site'))
        self.a.spec['items']['나무열매플랜터']=2;self.box('second',slot=1)
        self.native();self.native('second-plant',slot=1)
        self.assertEqual(self.a.spec['plants']['second-plant']['growth']['site_id'],'second')

    def test_identified_unknown_herb_keeps_existing_pending_policy_and_no_free_yield(self):
        self.box();self.native();plant=self.a.spec['plants']['plant'];value=deepcopy(plant['growth']['definition']);self.remove()
        identity={'species':'관측허브','kind':'herb','seed_source':P.SOURCE,'reason':'GM identified this actual named herb seed'}
        value.update(species='관측허브',seed={'item_id':P.SOURCE,'key':'관측허브','count':1},plant_identity=identity,maturity={'clock':'pending','amount':None})
        self.a.spec['items']['관측허브']=2
        self.e.plant_growth(self.a,value,plant_id='unknown-herb',site_id='pot',slot=0,reason='actual identified herb without invented species policy')
        self.assertEqual(self.a.spec['items']['관측허브'],1);self.assertEqual(self.e.growth_status(self.a,'unknown-herb')['clock'],'pending')
        before=self.snapshot();result=self.act('harvest_berry',plant_id='unknown-herb',fixed=999)
        self.assertIsInstance(result,CHECKS.PendingDecision);self.assertEqual(before,self.snapshot())
        self.restore();self.assertIsInstance(self.act('harvest_berry',plant_id='unknown-herb'),CHECKS.PendingDecision)

    def test_new_binding_and_removal_late_record_failures_are_atomic(self):
        for boundary in ('bind','remove'):
            with self.subTest(boundary=boundary):
                self.setUp();self.box(bind=boundary!='bind')
                if boundary=='remove':self.native()
                before=self.snapshot();spec=self.a.spec;body=self.e._physical_objects['pot']
                rulings=self.e.rulings.log;logs=self.e.log_lines;record=type(self.e.gm)._rec;seen=[]
                def late(gm,*args,**kwargs):
                    record(gm,*args,**kwargs);seen.append(True);raise ValueError('late actual planter record')
                operation=(lambda:POT.bind(self.e,self.a,'pot',slot=0,planter_policy='book-literal',reason='actual tool binding')) if boundary=='bind' else self.remove
                with patch.object(type(self.e.gm),'_rec',autospec=True,side_effect=late):
                    with self.assertRaisesRegex(ValueError,'late actual planter'):operation()
                self.assertEqual(seen,[True]);self.assertEqual(self.snapshot(),before)
                self.assertIs(self.a.spec,spec);self.assertIs(self.e._physical_objects['pot'],body)
                self.assertIs(self.e.rulings.log,rulings);self.assertIs(self.e.log_lines,logs)

    def test_changed_body_site_policy_removal_and_alias_reject_save_or_restore(self):
        for boundary in ('body','site','policy','release','alias'):
            with self.subTest(boundary=boundary):
                self.setUp();self.box();self.native()
                if boundary=='release':self.remove()
                plant=self.a.spec['plants']['plant'];body=self.e._physical_objects['pot']
                original_plant=deepcopy(plant);original_body=deepcopy(body)
                if boundary=='body':body['item_rule_id']='item/비료'
                elif boundary=='site':plant['growth']['site_id']='missing-body'
                elif boundary=='policy':body[POT.KEY]['policy']='sheet-current'
                elif boundary=='release':plant[POT.RELEASE]['soil_quality']=9
                else:self.a.spec['plants']['plant']=deepcopy(plant)
                with self.assertRaises(ValueError):self.snapshot()
                with patch.object(P,'validate',return_value={}),patch.object(G,'validate_world',return_value=True):broken=self.snapshot()
                plant.clear();plant.update(original_plant);body.clear();body.update(original_body);self.a.spec['plants']['plant']=plant
                before=self.snapshot()
                with self.assertRaises(ValueError):CODEC.load_engine(self.rules,broken)
                self.assertEqual(self.snapshot(),before)

    def test_actual_body_lifecycle_blocks_benefits_without_inventing_plant_damage_or_new_clock(self):
        self.box();self.native();plant=self.a.spec['plants']['plant'];origin=deepcopy(plant['growth'])
        for flag in ('disabled','suppressed','destroyed'):
            body=self.e._physical_objects['pot'];body[flag]=True
            with self.assertRaises(ValueError):self.e.growth_status(self.a,'plant')
            self.assertEqual(plant['growth'],origin);self.assertNotIn(flag,plant)
            body.pop(flag)
        self.assertEqual(self.e.growth_status(self.a,'plant')['remaining'],172800)
        def actual_break(e,a):
            W.finish_physical_use(e,e._physical_objects['pot'],'destroyed',{'source':'gm/actual-break','by_actor_id':a.entity_id,'at':e.elapsed_seconds})
            a.spec['items']['나무열매플랜터']=0
        GRANTS.transition(self.e,self.a,actual_break)
        self.assertEqual(plant['growth'],origin);self.assertNotIn('destroyed',plant)
        self.snapshot();self.a.spec['items']['나무열매플랜터']=1;self.box('new-pot');self.native('new-plant')
        self.assertEqual(self.a.spec['plants']['new-plant']['growth']['site_id'],'new-pot')
        with self.assertRaises(ValueError):self.e.growth_status(self.a,'plant')


if __name__=='__main__':unittest.main()
