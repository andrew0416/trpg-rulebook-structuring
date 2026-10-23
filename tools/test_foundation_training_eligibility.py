"""Shared admission data and actual native training consumers."""
from pathlib import Path
from copy import deepcopy,copy
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_foundation_policy_training as fixtures
from builder import build_pokemon,build_trainer
import training_eligibility as E,training_features as T,pokemon_progression as P
import pokemon_party as PARTY,pokemon_entities as ENTITIES,downtime as D,world_entities as W
from state_codec import dump_engine,load_engine


class EligibilityTests(unittest.TestCase):
 setUpClass=classmethod(fixtures.PolicyTrainingTests.setUpClass.__func__)
 add=fixtures.PolicyTrainingTests.add
 def setUp(self):
  fixtures.PolicyTrainingTests.setUp(self)
  self.a.spec.update(edges=['edge/미용사','edge/비스트-마스터'],feats=list(T.RULES))
  self.a.spec['skills'].update({'명령':2,'일반 지식':5,'포켓몬학':4,'협박':5,'매력':3,'육상':3})
  self.a.spec['items']['미용사 킷']=1
  self.ps += [self.add(build_pokemon(self.r,'이상해씨',5,name='extra'+str(i),moves=[],abilities=[],extra={'trainer_id':self.a.entity_id})) for i in range(4)]
  for pokemon in self.ps:ENTITIES.observe_loyalty(self.e,pokemon,3,reason='actual willing training participant')
 def policy(self,index=0):return json.loads((ROOT/'data/examples/training-eligibility.json').read_text(encoding='utf8'))[index]
 def plan(self,targets=None,value=None,**observations):
  return self.e.plan_training_eligibility(self.a,self.ps if targets is None else targets,self.policy() if value is None else value,**dict({'safe':True},**observations))
 def snap(self):return dump_engine(self.e)
 def test_external_capacity_and_xp_formulas_match_actual_native_csv_consumer(self):
  before=self.snap();plan=self.plan(self.ps[:5],self.policy(1))
  self.assertEqual((plan['target_limit'],plan['xp_rank']),(5,2));self.assertEqual(before,self.snap())
  self.e.pokemon_activity(self.a,'groom',targets=self.ps,safe=True)
  result=self.e.pokemon_activity(self.a,'experience_training',targets=self.ps[:5],from_grooming=True,bonus_skill='일반 지식',grooming_policy='csv_target_limit')
  self.assertEqual((result['limit'],result['xp_rank'],result['awards']),(5,2,[2]*5))
  self.assertEqual(result['eligibility']['rank_plans'],result['rank_plans']);self.assertEqual(self.e.elapsed_seconds,3600)
  self.assertEqual(self.plan()['target_limit'],6)
  with self.assertRaises(ValueError):self.plan(self.ps[:1],self.policy(1))
 def test_declared_session_limit_is_independent_of_xp_capacity(self):
  value=self.policy();value['session_limit']=3;before=self.snap()
  with self.assertRaises(ValueError):self.plan(value=value)
  self.assertEqual(self.plan(self.ps[:3],value)['target_limit'],3);self.assertEqual(before,self.snap())
  self.e.complete_training_hour(self.a,self.ps,safe=True,reason='six real session participants',request_id='hour')
  self.e.pokemon_activity(self.a,'experience_training',targets=self.ps[:2],from_training=True)
  before=self.snap()
  with self.assertRaisesRegex(ValueError,'daily training target limit'):self.e.pokemon_activity(self.a,'experience_training',targets=self.ps[2:3],from_training=True)
  self.assertEqual(before,self.snap());self.assertEqual(self.e.elapsed_seconds,3600)
 def test_invalid_actual_targets_and_safety_do_not_mutate_or_roll(self):
  before=self.snap()
  for targets in ([],[self.ps[0],self.ps[0]],[copy(self.ps[0])]):
   with self.assertRaises(ValueError):self.plan(targets)
   self.assertEqual(before,self.snap())
  for safe in (False,None,1):
   with self.assertRaises(ValueError):self.plan(safe=safe)
   self.assertEqual(before,self.snap())
  other=self.add(build_trainer(self.r,'other-observed-owner',20,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),skills={'명령':3},extra={'edges':[]}))
  self.ps[0].spec['trainer_id']=other.entity_id;before=self.snap()
  with self.assertRaisesRegex(ValueError,'different trainer'):self.plan(self.ps[:1])
  self.assertEqual(before,self.snap())
 def test_fainted_participant_cannot_spend_completed_safe_credit(self):
  self.e.complete_training_hour(self.a,self.ps,safe=True,reason='observed safe hour',request_id='hour')
  self.ps[-1].hp=0;before=self.snap()
  with self.assertRaisesRegex(ValueError,'conscious training participant'):self.plan(from_training=True)
  self.assertEqual(before,self.snap())
 def test_shared_hour_is_observed_without_consumption_then_native_regime_uses_it(self):
  self.e.complete_training_hour(self.a,self.ps,safe=True,reason='shared actual hour',request_id='hour')
  before=self.snap();plan=self.plan(from_training=True)
  self.assertEqual(len(plan['completed_training_credits']),6);self.assertEqual(before,self.snap())
  out=self.e.train_pokemon(self.a,[(p,[T.AGILITY]) for p in self.ps],minutes=30,reason='apply from the actual hour',request_id='regime',from_training=True)
  self.assertEqual((self.e.elapsed_seconds,out['time_cost_seconds']),(3600,0));self.assertEqual(out['eligibility']['target_limit'],6)
  before=self.snap()
  with self.assertRaisesRegex(ValueError,'already consumed'):self.plan(from_training=True)
  self.assertEqual(before,self.snap())
 def test_real_transfer_and_restore_cannot_refresh_target_daily_xp(self):
  self.e.pokemon_activity(self.a,'experience_training',targets=self.ps[:1],safe=True)
  other=self.add(build_trainer(self.r,'receiver',20,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),skills={'명령':4},extra={'edges':[]}))
  PARTY.configure(self.e,self.a,mode='unlimited',reason='real roster',roster=self.ps)
  PARTY.configure(self.e,other,mode='unlimited',reason='real empty roster',roster=[])
  PARTY.transfer(self.e,self.a,target=self.ps[0],new_owner=other,reason='real transfer',request_id='transfer')
  self.ps[0].spec.pop('experience_training_day');before=self.snap()
  with self.assertRaisesRegex(ValueError,'already received'):self.e.pokemon_activity(other,'experience_training',targets=self.ps[:1],safe=True)
  self.assertEqual(before,self.snap())
  loaded=load_engine(self.r,self.snap());actors=W.actor_index(loaded);before=dump_engine(loaded)
  with self.assertRaisesRegex(ValueError,'already received'):loaded.pokemon_activity(actors[other.entity_id],'experience_training',targets=[actors[self.ps[0].entity_id]],safe=True)
  self.assertEqual(before,dump_engine(loaded))
 def test_elapsed_seconds_do_not_refresh_day_but_real_next_day_does(self):
  self.e.pokemon_activity(self.a,'experience_training',targets=self.ps[:1],safe=True);self.e.advance_time(86400,[self.a,*self.ps])
  before=self.snap()
  with self.assertRaises(ValueError):self.e.pokemon_activity(self.a,'experience_training',targets=self.ps[:1],safe=True)
  self.assertEqual(before,self.snap())
  for actor in (self.a,*self.ps):D.new_day(actor)
  result=self.e.pokemon_activity(self.a,'experience_training',targets=self.ps[:1],safe=True)
  self.assertEqual((result['eligibility']['day'],result['eligibility']['daily_used']),(1,0))
 def test_missing_provider_invalid_types_and_conflated_purposes_reject(self):
  before=self.snap()
  for mutation in ('limit','multiplier','purpose','source','credit'):
   value=self.policy(1);observations={}
   if mutation=='limit':value['session_limit']=True
   elif mutation=='multiplier':value['capacity']['multiplier']=0
   elif mutation=='purpose':value['xp_rank']['purpose']=value['capacity']['purpose']
   elif mutation=='source':value['source']='edge/missing-source'
   else:observations={'from_grooming':True,'from_training':True}
   with self.assertRaises((ValueError,KeyError)):self.plan(self.ps[:1],value,**observations)
   self.assertEqual(before,self.snap())
  self.a.spec['edges']=[];before=self.snap()
  with self.assertRaisesRegex(ValueError,'acquired example provider'):self.plan(self.ps[:1],self.policy(1))
  self.assertEqual(before,self.snap())


if __name__=='__main__':unittest.main()
