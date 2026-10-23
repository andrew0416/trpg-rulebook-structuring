"""Shared trainer/Pokemon combat state through real producers and restore paths."""
from copy import deepcopy
from pathlib import Path
import sys, unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_progression_state as _fixture_test_category2_progression_state
from engine import Engine, Combatant
from builder import build_pokemon
import combat_stage_sources as CS, combat_state_lifecycle as L
import effects as FX, effects_ext as EXT, movement_actions as MOVE
import state_fields as F, state_codec as CODEC

class CombatStateBatchTests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_progression_state.ProgressionStateTests.setUpClass.__func__)
 add=_fixture_test_category2_progression_state.ProgressionStateTests.add
 restored=_fixture_test_category2_progression_state.ProgressionStateTests.restored
 def setUp(self):
  _fixture_test_category2_progression_state.ProgressionStateTests.setUp(self)
  self.p=self.add(build_pokemon(self.r,'이브이',20,moves=['칼춤','흑안개'],abilities=[]))
  self.actors=[self.a,self.p]
 def test_same_five_stage_domain_and_original_stat_formula_for_both_actor_kinds(self):
  for actor in self.actors:
   F.base_patch(actor,{'stats':dict.fromkeys(F.STATS,11)},reason='observed stat input')
   hp=(actor.hp,actor.base_max_hp,actor.stats['hp'])
   for stat in CS.STATS:
    for stage in range(-6,7):
     self.e.gm.set_stage(actor,stat,value=stage,reason='observed stage')
     self.assertEqual(actor.staged(stat),11*(10+(2*stage if stage>=0 else stage))//10)
    self.e.change_stage(actor,stat,100);self.assertEqual(actor.stages[stat],6)
    self.e.change_stage(actor,stat,-100);self.assertEqual(actor.stages[stat],-6)
   self.assertEqual(hp,(actor.hp,actor.base_max_hp,actor.stats['hp']))
   before=deepcopy(actor.stages)
   for stat,delta in [('hp',1),('unknown',1),('atk',True),('atk',0.5)]:
    with self.assertRaises(ValueError):self.e.change_stage(actor,stat,delta)
    self.assertEqual(actor.stages,before)
 def test_low_final_stats_keep_one_without_changing_raw_stats_stages_or_hp(self):
  for actor in self.actors:
   hp=(actor.hp,actor.base_max_hp,actor.stats['hp'])
   F.base_patch(actor,{'stats':dict(actor.spec['stats'],**dict.fromkeys(CS.STATS,1))},reason='observed low non-HP statistics')
   for stat in CS.STATS:
    for stage in (-1,-6):
     self.e.gm.set_stage(actor,stat,value=stage,reason='observed negative stage')
     self.assertEqual(actor.staged(stat),1,(actor.kind,stat,stage))
     self.assertEqual((actor.stats[stat],actor.stages[stat]),(1,stage))
    self.e.change_stage(actor,stat,-100)
    self.assertEqual((actor.stages[stat],actor.staged(stat)),(-6,1))
   self.assertEqual(hp,(actor.hp,actor.base_max_hp,actor.stats['hp']))
 def test_actual_swords_dance_uses_shared_stage_path_for_both_actor_kinds(self):
  self.e.gm.set_move(self.a,'move/칼춤',True,reason='observed learned move')
  self.e.start_round(self.actors)
  for actor in self.actors:
   self.e.start_of_turn(actor);self.e.use_move(actor,actor,'move/칼춤')
   self.assertEqual(actor.stages['atk'],2);self.e.end_of_turn(actor)
 def test_component_reset_uses_same_actor_state_boundary(self):
  # The native all-target Haze dispatch is an independently recorded gap.
  # This checks only the existing reset effect handler, not that dispatch.
  self.e.change_stage(self.p,'spd',-3);self.e.gm.set_stage(self.p,'acc',value=2);self.e.gm.set_stage(self.a,'eva',value=4)
  effect=next(x for x in self.r.moves_mech['move/흑안개']['effects'] if x['type']=='reset_stages')
  for actor in self.actors:FX.h_reset_stages(self.e,actor,actor,{**effect,'target':'self'},{})
  for actor in self.actors:
   self.assertEqual(actor.stages,dict.fromkeys(CS.STATS,0))
   self.assertEqual((actor.accuracy_stage,actor.evasion_mod),(0,0))
 def test_recall_preserves_afflicted_sources_but_removes_ordinary_stage_history(self):
  self.e.begin_encounter(self.actors)
  for cond in ['화상','독','혼란']:self.e.apply_status(self.p,cond)
  self.e.change_stage(self.p,'def',-6);self.e.change_stage(self.p,'spd',5)
  self.e.change_stage(self.p,'atk',2);self.e.gm.set_stage(self.p,'acc',value=-3)
  self.e.gm.recall(self.p,reason='actual switch')
  self.assertFalse(self.p.on_field);self.assertNotIn('혼란',self.p.conditions)
  self.assertEqual(self.p.stages,dict(atk=0,**{'def':-2},spa=0,spd=-2,spe=0))
  self.assertEqual(self.p.accuracy_stage,0)
  self.e.gm.send_out(self.p);self.e.cure_status(self.p,'화상');self.e.cure_status(self.p,'독')
  self.assertEqual(self.p.stages,dict.fromkeys(CS.STATS,0))
 def test_cure_at_stage_limit_removes_only_the_actual_condition_contribution(self):
  for actor in self.actors:
   self.e.change_stage(actor,'def',-6);self.e.apply_status(actor,'화상')
   self.assertEqual(actor.stages['def'],-6)
   self.e.cure_status(actor,'화상');self.assertEqual(actor.stages['def'],-6)
 def test_end_encounter_resets_all_members_even_if_current_roster_is_subset(self):
  outsider=self.add(build_pokemon(self.r,'잉어킹',20,moves=[],abilities=[]))
  self.e.time_actors([outsider]);self.e.begin_encounter(self.actors)
  for actor in [*self.actors,outsider]:self.e.change_stage(actor,'atk',3)
  self.e.gm.recall(self.p);self.e.change_stage(self.p,'atk',2)
  self.e.everyone=[self.a]
  self.e.end_encounter([self.a])
  self.assertEqual([actor.stages['atk'] for actor in [*self.actors,outsider]],[0,0,3])
  self.assertIsNone(self.e._encounter_actors)
 def test_end_encounter_keeps_persistent_conditions_for_both_actor_kinds(self):
  self.e.begin_encounter(self.actors)
  for actor in self.actors:
   self.e.apply_status(actor,'화상');self.e.change_stage(actor,'atk',3)
  self.e.end_encounter()
  for actor in self.actors:
   self.assertIn('화상',actor.conditions);self.assertEqual(actor.stages['def'],-2)
   self.assertEqual(actor.stages['atk'],0)
   self.e.cure_status(actor,'화상');self.assertEqual(actor.stages['def'],0)
 def test_encounter_membership_and_sources_survive_both_restore_paths(self):
  self.e.begin_encounter(self.actors);self.e.apply_status(self.p,'독');self.e.change_stage(self.p,'atk',2)
  snap=self.e.gm.snapshot();self.e.end_encounter();self.e.gm.restore(snap)
  self.assertIs(self.e._encounter_actors[1],self.p)
  self.assertEqual(self.p.stages['atk'],2)
  loaded=self.restored();p=next(c for c in loaded.gm.everyone if c.entity_id==self.p.entity_id)
  self.assertIs(loaded._encounter_actors[1],p)
  self.assertIsNot(p,self.p);loaded.end_encounter()
  self.assertEqual((p.stages['atk'],p.stages['spd']),(0,-2))
  loaded.cure_status(p,'독');self.assertEqual(p.stages['spd'],0)
 def test_new_participant_and_generator_registration_join_same_scope(self):
  self.e.begin_encounter(iter([self.a]));self.assertEqual(self.e._encounter_actors,[self.a])
  self.e.gm.send_out(self.p);self.assertEqual(self.e._encounter_actors,self.actors)
  self.e.begin_encounter(self.actors);self.assertEqual(self.e._encounter_actors,self.actors)
  another=self.add(build_pokemon(self.r,'잉어킹',10,moves=[],abilities=[]))
  self.assertIn(another,self.e._encounter_actors)
 def test_invalid_membership_never_partially_starts_or_serializes_encounter(self):
  with self.assertRaises(ValueError):self.e.begin_encounter([self.a,'not an actor'])
  self.assertIsNone(self.e._encounter_actors);self.assertFalse(self.e.encounter_active)
  for bad in [[self.a,self.a],[self.a,'bad'],{'actor':self.a}]:
   self.e._encounter_actors=bad
   self.assertFalse(self.e.validate_state()['valid'])
   with self.assertRaises(ValueError):CODEC.dump_engine(self.e)
  self.e._encounter_actors=None
 def test_speed_stage_applies_to_each_existing_movement_mode_for_both_kinds(self):
  values={'land':6,'sky':4,'swim':3,'levitate':2,'burrow':1,'teleport':5}
  for actor in self.actors:
   self.e.gm.set_movement_capabilities(actor,values,basis='current',reason='observed movement')
   for stage in [-6,-1,0,1,6]:
    self.e.gm.set_stage(actor,'spe',value=stage)
    for mode,value in values.items():
     got,_=self.e.move_profile(actor,movement_mode=mode)
     delta=stage//2;want=max(min(value,2),value+delta) if delta<0 else value+delta
     self.assertEqual(got,want,(actor.kind,stage,mode))
 def test_speed_does_not_create_absent_mode_and_slowed_is_applied_after_stage(self):
  self.e.gm.set_movement_capabilities(self.p,{'land':4,'sky':0},basis='current',reason='observed movement')
  self.e.gm.set_stage(self.p,'spe',value=6)
  with self.assertRaises(ValueError):EXT.movement_profile(self.e,self.p,4,0,movement_mode='sky',capabilities=MOVE.capabilities(self.e,self.p))
  self.e.gm.set_stage(self.p,'spe',value=-6);self.e.apply_status(self.p,'둔화')
  self.assertEqual(EXT.movement_profile(self.e,self.p,4,0,movement_mode='land',capabilities=MOVE.capabilities(self.e,self.p))[0],1)
 def test_actual_shift_and_speed_state_survive_both_restore_paths(self):
  from grid import Grid
  self.e.grid=Grid(30,10)
  target=self.add(build_pokemon(self.r,'잉어킹',10,moves=[],abilities=[]));target.pos=(20,1)
  self.e.start_round(self.actors)
  for actor in self.actors:
   actor.pos=(1,1)
   self.e.gm.set_movement_capabilities(actor,{'land':6},basis='current',reason='observed movement')
   self.e.gm.set_stage(actor,'spe',value=-6)
   self.e.start_of_turn(actor)
   saved=self.e.gm.snapshot()
   loaded=self.restored();actual=next(x for x in loaded.gm.everyone if x.entity_id==actor.entity_id)
   goal=next(x for x in loaded.gm.everyone if x.entity_id==target.entity_id)
   loaded.approach(actual,goal,movement_mode='land')
   expected=actual.pos
   self.assertEqual((max(abs(actual.pos[i]-(1,1)[i]) for i in (0,1)),actual.budget['shift']),(3,0))
   self.e.approach(actor,target,movement_mode='land');self.assertEqual(actor.pos,expected)
   self.e.gm.restore(saved)
   self.assertEqual((actor.pos,actor.stages['spe'],actor.budget['shift']),((1,1),-6,1))
   self.e.approach(actor,target,movement_mode='land');self.assertEqual(actor.pos,expected)
   self.e.end_of_turn(actor)
 def test_evasion_total_ceiling_and_negative_floor_reach_actual_accuracy_check(self):
  move=self.r.move('move/메가톤펀치')
  for actor in self.actors:
   F.base_patch(actor,{'stats':dict.fromkeys(F.STATS,50)},reason='observed stat evasion')
   self.e.gm.set_stage(actor,'eva',value=6)
   for kind in ['물리','특수','변화']:self.assertEqual(actor.evasion(kind,conditional_bonus=100),9)
   self.assertFalse(self.e.accuracy_check(self.p,actor,move,fixed_roll=12)[0])
   self.assertTrue(self.e.accuracy_check(self.p,actor,move,fixed_roll=13)[0])
   F.base_patch(actor,{'stats':dict.fromkeys(F.STATS,1)},reason='observed zero stat evasion')
   self.e.gm.set_stage(actor,'eva',value=-6)
   self.assertEqual(actor.evasion('물리'),0)
   self.assertFalse(self.e.accuracy_check(self.p,actor,move,fixed_roll=3)[0])
   self.assertTrue(self.e.accuracy_check(self.p,actor,move,fixed_roll=4)[0])

if __name__=='__main__':unittest.main()
