"""Native acquisition facts for external predicates, not acquisition approval."""
from pathlib import Path
from hashlib import sha256
from copy import copy,deepcopy
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
from builder import build_trainer
from state_codec import dump_engine,load_engine
import acquired_features as A
import world_entities as W

class OwnershipTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')
 def setUp(self):
  self.r=copy(self.rules);self.r.ruleset=deepcopy(self.rules.ruleset);self.r.selection=copy(self.rules.selection);self.r.selection.filter=self.r.ruleset
  self.e=Engine(self.r,23);self.c=Combatant(self.r,build_trainer(self.r,'owner',25,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),abilities=[]))
  self.e.everyone=self.e.gm.everyone=[self.c]
 def test_edge_aliases_repetitions_and_choices_without_grants(self):
  uid='edge/기본-스킬';self.c.spec['edge_choices']={uid:['athletics']}
  self.assertEqual(A.owned_rule_count(self.c,uid),0)
  self.c.spec['edges']=[uid,self.r.selection.units[uid]['title']]
  self.assertEqual(A.owned_rule_count(self.c,uid),2)
  self.c.spec['edges']=['not-an-edge']
  with self.assertRaisesRegex(ValueError,'unambiguous'):A.owned_rule_count(self.c,uid)
 def test_actual_feature_ranks_and_class_branches_survive_save(self):
  self.c.spec.update(classes=['class/스탯-에이스'],feats=['feat/스탯-링크','feat/근사한-행위'],
   feature_choices={'class/스탯-에이스':['atk','def'],'feat/스탯-링크':['공격','def']},feat_ranks={'feat/근사한-행위':2})
  self.assertEqual(A.owned_rule_count(self.c,'class/스탯-에이스'),2)
  self.assertEqual(A.owned_rule_count(self.c,'feat/스탯-링크'),2)
  self.assertEqual(A.owned_rule_count(self.c,'feat/근사한-행위'),2)
  restored=load_engine(self.r,dump_engine(self.e));c=W.actor_index(restored)[self.c.entity_id]
  self.assertEqual(A.owned_rule_count(c,'feat/스탯-링크'),2)
  c.spec['feature_choices']['feat/스탯-링크']=['spa']
  with self.assertRaisesRegex(ValueError,'matching acquired class'):A.owned_rule_count(c,'feat/스탯-링크')
 def document(self,uid):
  path='input/ch02-character-creation.md'
  return {'schema':1,'id':'ownership-policy','variants':[{'rule_id':'ch02-character-creation/캐릭터-발전',
   'source':{'file':path,'sha256':sha256((ROOT/path).read_bytes()).hexdigest()},
   'inputs':{'owned':{'type':'integer','authority':'state','question':'Actual acquired count',
     'binding':{'subject':'target','field':'owned_rule_count','rule_id':uid}}},
   'when':{'op':'ge','left':{'$input':'owned'},'right':1},
   'values':{'effects':[{'type':'stage_change','stat':'atk','delta':1,'target':'self'}]}}]}
 def test_external_predicate_tracks_actual_ownership_and_refuses_context_override(self):
  uid='edge/기본-스킬';doc=self.document(uid);before=dump_engine(self.e)
  self.assertEqual(self.e.execute_source_policy_effects(self.c,self.c,doc)['status'],'PolicyNotApplicable')
  self.assertEqual(dump_engine(self.e),before)
  with self.assertRaises(ValueError):self.e.execute_source_policy_effects(self.c,self.c,doc,context={'owned':1})
  self.c.spec['edges']=[uid]
  result=self.e.execute_source_policy_effects(self.c,self.c,doc)
  self.assertEqual(result['status'],'PolicyEffectsCompleted');self.assertEqual(result['input_values']['owned'],1)
  self.c.spec['edges']=[];before=dump_engine(self.e)
  self.assertEqual(self.e.execute_source_policy_effects(self.c,self.c,doc)['status'],'PolicyNotApplicable')
  self.assertEqual(dump_engine(self.e),before)
 def test_excluded_or_unknown_source_is_not_reported_as_false_ownership(self):
  uid='edge/기본-스킬';self.c.spec['edges']=[uid]
  self.r.ruleset.exclude_units.add(uid)
  with self.assertRaises(ValueError):A.owned_rule_count(self.c,uid)
  self.r.ruleset.exclude_units.remove(uid)
  for uid in ['edge/does-not-exist','기본 스킬','item/anything']:
   with self.assertRaises(ValueError):A.owned_rule_count(self.c,uid)

if __name__=='__main__':unittest.main()
