from pathlib import Path
from copy import deepcopy
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_foundation_policy_replay as F
from state_codec import dump_engine

class RollContextTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):F.PolicyReplayTests.setUpClass()
 def setUp(self):
  self.f=F.PolicyReplayTests();self.f.setUp();self.f.c.spec['skills']={'Athletics':3,'Acrobatics':4}
 def test_native_rank_dice_and_modifiers_stay_separate_without_consumption(self):
  f=self.f;before=dump_engine(f.e);out=f.e.plan_skill_check(f.c,'Athletics',purpose='climbing',mods=2)
  self.assertEqual((out['ordinary_rank'],out['effective_rank'],out['dice_count'],out['modifier']),(3,3,3,2))
  self.assertEqual(out['actor_id'],f.c.entity_id);self.assertFalse(out['consumed']);self.assertEqual(dump_engine(f.e),before)
 def declaration(self):
  f=self.f;return {'source':'combat/struggle','purpose':'climbing','actor_id':f.c.entity_id,'target_id':f.c.entity_id,'provider_id':f.c.entity_id,
   'from_skill':'Athletics','to_skill':'Acrobatics','allowed':True}
 def test_replacement_changes_only_scoped_plan(self):
  f=self.f;before=dump_engine(f.e)
  out=f.e.plan_skill_check(f.c,'Athletics',purpose='climbing',replacement=self.declaration())
  self.assertEqual((out['requested_rank'],out['ordinary_rank'],out['dice_count']),(3,4,4))
  self.assertEqual(f.e.plan_skill_check(f.c,'Athletics',purpose='swimming')['ordinary_rank'],3)
  self.assertEqual(dump_engine(f.e),before)
 def test_wrong_scope_or_denied_substitution_cannot_prepare(self):
  f=self.f;before=dump_engine(f.e)
  for key,value in [('purpose','swimming'),('provider_id','other'),('target_id','other'),('allowed',False)]:
   declaration=self.declaration();declaration[key]=value
   with self.assertRaises(ValueError):f.e.plan_skill_check(f.c,'Athletics',purpose='climbing',replacement=declaration)
  self.assertEqual(dump_engine(f.e),before)
 def policy_document(self):
  f=self.f
  declaration={'skill':'Athletics','purpose':'climbing','provider_id':f.c.entity_id,
   'provider_requirement':{'source_id':'edge/메딕-훈련','minimum_count':1},'options':{},'replacement':self.declaration()}
  f.row['values']={'roll_plan':declaration}
  return declaration
 def test_policy_requires_actual_provider_acquisition_without_granting_it(self):
  f=self.f;self.policy_document();before=dump_engine(f.e)
  def evaluate():return f.e.evaluate_source_policy_roll_plan(f.c,f.c,f.doc,purpose='climbing')
  self.assertEqual(evaluate()['status'],'PolicyRollPlanDenied');self.assertEqual(dump_engine(f.e),before)
  f.c.spec['edges']=['edge/메딕-훈련'];before=dump_engine(f.e)
  out=evaluate();self.assertEqual(out['status'],'PolicyRollPlanPrepared')
  self.assertEqual(out['provider_acquisition']['actual_count'],1);self.assertEqual(out['roll_plan']['dice_count'],4)
  self.assertEqual(dump_engine(f.e),before)
 def test_policy_scope_source_and_unknown_permission_remain_guarded(self):
  f=self.f;declaration=self.policy_document();f.c.spec['edges']=['edge/메딕-훈련'];before=dump_engine(f.e)
  with self.assertRaisesRegex(ValueError,'purpose'):f.e.evaluate_source_policy_roll_plan(f.c,f.c,f.doc,purpose='swimming')
  declaration['replacement']['source']='other'
  with self.assertRaisesRegex(ValueError,'selected policy'):f.e.evaluate_source_policy_roll_plan(f.c,f.c,f.doc,purpose='climbing')
  declaration['replacement']['source']='combat/struggle';declaration['replacement']['allowed']=None
  out=f.e.evaluate_source_policy_roll_plan(f.c,f.c,f.doc,purpose='climbing')
  self.assertEqual(out['status'],'PolicyRollPlanPending');self.assertNotIn('roll_plan',out)
  self.assertEqual(dump_engine(f.e),before)

 def stunt(self):
  import skill_stunts as ST
  f=self.f;f.c.spec['edges']=[ST.SOURCE]
  ST.approve(f.e,f.c,choice_id='climb-stunt',skill='Athletics',use='climbing',reason='specific climb use',approved=True)
  return {'choice_id':'climb-stunt','apply':True,'matches_approved_use':True,'reason':'actual approved climb'}
 def test_owned_stunt_replaces_one_die_without_changing_rank_or_consuming(self):
  f=self.f;declaration=self.stunt();before=dump_engine(f.e)
  out=f.e.plan_skill_check(f.c,'Athletics',purpose='climbing',skill_stunt=declaration)
  self.assertEqual((out['ordinary_rank'],out['effective_rank'],out['dice_count'],out['modifier']),(3,3,2,6))
  self.assertEqual(out['skill_stunt']['choice']['id'],'climb-stunt');self.assertEqual(dump_engine(f.e),before)
  ordinary=f.e.plan_skill_check(f.c,'Athletics',purpose='swimming')
  self.assertEqual((ordinary['dice_count'],ordinary['modifier']),(3,0))
 def test_owned_stunt_cannot_leak_to_another_purpose_even_with_match_flag(self):
  f=self.f;declaration=self.stunt();before=dump_engine(f.e)
  with self.assertRaisesRegex(ValueError,'approved narrow stunt use'):
   f.e.plan_skill_check(f.c,'Athletics',purpose='swimming',skill_stunt=declaration)
  self.assertEqual(dump_engine(f.e),before)

 def test_rank_only_context_has_no_dice_or_constant_and_binds_targets(self):
  f=self.f;before=dump_engine(f.e)
  out=f.e.plan_rank_context(f.c,'Athletics',purpose='training.limit',targets=[f.c],source='combat/struggle')
  self.assertEqual(out['ordinary_rank'],3);self.assertEqual(out['effective_rank'],3)
  self.assertIsNone(out['dice_count']);self.assertIsNone(out['modifier'])
  self.assertEqual(out['target_ids'],[f.c.entity_id]);self.assertEqual(dump_engine(f.e),before)

 def test_native_ordinary_action_checks_stunt_purpose_before_consuming(self):
  f=self.f;stunt=self.stunt();before=dump_engine(f.e)
  with self.assertRaisesRegex(ValueError,'approved narrow stunt use'):
   f.e.common_action(f.c,'Athletics',6,mode='skill',roll_purpose='swimming',skill_stunt=stunt,fixed=[3,3])
  self.assertEqual(dump_engine(f.e),before)
  out=f.e.common_action(f.c,'Athletics',6,mode='skill',roll_purpose='climbing',skill_stunt=stunt,fixed=[3,3])
  self.assertTrue(out.check.passed)
  self.assertEqual(out.basis['roll_plan']['purpose'],'climbing')
  self.assertEqual(f.c.spec['skills']['Athletics'],3)

if __name__=='__main__':unittest.main()
