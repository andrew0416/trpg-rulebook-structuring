"""Frozen training acceptance: substitution sites remain source-specific."""
from pathlib import Path
from copy import deepcopy,copy
from hashlib import sha256
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_progression_state as fixtures
from builder import build_pokemon
import pokemon_activities as A,pokemon_progression as P,world_entities as W
from state_codec import dump_engine,load_engine,rules_fingerprint

class SubstitutionTests(unittest.TestCase):
 setUpClass=classmethod(fixtures.ProgressionStateTests.setUpClass.__func__)
 add=fixtures.ProgressionStateTests.add
 snap=fixtures.ProgressionStateTests.snap
 def setUp(self):
  fixtures.ProgressionStateTests.setUp(self);self.e.r=self.r=copy(self.r);self.a.r=self.r
  self.a.spec.update(edges=['edge/비스트-마스터'],skills={'명령':2,'협박':5})
  self.ps=[self.add(build_pokemon(self.r,'이상해씨',5,moves=[],abilities=[],extra={'trainer_id':self.a.entity_id})) for _ in range(6)]
 def train(self,targets,policy=None):return self.e.pokemon_activity(self.a,'experience_training',targets=targets,use_intimidate=True,beast_policy=policy,safe=True)
 def test_csv_changes_count_only_and_body_changes_xp_without_resetting_daily_quota(self):
  csv=self.train(self.ps[:3],'csv_target_limit');body=self.train(self.ps[3:5])
  self.assertEqual((csv['limit'],csv['xp_rank'],csv['awards']),(5,2,[2]*3))
  self.assertEqual((body['limit'],body['xp_rank'],body['awards']),(5,5,[12]*2))
  self.assertEqual(self.a.spec['experience_training']['count'],5)
  self.assertEqual(self.ps[0].spec['experience_training_history'][-1]['beast_policy'],'csv_target_limit')
  before=self.snap()
  with self.assertRaisesRegex(ValueError,'limit'):self.train(self.ps[5:],'csv_target_limit')
  self.assertEqual(before,self.snap())
 def test_unselected_missing_acquisition_or_inapplicable_policy_rejects(self):
  for options in ({'beast_policy':'csv_target_limit'},{'use_intimidate':True,'beast_policy':'invented'},{'use_intimidate':True,'beast_policy':'csv_target_limit','use_reserves':True}):
   before=self.snap()
   with self.assertRaises(ValueError):self.e.pokemon_activity(self.a,'experience_training',targets=self.ps[:1],**options,safe=True)
   self.assertEqual(before,self.snap())
  self.a.spec['edges']=[];before=self.snap()
  with self.assertRaises(ValueError):self.train(self.ps[:1],'csv_target_limit')
  self.assertEqual(before,self.snap())
 def test_owned_reserves_forbids_both_substitution_providers_before_mutation(self):
  self.a.spec.update(edges=['edge/예비-훈련','edge/비스트-마스터','edge/미용사'],skills={'명령':3,'협박':5,'포켓몬학':5})
  for options in ({'use_intimidate':True},{'use_intimidate':True,'beast_policy':'csv_target_limit'},{'from_grooming':True,'bonus_skill':'포켓몬학'},{'from_grooming':True,'bonus_skill':'포켓몬학','grooming_policy':'csv_target_limit'}):
   with self.subTest(options=options):
    before=self.snap()
    with self.assertRaisesRegex(ValueError,'Train the Reserves cannot replace Command'):
     self.e.pokemon_activity(self.a,'experience_training',targets=self.ps[:1],use_reserves=True,safe=True,**options)
    self.assertEqual(before,self.snap())
  result=self.e.pokemon_activity(self.a,'experience_training',targets=self.ps,use_reserves=True,safe=True)
  self.assertEqual((result['limit'],result['xp_rank'],result['awards']),(6,3,[7]*6))
  self.assertEqual(self.e.elapsed_seconds,3600)
 def test_source_change_and_exclusion_reject_without_partial_training(self):
  A._beast_csv_source(self.r);native=Path.read_bytes
  for name in ('edges.csv','training-source-policies.json'):
   before=self.snap()
   def changed(path):return native(path)+(b'changed' if path.name==name else b'')
   with patch.object(Path,'read_bytes',changed):
    with self.assertRaisesRegex(ValueError,'changed'):self.train(self.ps[:1],'csv_target_limit')
   self.assertEqual(before,self.snap())
  uid='C2CSV/input/db/edges.csv:R21:main';self.r.ruleset.exclude_units.add(uid)
  try:
   before=self.snap()
   with self.assertRaises(ValueError):self.train(self.ps[:1],'csv_target_limit')
   self.assertEqual(before,self.snap())
  finally:self.r.ruleset.exclude_units.remove(uid)
 def test_external_csv_choice_and_warm_cache_roundtrip_replay(self):
  for key in ('_beast_csv_policy','_beast_csv_policy_identity','_groomer_csv_policy','_groomer_csv_policy_identity'):vars(self.r).pop(key,None)
  cold=rules_fingerprint(self.r);A._beast_csv_source(self.r);A._groomer_csv_source(self.r);self.assertEqual(cold,rules_fingerprint(self.r))
  path='input/'+self.r.selection.units[P.TRAINING]['source']['file']
  doc={'schema':1,'id':'source-specific-training','variants':[{'rule_id':P.TRAINING,'source':{'file':path,'sha256':sha256((ROOT/path).read_bytes()).hexdigest()},'inputs':{},'values':{'training_operation':{'safe':True,'kind':'experience','targets':[p.entity_id for p in self.ps[:3]],'use_intimidate':True,'beast_policy':'csv_target_limit'}}}]}
  self.r.load_source_policy_package(json.dumps({'schema':1,'sources':[],'policies':[doc]}))
  out=self.e.execute_source_policy_training(self.a,doc,request_id='csv-once');self.assertEqual(out['training_result']['awards'],[2]*3)
  loaded=load_engine(self.r,dump_engine(self.e));owner=W.actor_index(loaded)[self.a.entity_id];before=dump_engine(loaded)
  self.assertTrue(loaded.execute_source_policy_training(owner,doc,request_id='csv-once')['replayed']);self.assertEqual(before,dump_engine(loaded))

if __name__=='__main__':unittest.main()
