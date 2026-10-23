"""C11-037: explicitly adopted salon effects end at their recipient's next rest.

The two numeric/type declarations below are explicit GM fixture choices, never
claimed as missing canonical Stylish Grooming/Elaborate Masquerade rules.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
import campaign_rewards as REWARDS
import combat_timing as TIMING
import downtime as DT
import effect_lifetime_policy as LIFETIME
import effect_lifetimes as LIFE
import effects as FX
import frequency as FREQ


class SalonExpiryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r=Rules(ROOT,ruleset='core')
        cls.source={'file':'input/ch11-running-the-game.md',
            'sha256':sha256((ROOT/'input/ch11-running-the-game.md').read_bytes()).hexdigest()}
        cls.services={'스타일리시한 단장':'authored/salon/stylish','정교한 가장':'authored/salon/masquerade'}
        cls.r.register_source_policy_definitions([
            {'id':uid,'title':name,'source':cls.source,'locator':{'lines':[1418,1420]},
             'tags':[],'rationale':'GM explicitly adopts the fixture effect definition for this named service; no class-feature alias.'}
            for name,uid in cls.services.items()])

    def setUp(self):
        self.e=Engine(self.r,37,session_frequency=True,defer_session_refresh=False)
        def actor(uid,kind='trainer'):
            return Combatant(self.r,{'id':uid,'name':uid,'kind':kind,'level':10,
                'stats':dict(hp=20,atk=5,**{'def':5},spa=5,spd=5,spe=5),
                'types':['노말'],'abilities':[],'moves':[],'money':5000,'items':{}})
        self.payer=actor('trainer/payer');self.provider=actor('trainer/salon-provider')
        self.target=actor('pokemon/recipient','pokemon');self.other=actor('trainer/other-recipient')
        self.e.everyone=self.e.gm.everyone=[self.payer,self.provider,self.target,self.other]

    def document(self,service='스타일리시한 단장',effects=None):
        if effects is None:
            effects=[{'type':'evasion_mod','value':2 if service=='스타일리시한 단장' else 3,
                'target':'target','until':{'event':'extended_rest','owner':'target','after':1}}]
        return {'schema':1,'id':'gm/salon/'+self.services[service],'variants':[
            {'rule_id':self.services[service],'source':deepcopy(self.source),'inputs':{},'values':{'effects':effects}}]}

    def buy(self,event_id='grooming',**options):
        service=options.get('service','스타일리시한 단장')
        args=dict(event_id=event_id,provider=self.provider,target=self.target,service=service,
            document=self.document(service if service in self.services else '스타일리시한 단장'),
            reason='GM explicitly adopts this service definition and confirms this NPC salon offers it')
        args.update(options)
        return self.e.campaign_reward(self.payer,'salon',**args)

    def snapshot(self):return deepcopy(self.e.export_state())
    def restore(self):
        self.e=Engine.import_state(self.r,json.loads(json.dumps(self.e.export_state())))
        index={c.entity_id:c for c in self.e.everyone}
        self.payer=index['trainer/payer'];self.provider=index['trainer/salon-provider']
        self.target=index['pokemon/recipient'];self.other=index['trainer/other-recipient']

    def test_both_actual_selected_services_pay_and_change_native_recipient_evasion(self):
        before=[c.evasion('물리') for c in (self.target,self.other)]
        docs=[self.document(name) for name in self.services]
        for i,((service,uid),recipient) in enumerate(zip(self.services.items(),(self.target,self.other))):
            original=deepcopy(docs[i]);row=self.buy('service'+str(i),service=service,target=recipient,document=docs[i])
            self.assertEqual(recipient.evasion('물리'),before[i]+(2 if i==0 else 3))
            self.assertEqual((row['provider'],row['recipient'],row['service'],row['price']),
                (self.provider.entity_id,recipient.entity_id,service,1000))
            self.assertEqual(row['definition_source'],uid)
            self.assertEqual(self.e.source_policy_execution(row['execution_id'])['values'],original['variants'][0]['values'])
            self.assertEqual(docs[i],original)
            self.assertEqual(REWARDS.events(self.e)['service'+str(i)],row)
            self.assertEqual(row['occurrences'],[TIMING.records(recipient)[0]['effect_occurrence']])
        self.assertEqual(self.payer.spec['money'],3000);self.assertEqual(self.payer.spec['items'],{})
        self.assertFalse(self.target.spec.get('feats'));self.assertFalse(self.provider.spec.get('feats'))

    def test_only_recipient_actual_four_hour_milestone_ends_the_service(self):
        baseline=self.target.evasion('물리');self.buy()
        self.e.advance_time(24*3600)
        DT.new_day(self.target)
        self.e.begin_session('first');self.e.begin_session('second')
        self.e.end_scene()
        DT.extended_rest(self.e,self.provider,4,rest_id='provider-sleep')
        DT.extended_rest(self.e,self.other,4,rest_id='other-sleep')
        self.assertEqual(self.target.evasion('물리'),baseline+2)
        DT.rest(self.e,self.target,239,rest_id='actual-recipient-sleep')
        self.assertEqual(self.target.evasion('물리'),baseline+2)
        DT.rest(self.e,self.target,1,rest_id='actual-recipient-sleep')
        self.assertEqual(self.target.evasion('물리'),baseline)
        history=self.target.custom_conditions['effect_lifetime_history']
        self.assertEqual(len(history),1);self.assertEqual(history[0]['event'],{'kind':'extended_rest'})
        self.assertEqual(history[0]['state'],'expired')
        DT.rest(self.e,self.target,10,rest_id='actual-recipient-sleep')
        self.assertEqual(len(self.target.custom_conditions['effect_lifetime_history']),1)

    def test_json_restore_keeps_real_effect_owner_and_preserves_other_source_contributions(self):
        type_effect={'type':'type_change','add_type':'물','target':'target',
            'until':{'event':'extended_rest','owner':'target','after':1}}
        row=self.buy(service='정교한 가장',document=self.document('정교한 가장',[type_effect]))
        independent={'type':'evasion_mod','value':4,'target':'target','duration':{'seconds':24*3600}}
        self.assertFalse(FX.run_effects(self.e,self.provider,self.target,[independent],{'hit':True},'gm/independent').pending)
        self.assertIn('물',self.target.types);self.restore()
        installed=next(record for record in TIMING.records(self.target) if record['source']==row['definition_source'])
        self.assertIs(installed['lifetime_actor'],self.provider)
        self.assertIs(installed['lifetime_target'],self.target)
        self.assertEqual(REWARDS.events(self.e)['grooming'],row)
        DT.extended_rest(self.e,self.other,4,rest_id='other');self.assertIn('물',self.target.types)
        DT.extended_rest(self.e,self.target,4,rest_id='recipient')
        self.assertEqual(self.target.types,['노말']);self.assertEqual(LIFE.numeric(self.target,'evasion_modifier'),4)
        self.assertEqual([record['source'] for record in TIMING.records(self.target)],['gm/independent'])
        self.restore();self.assertEqual(self.target.types,['노말'])

    def test_interrupted_bouts_and_new_service_never_borrow_old_rest_credit(self):
        baseline=self.target.evasion('물리');self.buy()
        DT.extended_rest(self.e,self.target,2,rest_id='first')
        DT.extended_rest(self.e,self.target,2,rest_id='second')
        self.assertEqual(self.target.evasion('물리'),baseline+2)
        DT.extended_rest(self.e,self.target,2,rest_id='second')
        self.assertEqual(self.target.evasion('물리'),baseline)
        self.buy('second-service');self.assertNotIn('rest_interval',self.target.spec)
        DT.rest(self.e,self.target,1,rest_id='second')
        self.assertEqual(self.target.evasion('물리'),baseline+2)
        DT.interrupt_rest(self.target)
        DT.rest(self.e,self.target,239,rest_id='fresh')
        self.assertEqual(self.target.evasion('물리'),baseline+2)
        DT.rest(self.e,self.target,1,rest_id='fresh')
        self.assertEqual(self.target.evasion('물리'),baseline)

    def test_missing_effect_authority_aliases_lifetimes_and_funds_refuse_without_payment(self):
        before=self.snapshot()
        invalid=[]
        for effect in ({'type':'heal','amount':1,'target':'target'},
                       {'type':'evasion_mod','value':2,'target':'self','until':{'event':'extended_rest','owner':'target','after':1}},
                       {'type':'evasion_mod','value':2,'target':'target','until':{'event':'extended_rest','owner':'user','after':1}},
                       {'type':'evasion_mod','value':2,'target':'target','until':{'event':'extended_rest','owner':'target','after':2}},
                       {'type':'evasion_mod','value':2,'target':'target','until':{'event':'scene_end'}},
                       {'type':'not_implemented','target':'target','until':{'event':'extended_rest','owner':'target','after':1}}):
            invalid.append({'document':self.document(effects=[effect])})
        invalid.extend([{'document':self.document(effects=[])},{'document':self.document('정교한 가장')},
            {'service':'근사한 단장'},{'provider':self.target},{'provider':object()},
            {'target':object()},{'reason':''}])
        for options in invalid:
            with self.subTest(options=repr(options)),self.assertRaises((ValueError,AttributeError)):self.buy(**options)
            self.assertEqual(before,self.snapshot())
        self.payer.spec['money']=999;before=self.snapshot()
        with self.assertRaisesRegex(ValueError,'insufficient'):self.buy()
        self.assertEqual(before,self.snapshot())

    def test_pending_gm_choice_source_changes_and_duplicate_event_keep_payment_atomic(self):
        doc=self.document();variant=doc['variants'][0]
        variant['inputs']={'bonus':{'type':'integer','authority':'gm','question':'GM chosen service effect value'}}
        variant['values']['effects'][0]['value']={'$input':'bonus'}
        before=self.snapshot()
        pending=self.buy(document=doc)
        self.assertEqual(pending['status'],'PolicyInputsRequired');self.assertEqual(before,self.snapshot())
        stale=self.document();stale['variants'][0]['source']['sha256']='0'*64
        with self.assertRaises(ValueError):self.buy(document=stale)
        self.assertEqual(before,self.snapshot())
        original=self.r._selected_rule
        with patch.object(self.r,'_selected_rule',side_effect=lambda uid,**kwargs:'unselected/salon' if uid==REWARDS.SALON_SOURCE else original(uid,**kwargs)):
            with self.assertRaises(ValueError):self.buy()
        self.assertEqual(before,self.snapshot())
        row=self.buy(document=doc,decisions={'bonus':{'value':2,'reason':'GM adopts this service effect'}})
        self.assertEqual(row['price'],1000);before=self.snapshot()
        with self.assertRaisesRegex(ValueError,'already'):self.buy()
        self.assertEqual(before,self.snapshot())

    def test_late_paid_service_failure_rolls_back_effects_money_receipt_and_rest(self):
        DT.rest(self.e,self.target,15,rest_id='before-service');before=self.snapshot()
        original=REWARDS.put
        def fail(engine,event_id,row):
            if row['kind']=='salon':
                self.assertEqual(row['price'],1000)
                self.assertEqual(engine.gm.everyone[0].spec['money'],4000)
                self.assertTrue(any(TIMING.records(c) for c in engine.gm.everyone))
                engine.rng.random()
                raise ValueError('observed late salon receipt failure')
            return original(engine,event_id,row)
        with patch.object(REWARDS,'put',side_effect=fail):
            with self.assertRaisesRegex(ValueError,'late salon receipt'):self.buy()
        self.assertEqual(before,self.snapshot())
        self.buy();self.assertNotIn('rest_interval',self.target.spec)

    def test_late_rest_failure_rolls_back_clock_expiry_and_existing_rest_benefits(self):
        self.buy();self.target.spec['ap_removed']=2
        DT.rest(self.e,self.target,239,rest_id='sleep');before=self.snapshot()
        original=FREQ.restore_daily_moves
        def fail(engine,actor,**options):
            original(engine,actor,**options)
            self.assertFalse(TIMING.records(actor));self.assertEqual(actor.spec['ap_removed'],0)
            raise ValueError('observed late extended-rest benefit failure')
        with patch.object(FREQ,'restore_daily_moves',side_effect=fail):
            with self.assertRaisesRegex(ValueError,'late extended-rest'):DT.rest(self.e,self.target,1,rest_id='sleep')
        self.assertEqual(before,self.snapshot())
        DT.rest(self.e,self.target,1,rest_id='sleep')
        self.assertFalse(TIMING.records(self.target));self.assertEqual(self.target.spec['ap_removed'],0)


if __name__=='__main__':unittest.main()
