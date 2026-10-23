"""Belch consumes the native food exchange history and narrative scene boundary."""
from copy import deepcopy
from pathlib import Path
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine
import test_category3_pokemon_activities as ACTIVITY_TESTS
import food_effects as FOOD
from state_codec import dump_engine,load_engine

class FoodSceneHistoryTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='core')
 actor=ACTIVITY_TESTS.PokemonActivityTests.actor
 def setUp(self):
  self.e=Engine(self.rules,seed=181)
  self.a=self.actor('trainer','trainer');self.p=self.actor('wild','pokemon');self.q=self.actor('other','pokemon')
  self.p.spec.update(wild=True,side='wild',disposition='중립',nature='대담');self.p.side='wild'
  for actor in (self.a,self.p,self.q):self.e.gm.add_combatant(actor)
 def state(self):
  return deepcopy((self.e.rng.getstate(),self.e.elapsed_seconds,self.e.round_no,self.e.encounter_active,[(c.spec,c.hp,c.temp_hp,c.stages,c.buffs,c.conditions,c.custom_conditions,c.counters,c.move_uses,c.last_move,getattr(c,'budget',None),getattr(c,'_action_history',None),getattr(c,'pending_action_loss',None),c.modifiers,c.registry) for c in (self.a,self.p,self.q)]))
 def feed(self,actor=None):
  actor=self.p if actor is None else actor
  self.a.spec['items']['초코바']=self.a.spec['items'].get('초코바',0)+1
  self.e.use_item(self.a,'초코바',actor,duration_minutes=1,duration_reason='actual snack intake')
  return actor.buffs[-1]['id']
 def consume(self,actor=None):
  actor=self.p if actor is None else actor;uid=self.feed(actor)
  self.e.consume_food_buff(actor,buff_id=uid,action_kind='free',action_reason='actual food consumption')
  return actor.spec['food_consumption_receipts'][-1]
 def begin(self):
  self.p.moves=['move/트림','move/볼가득넣기'];self.e.start_round([self.p,self.q]);self.e.start_of_turn(self.p)
 def next_turn(self):
  self.e.end_of_turn(self.p);self.e.end_round();self.e.start_round([self.p,self.q]);self.e.start_of_turn(self.p)
 def reject_without_cost(self):
  before=self.state();self.assertEqual(self.e.use_move(self.p,self.q,'move/트림'),0)
  self.assertEqual(before,self.state())
 def test_no_food_eating_only_and_counter_only_refuse_before_action_frequency_or_rng(self):
  for mode in ('none','eaten','counter'):
   self.setUp()
   if mode=='eaten':self.feed()
   if mode=='counter':self.p.counters['food_buff_consumed']=17
   self.begin();self.reject_without_cost();self.assertFalse(FOOD.consumed_this_scene(self.e,self.p))
 def test_actual_consumption_allows_real_belch_without_consuming_history_again(self):
  receipt=deepcopy(self.consume());self.begin();self.e.rng.seed(5);hp=self.q.hp
  self.e.use_move(self.p,self.q,'move/트림')
  self.assertLess(self.q.hp,hp);self.assertEqual(self.p.budget['standard'],0)
  self.assertEqual(self.p.move_uses['move/트림'],1);self.assertEqual(self.p.spec['food_consumption_receipts'],[receipt])
 def test_another_actor_consumption_does_not_qualify_attacker(self):
  self.consume(self.q);self.begin();self.assertTrue(FOOD.consumed_this_scene(self.e,self.q));self.reject_without_cost()
 def test_encounter_preserves_same_scene_but_scene_end_invalidates_old_receipt(self):
  self.consume();self.begin();self.e.end_of_turn(self.p);self.e.end_encounter(self.e.everyone)
  self.assertTrue(FOOD.consumed_this_scene(self.e,self.p));history=deepcopy(self.p.spec['food_consumption_receipts'])
  self.e.end_scene([self.a,self.p,self.q]);self.assertFalse(FOOD.consumed_this_scene(self.e,self.p))
  self.assertEqual(history,self.p.spec['food_consumption_receipts']);self.assertGreater(self.p.counters['food_buff_consumed'],0)
  self.begin();self.reject_without_cost()
 def test_native_scene_frequency_spacing_and_quota_still_apply_after_qualification(self):
  self.consume();self.begin();self.e.accuracy_check=lambda *a,**k:(False,1,False)
  self.e.use_move(self.p,self.q,'move/트림');self.assertEqual(self.p.move_uses['move/트림'],1)
  self.next_turn();self.reject_without_cost();self.next_turn();self.e.use_move(self.p,self.q,'move/트림')
  self.assertEqual(self.p.move_uses['move/트림'],2);self.next_turn();self.next_turn();self.reject_without_cost()
 def test_actual_stuff_cheeks_exchange_qualifies_following_native_turn(self):
  uid=self.feed();self.begin();self.e.use_move(self.p,self.p,'move/볼가득넣기')
  self.assertFalse(self.p.buffs);self.assertEqual(self.p.spec['food_consumption_receipts'][-1]['buff_id'],uid)
  self.assertTrue(FOOD.consumed_this_scene(self.e,self.p));self.next_turn();self.e.rng.seed(5)
  self.e.use_move(self.p,self.q,'move/트림');self.assertEqual(self.p.move_uses['move/트림'],1)
 def test_json_retains_actual_scene_and_exchange_then_native_scene_boundary_expires(self):
  self.consume();self.begin();loaded=load_engine(self.rules,json.loads(json.dumps(dump_engine(self.e),ensure_ascii=False)))
  actors={a.entity_id:a for a in loaded.everyone};p=actors[self.p.entity_id];q=actors[self.q.entity_id]
  self.assertIsNot(p,self.p);self.assertTrue(FOOD.consumed_this_scene(loaded,p));loaded.rng.seed(5)
  loaded.use_move(p,q,'move/트림');self.assertEqual(p.move_uses['move/트림'],1)
  loaded.end_of_turn(p);loaded.end_scene(loaded.everyone);self.assertFalse(FOOD.consumed_this_scene(loaded,p))
 def test_legacy_undated_receipt_is_preserved_without_guessing_current_scene(self):
  receipt=self.consume();receipt.pop('scene');self.begin();history=deepcopy(self.p.spec['food_consumption_receipts'])
  self.reject_without_cost();self.assertEqual(history,self.p.spec['food_consumption_receipts'])

if __name__=='__main__':unittest.main()
