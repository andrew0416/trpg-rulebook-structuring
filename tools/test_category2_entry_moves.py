"""Entry-limited source moves through real turns, field entry and persistence."""
from pathlib import Path
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_trainer,build_pokemon
from grid import Grid
from state_codec import dump_engine,load_engine
import effects_ext as EXT

MOVES=('move/만나자마자','move/속이기')

class EntryMoveTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(ROOT,ruleset='core')
 def setUp(self):
  self.e=Engine(self.r,706);self.e.grid=Grid(20,10)
  self.a=self.actor('source',(2,2),'party');self.t=self.actor('target',(3,2),'enemy')
 def actor(self,name,pos,side,*,pokemon=False):
  extra={'moves':list(MOVES)+['move/몸통박치기'],'pos':pos,'side':side,'size':'중형','abilities':[]}
  spec=build_pokemon(self.r,'이상해씨',30,name=name,moves=extra['moves'],extra=extra) if pokemon else build_trainer(self.r,name,30,{'hp':60,'atk':20,'def':20,'spa':20,'spd':20,'spe':20},extra=extra)
  actor=Combatant(self.r,spec);self.e.gm.add_combatant(actor);return actor
 def begin(self):self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20)
 def next_turn(self):
  self.e.end_of_turn(self.a);self.e.end_round();self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20)
 def hit(self,mid=MOVES[0],*,area=False):
  with patch.object(self.e,'d20',return_value=10):
   return self.e.use_move_on(self.a,self.t,mid,self.e.everyone) if area else self.e.use_move(self.a,self.t,mid)
 def state(self):
  with patch.object(self.e,'log_lines',[]):return dump_engine(self.e)
 def reject(self,mid,*,area=False):
  before=self.state();self.assertEqual(self.hit(mid,area=area),0);self.assertEqual(before,self.state())
 def test_actual_first_turn_preserves_two_sources_priority_cost_hit_and_flinch(self):
  for mid in MOVES:
   for pokemon in (False,True):
    with self.subTest(move=mid,pokemon=pokemon):
     self.setUp()
     if pokemon:
      self.a.on_field=False;self.a=self.actor('Pokemon source',(2,2),'party',pokemon=True)
     self.begin();hp=self.t.hp;self.hit(mid)
     self.assertLess(self.t.hp,hp);self.assertEqual(self.a.budget['standard'],0)
     self.assertEqual(self.a.turns_taken,1);self.assertEqual(self.a.move_uses[mid],1)
     self.assertEqual('풀죽음' in self.t.conditions,mid==MOVES[1]);self.assertFalse(self.a.registry)
 def test_later_turn_rejects_before_direct_or_approach_action_and_rng(self):
  for mid in MOVES:
   for area in (False,True):
    with self.subTest(move=mid,area=area):
     self.setUp();self.begin();self.next_turn();self.next_turn()
     self.e.gm.set_position(self.t,(8,2),reason='actual distant target before rejected approach')
     self.assertEqual(self.a.turns_taken,3);self.reject(mid,area=area)
 def test_actual_recall_and_release_rearm_entry_without_resetting_move_frequency(self):
  for mid in MOVES:
   with self.subTest(move=mid):
    self.setUp();self.begin();self.hit(mid);self.next_turn();self.next_turn();self.reject(mid)
    uses=dict(self.a.move_uses);self.e.end_of_turn(self.a)
    self.e.gm.recall(self.a,reason='actual switch out');self.reject(mid)
    self.e.gm.send_out(self.a,(2,2),reason='actual re-release')
    self.assertEqual(self.a.turns_taken,0);self.assertEqual(self.a.move_uses,uses)
    self.e.end_round();self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20)
    hp=self.t.hp;self.hit(mid);self.assertLess(self.t.hp,hp);self.assertEqual(self.a.move_uses[mid],2)
 def test_duplicate_send_out_and_unrelated_stage_reset_do_not_rearm_entry(self):
  self.begin();self.next_turn();self.e.gm.send_out(self.a,(2,2),reason='already on field, no new entry')
  self.assertEqual(self.a.turns_taken,2)
  reset=dict(next(x for x in self.r.moves_mech['move/흑안개']['effects'] if x['type']=='reset_stages'),target='self')
  self.e.apply_effect(self.a,self.a,reset,None,True,0,'gm/stage-reset')
  self.assertEqual(self.a.turns_taken,2);self.reject(MOVES[1])
 def test_encounter_end_resets_members_and_next_encounter_has_a_fresh_first_turn(self):
  actors=list(self.e.everyone);self.begin();self.hit(MOVES[1]);self.next_turn();self.reject(MOVES[1])
  self.e.end_encounter([self.t]);self.assertEqual(self.a.turns_taken,0)
  self.e.start_round(actors);self.e.start_of_turn(self.a,initiative_count=20);hp=self.t.hp;self.hit(MOVES[1])
  self.assertLess(self.t.hp,hp);self.assertEqual(self.a.turns_taken,1)
 def test_json_restore_preserves_late_turn_then_actual_reentry_qualifies(self):
  self.begin();self.next_turn();self.next_turn()
  self.e=load_engine(self.r,json.loads(json.dumps(dump_engine(self.e))))
  self.a=next(c for c in self.e.everyone if c.name=='source');self.t=next(c for c in self.e.everyone if c.name=='target')
  self.assertEqual(self.a.turns_taken,3);self.reject(MOVES[0],area=True)
  self.e.end_of_turn(self.a);self.e.gm.recall(self.a,reason='restored actual switch')
  self.e.gm.send_out(self.a,(2,2),reason='restored actual release');self.e.end_round()
  self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20);hp=self.t.hp
  self.hit();self.assertLess(self.t.hp,hp);self.assertEqual(self.a.turns_taken,1)
 def test_miss_keeps_first_turn_counter_and_does_not_invent_a_consumed_entry_quota(self):
  self.begin();hp=self.t.hp
  with patch.object(self.e,'d20',return_value=1):self.e.use_move(self.a,self.t,MOVES[1])
  self.assertEqual(self.t.hp,hp);self.assertNotIn('풀죽음',self.t.conditions)
  self.assertEqual(self.a.turns_taken,1);self.assertEqual(self.a.move_uses[MOVES[1]],1)
  self.assertTrue(EXT.entry_move_allowed(self.e,self.a,self.r.move(MOVES[1]),self.r.move_mech(MOVES[1])[0]))
 def test_no_encounter_off_field_and_invalid_counter_reject_before_payment(self):
  self.reject(MOVES[0]);self.begin();self.e.end_of_turn(self.a);self.e.gm.recall(self.a,reason='actual off-field source')
  self.reject(MOVES[1]);self.e.gm.send_out(self.a,reason='actual return for invalid state check')
  self.a.turns_taken=-1;before=(dict(self.a.budget),dict(self.a.move_uses),self.e.rng.getstate(),self.a.pos,self.t.hp)
  with self.assertRaisesRegex(ValueError,'actual turns since field entry'):self.e.use_move(self.a,self.t,MOVES[0])
  self.assertEqual(before,(dict(self.a.budget),dict(self.a.move_uses),self.e.rng.getstate(),self.a.pos,self.t.hp))

if __name__=='__main__':unittest.main()
