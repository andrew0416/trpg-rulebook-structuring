"""C02 HP/evasion state contracts on native creation, GM and durable graphs."""
from pathlib import Path
from copy import deepcopy
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
from builder import build_trainer,build_pokemon
import state_codec as CODEC
import state_grants as GRANTS

class HpEvasionStateTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='core')
 def setUp(self):
  self.e=Engine(self.r,seed=510)
  self.c=Combatant(self.r,build_trainer(self.r,'derived-defender',10,{'hp':10,'atk':10,'def':1,'spa':10,'spd':1,'spe':1},abilities=[]))
  self.e.gm.add_combatant(self.c,pos=(1,1),side='party',reason='actual created trainer enters roster')
  self.a=Combatant(self.r,build_trainer(self.r,'attacker',10,{'hp':10,'atk':10,'def':1,'spa':10,'spd':1,'spe':1},abilities=[]))
  self.e.gm.add_combatant(self.a,pos=(2,1),side='wild',reason='actual opposing trainer enters roster')
 def restored(self):
  return CODEC.load_engine(self.r,json.loads(json.dumps(CODEC.dump_engine(self.e),ensure_ascii=False)))
 def test_three_stat_evasion_channels_floor_boundaries_and_six_cap(self):
  for stat,move_class in [('def','물리'),('spd','특수'),('spe','변화')]:
   for value,want in [(1,0),(4,0),(5,1),(9,1),(10,2),(14,2),(19,3),(24,4),(29,5),(30,6),(34,6),(70,6)]:
    with self.subTest(stat=stat,value=value):
     for other in ('def','spd','spe'):self.e.gm.set_stat(self.c,other,1,reason='isolate actual source channel')
     self.e.gm.set_stat(self.c,stat,value,reason='observed base-stat value')
     self.assertEqual(self.c.evasion(move_class),want)
 def test_stages_use_current_stat_without_mutating_baseline_and_do_not_sum_channels(self):
  for stat,value in [('def',15),('spd',25),('spe',20)]:self.e.gm.set_stat(self.c,stat,value,reason='observed distinct evasion sources')
  self.assertEqual([self.c.evasion(k) for k in ('물리','특수','변화')],[4,5,4])
  baseline=deepcopy(self.c.spec['stats'])
  self.e.gm.set_stage(self.c,'def',6,reason='positive stage');self.assertEqual(self.c.staged('def'),33)
  self.assertEqual(self.c.evasion('물리'),6)
  self.e.gm.set_stage(self.c,'spe',-6,reason='negative speed stage');self.e.gm.set_stage(self.c,'def',-6,reason='negative defense stage')
  self.assertEqual([self.c.evasion(k) for k in ('물리','특수','변화')],[1,5,1])
  self.assertEqual(self.c.spec['stats'],baseline)
 def test_stat_cap_is_separate_from_other_sources_and_actual_accuracy_threshold(self):
  self.e.gm.set_stat(self.c,'def',50,reason='high defense');GRANTS.numeric(self.c,'evasion_mod',2,'fixture:equipment',bounds=(-6,6))
  self.assertEqual(self.c.evasion('물리'),8)
  move=dict(self.r.moves[self.r.move_id('몸통박치기')]);move['ac']=2;move['class']='물리'
  self.assertFalse(self.e.accuracy_check(self.a,self.c,move,fixed_roll=9)[0])
  self.assertTrue(self.e.accuracy_check(self.a,self.c,move,fixed_roll=10)[0])
  self.e.gm.set_stage(self.c,'eva',value=6,reason='explicit independent aggregate modifier')
  self.assertEqual(self.c.evasion('물리'),9)
  self.e.gm.set_stage(self.c,'eva',value=-6,reason='negative modifiers can remove evasion')
  self.assertEqual(self.c.evasion('물리'),0)
 def test_evasion_conditions_suppress_effective_values_without_erasing_sources(self):
  for stat,value in [('def',15),('spd',25),('spe',30)]:self.e.gm.set_stat(self.c,stat,value,reason='known base values')
  self.e.gm.add_condition(self.c,'구속',reason='actual stuck state')
  self.assertEqual([self.c.evasion(k) for k in ('물리','특수','변화')],[3,5,0])
  self.e.gm.add_condition(self.c,'잠듦',reason='actual asleep state')
  self.assertEqual(self.c.evasion('물리'),0)
  self.e.gm.remove_condition(self.c,'잠듦',reason='awakened');self.e.gm.remove_condition(self.c,'구속',reason='released')
  self.assertEqual(self.c.evasion('물리'),6)
  self.e.gm.set_hp(self.c,value=0,reason='unconscious');self.assertEqual(self.c.evasion('물리'),0)
 def test_trainer_max_hp_formula_uses_level_and_hp_stat_not_current_or_stages(self):
  self.assertEqual((self.c.base_max_hp,self.c.max_hp,self.c.hp),(60,60,60))
  self.e.gm.set_level(self.c,20,reason='record actual level');self.e.gm.set_stat(self.c,'hp',12,reason='record actual HP stat')
  self.assertEqual((self.c.spec['level'],self.c.spec['stats']['hp'],self.c.base_max_hp),(20,12,86))
  self.e.gm.set_stage(self.c,'def',6,reason='ordinary non-HP stage');self.assertEqual(self.c.base_max_hp,86)
  self.e.gm.set_hp(self.c,value=31,reason='current injury-independent HP');self.e.gm.set_temp_hp(self.c,7,reason='explicit temporary HP')
  self.assertEqual((self.c.hp,self.c.temp_hp,self.c.base_max_hp,self.c.max_hp),(31,7,86,86))
  self.e.gm.set_hp(self.c,value=500,reason='explicit healing observation clamps to capacity');self.assertEqual(self.c.hp,86)
  p=Combatant(self.r,build_pokemon(self.r,'이상해씨',20,abilities=[]))
  self.assertEqual(p.base_max_hp,20+3*p.stats['hp']+10)
 def test_injury_adjusted_capacity_stays_separate_from_base_hp_and_healing(self):
  self.e.gm.set_stat(self.c,'hp',13,reason='HP stat');self.assertEqual(self.c.base_max_hp,69)
  stats=deepcopy(self.c.stats);self.e.gm.set_hp(self.c,value=69,reason='full health observation')
  self.e.gm.set_injuries(self.c,value=2,reason='observed injuries')
  self.assertEqual((self.c.base_max_hp,self.c.max_hp,self.c.hp),(69,55,69))
  self.assertEqual(self.c.stats,stats)
  self.e.gm.set_injuries(self.c,value=0,reason='injury healing')
  self.assertEqual((self.c.base_max_hp,self.c.max_hp,self.c.hp),(69,69,69))
 def test_hp_evasion_gear_and_stage_state_survive_gm_and_durable_restore(self):
  self.e.gm.set_stat(self.c,'def',15,reason='base');self.e.gm.set_stage(self.c,'def',3,reason='stage')
  GRANTS.numeric(self.c,'evasion_mod',2,'fixture:equipment',bounds=(-6,6))
  self.e.gm.set_injuries(self.c,value=2,reason='injuries');self.e.gm.set_hp(self.c,value=31,reason='current HP')
  expected=(self.c.base_max_hp,self.c.max_hp,self.c.hp,self.c.evasion('물리'))
  self.assertEqual(expected,(60,48,31,6))
  self.e.gm.snapshot('derived-state');self.e.gm.set_stage(self.c,'def',-6,reason='temporary change');self.e.gm.set_hp(self.c,value=1,reason='temporary change')
  self.e.gm.restore('derived-state')
  self.assertEqual((self.c.base_max_hp,self.c.max_hp,self.c.hp,self.c.evasion('물리')),expected)
  e=self.restored();c=next(x for x in e.everyone if x.entity_id==self.c.entity_id)
  self.assertEqual((c.base_max_hp,c.max_hp,c.hp,c.evasion('물리')),expected)
  GRANTS.remove_owned(e,c,'fixture:equipment');self.assertEqual(c.evasion('물리'),4)
  self.assertEqual((c.base_max_hp,c.max_hp,c.hp),(60,48,31))

if __name__=='__main__':unittest.main()
