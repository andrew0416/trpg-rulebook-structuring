"""Actual target-global Pounce scene limit boundaries through the public move API."""
import json,unittest
from unittest.mock import patch
from state_codec import dump_engine,load_engine
from test_category2_sourced_conditions import POUNCE
import test_category2_sourced_conditions as _fixture_test_category2_sourced_conditions
import combat_timing as TIME

class PounceTargetSceneTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):_fixture_test_category2_sourced_conditions.SourcedConditionTests.setUpClass()
 def world(self):
  f=_fixture_test_category2_sourced_conditions.SourcedConditionTests();f.setUp();return f
 def restore(self,f):
  ids={key:getattr(f,key).entity_id for key in ('a','t','second','other')}
  f.e=load_engine(f.r,json.loads(json.dumps(dump_engine(f.e),ensure_ascii=False)))
  for key,entity_id in ids.items():setattr(f,key,next(a for a in f.e.everyone if a.entity_id==entity_id))
 def test_second_user_stays_blocked_after_expiry_and_json_then_scene_reset_reopens_target(self):
  f=self.world();f.begin();f.hit();f.next_turn();self.assertNotIn('둔화',f.t.conditions)
  self.restore(f);self.assertEqual(list(f.limits().values()),[1]);self.assertFalse(TIME.records(f.t))
  f.e.end_of_turn(f.a);f.e.start_of_turn(f.second,initiative_count=10)
  hp=f.t.hp;f.hit(actor=f.second);self.assertLess(f.t.hp,hp)
  self.assertNotIn('둔화',f.t.conditions);self.assertEqual(list(f.limits().values()),[1]);self.assertFalse(f.limits(f.second))
  f.e.end_scene(f.e.everyone);self.assertFalse(f.limits())
  f.e.start_round(f.e.everyone);f.e.start_of_turn(f.second,initiative_count=10)
  f.hit(actor=f.second);self.assertIn('둔화',f.t.conditions);self.assertEqual(list(f.limits().values()),[1])
 def test_different_actual_targets_with_same_name_have_independent_scene_limits(self):
  f=self.world();other=f.actor('target',(4,3),'enemy')
  self.assertEqual(other.name,f.t.name);self.assertEqual(other.stats,f.t.stats);self.assertNotEqual(other.entity_id,f.t.entity_id)
  f.begin();f.hit();f.next_turn();f.e.end_of_turn(f.a);f.e.start_of_turn(f.second,initiative_count=10)
  f.hit(actor=f.second,target=other)
  self.assertIn('둔화',other.conditions);self.assertNotIn('둔화',f.t.conditions)
  self.assertEqual(list(f.limits(other).values()),[1]);self.assertEqual(list(f.limits().values()),[1])
 def test_miss_keeps_target_history_and_lifetime_untouched_then_second_user_can_apply(self):
  f=self.world();f.begin();hp=f.t.hp;before=dict(f.t.counters)
  with patch.object(f.e,'d20',return_value=1):f.e.use_move(f.a,f.t,POUNCE)
  self.assertEqual(f.t.hp,hp);self.assertEqual(f.t.counters,before);self.assertFalse(TIME.records(f.t))
  self.assertNotIn('둔화',f.t.conditions);self.assertFalse(f.limits());self.assertFalse(f.limits(f.a))
  self.assertEqual((f.a.budget['standard'],f.a.move_uses[POUNCE]),(0,1))
  f.e.end_of_turn(f.a);f.e.start_of_turn(f.second,initiative_count=10);f.hit(actor=f.second)
  self.assertIn('둔화',f.t.conditions);self.assertEqual(list(f.limits().values()),[1])
 def test_target_scene_history_does_not_depend_on_first_user_remaining_registered(self):
  f=self.world();f.begin();f.hit();f.next_turn()
  f.e.gm.recall(f.a,reason='actual first Pounce user recall')
  f.e.gm.faint(f.a,reason='actual first Pounce user faint')
  f.e.end_of_turn(f.a);f.e.start_of_turn(f.second,initiative_count=10);hp=f.t.hp
  f.hit(actor=f.second);self.assertLess(f.t.hp,hp);self.assertNotIn('둔화',f.t.conditions)
  self.assertEqual(list(f.limits().values()),[1])

if __name__=='__main__':unittest.main()
