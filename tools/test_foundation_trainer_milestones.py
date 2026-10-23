"""Observed special milestones, explicit choices and native stat allocation."""
from pathlib import Path
from copy import deepcopy
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
from builder import build_trainer
from state_codec import dump_engine,load_engine,StateCodecError
import state_grants as G
import world_entities as W

class MilestoneTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')
 def setUp(self):
  self.e=Engine(self.rules,31);self.c=Combatant(self.rules,build_trainer(self.rules,'milestone',4,{'hp':10,'atk':10,'def':10,'spa':10,'spd':10,'spe':10},abilities=[]))
  self.e.everyone=self.e.gm.everyone=[self.c]
 def grow(self,amount,uid):return self.e.award_trainer_progression(self.c,kind='experience',amount=amount,request_id=uid,reason='observed growth')
 def choose(self,level,option):return self.e.choose_trainer_milestone(self.c,level,option,reason='explicit branch')
 def allocate(self,level,atk,spa,uid='allocation/one'):
  return self.e.allocate_trainer_milestone_stats(self.c,level,{'atk':atk,'spa':spa},request_id=uid,reason='explicit stat choice')
 def rewards(self):return {row['level']:row for row in self.e.trainer_milestone_rewards(self.c)}
 def test_five_retroactive_two_then_observed_even_levels_and_native_permanent_spend(self):
  self.grow(10,'five');self.assertEqual(self.rewards()[5]['status'],'pending_branch_choice')
  self.choose(5,'stats');self.assertEqual(self.rewards()[5]['available'],2)
  G.stat(self.c,'atk',3,'independent')
  receipt=self.allocate(5,1,1);self.assertEqual(self.c.spec['stats']['atk'],11);self.assertEqual(self.c.stats['atk'],14)
  before=dump_engine(self.e);self.assertEqual(self.allocate(5,1,1),receipt);self.assertEqual(dump_engine(self.e),before)
  self.grow(50,'ten');self.assertEqual(self.rewards()[5]['earned'],5);self.assertEqual(self.rewards()[5]['available'],3)
  self.choose(10,'stats');self.assertEqual(self.rewards()[10]['earned'],0)
  self.grow(20,'twelve');self.assertEqual(self.rewards()[5]['earned'],5);self.assertEqual(self.rewards()[10]['earned'],1)
 def test_all_stat_windows_and_delayed_choice_use_recorded_levels_once(self):
  self.grow(460,'fifty')
  for level,expected in [(5,5),(10,5),(20,5),(30,5),(40,5)]:
   self.choose(level,'stats');self.assertEqual(self.rewards()[level]['earned'],expected)
  before=dump_engine(self.e);self.grow(460,'fifty');self.assertEqual(dump_engine(self.e),before)
  before=dump_engine(self.e)
  with self.assertRaisesRegex(ValueError,'level is outside'):self.grow(20,'fiftytwo')
  self.assertEqual(dump_engine(self.e),before);self.assertEqual(self.rewards()[40]['earned'],5)
 def test_each_nonstat_branch_remains_qualified_pending_and_choice_cannot_change(self):
  for level,options in [(5,['general_feat']),(10,['edges']),(20,['edges']),(30,['edges','general_feat']),(40,['edges','general_feat'])]:
   for option in options:
    self.setUp();self.grow((level-4)*10,'threshold');first=self.choose(level,option)
    row=self.rewards()[level];self.assertEqual(row['status'],'pending_qualified_choice')
    self.assertEqual(row['count'],2 if option=='edges' else 1);self.assertEqual(self.choose(level,option),first)
    before=dump_engine(self.e)
    with self.assertRaises(ValueError):self.choose(level,'stats')
    with self.assertRaises(ValueError):self.allocate(level,1,0)
    self.assertEqual(dump_engine(self.e),before)
 def test_unobserved_threshold_invalid_option_and_overallocation_do_not_mutate(self):
  before=dump_engine(self.e)
  with self.assertRaises(ValueError):self.choose(5,'stats')
  self.assertEqual(dump_engine(self.e),before)
  self.grow(10,'five');before=dump_engine(self.e)
  with self.assertRaises(ValueError):self.choose(5,'edges')
  self.assertEqual(dump_engine(self.e),before);self.choose(5,'stats');before=dump_engine(self.e)
  with self.assertRaises(ValueError):self.allocate(5,3,0)
  with self.assertRaises(ValueError):self.e.allocate_trainer_milestone_stats(self.c,5,{'hp':1,'atk':0},request_id='wrong',reason='wrong')
  self.assertEqual(dump_engine(self.e),before)
 def test_saved_choice_allocation_and_future_reward_resume_without_reapplication(self):
  self.grow(10,'five');self.choose(5,'stats');receipt=self.allocate(5,2,0)
  restored=load_engine(self.rules,dump_engine(self.e));c=W.actor_index(restored)[self.c.entity_id];before=dump_engine(restored)
  self.assertEqual(restored.allocate_trainer_milestone_stats(c,5,{'atk':2,'spa':0},request_id='allocation/one',reason='explicit stat choice'),receipt)
  self.assertEqual(dump_engine(restored),before)
  restored.award_trainer_progression(c,kind='milestone',request_id='six',reason='milestone')
  self.assertEqual(restored.trainer_milestone_rewards(c)[0]['available'],1)
  c.spec['trainer_milestone_rewards']['allocations']['allocation/one']['result']['stats']['atk']=99
  with self.assertRaises(StateCodecError):dump_engine(restored)
 def test_late_stat_validation_failure_rolls_back_allocation_and_rights(self):
  from unittest.mock import patch
  import state_fields as F
  self.grow(10,'five');self.choose(5,'stats');before=dump_engine(self.e);original=F.base_patch
  def fail(*args,**kwargs):original(*args,**kwargs);raise ValueError('late patch failure')
  with patch('state_fields.base_patch',side_effect=fail):
   with self.assertRaisesRegex(ValueError,'late patch failure'):self.allocate(5,2,0)
  self.assertEqual(dump_engine(self.e),before);self.allocate(5,2,0)

 def test_ordinary_point_pool_stays_separate_from_special_reward(self):
  self.grow(30,'seven');self.choose(5,'stats')
  self.assertEqual(self.e.trainer_growth_stat_points(self.c)['available'],3)
  self.assertEqual(self.rewards()[5]['available'],3)
  G.stat(self.c,'def',2,'independent')
  receipt=self.e.allocate_trainer_growth_stats(self.c,{'hp':1,'def':2},request_id='ordinary/one',reason='ordinary allocation')
  self.assertEqual(self.c.spec['stats']['hp'],11);self.assertEqual(self.c.spec['stats']['def'],12);self.assertEqual(self.c.stats['def'],14)
  self.assertEqual(self.e.trainer_growth_stat_points(self.c)['available'],0);self.assertEqual(self.rewards()[5]['available'],3)
  before=dump_engine(self.e)
  self.assertEqual(self.e.allocate_trainer_growth_stats(self.c,{'def':2,'hp':1},request_id='ordinary/one',reason='ordinary allocation'),receipt)
  self.assertEqual(dump_engine(self.e),before)
  with self.assertRaisesRegex(ValueError,'insufficient'):self.e.allocate_trainer_growth_stats(self.c,{'atk':1},request_id='overspend',reason='overspend')
  self.assertEqual(dump_engine(self.e),before)
  self.allocate(5,3,0);self.assertEqual(self.e.trainer_growth_stat_points(self.c)['available'],0)
 def test_ordinary_allocation_survives_save_and_cannot_change_scope(self):
  self.grow(10,'five');first=self.e.allocate_trainer_growth_stats(self.c,{'spe':1},request_id='same',reason='allocation')
  restored=load_engine(self.rules,dump_engine(self.e));c=W.actor_index(restored)[self.c.entity_id];before=dump_engine(restored)
  self.assertEqual(restored.allocate_trainer_growth_stats(c,{'spe':1},request_id='same',reason='allocation'),first)
  self.assertEqual(dump_engine(restored),before)
  self.choose(5,'stats')
  with self.assertRaisesRegex(ValueError,'changed input'):self.e.allocate_trainer_milestone_stats(self.c,5,{'atk':1,'spa':0},request_id='same',reason='allocation')
 def test_ordinary_rewards_are_not_inferred_from_current_or_legacy_levels(self):
  self.assertEqual(self.e.trainer_growth_stat_points(self.c)['earned'],0)
  self.grow(20,'six');self.c.spec['trainer_progression_events']['six']['result'].pop('stat_reward_levels')
  self.assertEqual(self.e.trainer_growth_stat_points(self.c)['earned'],0)
 def test_ordinary_allocation_invalid_input_and_late_failure_preserve_pool(self):
  from unittest.mock import patch
  self.grow(20,'six');before=dump_engine(self.e)
  for stats in ({'hp':True},{'atk':-1},{'unknown':1},{}, {'atk':0}):
   with self.assertRaises(ValueError):self.e.allocate_trainer_growth_stats(self.c,stats,request_id='invalid',reason='invalid')
   self.assertEqual(dump_engine(self.e),before)
  import state_fields as F
  original=F.base_patch
  def late(*args,**kwargs):original(*args,**kwargs);raise ValueError('late ordinary failure')
  with patch('state_fields.base_patch',side_effect=late):
   with self.assertRaisesRegex(ValueError,'late ordinary failure'):self.e.allocate_trainer_growth_stats(self.c,{'hp':2},request_id='late',reason='late')
  self.assertEqual(dump_engine(self.e),before)

if __name__=='__main__':unittest.main()
