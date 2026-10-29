"""Persistent state sources, native loss/thaw consumers and counter restoration."""
from pathlib import Path
from unittest.mock import patch
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_team_blessings as _fixture_test_category2_team_blessings
import condition_instances as CI,persistent_conditions as P,turn as TURN,state_codec as CODEC

class PersistentConditionsTests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_team_blessings.TeamBlessingTests.setUpClass.__func__)
 known=_fixture_test_category2_team_blessings.TeamBlessingTests.known; snap=_fixture_test_category2_team_blessings.TeamBlessingTests.snap; valid=_fixture_test_category2_team_blessings.TeamBlessingTests.valid; restored=_fixture_test_category2_team_blessings.TeamBlessingTests.restored
 add=_fixture_test_category2_team_blessings.TeamBlessingTests.add; begin=_fixture_test_category2_team_blessings.TeamBlessingTests.begin; setUp=_fixture_test_category2_team_blessings.TeamBlessingTests.setUp
 def cast(self,move,target=None,face=18):
  self.known(self.other,move);self.begin(self.other)
  with patch.object(self.e,'d20',return_value=face):self.e.use_move(self.other,target or self.p,'move/'+move,set_damage=True)
 def standard(self,c):
  with patch.object(self.e,'d20',return_value=18):self.e.use_move(c,self.other,'struggle',set_damage=True)
 def finish(self,c):
  with patch.object(self.e,'d20',return_value=1):self.e.end_of_turn(c)
 def test_native_burn_poison_share_stage_ownership_and_real_standard_loss(self):
  for kind in ('a','p'):
   for cond,move,stat in [('화상','도깨비불','def'),('독','독가스','spd')]:
    with self.subTest(kind=kind,condition=cond):
     self.setUp();c=getattr(self,kind);self.e.change_stage(c,stat,-5);self.cast(move,c)
     self.assertIn(cond,c.conditions);self.assertEqual(c.stages[stat],-6)
     self.begin(c);hp=c.hp;self.standard(c);self.finish(c)
     self.assertEqual(hp-c.hp,self.e.tick(c));self.e.cure_status(c,cond)
     self.assertEqual(c.stages[stat],-5);self.valid()
 def test_shared_loss_trigger_distinguishes_action_inability_and_voluntary_waiting(self):
  cases={'standard':True,'wait':False,'sleep':True,'frozen':True,'paralysis_shift':True,'paralysis_wait':False,'paralysis_success_shift':False,'modern_flinch':False}
  for condition in ('화상','독'):
   for case,loses in cases.items():
    with self.subTest(condition=condition,case=case):
     self.setUp();c=self.p;self.e.apply_status(c,condition)
     status={'sleep':'잠듦','frozen':'얼음','modern_flinch':'풀죽음'}.get(case)
     if status and case!='modern_flinch':self.e.apply_status(c,status)
     if case.startswith('paralysis'):self.e.apply_status(c,'마비')
     with patch.object(self.e,'d20',return_value=11 if case=='paralysis_success_shift' else 10):self.begin(c)
     if case=='modern_flinch':self.e.apply_status(c,status)
     hp=c.hp
     if case=='standard':self.standard(c)
     elif case.endswith('shift'):
      self.assertTrue(TURN.spend(self.e,c,'shift','native Shift selection'))
      if case=='paralysis_shift':self.assertFalse(TURN.spend(self.e,c,'standard','blocked Standard'))
     self.finish(c);self.assertEqual(hp-c.hp,self.e.tick(c) if loses else 0);self.valid()
 def test_native_toxic_is_an_owned_variant_and_doubles_by_round_not_loss_event(self):
  self.cast('맹독');self.assertIn('독',self.p.conditions);self.assertNotIn('맹독',self.p.conditions)
  row=CI.records(self.p,'독')[0];self.assertEqual(row['source'],'move/맹독');self.assertEqual(self.p.stages['spd'],-2)
  self.finish(self.other)
  losses=[]
  for round_index,act in enumerate((True,False,True)):
   if round_index:self.e.start_round(self.e.gm.everyone)
   self.e.start_of_turn(self.p,initiative_count=10);hp=self.p.hp
   if act:self.standard(self.p)
   self.finish(self.p);losses.append(hp-self.p.hp)
   self.assertFalse(self.e.apply_status(self.p,'맹독'));self.e.end_round()
  self.assertEqual(losses,[5,0,20]);self.assertEqual(row['completed_rounds'],3);self.assertEqual(len(row['round_history']),3)
  self.assertEqual(P.loss(self.e,self.p,'독',1),40);self.valid()
 def test_variant_recall_encounter_and_both_restore_paths_preserve_until_actual_cure(self):
  self.e.gm.add_condition(self.p,'맹독',reason='observed variant');self.begin(self.a);self.finish(self.a);self.e.end_round()
  self.assertEqual(P.loss(self.e,self.p,'독',1),10);self.e.gm.recall(self.p,reason='actual recall')
  self.assertIn('독',self.p.conditions);self.assertEqual(self.p.stages['spd'],-2);self.assertEqual(P.loss(self.e,self.p,'독',1),10)
  self.e.end_encounter();self.e.gm.snapshot('poison');self.e.cure_status(self.p,'맹독');self.e.gm.restore('poison')
  restored=self.restored();rc=next(c for c in restored.gm.everyone if c.entity_id==self.p.entity_id)
  self.assertEqual(P.loss(restored,rc,'독',1),10);restored.cure_status(rc,'맹독');self.assertNotIn('독',rc.conditions);self.assertFalse(CI.records(rc,'독'))
  self.assertTrue(restored.validate_state()['valid']);self.e.gm.send_out(self.p,reason='actual deployment')
  self.a.spec['items']['해독제']=1;self.e.use_item(self.a,'해독제',self.p)
  self.assertNotIn('독',self.p.conditions);self.assertFalse(CI.records(self.p,'독'));self.valid()
 def test_frozen_type_weather_save_thresholds_and_ice_immunity(self):
  for types in (['노말'],['불꽃']):
   for weather,modifier in [(None,0),('sunny',4),('hail',-2)]:
    dc=(11 if types==['불꽃'] else 16)-modifier
    for face in (dc-1,dc):
     with self.subTest(types=types,weather=weather,face=face):
      self.setUp();self.e.gm.set_types(self.p,types,reason='actual type');self.e.apply_status(self.p,'얼음');self.begin(self.p)
      self.e.weather=weather;self.e.weather_rounds=5 if weather else None
      with patch.object(type(self.e),'d20',return_value=face) as roll:self.e.end_of_turn(self.p)
      self.assertEqual(roll.call_count,1);self.assertEqual('얼음' in self.p.conditions,face<dc);self.valid()
  self.setUp();self.e.gm.set_types(self.p,['얼음'],reason='actual type');self.assertFalse(self.e.apply_status(self.p,'얼음'))
 def test_actual_matching_attack_hits_thaw_but_misses_status_moves_and_hp_loss_do_not(self):
  for move,face in [('화염방사',10),('깨트리기',10),('파워젬',10),('아이언헤드',10)]:
   with self.subTest(move=move):
    self.setUp();self.e.apply_status(self.p,'얼음');self.cast(move,face=face)
    self.assertGreater(self.p.hp,0);self.assertNotIn('얼음',self.p.conditions);self.valid()
  for move,face in [('화염방사',1),('도깨비불',18),('물대포',10)]:
   with self.subTest(negative_move=move):
    self.setUp();self.e.apply_status(self.p,'얼음');self.cast(move,face=face)
    self.assertIn('얼음',self.p.conditions);self.valid()
  self.setUp();self.e.apply_status(self.p,'얼음');self.e.lose_hp(self.p,1,source='화염방사')
  self.assertIn('얼음',self.p.conditions)
 def test_frozen_both_actor_kinds_keep_no_actions_no_evasion_and_restore_cure(self):
  for kind in ('a','p'):
   self.setUp();c=getattr(self,kind);self.e.apply_status(c,'얼음');self.begin(c)
   for action in ('standard','shift','swift','free'):self.assertFalse(TURN.spend(self.e,c,action,'blocked frozen action'))
   for cls in ('물리','특수','변화'):self.assertEqual(c.evasion(cls),0)
   self.e.gm.snapshot('frozen');self.e.cure_status(c,'얼음');self.e.gm.restore('frozen');restored=self.restored();rc=next(x for x in restored.gm.everyone if x.entity_id==c.entity_id)
   self.assertFalse(TURN.spend(restored,rc,'standard','still frozen'))
   with patch.object(restored,'d20',return_value=16):restored.end_of_turn(rc)
   self.assertNotIn('얼음',rc.conditions);self.assertTrue(restored.validate_state()['valid'])
 def test_persistent_immunities_faint_cleanup_and_malformed_variant_rejection(self):
  for status,types in [('화상',['불꽃']),('독',['독']),('맹독',['강철'])]:
   self.setUp();self.e.gm.set_types(self.p,types,reason='type immunity');self.assertFalse(self.e.apply_status(self.p,status))
   self.assertFalse(CI.records(self.p,'독'));self.valid()
  self.setUp();self.e.apply_status(self.p,'맹독');self.e.apply_status(self.p,'화상');self.e.gm.faint(self.p,reason='actual faint')
  self.assertFalse({'독','화상'} & self.p.conditions);self.assertFalse(CI.records(self.p));self.assertEqual(self.p.stages['spd'],0);self.valid()
  self.setUp();self.e.apply_status(self.p,'맹독');CI.records(self.p,'독')[0]['completed_rounds']=3
  with self.assertRaises(CODEC.StateCodecError):CODEC.dump_engine(self.e)

if __name__=='__main__':unittest.main()
