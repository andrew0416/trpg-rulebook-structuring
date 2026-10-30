"""Stockpile / Swallow / Spit Up: printed count semantics through actual paid Moves. Declared only; not locally run.

Editions are selected the way existing version tests do it: a fresh Rules whose
RuleFilter profile carries unit_versions, then _apply_ruleset(); the shared
ruleset is never mutated in place (that invalidates the selection index).
"""
from pathlib import Path
import sys,json,unittest
from copy import deepcopy
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_trainer
from ruleset import RuleFilter
import arithmetic_policy as M
import counter_effects as COUNTERS
import stockpile_moves as S
from state_codec import dump_engine,load_engine


class StockpileFamilyTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(ROOT,ruleset='core')
 def setUp(self):self.build(self.r)
 def build(self,rules):
  self.rules=rules;self.e=Engine(rules,41)
  def actor(name,moves):
   return Combatant(rules,build_trainer(rules,name,20,dict.fromkeys(('hp','atk','def','spa','spd','spe'),20),moves=moves))
  self.a=actor('user',[S.STOCKPILE,S.SWALLOW,S.SPIT]);self.b=actor('foe',[])
  self.e.everyone=self.e.gm.everyone=[self.a,self.b]
  self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20)
 def rules_for(self,version):
  rules=Rules(ROOT,ruleset='core');profile=deepcopy(rules.ruleset.profile)
  profile['unit_versions']={**profile.get('unit_versions',{}),S.SWALLOW:version}
  rules.ruleset=RuleFilter(profile);rules._apply_ruleset();return rules
 def stock(self,count):
  for _ in range(count):COUNTERS.change(self.e,self.a,{'name':'stockpile','delta':1,'max':3},S.STOCKPILE)
 def paid(self):return deepcopy((self.a.budget,self.a.move_uses,self.a.counters,self.a.stages))
 def injure(self):
  self.e.gm.set_hp(self.a,1,reason='actual fixture injury without a massive-damage injury');return self.a.hp
 def heal_expected(self,hp,num,den):
  # r598 / en11923 heal by the current maximum HP ('현재최대체력'), capped at that maximum
  return min(self.a.max_hp,hp+M.ratio(self.a.max_hp*num,den))

 def test_spit_up_is_refused_before_cost_without_a_count(self):
  before=self.paid()
  with self.assertRaisesRegex(ValueError,'Stockpiled count'):self.e.use_move(self.a,self.b,S.SPIT)
  self.assertEqual(self.paid(),before);self.assertNotIn(S.SPIT,self.a.move_uses);self.assertEqual(self.b.hp,self.b.base_max_hp)

 def test_spit_up_damage_base_is_eight_per_count_and_never_consumes_the_count(self):
  move=self.r.move(S.SPIT)
  for count in (1,2,3):
   with self.subTest(count=count):
    self.setUp();self.stock(count)
    self.assertEqual(self.e.damage_base(self.a,move,target=self.b),8*count)
    seen=[]
    def damage(a,t,m,*args,**kwargs):seen.append(self.e.damage_base(a,m,target=t));return 1
    with patch.object(self.e,'accuracy_check',return_value=(True,10,False)),patch.object(self.e,'roll_damage',side_effect=damage):
     self.e.use_move(self.a,self.b,S.SPIT)
    self.assertEqual(seen,[8*count]);self.assertEqual(self.a.counters['stockpile'],count)
    self.assertEqual((self.a.stages['def'],self.a.stages['spd']),(count,count));self.assertEqual(self.a.move_uses[S.SPIT],1)
    COUNTERS.validate(self.a)

 def test_swallow_without_a_count_is_a_paid_no_op(self):
  hp=self.injure();budget=deepcopy(self.a.budget)
  self.e.use_move(self.a,self.a,S.SWALLOW)
  self.assertEqual(self.a.hp,hp);self.assertEqual(self.a.move_uses[S.SWALLOW],1);self.assertNotEqual(self.a.budget,budget)
  self.assertEqual(self.a.counters.get('stockpile',0),0);COUNTERS.validate(self.a)
  load_engine(self.r,json.loads(json.dumps(dump_engine(self.e))))

 def test_swallow_english_edition_heals_quarter_half_full_and_clears_owned_stages(self):
  for count,(num,den) in ((1,(1,4)),(2,(1,2)),(3,(1,1))):
   with self.subTest(count=count):
    self.setUp();self.stock(count);hp=self.injure()
    self.e.use_move(self.a,self.a,S.SWALLOW)
    self.assertEqual(self.a.hp,self.heal_expected(hp,num,den))
    self.assertEqual((self.a.counters['stockpile'],self.a.stages['def'],self.a.stages['spd']),(0,0,0));COUNTERS.validate(self.a)

 def test_swallow_korean_literal_edition_keeps_one_and_two_and_refuses_undefined_three_before_cost(self):
  literal=self.rules_for('swallow-kr-literal');self.assertEqual(S.edition(literal),'swallow-kr-literal')
  for count,(num,den) in ((1,(1,4)),(2,(1,2))):
   with self.subTest(count=count):
    self.build(literal);self.stock(count);hp=self.injure()
    self.e.use_move(self.a,self.a,S.SWALLOW);self.assertEqual(self.a.hp,self.heal_expected(hp,num,den))
  self.build(literal);self.stock(3);before=self.paid()
  with self.assertRaisesRegex(ValueError,'count 3|GM ruling'):self.e.use_move(self.a,self.a,S.SWALLOW)
  self.assertEqual(self.paid(),before);self.assertNotIn(S.SWALLOW,self.a.move_uses)

 def test_unknown_swallow_edition_is_rejected_and_restore_keeps_counters(self):
  invented=self.rules_for('swallow-invented')
  with self.assertRaisesRegex(ValueError,'Swallow edition'):invented.move_mech(S.SWALLOW)
  self.stock(2)
  restored=load_engine(self.r,json.loads(json.dumps(dump_engine(self.e))));user=restored.everyone[0]
  COUNTERS.validate(user);self.assertEqual((user.counters['stockpile'],user.stages['def']),(2,2))


if __name__=='__main__':unittest.main()
