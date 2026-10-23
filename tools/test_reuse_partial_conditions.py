"""Typed coat consumption and selected custom volatile turn damage."""
from pathlib import Path
import sys,unittest,json
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_reuse_partial_completion as FIX
from engine import Rules
from state_codec import dump_engine,load_engine
import coat_effects as COATS
import damage_coats as DAMAGE_COATS
import custom_condition_effects as CUSTOM
import effects_ext as EXT
import status_sets as STATUS

class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(ROOT,ruleset='core')
 def setUp(self):
  FIX.Tests.setUp(self)
  self.a.moves+=['move/불꽃세례','move/소금절이']
 def coat(self,source='move/타르샷'):
  raw=COATS.definition(self.r,source)['raw']
  self.assertEqual(self.e.apply_effect(self.a,self.b,raw,nat=None,hit=True,dealt=0,src=source),(1,0))
 def custom(self):
  row=CUSTOM.definition(self.r,'move/소금절이')
  self.assertEqual(self.e.apply_effect(self.a,self.b,row['raw'],nat=None,hit=True,dealt=0,src='move/소금절이'),(1,0))
 def test_coat_effectiveness_queries_are_read_only_and_keep_actual_creator(self):
  self.coat();before=dump_engine(self.e);move=self.r.move('move/불꽃세례')
  for _ in range(2):self.assertEqual(EXT.effectiveness_hook(self.e,self.a,self.b,move,{},1,{}),1.5)
  self.assertEqual(dump_engine(self.e),before)
  self.assertEqual(COATS.live(self.b)[0]['effect_instance']['applied_by_actor_id'],self.a.entity_id)
 def test_real_matching_damage_consumes_once_after_application(self):
  self.coat();self.e.accuracy_check=lambda *a,**k:(True,10,False)
  with patch.object(self.e,'roll_damage',return_value=5):self.e.use_move(self.a,self.b,'move/불꽃세례')
  self.assertFalse(COATS.live(self.b));history=self.b.spec['effect_instance_history']
  self.assertEqual((len(history),history[0]['effect_instance']['state']),(1,'consumed'))
 def test_miss_zero_wrong_type_and_nonattack_loss_keep_coat(self):
  self.coat()
  with patch.object(self.e,'accuracy_check',return_value=(False,1,False)):self.e.use_move(self.a,self.b,'move/불꽃세례')
  self.e.lose_hp(self.b,2,source='actual environmental loss')
  self.assertEqual(len(COATS.live(self.b)),1)
  receipt={'requested':0,'net_hp_loss':0,'net_temporary_hp_loss':0}
  DAMAGE_COATS.after_damage(self.e,self.a,self.b,self.r.move('move/불꽃세례'),receipt)
  self.assertEqual(len(COATS.live(self.b)),1)
 def test_resistance_coat_targets_actual_recipient_and_roundtrips(self):
  self.coat('move/물놀이')
  self.assertFalse(COATS.live(self.a));self.assertEqual(DAMAGE_COATS.steps(self.e,self.b,self.r.move('move/불꽃세례')),-1)
  e=load_engine(self.r,json.loads(json.dumps(dump_engine(self.e))));self.assertEqual(len(COATS.live(e.everyone[1])),1)
 def test_custom_condition_ticks_once_at_actual_holder_turn(self):
  self.custom();before=self.b.hp
  self.e.end_of_turn(self.a);self.e.start_of_turn(self.b,initiative_count=10)
  self.assertEqual(self.b.hp,before-self.e.tick(self.b))
  CUSTOM.turn_start(self.e,self.b);self.assertEqual(self.b.hp,before-self.e.tick(self.b))
  self.assertEqual(STATUS.afflictions(self.b,'volatile'),('소금절이',))
 def test_current_holder_types_select_double_ticks_without_double_counting(self):
  self.e.gm.set_types(self.b,['물','강철'],reason='actual dual type')
  self.custom();before=self.b.hp
  self.e.end_of_turn(self.a);self.e.start_of_turn(self.b,initiative_count=10)
  self.assertEqual(self.b.hp,before-2*self.e.tick(self.b))
 def test_cure_volatile_and_json_restore_use_common_condition_lifecycle(self):
  self.custom();e=load_engine(self.r,json.loads(json.dumps(dump_engine(self.e))));b=e.everyone[1]
  STATUS.cure_group(e,b,'volatile')
  self.assertNotIn('소금절이',b.conditions);self.assertFalse(CUSTOM.records(b))
  self.assertEqual(b.spec['effect_instance_history'][-1]['effect_instance']['state'],'expired')
 def test_native_salt_cure_connects_typed_condition(self):
  with patch.object(self.e,'accuracy_check',return_value=(True,10,False)),patch.object(self.e,'roll_damage',return_value=1):
   self.e.use_move(self.a,self.b,'move/소금절이')
  self.assertEqual(len(CUSTOM.records(self.b)),1)
 def test_real_wrong_type_keeps_tar_but_successful_zero_damage_hit_consumes_it(self):
  self.coat();self.a.moves.append('move/몸통박치기')
  with patch.object(self.e,'accuracy_check',return_value=(True,10,False)),patch.object(self.e,'roll_damage',return_value=2):
   self.e.use_move(self.a,self.b,'move/몸통박치기')
  self.assertEqual(len(COATS.live(self.b)),1)
  self.e.end_of_turn(self.a);self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20)
  with patch.object(self.e,'accuracy_check',return_value=(True,10,False)),patch.object(self.e,'roll_damage',return_value=0):
   self.e.use_move(self.a,self.b,'move/불꽃세례')
  self.assertFalse(COATS.live(self.b))
 def test_damage_fully_absorbed_by_actual_temporary_hp_consumes_once(self):
  self.coat();self.e.gm.set_temp_hp(self.b,20,reason='actual temporary HP')
  hp=self.b.hp
  with patch.object(self.e,'accuracy_check',return_value=(True,10,False)),patch.object(self.e,'roll_damage',return_value=5):
   self.e.use_move(self.a,self.b,'move/불꽃세례')
  self.assertEqual(self.b.hp,hp);self.assertEqual(self.b.temp_hp,15);self.assertFalse(COATS.live(self.b))

if __name__=='__main__':unittest.main()
