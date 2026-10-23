"""Shared native Move quotas and actual recovery; no synthetic move effects."""
from copy import deepcopy
from pathlib import Path
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_progression_state as FIX
from builder import build_pokemon
import frequency as F,downtime as D,world_entities as W,state_codec as CODEC
SCENE='move/나비춤'
ONCE='move/코튼가드'
DAILY='move/회복지령'

class FrequencyStateTests(unittest.TestCase):
 setUpClass=classmethod(FIX.ProgressionStateTests.setUpClass.__func__)
 add=FIX.ProgressionStateTests.add
 restored=FIX.ProgressionStateTests.restored
 def setUp(self):
  FIX.ProgressionStateTests.setUp(self)
  self.p=self.add(build_pokemon(self.r,'이브이',20,moves=[SCENE,ONCE,DAILY],abilities=[]))
  for mid in (SCENE,ONCE,DAILY):self.e.gm.set_move(self.a,mid,True,reason='observed learned move')
  self.actors=[self.a,self.p]
 def turn(self,actor):
  active=getattr(self.e,'_active_turn_actor',None)
  if active is not None:self.e.end_of_turn(active)
  if self.e.round_start_seconds is not None:self.e.end_round()
  self.e.start_round(self.actors);self.e.start_of_turn(actor)
 def use(self,actor,mid=SCENE):
  if mid==DAILY:actor.hp=max(1,actor.base_max_hp//3)
  return self.e.use_move(actor,actor,mid)
 def state(self,actor):
  return deepcopy((actor.spec,actor.hp,actor.stages,actor.budget,self.e.rng.getstate(),actor._action_history))
 def test_core_every_other_turn_uses_native_move_and_preserves_gap_after_codec(self):
  mid='move/방어지령'
  for index in range(2):
   with self.subTest(actor_kind=index):
    self.setUp();actor=self.actors[index]
    self.e.gm.set_move(actor,mid,True,reason='observed learned native EOT move')
    self.assertEqual(F.move_frequency(self.e,mid,actor),('every_other_turn',1))
    self.turn(actor);self.use(actor,mid)
    self.assertEqual((actor.stages['def'],actor.stages['spd'],actor.move_uses[mid]),(1,1,1))
    self.assertFalse(F.move_allowed(self.e,actor,mid)[0])
    self.turn(actor);before=self.state(actor);self.use(actor,mid)
    self.assertEqual(self.state(actor),before)
    old_ids=[c.entity_id for c in self.actors]
    self.e=CODEC.load_engine(self.r,CODEC.dump_engine(self.e))
    actors={c.entity_id:c for c in self.e.everyone};self.actors=[actors[x] for x in old_ids];actor=self.actors[index]
    self.assertFalse(F.move_allowed(self.e,actor,mid)[0])
    self.turn(actor);self.use(actor,mid)
    self.assertEqual((actor.stages['def'],actor.stages['spd'],actor.move_uses[mid]),(2,2,2))
    self.assertTrue(self.e.validate_state()['valid'])
 def test_scene_two_cap_and_intervening_personal_turn_for_both_kinds(self):
  for actor in self.actors:
   self.turn(actor);self.use(actor);self.assertEqual(actor.stages['spa'],1)
   before=self.state(actor);self.e.use_move(actor,actor,SCENE);self.assertEqual(self.state(actor),before)
   self.turn(actor);before=self.state(actor);self.e.use_move(actor,actor,SCENE);self.assertEqual(self.state(actor),before)
   self.turn(actor);self.use(actor);self.assertEqual(actor.stages['spa'],2)
   self.turn(actor);self.turn(actor);before=self.state(actor);self.e.use_move(actor,actor,SCENE);self.assertEqual(self.state(actor),before)
   self.assertEqual(actor.move_uses[SCENE],2)
  self.e.end_scene()
  for actor in self.actors:
   self.turn(actor);self.use(actor);self.assertEqual(actor.move_uses[SCENE],1);self.assertEqual(actor.stages['spa'],1)
 def test_scene_one_is_not_implicitly_two_and_encounter_end_is_not_scene_end(self):
  for actor in self.actors:
   self.turn(actor);self.use(actor,ONCE);self.assertEqual(actor.stages['def'],3)
  self.e.end_encounter()
  for actor in self.actors:
   self.turn(actor);self.turn(actor);before=self.state(actor);self.e.use_move(actor,actor,ONCE)
   self.assertEqual(self.state(actor),before);self.assertEqual(actor.move_uses[ONCE],1)
 def test_daily_multiple_uses_remain_one_per_scene_and_cap_across_scenes(self):
  for n in (1,2):
   for actor in self.actors:
    self.turn(actor);self.use(actor,DAILY);self.assertEqual(actor.move_uses[DAILY],n)
    self.assertGreater(actor.hp,actor.base_max_hp//3)
    self.turn(actor);before=self.state(actor);self.e.use_move(actor,actor,DAILY);self.assertEqual(self.state(actor),before)
   self.e.end_scene()
  for actor in self.actors:
   self.turn(actor);before=self.state(actor);self.e.use_move(actor,actor,DAILY);self.assertEqual(self.state(actor),before)
 def spend_daily(self):
  for actor in self.actors:self.turn(actor);self.use(actor,DAILY)
  self.e.end_scene()
 def test_new_day_alone_does_not_restore_daily_moves(self):
  self.spend_daily()
  for actor in self.actors:
   D.new_day(actor);self.assertEqual(actor.move_uses[DAILY],1)
   self.turn(actor);self.use(actor,DAILY);self.assertEqual(actor.move_uses[DAILY],2)
 def test_same_day_extended_rest_keeps_daily_usage(self):
  self.spend_daily()
  for actor in self.actors:
   D.extended_rest(self.e,actor,4);self.assertEqual(actor.move_uses[DAILY],1)
 def test_short_rest_previous_day_does_not_restore_daily_usage(self):
  self.spend_daily()
  for actor in self.actors:
   D.new_day(actor);D.extended_rest(self.e,actor,3);self.assertEqual(actor.move_uses[DAILY],1)
 def test_previous_day_extended_rest_restores_both_actor_kinds(self):
  self.spend_daily()
  for actor in self.actors:
   D.new_day(actor);D.extended_rest(self.e,actor,4);self.assertNotIn(DAILY,actor.move_uses)
  for actor in self.actors:
   self.turn(actor);self.use(actor,DAILY);self.assertEqual(actor.move_uses[DAILY],1)
 def test_center_restores_daily_pool_without_resetting_scene_or_scene_pool(self):
  for actor in self.actors:
   self.turn(actor);self.use(actor,ONCE);self.turn(actor);self.use(actor,DAILY)
  self.e.end_encounter()
  for actor in self.actors:
   D.pokemon_center(self.e,actor);self.assertNotIn(DAILY,actor.move_uses);self.assertEqual(actor.move_uses[ONCE],1)
  for actor in self.actors:
   self.turn(actor);before=self.state(actor);self.e.use_move(actor,actor,DAILY);self.assertEqual(self.state(actor),before)
  self.e.end_scene()
  for actor in self.actors:
   self.turn(actor);self.use(actor,DAILY);self.assertEqual(actor.move_uses[DAILY],1)
 def test_forget_relearn_and_recall_do_not_create_another_usage_pool(self):
  self.turn(self.p);self.use(self.p,SCENE);self.e.gm.recall(self.p);self.e.gm.send_out(self.p)
  self.e.gm.set_move(self.p,SCENE,False,reason='observed forgotten move')
  self.e.gm.set_move(self.p,SCENE,True,reason='observed relearned move')
  self.assertEqual(self.p.move_uses[SCENE],1)
  self.turn(self.p);before=self.state(self.p);self.e.use_move(self.p,self.p,SCENE);self.assertEqual(self.state(self.p),before)
  self.turn(self.p);self.use(self.p);self.assertEqual(self.p.move_uses[SCENE],2)
 def test_gm_and_durable_restore_keep_counts_occurrence_and_native_rejection(self):
  self.spend_daily();self.turn(self.p);self.use(self.p,SCENE)
  self.e.gm.snapshot('spent');saved=deepcopy((self.p.move_uses,F.state(self.p)))
  self.e.end_scene();D.new_day(self.p);D.extended_rest(self.e,self.p,4);self.e.gm.restore('spent')
  self.assertEqual((self.p.move_uses,F.state(self.p)),saved)
  loaded=self.restored();p=W.actor_index(loaded)[self.p.entity_id]
  self.assertEqual((p.move_uses,F.state(p)),saved)
  before=(deepcopy(p.spec),deepcopy(p.stages),deepcopy(p.budget),loaded.rng.getstate())
  loaded.use_move(p,p,SCENE)
  self.assertEqual((p.spec,p.stages,p.budget,loaded.rng.getstate()),before)
 def test_invalid_counts_and_calendars_reject_native_use_and_export(self):
  self.turn(self.p);self.use(self.p);good=deepcopy((self.p.spec,self.p.move_uses))
  mutations=[lambda:setattr(self.p,'move_uses',{SCENE:True}),lambda:self.p.spec['frequency_state'].__setitem__('turn',-1),lambda:self.p.spec['frequency_state']['moves'][SCENE].__setitem__('turn',999),lambda:self.p.spec['move_uses'].__setitem__(SCENE,0),lambda:self.p.spec['frequency_state'].__setitem__('activations',[])]
  for mutate in mutations:
   self.p.spec,self.p.move_uses=deepcopy(good);mutate();before=self.state(self.p)
   with self.assertRaises(ValueError):self.e.use_move(self.p,self.p,SCENE)
   self.assertEqual(self.state(self.p),before)
   self.assertFalse(self.e.validate_state()['valid'])
   with self.assertRaises(ValueError):self.e.export_state()
  self.p.spec,self.p.move_uses=deepcopy(good)
 def test_structured_frequency_caps_do_not_coerce_bool_or_fraction(self):
  for kind in ('scene','daily','every_other_turn','at_will'):
   for bad in (True,False,0,-1,1.5,'2'):
    with self.assertRaises(ValueError):F.parse({'kind':kind,'uses':bad})

if __name__=='__main__':unittest.main()
