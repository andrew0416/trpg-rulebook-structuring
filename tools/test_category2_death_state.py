"""Shared ordinary death policy, native HP/injury producers and both restores."""
from pathlib import Path
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_condition_recovery as FIX
from builder import build_trainer,build_pokemon
from engine import Engine
import effects_ext as EXT,turn as TURN,state_codec as CODEC

class DeathStateTests(unittest.TestCase):
 setUpClass=classmethod(FIX.ConditionRecoveryTests.setUpClass.__func__)
 setUp=FIX.ConditionRecoveryTests.setUp
 add=FIX.ConditionRecoveryTests.add
 restored=FIX.ConditionRecoveryTests.restored
 snap=FIX.ConditionRecoveryTests.snap
 def small(self):
  return [self.add(build_trainer(self.r,'small trainer',1,dict.fromkeys(('hp','atk','def','spa','spd','spe'),1),extra={'items':{},'edges':[]})),self.add(build_pokemon(self.r,'잉어킹',1,moves=[],abilities=[]))]
 def test_native_loss_at_each_hp_threshold_branch_and_equality_for_both_kinds(self):
  for c in self.actors+self.small():
   threshold=min(-50,-2*c.base_max_hp)
   self.assertEqual(threshold==-50,c.base_max_hp<=25)
   c.hp=threshold+2;self.e.check_fainted(c)
   self.assertFalse(c.dead);self.e.lose_hp(c,1);self.assertFalse(c.dead)
   self.e.lose_hp(c,1);self.assertEqual(c.hp,threshold);self.assertTrue(c.dead)
   self.assertLess(c.injuries,10);self.assertTrue(c.fainted)
 def test_friendly_native_loss_ignores_hp_threshold_but_not_injury_death(self):
  self.e.friendly_battle=True
  for c in self.actors+self.small():
   threshold=min(-50,-2*c.base_max_hp);c.hp=threshold+1
   self.e.lose_hp(c,2);self.assertEqual(c.hp,threshold-1);self.assertFalse(c.dead)
   c.injuries=9
   EXT.h_injury(self.e,self.a,c,{'value':1,'target':'target'},{})
   self.assertEqual(c.injuries,10);self.assertTrue(c.dead)
 def test_tenth_marker_injury_from_actual_damage_kills_even_in_friendly_battle(self):
  self.e.friendly_battle=True
  for c in self.actors:
   c.hp=1;c.injuries=9;self.e.take_damage(c,1)
   self.assertEqual((c.hp,c.injuries,c.dead),(0,10,True))
 def test_positive_hp_tenth_injury_kills_and_clears_recovery_timer(self):
  for c in self.actors:
   c.hp=0;self.e.check_fainted(c);self.e.heal(c,20,source_kind='ordinary_item')
   self.assertEqual(c.faint_recovery_seconds,600);c.injuries=9
   EXT.h_injury(self.e,self.a,c,{'value':1,'target':'target'},{})
   self.assertGreater(c.hp,0);self.assertTrue(c.dead);self.assertTrue(c.fainted)
   self.assertEqual((c.faint_recovery_seconds,c.faint_recovery_pending),(None,None))
 def test_true_maximum_not_injury_ceiling_defines_hp_death_threshold(self):
  for c in self.actors:
   c.injuries=3;self.assertLess(c.max_hp,c.base_max_hp)
   threshold=min(-50,-2*c.base_max_hp);c.hp=threshold+1
   self.e.check_fainted(c);self.assertFalse(c.dead)
   self.e.lose_hp(c,1);self.assertTrue(c.dead)
 def test_temporary_hp_absorption_can_delay_actual_hp_death_but_not_injury_death(self):
  for c in self.actors:
   threshold=min(-50,-2*c.base_max_hp);c.hp=threshold+1;self.e.gm.set_temp_hp(c,1)
   self.e.lose_hp(c,1);self.assertEqual(c.hp,threshold+1);self.assertFalse(c.dead)
   self.e.lose_hp(c,1);self.assertTrue(c.dead)
  self.setUp()
  for c in self.actors:
   self.e.gm.set_temp_hp(c,1000);c.injuries=9
   EXT.h_injury(self.e,self.a,c,{'value':1,'target':'target'},{})
   self.assertTrue(c.dead);self.assertEqual(c.temp_hp,1000)
 def test_opt_out_disables_both_death_causes_without_disabling_faint(self):
  self.e.death_enabled=False
  for c in self.actors:
   c.hp=min(-50,-2*c.base_max_hp);c.injuries=10;self.e.check_fainted(c)
   self.assertFalse(c.dead);self.assertTrue(c.fainted)
   self.assertFalse(TURN.can_act(self.e,c))
  loaded=self.restored();self.assertFalse(loaded.death_enabled)
  for original in self.actors:
   c=next(x for x in loaded.gm.everyone if x.entity_id==original.entity_id)
   loaded.check_fainted(c);self.assertFalse(c.dead);self.assertTrue(c.fainted)
 def test_ordinary_heal_revive_and_injury_healing_cannot_resurrect(self):
  for c in self.actors:
   c.hp=1;c.injuries=9;EXT.h_injury(self.e,self.a,c,{'value':1,'target':'target'},{})
   before=(c.hp,c.injuries,c.temp_hp,c.dead)
   for kind in ('ordinary_item','move','feature','explicit_revive','rest'):
    self.assertEqual(self.e.heal(c,1000,source_kind=kind),0)
   self.assertFalse(self.e.revive(c,10))
   EXT.h_heal_injury(self.e,c,c,{'value':1},{})
   self.e.advance_time(600,[c]);self.assertEqual((c.hp,c.injuries,c.temp_hp,c.dead),before)
   self.assertFalse(TURN.can_act(self.e,c));self.assertEqual(c.evasion('물리'),0)
 def test_native_policy_and_death_survive_both_restores_and_replay_transition(self):
  for friendly in (False,True):
   self.setUp();self.e.friendly_battle=friendly
   for c in self.actors:c.hp=1;c.injuries=9
   self.e.gm.snapshot('before-death');loaded=self.restored()
   for e in (self.e,loaded):
    self.assertEqual(e.friendly_battle,friendly);self.assertTrue(e.death_enabled)
    for original in self.actors:
     c=next(x for x in e.gm.everyone if x.entity_id==original.entity_id)
     e.take_damage(c,1);self.assertTrue(c.dead)
   dead=self.restored()
   for original in self.actors:
    c=next(x for x in dead.gm.everyone if x.entity_id==original.entity_id)
    self.assertTrue(c.dead);self.assertFalse(TURN.can_act(dead,c));self.assertFalse(dead.revive(c,10))
   self.e.gm.restore('before-death')
   for c in self.actors:self.assertFalse(c.dead);self.e.take_damage(c,1);self.assertTrue(c.dead)
 def test_explicit_gm_revive_is_separate_and_does_not_resurrect_by_policy_toggle(self):
  for c in self.actors:
   c.hp=min(-50,-2*c.base_max_hp);self.e.check_fainted(c);self.assertTrue(c.dead)
   self.e.death_enabled=False;self.e.friendly_battle=True;self.e.check_fainted(c);self.assertTrue(c.dead)
   self.e.gm.revive(c,1,reason='explicit external resurrection ruling')
   self.assertFalse(c.dead);self.assertFalse(c.fainted);self.e.death_enabled=True;self.e.friendly_battle=False

if __name__=='__main__':unittest.main()
