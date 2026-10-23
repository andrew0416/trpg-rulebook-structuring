"""Native Mystic Senses optional friendship substitution and admission."""
import unittest
from tools import test_category3_pokemon_activities as fixtures
from copy import deepcopy

class MysticTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):fixtures.PokemonActivityTests.setUpClass()
 def setUp(self):
  self.f=fixtures.PokemonActivityTests();self.f.setUp()
  self.f.a.spec['edges']=['edge/신비한-감각']
  self.f.a.spec['skills'].update({'직감':3,'매력':1})
 def test_optional_intuition_improves_actual_wild_disposition(self):
  f=self.f
  r=f.act('befriend',target=f.p,use_mystic_senses=True,fixed=[4]*3)
  self.assertEqual((r['skill'],r['check'].total,r['disposition']),('직감',12,'우호적'))
  f.p.spec['dispositions']={}
  r=f.act('befriend',target=f.p,fixed=[6])
  self.assertEqual((r['skill'],r['check'].total,r['disposition']),('매력',6,'중립'))
  self.assertEqual(f.e.skill_roll(f.a,'매력',fixed=[2]).total,2)
 def test_invalid_ownership_prerequisite_exclusion_and_duplicates_are_atomic(self):
  f=self.f
  for edges,rank in [([],3),(['신비한 감각'],2),(['신비한 감각','원소 교감'],3),(['신비한 감각','Mystic Senses'],3)]:
   with self.subTest(edges=edges,rank=rank):
    f.a.spec.update(edges=edges);f.a.spec['skills']['직감']=rank;before=f.state()
    with self.assertRaises(ValueError):f.act('befriend',target=f.p,use_mystic_senses=True)
    self.assertEqual(f.state(),before)
 def test_failed_intuition_retains_retry_lock_and_combination_rejects(self):
  f=self.f;before=f.state()
  with self.assertRaises(ValueError):f.act('befriend',target=f.p,use_mystic_senses=True,use_pokemon_education=True)
  self.assertEqual(f.state(),before)
  r=f.act('befriend',target=f.p,use_mystic_senses=True,fixed=[1]*3)
  self.assertFalse(r['check'].passed);self.assertEqual(r['disposition'],'중립')
  before=f.state()
  with self.assertRaises(ValueError):f.act('befriend',target=f.p,use_mystic_senses=True,fixed=[6]*3)
  self.assertEqual(f.state(),before)

if __name__=='__main__':unittest.main()
