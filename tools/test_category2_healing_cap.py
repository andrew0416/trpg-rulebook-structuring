"""Injury ceiling versus actual maximum: native passive consumers and persistence.
Whole C07-183 remains open at the separately recorded rounding/other-source boundary.
"""
from pathlib import Path
from copy import deepcopy
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_condition_recovery as FIX
from engine import Rules
import life as LIFE,effects as FX,effects_ext as EXT,downtime as D,encounter as ENC

class HealingCapTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='playtest')
 setUp=FIX.ConditionRecoveryTests.setUp
 add=FIX.ConditionRecoveryTests.add
 restored=FIX.ConditionRecoveryTests.restored
 def ability(self,c,name):self.e.gm.set_ability(c,name,True,reason='observed native full-HP ability')
 def damage(self,c):return self.e.roll_damage(self.target,c,self.r.move('move/메가톤펀치'),set_damage=True)
 def test_native_full_hp_abilities_do_not_treat_injury_cap_as_actual_full_hp(self):
  for name in ('멀티스케일 [Playtest]',):
   for kind in ('trainer','pokemon'):
    self.setUp();c=self.a if kind=='trainer' else self.p;c.injuries=3;c.hp=c.max_hp
    without=self.damage(c);self.ability(c,name)
    self.assertFalse(LIFE.at_full_hp(c));self.assertEqual(self.damage(c),without)
    self.e.gm.set_temp_hp(c,1000);self.assertEqual(self.damage(c),without)
    c.hp=c.base_max_hp;self.assertTrue(LIFE.at_full_hp(c));self.assertLess(self.damage(c),without)
    c.hp-=1;self.assertEqual(self.damage(c),without)
 def test_native_fractional_heal_uses_actual_base_but_stops_at_injury_cap(self):
  for c in self.actors:
   self.e.gm.set_move(c,'move/hp회복',True,reason='observed actual recovery move')
   c.injuries=3;c.hp=1
   self.e.use_move(c,c,'move/hp회복')
   self.assertEqual(c.hp,min(c.max_hp,1+c.base_max_hp//2));self.assertEqual(c.injuries,3)
   before=c.hp;self.e.heal(c,1000,source_kind='move');self.assertEqual(c.hp,c.max_hp)
   c.hp=c.base_max_hp;self.assertEqual(self.e.heal(c,1000,source_kind='move'),0);self.assertEqual(c.hp,c.base_max_hp)
 def test_divisible_source_example_and_rest_tick_preserve_distinct_values(self):
  c=self.a;self.assertEqual(c.base_max_hp,80);c.injuries=3;c.hp=50
  D.rest(self.e,c,30);self.assertEqual((c.hp,c.max_hp,c.base_max_hp),(55,56,80))
  D.rest(self.e,c,30);self.assertEqual(c.hp,56);self.assertFalse(LIFE.at_full_hp(c))
 def test_new_damage_injury_threshold_uses_true_maximum_despite_existing_injuries(self):
  for c in self.actors:
   c.injuries=3;c.hp=c.base_max_hp;old=c.injuries
   damage=c.max_hp//2
   self.e.take_damage(c,damage)
   self.assertEqual(c.injuries,old)
   self.assertGreater(c.hp,c.base_max_hp/2)
 def test_gm_and_durable_restore_preserve_distinct_hp_bases_and_native_passive(self):
  for c in self.actors:self.ability(c,'멀티스케일 [Playtest]');c.injuries=3;c.hp=c.max_hp
  expected={c.entity_id:(c.hp,c.max_hp,c.base_max_hp,self.damage(c)) for c in self.actors}
  self.e.gm.snapshot('injured');loaded=self.restored()
  for c in self.actors:
   other=next(x for x in loaded.gm.everyone if x.entity_id==c.entity_id)
   target=next(x for x in loaded.gm.everyone if x.entity_id==self.target.entity_id)
   damage=loaded.roll_damage(target,other,self.r.move('move/메가톤펀치'),set_damage=True)
   self.assertEqual((other.hp,other.max_hp,other.base_max_hp,damage),expected[c.entity_id])
   c.injuries=0;c.hp=c.base_max_hp
  self.e.gm.restore('injured')
  for c in self.actors:self.assertEqual((c.hp,c.max_hp,c.base_max_hp,self.damage(c)),expected[c.entity_id])
 def test_encounter_capture_candidate_uses_actual_half_not_injury_ceiling(self):
  self.a.pos=(0,0);self.p.pos=(1,0);self.p.spec['wild']=True;self.p.side='wild'
  self.a.spec['items']['poke_ball']=1;self.p.injuries=3;self.p.hp=self.p.base_max_hp//2
  self.assertGreater(self.p.hp,self.p.max_hp/2)
  kind,move,target=ENC.choose_action(self.e,self.a,[self.p],[self.a])
  self.assertEqual(kind,'ball');self.assertIs(target,self.p)

if __name__=='__main__':unittest.main()
