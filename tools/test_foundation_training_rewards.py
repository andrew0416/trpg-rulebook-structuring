"""Declared reward batches use actual native consumers and completed jobs."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_foundation_training_hour as fixtures
import training_rewards as R,training_features as F,training_sessions as S,pokemon_teaching as T
import activity_jobs as J,downtime as D,world_entities as W,researcher_features as RF,pokemon_party as PARTY
from builder import build_trainer
from state_codec import dump_engine,load_engine


class RewardTests(unittest.TestCase):
 setUpClass=classmethod(fixtures.TrainingHourTests.setUpClass.__func__)
 add=fixtures.TrainingHourTests.add
 def setUp(self):
  fixtures.TrainingHourTests.setUp(self);self.a.spec['skills']['일반 지식']=5
 def policy(self,index=0):return json.loads((ROOT/'data/examples/training-rewards.json').read_text(encoding='utf8'))[index]
 def execute(self,value=None,**kw):
  return self.e.apply_training_rewards(self.a,self.ps,self.policy() if value is None else value,**dict({'safe':True,'request_id':'reward'},**kw))
 def snap(self):return dump_engine(self.e)
 def mixed(self):
  value=self.policy();value['rewards'].append({'id':'skill-edge','source':T.EDGE,'kind':'teach','edge':T.EDGE,
    'choices':{p.entity_id:{'skill':'육상'} for p in self.ps}})
  return value
 def test_one_actual_hour_pays_every_reward_and_replays_after_json_without_duplicate(self):
  value=self.mixed();before=[p.spec['tutor_points'] for p in self.ps];out=self.execute(value)
  self.assertEqual(self.e.elapsed_seconds,3600);self.assertEqual([p.spec['exp'] for p in self.ps],[47,47])
  self.assertEqual(out['eligibility']['target_limit'],5);self.assertEqual(out['eligibility']['xp_rank'],4)
  for p,tp in zip(self.ps,before):
   self.assertEqual(p.spec['tutor_points'],tp-1);self.assertEqual(F.bonus(p,'save'),3)
   self.assertEqual(p.spec[S.KEY]['applications'],['experience_training','training_regime',T.EDGE+':athletics'])
   actual=p.custom_conditions[J.CREDITS][p.spec[S.KEY]['credit_id']]
   self.assertEqual(actual['claims'],p.spec[S.KEY]['applications'])
  loaded=load_engine(self.r,json.loads(json.dumps(self.snap(),ensure_ascii=False)));actors=W.actor_index(loaded);before=dump_engine(loaded)
  self.assertEqual(out,loaded.apply_training_rewards(actors[self.a.entity_id],[actors[p.entity_id] for p in self.ps],value,safe=True,request_id='reward'))
  self.assertEqual(before,dump_engine(loaded))
  changed=deepcopy(value);changed['rewards'][1]['formula']['flat']=1
  with self.assertRaisesRegex(ValueError,'changed input'):self.execute(changed)
  with self.assertRaisesRegex(ValueError,'already received'):self.execute(value,request_id='again')
 def test_custom_formula_and_bonus_values_reach_existing_skill_consumer(self):
  before=[self.e.skill_roll(p,'육상',fixed=[1]*RF.native_plan(self.e,p,'육상')['dice_count']).modifier for p in self.ps]
  self.execute(self.policy(1));self.assertEqual([p.spec['exp'] for p in self.ps],[44,44])
  for p,modifier in zip(self.ps,before):
   self.assertEqual(F.bonus(p,'skill'),3)
   actual=self.e.skill_roll(p,'육상',fixed=[1]*RF.native_plan(self.e,p,'육상')['dice_count']);self.assertEqual(actual.modifier,modifier+3)
  self.assertEqual(self.e.elapsed_seconds,3600)
 def test_shared_completed_hour_pays_xp_bonus_once_without_new_work(self):
  self.e.complete_training_hour(self.a,self.ps,safe=True,reason='actual shared hour',request_id='hour')
  value=self.policy();value['rewards']=value['rewards'][1:];before_jobs=len(self.e._activity_jobs['jobs'])
  self.execute(value,from_training=True);self.assertEqual(self.e.elapsed_seconds,3600)
  self.assertEqual(len(self.e._activity_jobs['jobs']),before_jobs)
  for p in self.ps:self.assertEqual(p.spec[S.KEY]['applications'],['experience_training','training_regime'])
  before=self.snap()
  with self.assertRaisesRegex(ValueError,'already received'):self.execute(value,request_id='second',from_training=True)
  self.assertEqual(before,self.snap())
 def test_shared_time_cannot_publish_another_credit(self):
  self.e.complete_training_hour(self.a,self.ps,safe=True,reason='actual shared hour',request_id='hour');before=self.snap()
  with self.assertRaisesRegex(ValueError,'cannot mint'):self.execute(from_training=True)
  self.assertEqual(before,self.snap())
 def test_late_second_teaching_failure_rolls_back_xp_bonus_credit_clock_and_rng(self):
  self.ps[-1].spec['tutor_points']=0;before=self.snap()
  with self.assertRaisesRegex(ValueError,'Tutor Point'):self.execute(self.mixed())
  self.assertEqual(before,self.snap())
  self.ps[-1].spec['tutor_points']=6;out=self.execute(self.mixed());self.assertEqual(out['completed_at'],3600)
 def test_late_native_xp_failure_rolls_back_actual_group_and_can_retry(self):
  before=self.snap();native=D.gain_exp_combatant
  def fail(e,target,amount):
   result=native(e,target,amount)
   if target.entity_id==self.ps[-1].entity_id:raise ValueError('late XP reward')
   return result
  with patch.object(D,'gain_exp_combatant',side_effect=fail):
   with self.assertRaisesRegex(ValueError,'late XP reward'):self.execute()
  self.assertEqual(before,self.snap());self.execute();self.assertEqual(self.e.elapsed_seconds,3600)
 def test_missing_actual_progression_and_rejected_participant_leave_all_rewards_untouched(self):
  self.ps[-1].spec.pop('exp');before=self.snap()
  with self.assertRaises(ValueError):self.execute()
  self.assertEqual(before,self.snap());self.ps[-1].spec['exp']=40;self.ps[-1].hp=0;before=self.snap()
  with self.assertRaisesRegex(ValueError,'conscious training participant'):self.execute()
  self.assertEqual(before,self.snap())
 def test_push_effect_is_one_native_action_for_whole_reward_batch(self):
  self.a.spec.update(classes=[RF.RESEARCHER],feats=[RF.PUSHER,RF.SKILL_TRAINER],feature_choices={RF.RESEARCHER:[['pokemon_caretaking','paleontology']]})
  self.execute(self.mixed(),pushed_skills={p.entity_id:'직감' for p in self.ps})
  self.assertEqual(self.a._action_history,['free'])
  for p in self.ps:self.assertEqual(p.spec['pushed_skill']['training_source'],self.policy()['source'])
 def test_bonus_uses_actual_owner_and_expires_on_native_extended_rest(self):
  self.execute();self.assertEqual(F.bonus(self.ps[0],'evasion'),2)
  other=self.add(build_trainer(self.r,'receiver',20,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),skills={'명령':4,'일반 지식':5},extra={'edges':[]}))
  PARTY.configure(self.e,self.a,mode='unlimited',reason='real roster',roster=self.ps)
  PARTY.configure(self.e,other,mode='unlimited',reason='real empty roster',roster=[])
  PARTY.transfer(self.e,self.a,target=self.ps[0],new_owner=other,reason='actual transfer',request_id='transfer')
  self.assertEqual(F.bonus(self.ps[0],'evasion'),0);self.ps[0].spec.pop('experience_training_day')
  with self.assertRaisesRegex(ValueError,'already received'):self.e.apply_training_rewards(other,[self.ps[0]],self.policy(),safe=True,request_id='transfer-xp')
  F.extended_rest(self.e,self.a);self.assertEqual(F.bonus(self.ps[1],'save'),0)
  R.validate_world(self.e)
 def test_forged_reward_formula_source_participant_and_credit_claim_are_rejected(self):
  self.execute();record=self.a.spec[R.KEY]['reward'];original=deepcopy(record)
  for key in ('formula','source','target','claim'):
   if key=='formula':record['result']['awards'][1]['outputs'][0]['base_award']+=1
   elif key=='source':record['result']['awards'][1]['source']='edge/미용사'
   elif key=='target':record['result']['target_ids'].reverse()
   else:record['claims'][0]['credit_id']='invented-credit'
   with self.assertRaises(ValueError):R.validate_world(self.e)
   record.clear();record.update(deepcopy(original))
  R.validate_world(self.e)
 def test_native_gm_snapshot_restores_shared_receipts_and_replay(self):
  value=self.mixed();out=self.execute(value);snapshot=self.e.gm.snapshot()
  self.ps[0].spec['exp']=999;self.e.gm.restore(snapshot);before=self.snap()
  self.assertEqual(out,self.execute(value));self.assertEqual(before,self.snap())
  p=self.ps[0];credit=p.custom_conditions[J.CREDITS][p.spec[S.KEY]['credit_id']]
  job=J._row(self.e,credit['job_id']);self.assertIs(job['credits'][p.entity_id],credit)
 def test_data_regime_choices_use_shared_native_grants_and_consumption(self):
  self.e.complete_training_hour(self.a,self.ps,safe=True,reason='actual shared hour',request_id='hour')
  value=self.policy();value['rewards']=[{'id':'selected-regimes','source':F.FOCUSED,'kind':'regime','choices':{p.entity_id:[F.FOCUSED] for p in self.ps}}]
  value['eligibility']=deepcopy(value['eligibility']);value['eligibility']['daily']=None
  value['eligibility']['shared_time']['application']='training_regime'
  out=self.execute(value,from_training=True);self.assertEqual(self.e.elapsed_seconds,3600)
  for p in self.ps:self.assertEqual(F.bonus(p,'skill'),2)
  self.assertEqual(out['awards'][0]['kind'],'regime');before=self.snap()
  with self.assertRaisesRegex(ValueError,'already consumed'):self.execute(value,from_training=True,request_id='other-regime')
  self.assertEqual(before,self.snap())
 def test_invalid_source_formula_family_and_duration_reject_without_work(self):
  before=self.snap()
  for change in ('formula','source','duplicate','duration','daily'):
   value=self.policy()
   if change=='formula':value['rewards'][1]['formula']['level_divisor']=True
   elif change=='source':value['rewards'][2]['source']='feat/nonexistent-training-source'
   elif change=='duplicate':value['rewards'].append(deepcopy(value['rewards'][1]))
   elif change=='duration':value['seconds']=60
   else:value['eligibility']['daily']=None
   with self.assertRaises(ValueError):self.execute(value)
   self.assertEqual(before,self.snap())


if __name__=='__main__':unittest.main()
