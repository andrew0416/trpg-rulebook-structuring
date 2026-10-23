"""Actual Trip/stand-up and explicit versus implied Vulnerable state."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_condition_recovery as _fixture_test_category2_condition_recovery
import turn as TURN,action_lifecycle as ACTION,state_fields as FIELDS,world_entities as W,skill_modifiers as SKILL
from action_metadata import ActionCost

class StandUpTests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_condition_recovery.ConditionRecoveryTests.setUpClass.__func__)
 setUp=_fixture_test_category2_condition_recovery.ConditionRecoveryTests.setUp
 add=_fixture_test_category2_condition_recovery.ConditionRecoveryTests.add
 restored=_fixture_test_category2_condition_recovery.ConditionRecoveryTests.restored
 apply=_fixture_test_category2_condition_recovery.ConditionRecoveryTests.apply
 snap=_fixture_test_category2_condition_recovery.ConditionRecoveryTests.snap
 def active(self,actor):
  if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)
  if self.e.round_start_seconds is not None:self.e.end_round()
  self.e.start_round(self.actors);self.e.start_of_turn(actor)
 def test_actual_trip_then_stand_up_spends_one_shift_and_allows_next_move(self):
  self.a.pos=(1,1);self.p.pos=(2,1);self.a.spec['skills']['전투']=4
  self.e.gm.set_move(self.p,'move/칼춤',True,reason='observed actual learned move')
  self.active(self.a)
  rank=SKILL.effective_rank(self.r,self.p,'전투')
  self.assertTrue(self.e.trip(self.a,self.p,challenger_skill='전투',defender_skill='전투',fixed_accuracy=20,challenger_options={'fixed':[6]*4},defender_options={'fixed':[1]*rank}))
  self.active(self.p);self.assertIn('넘어짐',self.p.conditions);before=self.snap()
  self.e.use_move(self.p,self.p,'move/칼춤');self.assertEqual(self.snap(),before)
  pos=self.p.pos;self.assertTrue(self.e.stand_up(self.p));self.assertEqual(self.p.pos,pos)
  self.assertEqual(self.p.budget,{'standard':1,'shift':0,'swift':1});self.assertNotIn('넘어짐',self.p.conditions)
  self.e.use_move(self.p,self.p,'move/칼춤');self.assertEqual(self.p.stages['atk'],2)
 def test_all_new_action_kinds_blocked_until_shared_stand_up_for_both_kinds(self):
  for actor in self.actors:
   self.active(actor);self.apply(actor,'넘어짐');before=self.snap()
   for kind in ('standard','shift','swift','free','extended','full',ActionCost(('standard','swift'))):
    self.assertFalse(TURN.spend(self.e,actor,kind,'ordinary action while tripped'));self.assertEqual(self.snap(),before)
   self.assertTrue(self.e.stand_up(actor));self.assertEqual(actor._action_history,['shift']);self.assertTrue(TURN.spend(self.e,actor,'swift','action after standing'))
 def test_stand_up_can_use_downgraded_standard_without_becoming_movement(self):
  for actor in self.actors:
   self.active(actor);actor.budget['shift']=0;self.apply(actor,'넘어짐','구속')
   self.assertTrue(self.e.stand_up(actor));self.assertEqual(actor.budget['standard'],0)
   self.assertIn('구속',actor.conditions);self.assertNotIn('넘어짐',actor.conditions)
   self.assertFalse(getattr(actor,'_regular_shift_movement_used',False))
 def test_no_cost_or_cure_when_wrong_turn_no_budget_frozen_or_unconscious(self):
  self.active(self.a);self.apply(self.p,'넘어짐');before=self.snap();self.assertFalse(self.e.stand_up(self.p));self.assertEqual(self.snap(),before)
  self.active(self.p);self.p.budget.update(shift=0,standard=0);before=self.snap();self.assertFalse(self.e.stand_up(self.p));self.assertEqual(self.snap(),before)
  self.p.budget.update(shift=1,standard=1);self.apply(self.p,'얼음');before=self.snap();self.assertFalse(self.e.stand_up(self.p));self.assertEqual(self.snap(),before)
  self.e.cure_status(self.p,'얼음');self.e.gm.faint(self.p,reason='observed unconscious actor');before=self.snap();self.assertFalse(self.e.stand_up(self.p));self.assertEqual(self.snap(),before)
 def test_standing_provokes_native_opportunity_attack_before_cure(self):
  self.a.pos=(1,1);self.p.pos=(2,1);self.a.side='wild';self.p.side='party';self.e.rng.seed(6)
  self.active(self.p);self.apply(self.p,'넘어짐');hp=self.p.hp
  self.assertTrue(self.e.stand_up(self.p));self.assertTrue(self.a.aoo_used);self.assertLess(self.p.hp,hp)
  self.assertNotIn('넘어짐',self.p.conditions);self.assertEqual(self.p.budget['shift'],0);self.assertIn('free',self.a._action_history)
 def test_fainting_from_interrupt_keeps_paid_shift_and_prevents_completed_stand(self):
  self.a.pos=(1,1);self.p.pos=(2,1);self.a.side='wild';self.p.side='party';self.e.rng.seed(6)
  self.active(self.p);self.apply(self.p,'넘어짐');self.p.hp=1
  self.assertFalse(self.e.stand_up(self.p));self.assertTrue(self.p.fainted);self.assertIn('넘어짐',self.p.conditions)
  self.assertEqual(self.p.budget['shift'],0);self.assertTrue(self.a.aoo_used)
 def test_tripped_adjacent_enemy_cannot_spend_opportunity_quota(self):
  self.a.pos=(1,1);self.p.pos=(2,1);self.a.side='wild';self.p.side='party'
  self.active(self.p);self.apply(self.a,'넘어짐');self.apply(self.p,'넘어짐');hp=self.p.hp
  self.assertTrue(self.e.stand_up(self.p));self.assertFalse(self.a.aoo_used);self.assertEqual(self.p.hp,hp)
 def test_stand_up_is_not_repeatable_and_failed_cure_rolls_back_shift(self):
  from engine import Engine
  self.active(self.p);self.apply(self.p,'넘어짐');before=self.snap()
  with patch.object(Engine,'cure_status',side_effect=ValueError('injected recovery failure')):
   with self.assertRaises(ValueError):self.e.stand_up(self.p)
  self.assertEqual(self.snap(),before);self.assertTrue(self.e.stand_up(self.p));before=self.snap()
  with self.assertRaises(ValueError):self.e.stand_up(self.p)
  self.assertEqual(self.snap(),before)
 def test_direct_and_implied_vulnerability_zero_every_evasion_at_actual_accuracy(self):
  move=self.r.move('move/메가톤펀치')
  for condition in ('취약','실명','잠듦','기절','얼음','넘어짐'):
   for kind in ('trainer','pokemon'):
    self.setUp();self.a.pos=(1,1);self.p.pos=(1,3);actor=next(x for x in self.actors if x.kind==kind)
    FIELDS.base_patch(actor,{'stats':dict.fromkeys(FIELDS.STATS,40)},reason='observed high evasion stats');self.e.gm.set_stage(actor,'eva',value=3)
    self.assertEqual(actor.evasion('물리'),9);self.apply(actor,condition)
    for category in ('물리','특수','변화'):self.assertEqual(actor.evasion(category,conditional_bonus=100),0)
    self.assertTrue(self.e.accuracy_check(self.target,actor,move,fixed_roll=move['ac'])[0])
 def test_curing_one_cause_keeps_other_implied_and_explicit_vulnerability(self):
  for actor in self.actors:
   self.apply(actor,'넘어짐','실명','취약');self.e.cure_status(actor,'취약');self.assertEqual(actor.evasion('물리'),0)
   self.e.cure_status(actor,'실명');self.assertEqual(actor.evasion('물리'),0)
   self.apply(actor,'취약');self.assertTrue(self.e.stand_up(actor));self.assertIn('취약',actor.conditions);self.assertEqual(actor.evasion('물리'),0)
   self.e.cure_status(actor,'취약');self.assertGreater(actor.evasion('물리'),0)
 def test_both_restore_paths_keep_cause_independence_and_paid_stand(self):
  for actor in self.actors:
   self.active(actor);self.apply(actor,'넘어짐','취약');snapshot=self.e.gm.snapshot()
   loaded=self.restored();a=W.actor_index(loaded)[actor.entity_id]
   self.assertTrue(loaded.stand_up(a));self.assertIn('취약',a.conditions);self.assertEqual(a.evasion('물리'),0)
   self.assertTrue(self.e.stand_up(actor));self.e.gm.restore(snapshot)
   self.assertTrue({'넘어짐','취약'}<=actor.conditions);self.assertEqual(actor.budget['shift'],1)
   self.assertTrue(self.e.stand_up(actor));self.assertEqual(actor.budget['shift'],0);self.assertIn('취약',actor.conditions)
 def test_existing_activation_continuation_is_not_a_new_action(self):
  self.apply(self.p,'넘어짐');self.assertTrue(ACTION.status_permission(self.e,self.p,'standard',new_action=False))
  self.assertFalse(ACTION.status_permission(self.e,self.p,'standard',new_action=True))

if __name__=='__main__':unittest.main()
