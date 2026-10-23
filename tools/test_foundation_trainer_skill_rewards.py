"""Restricted skill reward facts: ordinary dice/ownership stay separate."""
from pathlib import Path
from hashlib import sha256
from copy import deepcopy
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
from builder import build_trainer
from state_codec import dump_engine,load_engine,StateCodecError
import world_entities as W

class SkillRewardTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')
 def setUp(self):
  self.e=Engine(self.rules,23);self.c=Combatant(self.rules,build_trainer(self.rules,'skill-rewards',1,{'hp':10,'atk':10,'def':10,'spa':10,'spd':10,'spe':10},abilities=[]))
  self.e.everyone=self.e.gm.everyone=[self.c]
 def grow(self,amount=110):return self.e.award_trainer_progression(self.c,kind='experience',amount=amount,request_id='growth',reason='observed growth')
 def test_all_threshold_rewards_persist_and_do_not_change_skill_ranks(self):
  original=deepcopy(self.c.spec.get('skills',{}));result=self.grow()
  rows=self.e.pending_trainer_skill_rewards(self.c)
  self.assertEqual([(r['level'],r['max_rank'],r['excluded_rank']) for r in rows],[(2,3,4),(6,4,5),(12,5,6)])
  self.assertEqual(self.c.spec.get('skills',{}),original)
  self.assertEqual(result['skill_reward_levels'],[2,6,12]);before=dump_engine(self.e)
  self.grow();self.assertEqual(dump_engine(self.e),before)
  rows[0]['max_rank']=99;self.assertEqual(self.e.pending_trainer_skill_rewards(self.c)[0]['max_rank'],3)
  restored=load_engine(self.rules,dump_engine(self.e));c=W.actor_index(restored)[self.c.entity_id]
  self.assertEqual(restored.pending_trainer_skill_rewards(c),self.e.pending_trainer_skill_rewards(self.c))
 def test_current_level_and_legacy_growth_do_not_invent_reward_history(self):
  self.c.spec['level']=12;self.assertEqual(self.e.pending_trainer_skill_rewards(self.c),[])
  self.c.spec['level']=1;self.grow();self.c.spec['trainer_progression_events']['growth']['result'].pop('skill_reward_levels')
  restored=load_engine(self.rules,dump_engine(self.e));c=W.actor_index(restored)[self.c.entity_id]
  self.assertEqual(restored.pending_trainer_skill_rewards(c),[])
 def test_changed_threshold_record_is_rejected_by_query_replay_and_save(self):
  self.grow();self.c.spec['trainer_progression_events']['growth']['result']['skill_reward_levels']=[2,6]
  with self.assertRaisesRegex(ValueError,'skill reward thresholds'):self.e.pending_trainer_skill_rewards(self.c)
  with self.assertRaisesRegex(ValueError,'skill reward thresholds'):self.grow()
  with self.assertRaises(StateCodecError):dump_engine(self.e)
 def test_external_condition_reads_actual_reward_limit_and_denies_unlocked_rank(self):
  path='input/ch02-character-creation.md'
  row={'rule_id':'ch02-character-creation/캐릭터-발전','source':{'file':path,'sha256':sha256((ROOT/path).read_bytes()).hexdigest()},
   'inputs':{'limit':{'type':'integer','authority':'state','question':'Actual restricted reward cap',
    'binding':{'subject':'target','field':'skill_reward_max_rank','milestone':2}},
    'wanted':{'type':'integer','authority':'context','question':'Proposed rank'}},
   'when':{'op':'le','left':{'$input':'wanted'},'right':{'$input':'limit'}},
   'values':{'effects':[{'type':'stage_change','stat':'atk','delta':1,'target':'self'}]}}
  doc={'schema':1,'id':'skill-reward-condition','variants':[row]}
  before=dump_engine(self.e)
  pending=self.e.execute_source_policy_effects(self.c,self.c,doc,context={'wanted':3})
  self.assertEqual(pending['status'],'PolicyInputsRequired');self.assertEqual(dump_engine(self.e),before)
  self.grow(10);before=dump_engine(self.e)
  rejected=self.e.execute_source_policy_effects(self.c,self.c,doc,context={'wanted':4})
  self.assertEqual(rejected['status'],'PolicyNotApplicable');self.assertEqual(dump_engine(self.e),before)
  allowed=self.e.execute_source_policy_effects(self.c,self.c,doc,context={'wanted':3})
  self.assertEqual(allowed['input_values']['limit'],3);self.assertEqual(allowed['status'],'PolicyEffectsCompleted')
  row['inputs']['limit']['binding']['milestone']=5
  with self.assertRaisesRegex(ValueError,'known skill reward milestone'):self.e.execute_source_policy_effects(self.c,self.c,doc,context={'wanted':3})

if __name__=='__main__':unittest.main()
