from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_pokemon
import downtime as D,growth_milestones as M,state_grants as G
from state_codec import dump_engine,load_engine

class GrowthMilestoneTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(ROOT,ruleset='core')
 def setUp(self):
  self.e=Engine(self.r);self.c=Combatant(self.r,build_pokemon(self.r,'이상해씨',19,moves=[],abilities=[]))
  self.e.everyone=self.e.gm.everyone=[self.c]
 def grow(self):D.gain_exp_combatant(self.e,self.c,'to next level')
 def test_level_awards_pending_right_and_explicit_choice_survives_restore_once(self):
  self.grow();self.assertEqual(self.c.abilities,[])
  row=self.c.spec[M.KEY]['ability:20'];self.assertIsNone(row['selection']);self.assertTrue(row['offered']['options'])
  e=load_engine(self.r,dump_engine(self.e));c=e.everyone[0];chosen=row['offered']['options'][-1]
  result=e.choose_growth_ability(c,20,chosen,reason='explicit selection')
  self.assertFalse(result['replayed']);self.assertEqual(c.abilities,[chosen])
  before=dump_engine(e);self.assertTrue(e.choose_growth_ability(c,20,chosen,reason='explicit selection')['replayed'])
  self.assertEqual(dump_engine(e),before)
 def test_unearned_invalid_or_late_failed_choice_cannot_spend_right(self):
  before=dump_engine(self.e)
  with self.assertRaises(ValueError):self.e.choose_growth_ability(self.c,20,'unknown',reason='invalid')
  self.assertEqual(dump_engine(self.e),before);self.grow();before=dump_engine(self.e)
  with self.assertRaises(ValueError):self.e.choose_growth_ability(self.c,20,'unknown',reason='invalid')
  choice=self.c.spec[M.KEY]['ability:20']['offered']['options'][-1]
  with patch.object(G,'reconcile',side_effect=ValueError('late application')):
   with self.assertRaisesRegex(ValueError,'late application'):self.e.choose_growth_ability(self.c,20,choice,reason='chosen')
  self.assertEqual(dump_engine(self.e),before)
 def test_generic_offer_keeps_empty_choice_pending_and_replay_is_detached(self):
  spec={};first=M.offer(spec,'stage/one',source='declared/source',stage={'kind':'creation'},options=[])
  self.assertIsNone(first['selection']);first['offered']['options'].append('invented')
  self.assertEqual(M.offer(spec,'stage/one',source='declared/source',stage={'kind':'creation'},options=[])['offered']['options'],[])
  with self.assertRaises(ValueError):M.offer(spec,'stage/one',source='declared/source',stage={'kind':'level'},options=[])

 def test_creation_never_chooses_first_and_does_not_offer_later_level_slots(self):
  spec=build_pokemon(self.r,'이상해씨',30,moves=[])
  self.assertEqual(spec['abilities'],[]);self.assertEqual(set(spec[M.KEY]),{'ability:creation'})
  c=Combatant(self.r,spec);self.e.everyone=self.e.gm.everyone=[c]
  options=M.ability_options(self.r,spec,'creation')
  with self.assertRaises(ValueError):self.e.choose_growth_ability(c,20,options[0],reason='not earned')
  out=self.e.choose_growth_ability(c,'creation',options[-1],reason='creation choice')
  self.assertFalse(out['replayed']);self.assertEqual(c.abilities,[options[-1]])
  explicit=build_pokemon(self.r,'이상해씨',5,moves=[],abilities=[])
  self.assertNotIn(M.KEY,explicit)
 def test_auto_evolution_records_pending_and_explicit_evolution_consumes_it(self):
  spec=build_pokemon(self.r,'잉어킹',19,moves=[],abilities=[]);species=spec['species']
  D.level_up(self.r,spec,auto_evolve=True)
  self.assertEqual(spec['species'],species)
  identity='evolution:'+species;self.assertIsNone(spec[M.KEY][identity]['selection'])
  target=spec[M.KEY][identity]['offered']['options'][-1]
  c=Combatant(self.r,spec);self.e.everyone=self.e.gm.everyone=[c]
  self.assertTrue(D.evolve_combatant(self.e,c,target)['evolved'])
  self.assertEqual(c.spec[M.KEY][identity]['selection']['choice'],target)
  loaded=load_engine(self.r,dump_engine(self.e));self.assertEqual(loaded.everyone[0].spec[M.KEY],c.spec[M.KEY])
 def test_corrupt_choice_stage_is_rejected_on_save(self):
  from state_codec import StateCodecError
  self.grow();self.c.spec[M.KEY]['ability:20']['offered']['stage']['level']=40
  with self.assertRaises(StateCodecError):dump_engine(self.e)

if __name__=='__main__':unittest.main()
