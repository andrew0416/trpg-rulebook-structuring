"""C10-036: a native summon reaches actual relationship/ownership consumers."""
from pathlib import Path
from copy import deepcopy
from random import Random
from unittest.mock import patch
import json,unittest

ROOT=Path(r'D:/trpg-rulebook-structuring/ptk-structure-experiment')
from engine import Rules,Engine,Combatant
from builder import build_pokemon,build_trainer
from state_codec import dump_engine,load_engine
import csv_item_capability_contracts as CAP
import world_entities as W,pokemon_entities as P,pokemon_party as PARTY,state_grants as G,downtime as D


class CoreGatherUnownTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='core')
    def setUp(self):
        self.e=Engine(self.r,seed=360)
        self.a=Combatant(self.r,build_trainer(self.r,'summoner trainer',30,
            {'hp':30,'atk':10,'def':10,'spa':10,'spd':10,'spe':10},
            extra={'id':'trainer/summoner','skills':{'매력':'숙련'},'items':{'몬스터볼':2}}))
        self.p=Combatant(self.r,build_pokemon(self.r,'안농',20,
            extra={'id':'pokemon/summoner','trainer_id':self.a.entity_id}))
        self.q=Combatant(self.r,build_pokemon(self.r,'피카츄',30,moves=[],abilities=[],wild=True,
            extra={'id':'pokemon/other'}))
        self.e.everyone=self.e.gm.everyone=[self.a,self.p,self.q]
    def summon(self,uid='pokemon/random-unown',**options):
        options.setdefault('selection',{'species_id':'pokemon/안농','form':'A','reason':'GM observed random Unown form A'})
        options.setdefault('location',{'kind':'grid','cell':[1,0]})
        options.setdefault('side','observed-independent-unown')
        options.setdefault('side_reason','GM independently observes this Unown battle affiliation')
        return CAP.summon_unown(self.e,self.p,entity_id=uid,**options)
    def act(self,activity,**options):return self.e.pokemon_activity(self.a,activity,**options)
    def policy(self):return self.act('party_policy',mode='unlimited',reason='GM campaign carrying policy',roster=[self.p])
    def assert_unowned(self,u):
        self.assertEqual(u.spec['species'],'pokemon/안농')
        self.assertTrue(u.spec['wild']);self.assertFalse(u.captured)
        self.assertNotEqual(u.side,self.p.side)
        self.assertNotIn('trainer_id',u.spec);self.assertIsNone(P.loyalty_value(u))
        self.assertFalse(P.disposition_projection(u,'trainer:'+self.a.entity_id)['known'])
        self.assertNotIn(u.entity_id,self.a.spec.get('pokemon_registry',{}))
    def state(self):
        return deepcopy((self.e.rng.getstate(),self.e.elapsed_seconds,
            [(x.entity_id,x.spec,getattr(x,'budget',None),x.captured) for x in W.actors(self.e)]))
    def test_native_standard_summon_has_real_sheet_without_relationship_or_command_after_restore(self):
        self.p.spec.pop('trainer_id');self.p.spec['wild']=True;self.p.side=self.p.spec['side']='wild'
        self.e.begin_encounter([self.a,self.p,self.q]);self.e.start_round([self.a,self.p,self.q]);self.e.start_of_turn(self.p)
        out=self.summon(fixed_d8=[8,8]);u=out['pokemon']
        self.assertIs(W.actor_index(self.e)[u.entity_id],u)
        self.assertIn(u,self.e.everyone);self.assertIn(u,self.e.gm.everyone)
        self.assertEqual(u.level,16);self.assertGreater(u.max_hp,0);self.assertTrue(u.moves)
        self.assertEqual(u.location,{'kind':'grid','cell':(1,0)});self.assertTrue(u.on_field)
        self.assertEqual(self.p.budget['standard'],0)
        self.assertEqual(u.spec['gather_unown_origin']['selection'],out['receipt']['selection'])
        self.assert_unowned(u)
        import effect_contracts as CONTRACTS
        self.assertFalse(CONTRACTS.condition_text(self.e,self.p,u,'target is ally',{}))
        with self.assertRaises(ValueError):self.act('command_move',pokemon=u,target=self.q,move_id='struggle')
        self.e.end_of_turn(self.p);self.e.end_encounter(round_elapsed_seconds=0)
        with self.assertRaisesRegex(ValueError,'GM-selected disposition'):self.act('befriend',target=u,fixed=[6]*4)
        self.act('party_policy',mode='unlimited',reason='GM campaign policy',roster=[])
        self.assertNotIn(u.entity_id,self.act('party_registry')['pokemon'])
        with self.assertRaises(ValueError):self.act('party_policy',mode='unlimited',reason='summon is not ownership',roster=[u])
        saved=json.loads(json.dumps(dump_engine(self.e)))
        self.e=load_engine(self.r,saved);index=W.actor_index(self.e)
        self.a,self.p,self.q,u=[index[x.entity_id] for x in (self.a,self.p,self.q,u)]
        self.assert_unowned(u)
        self.assertEqual(self.p.spec[CAP.STATE]['receipts'][-1],out['receipt'])
    def test_gm_befriend_then_independent_capture_enters_real_party_and_command(self):
        u=self.summon(fixed_d8=[1,1])['pokemon'];self.policy()
        self.act('disposition_ruling',target=u,disposition='중립',reason='GM independently observes this relationship')
        result=self.act('befriend',target=u,fixed=[3]*4)
        self.assertEqual(result['disposition'],'우호적')
        self.assertEqual(P.disposition_projection(u,'trainer:'+self.a.entity_id)['value'],'우호적')
        self.assertFalse(P.disposition_projection(u,'trainer:someone-else')['known'])
        self.assertTrue(u.spec['wild']);self.assertFalse(u.captured);self.assertNotIn('trainer_id',u.spec)
        self.assertEqual(u.spec['disposition_history'][-1]['after'],'우호적')
        with self.assertRaises(ValueError):self.act('command_move',pokemon=u,target=self.q,move_id='struggle')
        self.assertTrue(self.e.throw_ball(self.a,u,fixed_accuracy=20,fixed_capture=20))
        row=self.act('party_registry')['pokemon'][u.entity_id]
        self.assertEqual(row['owner_id'],self.a.entity_id);self.assertEqual(row['location'],'carried')
        self.assertEqual(u.spec['trainer_id'],self.a.entity_id);self.assertTrue(u.captured)
        self.e.gm.observe_loyalty(u,3,reason='GM independently judges the now-captured relationship')
        self.e.begin_encounter([self.a,u,self.q]);self.e.start_round([self.a,u,self.q]);self.e.start_of_turn(u)
        result=self.act('command_move',pokemon=u,target=self.q,move_id='struggle',set_damage=True)
        self.assertEqual(result['status'],'submitted');self.assertTrue(result['obedience']['obeys'])
        self.assertEqual(u.move_uses.get('struggle'),1);self.assertEqual(u.budget['standard'],0)
    def test_actual_week_survives_day_session_and_codec_before_next_summon(self):
        first=self.summon(fixed_d8=[1,8]);self.assertEqual(first['pokemon'].level,9)
        D.new_day(self.p)
        self.e.session_frequency=True;self.e.defer_session_refresh=False
        for n in range(5):self.e.begin_session('unown/session/'+str(n),[self.a,self.p,self.q])
        self.e.advance_time(604799,[])
        import resolution_transaction as TX
        row=self.p.spec[CAP.STATE]['receipts'][0];original=deepcopy(row)
        for key,value in (('at',self.e.elapsed_seconds+1),('unknown_index',len(self.e.unresolved_time_intervals)+1)):
            row[key]=value;row['sha256']=TX.request_fingerprint({k:v for k,v in row.items() if k!='sha256'})
            with self.assertRaisesRegex(ValueError,'future time'):CAP.validate_world(self.e,W.actor_index(self.e))
            with self.assertRaisesRegex(ValueError,'world reference integrity'):dump_engine(self.e)
            row.clear();row.update(deepcopy(original))
        self.e=load_engine(self.r,json.loads(json.dumps(dump_engine(self.e))))
        index=W.actor_index(self.e);self.a,self.p,self.q=[index[x.entity_id] for x in (self.a,self.p,self.q)]
        before=self.state()
        with self.assertRaises(ValueError):self.summon('pokemon/too-soon',fixed_d8=[8,8])
        self.assertEqual(before,self.state())
        self.e.advance_time(1,[])
        second=self.summon('pokemon/next-week',fixed_d8=[8,8])
        self.assertEqual(second['pokemon'].level,16)
        self.assertNotEqual(first['pokemon'].entity_id,second['pokemon'].entity_id)
        self.assert_unowned(second['pokemon'])
    def test_real_d8_rng_and_unchanged_csv_edition_frequency(self):
        expected=Random();expected.setstate(self.e.rng.getstate());faces=[expected.randint(1,8),expected.randint(1,8)]
        out=self.summon()
        self.assertEqual(out['receipt']['d8'],faces);self.assertEqual(out['pokemon'].level,sum(faces))
        self.assertEqual(self.e.rng.getstate(),expected.getstate())
        self.assertEqual(CAP.hidden_power_frequency(self.p,'Scene'),'Scene')
        self.assertNotIn('gather_unown_session',self.p.spec[CAP.STATE])
        self.assertNotIn('hidden_power_frequency',self.p.spec[CAP.STATE])
    def test_source_live_actor_identity_and_selection_fail_before_spawn_cost_or_roll(self):
        before=self.state()
        with patch.object(self.r,'_selected_rule',return_value='capability/other-edition'):
            with self.assertRaises(ValueError):self.summon()
        self.assertEqual(before,self.state())
        for changes in ({'level':19},{'capabilities':[]},{'kind':'trainer'}):
            key,value=next(iter(changes.items()));oldspec=deepcopy(self.p.spec.get(key));old=getattr(self.p,key,None)
            self.p.spec[key]=value
            if key in ('level','kind'):setattr(self.p,key,value)
            invalid=self.state()
            with self.assertRaises(ValueError):self.summon()
            self.assertEqual(invalid,self.state());self.p.spec[key]=oldspec
            if key in ('level','kind'):setattr(self.p,key,old)
        detached=Combatant(self.r,deepcopy(self.p.spec));before=self.state()
        with self.assertRaises(ValueError):CAP.summon_unown(self.e,detached,entity_id='fresh',selection={'species_id':'pokemon/안농','form':'B','reason':'random'},location={'kind':'unknown'},side='wild',side_reason='observed')
        self.assertEqual(before,self.state())
        W.register_object(self.e,'physical/collision',kind='physical_object',location={'kind':'unknown'},reason='actual physical identity')
        for uid,options in [(self.p.entity_id,{}),(self.a.entity_id,{}),('physical/collision',{}),('',{}),
                ('fresh',{'selection':{'species_id':'pokemon/피카츄','form':'A','reason':'random'}}),
                ('fresh',{'selection':{'species_id':'pokemon/안농','form':'','reason':'random'}}),
                ('fresh',{'selection':{'species_id':'pokemon/안농','form':'A','reason':''}}),
                ('fresh',{'location':{'kind':'invented'}}),
                ('fresh',{'side':''}),('fresh',{'side_reason':''}),
                ('fresh',{'fixed_d8':[8]}),('fresh',{'fixed_d8':[True,2]}),('fresh',{'fixed_d8':[1,9]})]:
            before=self.state()
            with self.subTest(uid=uid,options=options):
                with self.assertRaises(ValueError):self.summon(uid,**options)
                self.assertEqual(before,self.state());self.assertNotIn('fresh',W.actor_index(self.e))
    def test_unavailable_standard_and_late_registration_failure_do_not_create_or_spend_use(self):
        self.e.begin_encounter([self.a,self.p,self.q]);self.e.start_round([self.a,self.p,self.q]);self.e.start_of_turn(self.p)
        self.p.budget['standard']=0;before=self.state()
        self.assertEqual(self.summon()['reason'],'no_standard_action')
        self.assertEqual(before,self.state());self.assertNotIn('pokemon/random-unown',W.actor_index(self.e))
        self.p.budget['standard']=1;before=self.state()
        with patch.object(Engine,'register_abilities',side_effect=RuntimeError('late actual registration failure')):
            with self.assertRaises(RuntimeError):self.summon()
        self.assertEqual(before,self.state());self.assertNotIn(CAP.STATE,self.p.spec)
        self.assertNotIn('pokemon/random-unown',W.actor_index(self.e))


if __name__=='__main__':unittest.main()
