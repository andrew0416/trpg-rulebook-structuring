"""JSON growth declarations reuse native event and entitlement consumers."""
from pathlib import Path
from hashlib import sha256
from copy import copy,deepcopy
import sys,json,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
from builder import build_trainer
from state_codec import dump_engine,load_engine
import world_entities as W

class PolicyProgressionTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')
 def setUp(self):
  self.r=copy(self.rules);self.e=Engine(self.r,19)
  self.c=Combatant(self.r,build_trainer(self.r,'growth',5,{'hp':10,'atk':10,'def':10,'spa':10,'spd':10,'spe':10},abilities=[]))
  self.e.everyone=self.e.gm.everyone=[self.c];self.c.spec['exp_bank']=3
  path='input/ch11-running-the-game.md'
  self.op={'kind':'experience','request_id':'growth/one','reason':'explicit observed reward','amount':{'$input':'amount'}}
  self.row={'rule_id':'trainer/experience','source':{'file':path,'sha256':sha256((ROOT/path).read_bytes()).hexdigest()},
   'inputs':{'amount':{'type':'integer','authority':'gm','question':'Actual experience?'}},'values':{'progression_operation':self.op}}
  self.doc={'schema':1,'id':'growth-policy','variants':[self.row]}
 def load(self):
  self.r.load_source_policy_package(json.dumps({'schema':1,'sources':[],'policies':[self.doc]}))
  self.doc=self.r.source_policy_document('growth-policy')
 def run_policy(self,**options):return self.e.execute_source_policy_progression(self.c,self.c,self.doc,**options)
 def test_pending_then_actual_growth_and_entitlements_survive_replay_and_save(self):
  self.load();before=dump_engine(self.e)
  self.assertEqual(self.run_policy()['status'],'PolicyInputsRequired');self.assertEqual(dump_engine(self.e),before)
  args={'decisions':{'amount':{'value':19,'reason':'observed award'}},'request_id':'policy/one'}
  result=self.run_policy(**args);self.assertEqual(result['status'],'PolicyProgressionCompleted')
  self.assertFalse(result['effects_executed']);self.assertEqual(self.c.level,7)
  self.assertEqual(result['progression_result']['attained_levels'],[6,7]);self.assertEqual(len(self.e.pending_trainer_entitlements(self.c)),2)
  restored=load_engine(self.r,dump_engine(self.e));c=W.actor_index(restored)[self.c.entity_id];before=dump_engine(restored)
  replay=restored.execute_source_policy_progression(c,c,self.doc,**args)
  self.assertTrue(replay['replayed']);self.assertEqual(dump_engine(restored),before)
  # Native event deduplication also holds when no outer request ID is supplied.
  restored.execute_source_policy_progression(c,c,self.doc,decisions=args['decisions'])
  self.assertEqual(c.level,7);self.assertEqual(len(restored.pending_trainer_entitlements(c)),2)
 def test_milestone_and_false_condition_preserve_bank(self):
  self.op.pop('amount');self.op['kind']='milestone';self.row['inputs']={};self.row['when']=False
  self.load();before=dump_engine(self.e)
  self.assertEqual(self.run_policy()['status'],'PolicyNotApplicable');self.assertEqual(dump_engine(self.e),before)
  self.doc['variants'][0]['when']=True
  self.run_policy();self.assertEqual(self.c.level,6);self.assertEqual(self.c.spec['exp_bank'],3)
 def test_bad_package_is_not_published(self):
  for op in [dict(self.op,kind='unknown'),dict(self.op,amount=True),dict(self.op,rule_id='override')]:
   bad=deepcopy(self.doc);bad['id']='bad';bad['variants'][0]['values']['progression_operation']=op
   before=deepcopy(getattr(self.r,'_source_policy_documents',{}))
   with self.assertRaises(ValueError):self.r.load_source_policy_package(json.dumps({'schema':1,'sources':[],'policies':[self.doc,bad]}))
   self.assertEqual(getattr(self.r,'_source_policy_documents',{}),before)
 def test_late_reward_failure_rolls_back_policy_growth_and_entitlements(self):
  from unittest.mock import patch
  self.load();before=dump_engine(self.e)
  with patch('trainer_entitlements.verified_source',side_effect=ValueError('source changed')):
   with self.assertRaisesRegex(ValueError,'source changed'):self.run_policy(decisions={'amount':{'value':19,'reason':'observed award'}})
  self.assertEqual(dump_engine(self.e),before)
 def test_changed_event_intent_and_wrong_entry_do_not_change_growth(self):
  self.load();self.run_policy(decisions={'amount':{'value':19,'reason':'observed award'}});before=dump_engine(self.e)
  with self.assertRaisesRegex(ValueError,'changed input'):self.run_policy(decisions={'amount':{'value':20,'reason':'changed award'}})
  with self.assertRaises(ValueError):self.e.execute_source_policy_effects(self.c,self.c,self.doc,decisions={'amount':{'value':19,'reason':'observed award'}})
  self.assertEqual(dump_engine(self.e),before)

 def test_outer_policy_replay_cannot_hide_corrupt_native_growth_receipt(self):
  from copy import deepcopy
  self.load();args={'decisions':{'amount':{'value':19,'reason':'observed award'}},'request_id':'outer'}
  self.run_policy(**args)
  self.c.spec['trainer_progression_events']['growth/one']['result']['bank_after']=99
  before=deepcopy(self.c.spec);sequence=self.e._source_policy_sequence
  with self.assertRaisesRegex(ValueError,'original experience calculation'):self.run_policy(**args)
  self.assertEqual(self.c.spec,before);self.assertEqual(self.e._source_policy_sequence,sequence)

 def milestone_document(self,kind,**fields):
  path='input/ch02-character-creation.md'
  return {'schema':1,'id':'milestone/'+kind,'variants':[{'rule_id':'ch02-character-creation/캐릭터-발전',
   'source':{'file':path,'sha256':sha256((ROOT/path).read_bytes()).hexdigest()},'inputs':{},
   'values':{'progression_operation':dict(kind=kind,reason='explicit milestone decision',**fields)}}]}
 def reach_five(self):
  self.c.spec['level']=4;self.c.spec['exp_bank']=0
  self.e.award_trainer_progression(self.c,kind='milestone',request_id='reach/five',reason='actual milestone')
 def test_json_milestone_choice_allocation_pending_and_saved_replay(self):
  self.reach_five()
  choice=self.milestone_document('milestone_choice',level=5,option={'$input':'branch'})
  choice['variants'][0]['inputs']={'branch':{'type':'string','authority':'gm','question':'Milestone choice?','choices':['stats','general_feat']}}
  allocation=self.milestone_document('milestone_stats',level=5,stats={'atk':{'$input':'atk'},'spa':{'$input':'spa'}},request_id='stat/one')
  allocation['variants'][0]['inputs']={key:{'type':'integer','authority':'gm','question':'Allocate '+key} for key in ('atk','spa')}
  self.r.load_source_policy_package(json.dumps({'schema':1,'sources':[],'policies':[choice,allocation]}))
  before=dump_engine(self.e)
  self.assertEqual(self.e.execute_source_policy_progression(self.c,self.c,choice)['status'],'PolicyInputsRequired')
  self.assertEqual(dump_engine(self.e),before)
  self.e.execute_source_policy_progression(self.c,self.c,choice,decisions={'branch':{'value':'stats','reason':'chosen'}})
  decisions={key:{'value':1,'reason':'split equally'} for key in ('atk','spa')}
  result=self.e.execute_source_policy_progression(self.c,self.c,allocation,decisions=decisions,request_id='outer/stat')
  self.assertEqual(self.c.spec['stats']['atk'],11);self.assertEqual(self.c.spec['stats']['spa'],11)
  restored=load_engine(self.r,dump_engine(self.e));c=W.actor_index(restored)[self.c.entity_id];before=dump_engine(restored)
  replay=restored.execute_source_policy_progression(c,c,allocation,decisions=decisions,request_id='outer/stat')
  self.assertTrue(replay['replayed']);self.assertEqual(replay['progression_result'],result['progression_result']);self.assertEqual(dump_engine(restored),before)
  restored.execute_source_policy_progression(c,c,allocation,decisions=decisions)
  self.assertEqual(c.spec['stats']['atk'],11)
 def test_invalid_milestone_packages_publish_nothing(self):
  cases=[self.milestone_document('milestone_choice',level=5,option='edges'),
   self.milestone_document('milestone_stats',level=5,stats={'hp':1,'atk':0},request_id='bad'),
   self.milestone_document('milestone_stats',level=5,stats={'atk':True,'spa':0},request_id='bad'),
   self.milestone_document('milestone_stats',level=6,stats={'atk':1,'spa':0},request_id='bad'),
   self.milestone_document('milestone_stats',level=5,stats={'atk':0,'spa':0},request_id='bad')]
  for doc in cases:
   before=deepcopy(getattr(self.r,'_source_policy_documents',{}))
   with self.subTest(doc=doc),self.assertRaises(ValueError):self.r.load_source_policy_package(json.dumps({'schema':1,'sources':[],'policies':[doc]}))
   self.assertEqual(getattr(self.r,'_source_policy_documents',{}),before)
 def test_json_overspend_and_late_native_failure_leave_no_execution_record(self):
  from unittest.mock import patch
  self.reach_five();choice=self.milestone_document('milestone_choice',level=5,option='stats')
  self.e.execute_source_policy_progression(self.c,self.c,choice)
  allocation=self.milestone_document('milestone_stats',level=5,stats={'atk':3,'spa':0},request_id='stat/one');before=dump_engine(self.e)
  with self.assertRaisesRegex(ValueError,'insufficient'):self.e.execute_source_policy_progression(self.c,self.c,allocation)
  self.assertEqual(dump_engine(self.e),before)
  allocation['variants'][0]['values']['progression_operation']['stats']['atk']=2
  import state_fields as F
  original=F.base_patch
  def late(*args,**kwargs):original(*args,**kwargs);raise ValueError('late failure')
  with patch('state_fields.base_patch',side_effect=late):
   with self.assertRaisesRegex(ValueError,'late failure'):self.e.execute_source_policy_progression(self.c,self.c,allocation)
  self.assertEqual(dump_engine(self.e),before)
 def test_json_choice_bound_by_actual_native_threshold(self):
  self.reach_five();doc=self.milestone_document('milestone_choice',level={'$input':'level'},option='edges')
  doc['variants'][0]['inputs']={'level':{'type':'integer','authority':'context','question':'Threshold'}}
  self.r.load_source_policy_package(json.dumps({'schema':1,'sources':[],'policies':[doc]}));before=dump_engine(self.e)
  for level in (5,10):
   with self.assertRaises(ValueError):self.e.execute_source_policy_progression(self.c,self.c,doc,context={'level':level})
   self.assertEqual(dump_engine(self.e),before)

 def test_json_ordinary_growth_points_allocate_any_combat_stat(self):
  self.reach_five();doc=self.milestone_document('growth_stats',stats={'def':{'$input':'points'}},request_id='ordinary')
  doc['variants'][0]['inputs']={'points':{'type':'integer','authority':'gm','question':'Defense allocation'}}
  self.r.load_source_policy_package(json.dumps({'schema':1,'sources':[],'policies':[doc]}))
  before=dump_engine(self.e);self.assertEqual(self.e.execute_source_policy_progression(self.c,self.c,doc)['status'],'PolicyInputsRequired')
  self.assertEqual(dump_engine(self.e),before)
  args={'decisions':{'points':{'value':1,'reason':'explicit allocation'}}}
  self.e.execute_source_policy_progression(self.c,self.c,doc,**args)
  self.assertEqual(self.c.spec['stats']['def'],11);self.assertEqual(self.e.trainer_growth_stat_points(self.c)['available'],0)
  self.e.execute_source_policy_progression(self.c,self.c,doc,**args);self.assertEqual(self.c.spec['stats']['def'],11)

if __name__=='__main__':unittest.main()
