"""Groomer body and CSV substitute different training quantities."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_progression_state as fixtures
from builder import build_pokemon
class Tests(unittest.TestCase):
 setUpClass=classmethod(fixtures.ProgressionStateTests.setUpClass.__func__)
 add=fixtures.ProgressionStateTests.add
 snap=fixtures.ProgressionStateTests.snap
 def setUp(self):
  fixtures.ProgressionStateTests.setUp(self)
  self.a.spec.update(edges=['미용사'],skills={'명령':2,'포켓몬학':3,'일반 지식':5})
  self.a.spec['items']['미용사 킷']=1
  self.ps=[self.add(build_pokemon(self.r,'이상해씨',5,name='p'+str(i),moves=[],abilities=[],extra={'trainer_id':self.a.entity_id})) for i in range(6)]
  self.e.pokemon_activity(self.a,'groom',targets=self.ps,safe=True)
 def train(self,targets,policy=None):
  return self.e.pokemon_activity(self.a,'experience_training',targets=targets,from_grooming=True,bonus_skill='일반 지식',grooming_policy=policy,safe=True)
 def test_csv_education_changes_limit_only_while_body_changes_bonus_only(self):
  out=self.train(self.ps[:5],'csv_target_limit')
  self.assertEqual((out['limit'],out['xp_rank'],out['awards']),(5,2,[2]*5))
  plans=out['rank_plans']
  self.assertEqual(plans['experience_training.target_limit']['effective_rank'],5)
  self.assertEqual(plans['experience_training.xp_bonus']['effective_rank'],2)
  self.assertEqual(plans['experience_training.target_limit']['target_ids'],[p.entity_id for p in self.ps[:5]])
  self.assertEqual(self.ps[0].spec['experience_training_history'][-1]['rank_plans'],plans)
  self.assertEqual(self.e.elapsed_seconds,3600)
  for p in self.ps[:5]:self.assertEqual(p.spec['experience_training_history'][-1]['grooming_policy'],'csv_target_limit')
  before=self.snap()
  with self.assertRaisesRegex(ValueError,'limit'):self.train(self.ps[5:],'csv_target_limit')
  self.assertEqual(before,self.snap())
  self.setUp();out=self.train(self.ps[:2])
  self.assertEqual((out['limit'],out['xp_rank'],out['awards']),(2,5,[12]*2))
  self.assertEqual(out['rank_plans']['experience_training.target_limit']['effective_rank'],2)
  self.assertEqual(out['rank_plans']['experience_training.xp_bonus']['effective_rank'],5)
  self.assertEqual(self.e.elapsed_seconds,3600)
 def test_cached_source_or_definition_change_leaves_training_untouched(self):
  import pokemon_activities as ACT
  ACT._groomer_csv_source(self.r)
  original=Path.read_bytes
  for filename in ('edges.csv','training-source-policies.json'):
   before=self.snap()
   def changed(path):
    raw=original(path)
    return raw+b'changed' if path.name==filename else raw
   with patch.object(Path,'read_bytes',changed):
    with self.assertRaisesRegex(ValueError,'changed'):self.train(self.ps[:1],'csv_target_limit')
   self.assertEqual(before,self.snap())
 def test_changing_source_policy_does_not_reset_daily_count_or_consumed_training(self):
  self.train(self.ps[:2])
  out=self.train(self.ps[2:5],'csv_target_limit');self.assertEqual(out['awards'],[2]*3)
  before=self.snap()
  with self.assertRaises(ValueError):self.train([self.ps[0]],'csv_target_limit')
  with self.assertRaises(ValueError):self.train([self.ps[5]],'invented')
  self.assertEqual(before,self.snap())
 def test_source_choice_rejected_outside_grooming_and_profile_exclusion(self):
  before=self.snap()
  with self.assertRaises(ValueError):self.e.pokemon_activity(self.a,'experience_training',targets=self.ps[:1],grooming_policy='csv_target_limit',safe=True)
  self.assertEqual(before,self.snap())
  cid='C2CSV/input/db/edges.csv:R24:main';self.r.ruleset.exclude_units.add(cid)
  try:
   with self.assertRaises(ValueError):self.train(self.ps[:1],'csv_target_limit')
  finally:self.r.ruleset.exclude_units.remove(cid)
  self.assertEqual(before,self.snap())
if __name__=='__main__':unittest.main()
