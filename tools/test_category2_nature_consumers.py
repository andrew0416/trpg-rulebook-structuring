"""Source aliases use the same Nature contract in fossil and researcher consumers."""
from pathlib import Path
from copy import deepcopy
import sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'engine')]
from engine import Rules
import builder as B, nature_state as N
from tools import test_category3_researcher_features as Fixtures

class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(ROOT)
 def fixture(self):
  f=Fixtures.Tests();f.r=self.r;f.setUp();return f
 def test_three_source_aliases_hatch_actual_individual_with_original_label(self):
  for alias in N.ALIASES:
   with self.subTest(alias=alias):
    f=self.fixture();p=f.restored(nature=alias)
    self.assertEqual(p.spec['nature'],alias)
    self.assertEqual(f.e.gm.describe_actor(p)['nature_state'],N.describe(self.r,alias))
    self.assertTrue(f.t.spec['eggs'][0]['hatched'])
    self.assertEqual(f.t.spec['eggs'][0]['pokemon_id'],p.entity_id)
 def test_unknown_or_missing_hatch_nature_rejects_before_lifetime_transition(self):
  for invalid in ('unknown-mechanical-nature',None):
   with self.subTest(nature=invalid):
    f=self.fixture()
    with self.assertRaisesRegex(ValueError,'nature|Nature'):f.restored(nature=invalid)
    egg=f.t.spec['eggs'][0]
    self.assertFalse(egg['hatched'])
    self.assertNotIn('pokemon_id',egg)
    self.assertEqual(f.t.spec['fossils']['Fossil']['status'],'restored_to_egg')
 def test_relic_consumer_accepts_aliases_and_unknown_rejects_before_time_or_item(self):
  for alias in N.ALIASES:
   with self.subTest(alias=alias):
    f=self.fixture();p=f.restored(species='pokemon/아마루르가',nature=alias)
    base=B.nature_base(B.species_lookup(self.r,p.spec['species'])['base_stats'],alias,self.r)
    highest=[key for key,value in base.items() if value==max(base.values())]
    self.assertIn('hp',highest)
    before=f.e.elapsed_seconds
    record=f.crown(p,**({'tie_stat':'hp','tie_reason':'GM selects HP among equal nature-adjusted base stats'} if len(highest)>1 else {}))
    self.assertEqual(record['base_stats_with_nature'],base)
    self.assertEqual(f.e.elapsed_seconds-before,600)
  for invalid in ('unknown-mechanical-nature',None):
   f=self.fixture();p=f.restored(species='pokemon/아마루르가');p.spec['nature']=invalid
   before=(f.e.elapsed_seconds,deepcopy(f.t.spec),deepcopy(p.spec))
   with self.assertRaisesRegex(ValueError,'nature|Nature'):f.crown(p)
   self.assertEqual((f.e.elapsed_seconds,f.t.spec,p.spec),before)

if __name__=='__main__':unittest.main(verbosity=2)
