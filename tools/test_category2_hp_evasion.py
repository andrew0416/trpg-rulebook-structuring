"""C02 HP/evasion state contracts on native creation, GM and durable graphs."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
from builder import build_trainer,build_pokemon
import state_codec as CODEC
import state_grants as GRANTS
from ruleset import RuleFilter
from tools.native_scenario_fixture import assert_rejected_unchanged

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

 def _restore_evasion_ruleset(self,original):
  self.r.ruleset=original;self.r._apply_ruleset()
 def _select_evasion_profile(self,profile):
  original=self.r.ruleset
  self.addCleanup(self._restore_evasion_ruleset,original)
  self.r.ruleset=RuleFilter.load(str(ROOT),profile) if isinstance(profile,str) else RuleFilter(profile)
  self.r._apply_ruleset()
 def test_explicit_korean_nearest_and_default_floor_boundaries_all_channels(self):
  cases=[(1,0,0),(2,0,0),(3,0,1),(4,0,1),(5,1,1),(7,1,1),(8,1,2),(9,1,2),(10,2,2),(12,2,2),(13,2,3),(14,2,3),(28,5,6),(29,5,6),(30,6,6),(70,6,6)]
  for profile,index in [('core',1),('core-evasion-ptk-ch02-nearest',2)]:
   self._select_evasion_profile(profile)
   for stat,move_class in [('def','물리'),('spd','특수'),('spe','변화')]:
    for case in cases:
     with self.subTest(profile=profile,stat=stat,value=case[0]):
      for other in ('def','spd','spe'):self.e.gm.set_stat(self.c,other,1,reason='isolate source-qualified Evasion channel')
      self.e.gm.set_stat(self.c,stat,case[0],reason='observed Evasion source stat')
      self.assertEqual(self.c.evasion(move_class),case[index])
 def test_same_actor_source_switch_rejects_unknown_version_and_excluded_rule(self):
  identity=self.c.entity_id
  for stat in ('def','spd','spe'):self.e.gm.set_stat(self.c,stat,13,reason='same actor source-switch observation')
  for profile,want in [('core',2),('core-evasion-ptk-ch02-nearest',3),('core',2)]:
   self._select_evasion_profile(profile)
   self.assertEqual([self.c.evasion(kind) for kind in ('물리','특수','변화')],[want]*3)
   self.assertEqual(self.c.entity_id,identity)
  profile=deepcopy(self.r.ruleset.profile)
  profile['unit_versions']['combat/evasion']='unknown_evasion_source'
  self._select_evasion_profile(profile)
  assert_rejected_unchanged(self.e,lambda:self.c.evasion('물리'),reason_pattern='Selected rule version is missing or invalid: combat/evasion')
  self._select_evasion_profile('core-evasion-ptk-ch02-nearest')
  profile=deepcopy(self.r.ruleset.profile);profile['exclude_units']=['combat/evasion']
  self._select_evasion_profile(profile)
  assert_rejected_unchanged(self.e,lambda:self.c.evasion('물리'),reason_pattern='Excluded rule selection for combat/evasion')
  self._select_evasion_profile('core')
  with patch.dict(self.r.units['combat/evasion']['mech']['data'],{'stat_rounding':'unknown'}):
   assert_rejected_unchanged(self.e,lambda:self.c.evasion('물리'),reason_pattern='unknown Evasion stat rounding policy')
 def test_both_variants_public_accuracy_keep_stat_cap_and_independent_bonuses(self):
  move=dict(self.r.moves[self.r.move_id('몸통박치기')]);move['ac']=2;move['class']='물리'
  for profile,want in [('core',3),('core-evasion-ptk-ch02-nearest',4)]:
   self._select_evasion_profile(profile)
   self.e.gm.set_stage(self.c,'eva',value=0,reason='reset aggregate modifier between profiles')
   self.e.gm.set_stat(self.c,'def',8,reason='rounding-sensitive actual defense')
   self.e.gm.set_stat(self.c,'spe',1,reason='isolate physical channel')
   GRANTS.numeric(self.c,'evasion_mod',2,'fixture:evasion-source-bonus',bounds=(-6,6))
   self.assertEqual(self.c.evasion('물리'),want)
   self.assertFalse(self.e.accuracy_check(self.a,self.c,move,fixed_roll=want+1)[0])
   self.assertTrue(self.e.accuracy_check(self.a,self.c,move,fixed_roll=want+2)[0])
   self.assertEqual(self.c.evasion('물리',ignore_stats=True),2)
   self.assertEqual(self.c.evasion('물리',ignore_nonstats=True),want-2)
   self.e.gm.set_stat(self.c,'def',70,reason='stat component reaches its independent six cap')
   self.assertEqual(self.c.evasion('물리'),8)
   self.e.gm.set_stage(self.c,'eva',value=6,reason='aggregate source remains independent')
   self.assertEqual(self.c.evasion('물리'),9)
   GRANTS.remove_owned(self.e,self.c,'fixture:evasion-source-bonus')
 def test_both_variants_apply_current_stage_and_preserve_suppression(self):
  for profile,want in [('core',1),('core-evasion-ptk-ch02-nearest',2)]:
   self._select_evasion_profile(profile)
   for stat in ('def','spd','spe'):self.e.gm.set_stat(self.c,stat,8,reason='rounding-sensitive staged stat')
   self.e.gm.set_stage(self.c,'def',1,reason='current defense stage')
   baseline=deepcopy(self.c.spec['stats'])
   self.assertEqual(self.c.staged('def'),9)
   self.assertEqual([self.c.evasion(kind) for kind in ('물리','특수','변화')],[want]*3)
   self.e.gm.add_condition(self.c,'구속',reason='actual speed Evasion suppression')
   self.assertEqual(self.c.evasion('변화'),0);self.assertEqual(self.c.evasion('물리'),want)
   self.e.gm.add_condition(self.c,'잠듦',reason='actual all-channel suppression')
   self.assertEqual(self.c.evasion('물리'),0)
   self.e.gm.remove_condition(self.c,'잠듦',reason='awakened');self.e.gm.remove_condition(self.c,'구속',reason='released')
   self.assertEqual(self.c.evasion('물리'),want);self.assertEqual(self.c.spec['stats'],baseline)
   self.e.gm.set_hp(self.c,value=0,reason='actual unconscious Evasion suppression')
   self.assertEqual(self.c.evasion('물리'),0)
   self.e.gm.set_hp(self.c,value=self.c.max_hp,reason='GM observes conscious actor before next source variant')
 def test_selected_evasion_source_is_rechecked_without_cross_profile_leakage(self):
  for stat in ('def','spd','spe'):self.e.gm.set_stat(self.c,stat,8,reason='source-freshness observation')
  read_bytes=Path.read_bytes
  def changed(path):
   raw=read_bytes(path)
   return raw+b'changed' if path.name=='ch02-character-creation.md' else raw
  self._select_evasion_profile('core-evasion-ptk-ch02-nearest')
  self.assertEqual(self.c.evasion('물리'),2)
  with patch.object(Path,'read_bytes',changed):
   assert_rejected_unchanged(self.e,lambda:self.c.evasion('물리'),reason_pattern='Evasion stat rounding source changed')
   self._select_evasion_profile('core')
   self.assertEqual(self.c.evasion('물리'),1)
  self._select_evasion_profile('core-evasion-ptk-ch02-nearest')
  self.assertEqual(self.c.evasion('물리'),2)
 def test_both_variants_gm_and_cold_restore_keep_policy_identity_and_reject_mismatch(self):
  profiles=['core','core-evasion-ptk-ch02-nearest']
  for index,profile in enumerate(profiles):
   with self.subTest(profile=profile):
    rules=Rules(str(ROOT),ruleset=profile);engine=Engine(rules,seed=511)
    actor=Combatant(rules,build_trainer(rules,'cold Evasion defender',10,{'hp':10,'atk':10,'def':8,'spa':10,'spd':8,'spe':8},abilities=[]))
    engine.gm.add_combatant(actor,pos=(1,1),side='party',reason='actual cold-restore actor')
    engine.gm.set_stage(actor,'def',1,reason='staged Evasion boundary')
    GRANTS.numeric(actor,'evasion_mod',2,'fixture:cold-evasion-bonus',bounds=(-6,6))
    want=3+index
    self.assertEqual(actor.evasion('물리'),want)
    engine.gm.snapshot('source-selected-evasion')
    engine.gm.set_stage(actor,'def',-6,reason='temporary stage change')
    engine.gm.restore('source-selected-evasion')
    self.assertEqual((actor.staged('def'),actor.evasion('물리')),(9,want))
    payload=json.loads(json.dumps(CODEC.dump_engine(engine),ensure_ascii=False))
    fresh=Rules(str(ROOT),ruleset=profile)
    restored=CODEC.load_engine(fresh,payload)
    loaded=next(c for c in restored.everyone if c.entity_id==actor.entity_id)
    self.assertIs(loaded.r,restored.r)
    self.assertEqual((loaded.staged('def'),loaded.evasion('물리')),(9,want))
    self.assertEqual(restored.r.ruleset.name,profile)
    GRANTS.remove_owned(restored,loaded,'fixture:cold-evasion-bonus')
    self.assertEqual(loaded.evasion('물리'),want-2)
    other=Rules(str(ROOT),ruleset=profiles[1-index])
    with self.assertRaisesRegex(CODEC.StateCodecError,'selected rule/profile/source fingerprint mismatch'):
     CODEC.load_engine(other,payload)

if __name__=='__main__':unittest.main()
