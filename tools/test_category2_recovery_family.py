"""Shared timed condition recovery and sourced faint recovery, with real boundaries."""
from pathlib import Path
from unittest.mock import patch
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_team_blessings as _fixture_test_category2_team_blessings
import condition_recovery as R,common_checks as C,turn as TURN,world_entities as W
import downtime as DT,effects as FX,state_codec as CODEC
from engine import Engine

class RecoveryFamilyTests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_team_blessings.TeamBlessingTests.setUpClass.__func__)
 known=_fixture_test_category2_team_blessings.TeamBlessingTests.known; snap=_fixture_test_category2_team_blessings.TeamBlessingTests.snap; valid=_fixture_test_category2_team_blessings.TeamBlessingTests.valid; restored=_fixture_test_category2_team_blessings.TeamBlessingTests.restored
 add=_fixture_test_category2_team_blessings.TeamBlessingTests.add; begin=_fixture_test_category2_team_blessings.TeamBlessingTests.begin; setUp=_fixture_test_category2_team_blessings.TeamBlessingTests.setUp
 def recover(self,c,condition,**kw):
  return self.e.recover_condition(c,condition,duration_minutes=kw.pop('duration_minutes',2),reason=kw.pop('reason','GM observed sufficient recovery interval'),**kw)
 def frozen_boundary(self):
  self.e.apply_status(self.p,'얼음');self.e.begin_encounter(self.e.gm.everyone);self.e.end_encounter()
 def test_frozen_needs_actual_combat_end_and_known_duration_not_just_a_scene(self):
  self.e.apply_status(self.p,'얼음');self.e.end_scene();before=self.snap()
  self.assertIsInstance(self.recover(self.p,'얼음'),C.PendingDecision);self.assertEqual(self.snap(),before)
  self.e.begin_encounter(self.e.gm.everyone);before=self.snap()
  self.assertIsInstance(self.recover(self.p,'얼음'),C.PendingDecision);self.assertEqual(self.snap(),before)
  self.e.end_encounter();self.assertIn('얼음',self.p.conditions);before=self.snap()
  self.assertIsInstance(self.e.recover_condition(self.p,'얼음'),C.PendingDecision);self.assertEqual(self.snap(),before)
  self.e.end_scene();self.assertIn('얼음',self.p.custom_conditions[R.KEY]);start=self.e.elapsed_seconds
  result=self.recover(self.p,'얼음');self.assertEqual(result['method'],'extended_action_after_combat')
  self.assertEqual(self.e.elapsed_seconds-start,120);self.assertNotIn('얼음',self.p.conditions)
  self.assertEqual(self.p._action_history[-1],'extended');self.valid()
 def test_frozen_permission_is_specific_and_cannot_ignore_other_incapacity(self):
  self.frozen_boundary()
  for action in ('standard','shift','swift','free','extended'):
   self.assertFalse(TURN.spend(self.e,self.p,action,'unrelated action',_condition_recovery=True))
  self.e.apply_status(self.p,'잠듦');before=self.snap()
  self.assertIs(self.recover(self.p,'얼음'),False);self.assertEqual(self.snap()[:-1],before[:-1])
  self.e.cure_status(self.p,'잠듦');self.recover(self.p,'얼음');self.e.apply_status(self.p,'얼음')
  self.assertIsInstance(self.recover(self.p,'얼음'),C.PendingDecision)
  self.e.apply_status(self.a,'얼음');self.assertIsInstance(self.recover(self.a,'얼음'),C.PendingDecision);self.valid()
 def test_natural_sleep_is_passive_known_time_and_cascades_bad_sleep(self):
  self.e.apply_status(self.p,'잠듦');self.e.apply_status(self.p,'악몽');before=self.snap()
  self.assertIsInstance(self.e.recover_condition(self.p,'잠듦'),C.PendingDecision);self.assertEqual(self.snap(),before)
  self.e.advance_time(1000,[self.p]);self.assertIn('잠듦',self.p.conditions)
  actions=list(getattr(self.p,'_action_history',[]));start=self.e.elapsed_seconds
  result=self.recover(self.p,'잠듦');self.assertEqual(result['method'],'natural_sleep')
  self.assertEqual(self.e.elapsed_seconds-start,120);self.assertEqual(getattr(self.p,'_action_history',[]),actions)
  self.assertFalse({'잠듦','악몽'}&self.p.conditions);self.valid()
 def test_persistent_recall_item_center_and_extended_rest_boundaries(self):
  for condition,item in [('화상','화상치료제'),('마비','마비치료제'),('독','해독제')]:
   with self.subTest(condition=condition):
    self.setUp();self.e.apply_status(self.p,condition);self.e.gm.recall(self.p,reason='actual recall')
    self.assertIn(condition,self.p.conditions);self.e.gm.send_out(self.p,reason='actual deployment')
    with self.assertRaises(ValueError):self.recover(self.p,condition)
    self.a.spec['items'][item]=1;self.e.use_item(self.a,item,self.p);self.assertNotIn(condition,self.p.conditions)
    self.e.apply_status(self.p,condition);DT.extended_rest(self.e,self.p,4);self.assertNotIn(condition,self.p.conditions)
    self.e.apply_status(self.p,condition);DT.pokemon_center(self.e,self.p);self.assertNotIn(condition,self.p.conditions);self.valid()
 def test_repeated_healing_preserves_clock_and_reinjury_starts_a_fresh_interval(self):
  for role in ('a','p'):
   self.setUp();c=getattr(self,role);self.e.gm.faint(c,reason='actual faint')
   self.e.heal(c,10,source_kind='ordinary_item');self.e.advance_time(200,[c])
   for source in ('ordinary_item','rest','unspecified'):self.e.heal(c,1,source_kind=source)
   self.assertEqual(c.faint_recovery_seconds,400);self.e.advance_time(399,[c]);self.assertTrue(c.fainted)
   self.e.advance_time(1,[c]);self.assertFalse(c.fainted)
   self.e.gm.faint(c,reason='new knockout');self.e.heal(c,10,source_kind='ordinary_item');self.e.advance_time(400,[c])
   self.e.lose_hp(c,c.hp);self.assertTrue(c.faint_recovery_interrupted)
   self.e.heal(c,10,source_kind='ordinary_item');self.assertEqual(c.faint_recovery_seconds,600)
   self.assertFalse(c.faint_recovery_interrupted);self.e.advance_time(599,[c]);self.assertTrue(c.fainted)
   self.e.advance_time(1,[c]);self.assertFalse(c.fainted);self.valid()
 def test_native_item_and_move_recovery_preserve_source_and_cleanup(self):
  for item,immediate in [('상처약',False),('기력의조각',True)]:
   self.setUp();self.e.apply_status(self.p,'독');self.e.apply_status(self.p,'혼란');self.e.gm.faint(self.p,reason='actual faint')
   self.assertFalse({'독','혼란'}&self.p.conditions);self.a.spec['items'][item]=1;self.e.use_item(self.a,item,self.p)
   self.assertGreater(self.p.hp,0);self.assertEqual(self.p.fainted,not immediate)
   if not immediate:self.e.advance_time(600,[self.p]);self.assertFalse(self.p.fainted)
   self.valid()
  self.setUp();self.e.gm.faint(self.p,reason='actual faint');self.known(self.a,'치유파동');self.begin(self.a)
  self.e.use_move(self.a,self.p,'move/치유파동');self.assertGreater(self.p.hp,0);self.assertFalse(self.p.fainted);self.valid()
  self.setUp();self.e.gm.faint(self.p,reason='actual faint')
  FX.run_effects(self.e,self.a,self.p,[{'type':'heal','amount':10}],{'hit':True},'feat/recovery-observation')
  self.assertFalse(self.p.fainted);self.valid()
 def test_durable_and_gm_restore_preserve_opportunity_timer_and_receipt(self):
  self.frozen_boundary();snapshot=self.e.gm.snapshot('recovery');self.recover(self.p,'얼음');self.e.gm.restore(snapshot)
  self.assertIn('얼음',self.p.conditions);loaded=self.restored();c=W.actor_index(loaded)[self.p.entity_id]
  loaded.recover_condition(c,'얼음',duration_minutes=3,reason='actual thaw duration');self.assertNotIn('얼음',c.conditions)
  again=Engine.import_state(self.r,loaded.export_state());rc=W.actor_index(again)[c.entity_id]
  self.assertEqual(rc.spec[R.RECEIPTS],c.spec[R.RECEIPTS]);rc.spec[R.RECEIPTS][-1]['method']='natural_sleep'
  with self.assertRaises(CODEC.StateCodecError):CODEC.dump_engine(again)
  self.e.cure_status(self.p,'얼음');self.e.gm.faint(self.p,reason='actual faint');self.e.heal(self.p,10,source_kind='ordinary_item')
  self.e.advance_time(200,[self.p]);loaded=self.restored();c=W.actor_index(loaded)[self.p.entity_id]
  loaded.heal(c,1,source_kind='ordinary_item');loaded.advance_time(399,[c]);self.assertTrue(c.fainted)
  loaded.advance_time(1,[c]);self.assertFalse(c.fainted);self.assertTrue(loaded.validate_state()['valid'])
 def test_failed_timed_recovery_rolls_back_clock_action_and_affliction(self):
  for condition in ('얼음','잠듦'):
   self.setUp()
   if condition=='얼음':self.frozen_boundary()
   else:self.e.apply_status(self.p,condition)
   before=self.snap()
   with patch.object(Engine,'cure_status',side_effect=ValueError('injected cure failure')):
    with self.assertRaises(ValueError):self.recover(self.p,condition)
   self.assertEqual(self.snap(),before)
 def test_repeated_healing_does_not_lose_an_explicit_round_timestamp(self):
  self.e.gm.faint(self.p,reason='actual faint');self.begin(self.a)
  self.e.heal(self.p,10,source_kind='ordinary_item',round_offset_seconds=3)
  self.e.heal(self.p,1,source_kind='ordinary_item');self.assertIsNone(self.p.faint_recovery_pending)
  self.e.end_encounter(round_elapsed_seconds=10);self.assertEqual(self.p.faint_recovery_seconds,593)
  self.e.advance_time(592,[self.p]);self.assertTrue(self.p.fainted);self.e.advance_time(1,[self.p]);self.assertFalse(self.p.fainted)
  self.valid()

if __name__=='__main__':unittest.main()
