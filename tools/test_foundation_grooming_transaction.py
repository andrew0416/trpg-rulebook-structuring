"""Grooming issues training credit atomically for actual world participants."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_progression_state as fixtures
from engine import Combatant
from builder import build_pokemon
import researcher_features as RF

class GroomingTransactionTests(unittest.TestCase):
 setUpClass=classmethod(fixtures.ProgressionStateTests.setUpClass.__func__)
 add=fixtures.ProgressionStateTests.add
 snap=fixtures.ProgressionStateTests.snap
 def setUp(self):
  fixtures.ProgressionStateTests.setUp(self)
  self.a.spec['edges']=['edge/미용사'];self.a.spec['items']['미용사 킷']=1
  self.targets=[self.add(build_pokemon(self.r,'근육몬',35,moves=[],abilities=[],extra={'trainer_id':self.a.entity_id})) for _ in range(2)]
 def groom(self):return self.e.pokemon_activity(self.a,'groom',targets=self.targets,safe=True)
 def test_late_native_failure_leaves_time_credit_and_actor_aliases_unchanged(self):
  before=self.snap();aliases=[p.spec for p in self.targets]
  with patch.object(RF,'finish_training',side_effect=ValueError('late training failure')):
   with self.assertRaisesRegex(ValueError,'late training failure'):self.groom()
  self.assertEqual(before,self.snap())
  for p,alias in zip(self.targets,aliases):self.assertIs(p.spec,alias)
 def test_success_issues_all_credits_once_and_keeps_live_spec_aliases(self):
  aliases=[p.spec for p in self.targets];out=self.groom()
  self.assertEqual(out['groomed'],[p.entity_id for p in self.targets]);self.assertEqual(self.e.elapsed_seconds,3600)
  for p,alias in zip(self.targets,aliases):
   self.assertIs(p.spec,alias);self.assertEqual(p.spec['training_credit']['completed_at'],3600)
 def test_detached_target_cannot_be_registered_by_groom_or_experience(self):
  target=Combatant(self.r,build_pokemon(self.r,'근육몬',35,moves=[],abilities=[],extra={'trainer_id':self.a.entity_id}))
  for activity in ('groom','experience_training'):
   before=self.snap();sheet=deepcopy(target.spec)
   with self.subTest(activity=activity),self.assertRaisesRegex(ValueError,'actual registered'):
    self.e.pokemon_activity(self.a,activity,targets=[target])
   self.assertEqual(before,self.snap());self.assertEqual(sheet,target.spec)
 def test_invalid_later_target_does_not_issue_earlier_credit(self):
  self.targets[1].spec['trainer_id']='someone-else';before=self.snap()
  with self.assertRaises(ValueError):self.groom()
  self.assertEqual(before,self.snap())
 def test_mutable_rng_and_clock_commit_or_rollback_with_the_same_live_aliases(self):
  import state_grants as G
  class MutableRng:
   def __init__(self):self.values=[2,4]
   def randint(self,a,b):return self.values.pop(0)
  for reject in (False,True):
   with self.subTest(reject=reject):
    self.setUp();rng=self.e.rng=MutableRng();values=rng.values;sheet=deepcopy(self.a.spec)
    def apply(se,sa):
     se.advance_time(60,[sa]);sa.spec['items']['미용사 킷']-=1
     value=se.rng.randint(1,6)
     if reject:raise ValueError('late native rejection')
     return value
    if reject:
     with self.assertRaisesRegex(ValueError,'late native rejection'):G.transition(self.e,self.a,apply)
     self.assertEqual(self.a.spec,sheet);self.assertEqual((self.e.elapsed_seconds,values),(0,[2,4]))
    else:
     self.assertEqual(G.transition(self.e,self.a,apply),2)
     self.assertEqual((self.e.elapsed_seconds,values),(60,[4]))
     self.assertEqual(self.a.spec['items']['미용사 킷'],0)
    self.assertIs(self.e.rng,rng);self.assertIs(self.e.rng.values,values)

if __name__=='__main__':unittest.main()
