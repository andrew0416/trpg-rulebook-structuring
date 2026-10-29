"""Explicit HP-setting effects keep actual HP semantics despite damage caps."""
from copy import deepcopy
from unittest.mock import patch
import unittest
import test_category2_temporary_hp_state as FIX
import effects as FX,effects_ext as EXT,temporary_hp as TEMP,world_entities as W

class Tests(unittest.TestCase):
 setUpClass=classmethod(FIX.TemporaryHPStateTests.setUpClass.__func__)
 setUp=FIX.TemporaryHPStateTests.setUp
 add=FIX.TemporaryHPStateTests.add
 restored=FIX.TemporaryHPStateTests.restored
 grant=FIX.TemporaryHPStateTests.grant
 def prepare(self,actor,move):
  actor.pos=(1,1);target=self.target;target.pos=(2,1);target.side='enemy'
  self.e.gm.set_move(actor,move,True,reason='actual selected source for HP setting')
  self.e.start_round([actor,target]);self.e.start_of_turn(actor)
  return target
 def test_selected_final_gambit_zero_effect_ignores_cap_and_retains_temporary_pool(self):
  for kind in ('trainer','pokemon'):
   with self.subTest(kind=kind):
    self.setUp();actor=self.a if kind=='trainer' else self.p
    self.grant(actor,1000)
    actor.damage_cap={'value':1};lifetime=deepcopy(actor.custom_conditions[TEMP.STATE])
    effect=next(e for e in self.r.move_mech('move/목숨걸기')[0]['effects_exec'] if e['type']=='self_hp_set')
    FX.h_self_hp_set(self.e,actor,actor,effect,{'source_id':'move/목숨걸기','attacker':actor,'engine':self.e})
    self.assertEqual((actor.hp,actor.temp_hp),(0,1000));self.assertTrue(actor.fainted)
    self.assertEqual(actor.custom_conditions[TEMP.STATE],lifetime)
 def test_actual_execute_ignores_zero_damage_cap_without_spending_barrier(self):
  target=self.prepare(self.a,'move/절대영도');self.grant(target,1000)
  target.damage_cap={'value':0};lifetime=deepcopy(target.custom_conditions[TEMP.STATE])
  with patch.object(self.e,'accuracy_check',return_value=(True,10,False)),patch.object(self.e,'roll_damage',return_value=0),patch.object(EXT.POOLS,'die',return_value=1):
   self.e.use_move(self.a,target,'move/절대영도',set_damage=True)
  self.assertEqual((target.hp,target.temp_hp),(0,1000));self.assertTrue(target.fainted)
  self.assertEqual(target.custom_conditions[TEMP.STATE],lifetime)
 def test_selected_zero_effect_and_cap_survive_gm_and_json_restore(self):
  actor=self.a;self.grant(actor,35);actor.damage_cap={'value':1}
  effect=next(e for e in self.r.move_mech('move/목숨걸기')[0]['effects_exec'] if e['type']=='self_hp_set')
  self.e.gm.snapshot('before actual zero effect');hp=actor.hp
  def apply(engine,c):
   FX.h_self_hp_set(engine,c,c,effect,{'source_id':'move/목숨걸기','attacker':c,'target':c,'engine':engine})
   self.assertEqual((c.hp,c.temp_hp),(0,35));self.assertTrue(c.fainted)
  loaded=self.restored();copy=W.actor_index(loaded)[actor.entity_id]
  apply(self.e,actor);apply(loaded,copy)
  self.e.gm.restore('before actual zero effect')
  self.assertEqual((actor.hp,actor.temp_hp,actor.damage_cap),(hp,35,{'value':1}))
  apply(self.e,actor)
  again=self.restored();copy=W.actor_index(again)[actor.entity_id]
  self.assertEqual((copy.hp,copy.temp_hp),(0,35));self.assertTrue(copy.fainted)

if __name__=='__main__':unittest.main()
