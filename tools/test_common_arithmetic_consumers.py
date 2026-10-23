"""Actual arithmetic boundaries and intentionally distinct rule policies."""
from pathlib import Path
from fractions import Fraction
from unittest.mock import patch
import hashlib,json,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
import arithmetic as A
import arithmetic_policy as M
import rulings
import downtime as D
import movement_actions as MOVE
import common_checks as CHECKS
import action_points as AP
import effects_ext as EXT

class ArithmeticConsumers(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='core')
 def setUp(self):
  self.r=Rules(str(ROOT),ruleset='core');self.e=Engine(self.r,seed=904)
  self.c=Combatant(self.r,{'id':'math/a','name':'a','kind':'pokemon','level':3,'stats':{'hp':6,'atk':8,'def':8,'spa':8,'spd':8,'spe':8},'movement':{'land':7}})
  self.e.everyone=[self.c];self.e.gm.everyone=[self.c]
 def test_fixed_source_clauses_remain_byte_identical(self):
  ledger=json.loads((ROOT/'data/verification/category3-register.json').read_text(encoding='utf8'))
  expected={'C3-CORE-005':'23212796ce2f325a242d48af9148fd356805ef32065b35efa339533517ebc5e1','C3-CORE-006':'1f94f177efd9fe52bf307ea9ba1a3382bccd07bca6320c14f3829067aeb98fae'}
  for row in ledger['entries']:
   if row['id'] in expected:self.assertEqual(row['scope_sha256'],expected[row['id']])
  self.assertEqual(hashlib.sha256((ROOT/'input/ch06-gameplay.md').read_bytes()).hexdigest(),'b5719c7b300ff8d5e0eb84b782780d134d949654037e8128203dddd86639d9f6')
 def test_live_profile_change_blocks_native_arithmetic_after_actor_creation(self):
  self.assertEqual(self.c.staged('atk'),8)
  previous=self.r._selected_rule
  def selected(uid,*args):return uid+'/unreviewed-variant' if uid==M.SOURCE else previous(uid,*args)
  before=self.e.rng.getstate()
  with patch.object(self.r,'_selected_rule',side_effect=selected):
   with self.assertRaises(ValueError):self.c.staged('atk')
   with self.assertRaises(ValueError):D.award_exp(self.r,[39],2,significance=1,challenge=1)
  self.assertEqual(self.e.rng.getstate(),before)
 def test_contest_stat_pool_and_performance_recheck_live_math_source(self):
  from contest import ContestRules,ContestEngine
  rules=ContestRules(str(ROOT),ruleset='core');contest=ContestEngine(rules,seed=33)
  pool=contest.stat_pool_from_combatant(self.c,smart_stat_policy='ptu-original-special-defense')
  self.assertTrue(pool);before=(contest.rng.getstate(),list(contest.log_lines))
  previous=rules._selected_rule
  def selected(uid,*args):return uid+'/unreviewed-variant' if uid==M.SOURCE else previous(uid,*args)
  with patch.object(rules,'_selected_rule',side_effect=selected):
   with self.assertRaises(ValueError):contest.stat_pool_from_combatant(self.c,smart_stat_policy='ptu-original-special-defense')
   with self.assertRaises(ValueError):rules.performance_rules()
  self.assertEqual((contest.rng.getstate(),contest.log_lines),before)
 def test_signed_floor_and_ceil_are_operators_not_operand_selection(self):
  for value,expected in [('3.9999',3),('0.5',0),('-0.5',-1),('-3.9999',-4)]:self.assertEqual(M.floor(value),expected)
  self.assertEqual(M.ratio(-83,2),-42);self.assertEqual(-M.ratio(83,2),-41)
  self.assertEqual(M.ceil_ratio(83,2),42)
 def test_exact_formula_preserves_intermediates_and_explicit_boundaries(self):
  self.assertEqual(rulings.calc('0.1+0.2',{}),Fraction(3,10))
  self.assertEqual(M.floor(rulings.calc('100*1.15',{})),115)
  self.assertEqual(rulings.calc('floor(7/2)*2',{}),6)
  self.assertEqual(M.floor(rulings.calc('(7/2)*2',{})),7)
  self.assertEqual(rulings.calc('ceil(7/2)*2',{}),8)
 def test_formula_rejects_nonfinite_and_executable_tokens(self):
  for bad in ('__import__("os")','[x for x in (1,2)]','(1).__class__','True','min(x=1)'):
   with self.subTest(bad=bad),self.assertRaises((ValueError,SyntaxError)):rulings.calc(bad,{})
  for bad in (True,float('nan'),float('inf')):
   with self.assertRaises(ValueError):M.floor(bad)
 def test_native_stat_table_all_stages_and_small_base_boundaries(self):
  for base in range(1,101):
   self.c.stats['atk']=base
   for stage in range(-6,7):
    self.c.stages['atk']=stage
    expected=max(1,(base*(10+(2*stage if stage>=0 else stage)))//10)
    self.assertEqual(self.c.staged('atk'),expected,(base,stage))
 def test_native_stat_percentage_addition_not_compounding_or_per_piece_floor(self):
  self.c.stages['atk']=2;self.assertEqual(self.c.staged('atk'),11)
  self.c.stages['atk']=6;self.assertEqual(self.c.staged('atk'),17)
  self.c.stages['atk']=-3;self.assertEqual(self.c.staged('atk'),5)
 def test_selected_stat_factor_override_does_not_become_an_increase(self):
  self.e.rule_mech('combat/combat-stage-multipliers','multiplier_by_stage.2',1.125,reason='explicit local alternative factor')
  self.c.stages['atk']=2;self.assertEqual(self.c.staged('atk'),9)
 def test_same_base_increases_sum_before_one_final_floor(self):
  self.assertEqual(M.increase(100,'0.2','0.3',quantity='stat',base_id='a/base',stage='boost'),150)
  self.assertEqual(M.increase(3,'0.2','0.3',quantity='stat',base_id='a/base',stage='boost'),4)
 def test_unlike_quantity_base_or_stage_cannot_be_pooled(self):
  for fields in [('hp','a/base','boost'),('stat','b/base','boost'),('stat','a/base','later')]:
   contribution=M.PercentageIncrease('0.2',*fields,'source/test')
   with self.assertRaises(ValueError):M.accumulate_increases(100,[contribution],quantity='stat',base_id='a/base',stage='boost')
  with self.assertRaises(ValueError):M.increase(100,'-0.2',quantity='stat',base_id='a/base',stage='boost')
 def test_native_tick_uses_exact_decimal_formula_boundary(self):
  self.e.rule_formula('tick','100*1.15',reason='exact selected formula boundary')
  self.assertEqual(self.e.tick(self.c),115)
 def test_native_sprint_is_one_fifty_percent_increase(self):
  self.c.custom_conditions['질주']={'source_policy':'ch06_once'}
  self.assertEqual(MOVE.distance_budget(self.e,self.c,'land'),10)
 def test_native_rest_floors_each_completed_block_not_combined_duration(self):
  self.assertEqual(self.c.base_max_hp,31);self.c.hp=1
  D.rest(self.e,self.c,60)
  self.assertEqual(self.c.hp,3)
  self.assertEqual(self.e.elapsed_seconds,3600)
 def test_encounter_xp_factors_remain_multiplicative(self):
  self.assertEqual(D.award_exp(self.r,[10],1,significance=2,challenge=1.5)[0],30)
  self.assertEqual(D.award_exp(self.r,[39],2,significance=1,challenge=1)[0],19)
 def test_native_round_up_cap_remains_specific_exception(self):
  self.c.damage_cap={'value':'max_hp/2','round':'up'}
  self.assertEqual(EXT.cap_damage(self.e,self.c,100),16)
  self.c.damage_cap={'value':'max_hp/2'}
  self.assertEqual(EXT.cap_damage(self.e,self.c,100),15)
 def test_gm_numeric_mutation_uses_signed_floor_without_changing_command_parsing(self):
  self.e.gm.set_initiative(self.c,-1.2,'explicit fractional GM input')
  self.assertEqual(self.c.initiative_override,-2)
 def test_separate_fixed_damage_factors_do_not_become_percent_increases(self):
  self.assertEqual(M.product(19,'1.5','0.5'),14)
  self.assertEqual(M.product(19,'1.5'),28)
  self.assertNotEqual(M.product(M.product(19,'1.5'),'2'),M.product(19,'1.5','2'))

if __name__=='__main__':
 result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ArithmeticConsumers))
 report={'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'passed':result.wasSuccessful(),'failed_details':[(str(t),trace) for t,trace in result.failures+result.errors]}
 (ROOT/'output/common-arithmetic-consumers-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
 sys.exit(not result.wasSuccessful())
