"""Source moves share timed status ownership, native consumers and scene history."""
from pathlib import Path
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_trainer
from grid import Grid
from state_codec import dump_engine,load_engine
import combat_timing as TIME

POUNCE='move/달려들기';LOOK='move/검은눈빛'

class SourcedConditionTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(ROOT,ruleset='core')
 def setUp(self):
  self.e=Engine(self.r,707);self.e.grid=Grid(20,10)
  self.a=self.actor('source',(2,2),'party');self.t=self.actor('target',(3,2),'enemy')
  self.second=self.actor('second source',(3,3),'party');self.other=self.actor('other target',(2,3),'enemy')
 def actor(self,name,pos,side):
  spec=build_trainer(self.r,name,30,{'hp':60,'atk':20,'def':20,'spa':20,'spd':20,'spe':20},extra={'moves':[POUNCE,LOOK],'pos':pos,'side':side,'size':'중형','abilities':[]})
  actor=Combatant(self.r,spec);self.e.gm.add_combatant(actor);return actor
 def begin(self):self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20)
 def next_turn(self,owner=None):
  self.e.end_of_turn(owner or self.a);self.e.end_round();self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20)
 def hit(self,mid=POUNCE,*,actor=None,target=None):
  with patch.object(self.e,'d20',return_value=10):return self.e.use_move(actor or self.a,target or self.t,mid)
 def limits(self,actor=None):return {k:v for k,v in (actor or self.t).counters.items() if k.startswith('lim:'+POUNCE+':')}
 def test_mean_look_pays_scene_action_and_reaches_native_slow_and_switch_consumers(self):
  self.begin();baseline=self.e.move_profile(self.t)[0];self.hit(LOOK)
  self.assertEqual(self.a.budget['standard'],0);self.assertEqual(self.a.move_uses[LOOK],1)
  self.assertTrue({'수렁','둔화'}<=self.t.conditions);self.assertLess(self.e.move_profile(self.t)[0],baseline)
  self.assertEqual({r['source'] for r in TIME.records(self.t)},{LOOK});self.assertEqual(len(TIME.records(self.t)),2)
  result=self.e.apply_effect(self.t,self.t,{'type':'switch_out'},None,True,0,'gm/actual-switch-attempt')
  self.assertEqual(result,(0,1));self.assertTrue(self.t.on_field)
  self.e.end_encounter(self.e.everyone);self.assertFalse({'수렁','둔화'}&self.t.conditions)
  self.assertEqual(self.e.move_profile(self.t)[0],baseline)
  self.assertEqual(self.e.apply_effect(self.t,self.t,{'type':'switch_out'},None,True,0,'gm/actual-later-switch'),(1,0))
  self.assertFalse(self.t.on_field)
 def test_pounce_actual_damage_applies_full_round_and_expires_at_exact_count(self):
  self.begin();hp=self.t.hp;self.hit();self.assertLess(self.t.hp,hp)
  self.assertIn('둔화',self.t.conditions);self.assertEqual(list(self.limits().values()),[1])
  self.e.end_of_turn(self.a);self.e.end_round();self.assertIn('둔화',self.t.conditions)
  self.e.start_round(self.e.everyone);self.e.at_initiative_count(21);self.assertIn('둔화',self.t.conditions)
  self.e.at_initiative_count(20);self.assertNotIn('둔화',self.t.conditions)
 def test_pounce_scene_history_is_per_actual_target_across_source_actors(self):
  self.begin();self.hit();self.next_turn();hp=self.t.hp;self.hit()
  self.assertLess(self.t.hp,hp);self.assertNotIn('둔화',self.t.conditions);self.assertEqual(list(self.limits().values()),[1])
  self.e.end_of_turn(self.a);self.e.start_of_turn(self.second,initiative_count=10);self.hit(actor=self.second)
  self.assertNotIn('둔화',self.t.conditions);self.assertEqual(list(self.limits().values()),[1]);self.assertFalse(self.limits(self.second))
  self.next_turn(self.second);self.hit(target=self.other)
  self.assertIn('둔화',self.other.conditions);self.assertEqual(list(self.limits().values()),[1]);self.assertEqual(list(self.limits(self.other).values()),[1])
 def test_encounter_end_keeps_scene_history_and_real_scene_end_resets_it(self):
  actors=list(self.e.everyone);self.begin();self.hit();self.e.end_encounter(actors)
  self.assertEqual(list(self.limits().values()),[1]);self.e.start_round(actors);self.e.start_of_turn(self.a,initiative_count=20)
  hp=self.t.hp;self.hit();self.assertLess(self.t.hp,hp);self.assertNotIn('둔화',self.t.conditions)
  self.e.end_scene(actors);self.assertFalse(self.limits());self.e.start_round(actors);self.e.start_of_turn(self.a,initiative_count=20)
  self.hit();self.assertIn('둔화',self.t.conditions);self.assertEqual(list(self.limits().values()),[1])
 def test_miss_and_explicit_zero_damage_do_not_spend_status_limit(self):
  self.begin();hp=self.t.hp
  with patch.object(self.e,'d20',return_value=1):self.e.use_move(self.a,self.t,POUNCE)
  self.assertEqual(self.t.hp,hp);self.assertNotIn('둔화',self.t.conditions);self.assertFalse(self.limits())
  effect=self.r.move_mech(POUNCE)[0]['effects_exec'][0]
  result=self.e.apply_effect(self.a,self.t,effect,None,True,0,POUNCE)
  self.assertEqual(result,(0,0));self.assertNotIn('둔화',self.t.conditions);self.assertFalse(self.limits())
 def test_mean_look_target_state_survives_source_recall_and_faint(self):
  self.begin();self.hit(LOOK);self.e.end_of_turn(self.a)
  self.e.gm.recall(self.a,reason='actual source recall');self.assertTrue({'수렁','둔화'}<=self.t.conditions)
  self.e.gm.faint(self.a,reason='actual source faint after recall');self.assertTrue({'수렁','둔화'}<=self.t.conditions)
  self.e.end_encounter(self.e.everyone);self.assertFalse({'수렁','둔화'}&self.t.conditions)
 def test_overlapping_full_round_and_encounter_statuses_keep_remaining_source(self):
  self.begin();self.hit();self.e.end_of_turn(self.a);self.e.start_of_turn(self.second,initiative_count=10);self.hit(LOOK,actor=self.second)
  self.assertEqual(len(TIME.records(self.t)),3);self.next_turn(self.second)
  self.assertEqual(len(TIME.records(self.t)),2);self.assertTrue({'수렁','둔화'}<=self.t.conditions)
  self.assertEqual({r['source'] for r in TIME.records(self.t)},{LOOK})
  self.e.end_encounter(self.e.everyone);self.assertFalse({'수렁','둔화'}&self.t.conditions)
 def test_json_keeps_independent_source_receipts_and_pair_history_after_expiry(self):
  self.begin();self.hit();self.e.end_of_turn(self.a);self.e.start_of_turn(self.second,initiative_count=10);self.hit(LOOK,actor=self.second)
  self.e=load_engine(self.r,json.loads(json.dumps(dump_engine(self.e))))
  actors={c.name:c for c in self.e.everyone};self.a=actors['source'];self.t=actors['target'];self.second=actors['second source'];self.other=actors['other target']
  self.assertEqual(list(self.limits().values()),[1]);self.assertEqual(len(TIME.records(self.t)),3)
  for record in TIME.records(self.t):
   receipt=self.e._effect_dispatch_receipts[record['effect_receipt']]
   self.assertIs(receipt['target'],self.t);self.assertIs(receipt['actor'],self.a if record['source']==POUNCE else self.second)
  self.next_turn(self.second);hp=self.t.hp;self.hit()
  self.assertLess(self.t.hp,hp);self.assertEqual(len(TIME.records(self.t)),2)
  self.assertTrue({'수렁','둔화'}<=self.t.conditions);self.assertEqual(list(self.limits().values()),[1])

if __name__=='__main__':unittest.main()
