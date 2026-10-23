"""Actual shared condition producers, action consumers, clocks and restore."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_team_blessings as _fixture_test_category2_team_blessings
import condition_instances as CI,combat_timing as CLOCK,state_codec as CODEC

class ParameterizedConditionsTests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_team_blessings.TeamBlessingTests.setUpClass.__func__)
 known=_fixture_test_category2_team_blessings.TeamBlessingTests.known; snap=_fixture_test_category2_team_blessings.TeamBlessingTests.snap; valid=_fixture_test_category2_team_blessings.TeamBlessingTests.valid; restored=_fixture_test_category2_team_blessings.TeamBlessingTests.restored
 add=_fixture_test_category2_team_blessings.TeamBlessingTests.add; begin=_fixture_test_category2_team_blessings.TeamBlessingTests.begin; setUp=_fixture_test_category2_team_blessings.TeamBlessingTests.setUp
 def observed(self,c,condition,**kw):return self.e.gm.add_condition(c,condition,reason='observed exact condition source',**kw)
 def actions(self,c):return deepcopy((c.budget,c.move_uses,c.hp,self.e.rng.getstate()))
 def test_disabled_distinct_moves_share_one_parameterized_family_and_native_admission(self):
  for kind in ('a','p'):
   with self.subTest(kind=kind):
    self.setUp();c=getattr(self,kind);self.known(c,'몸통박치기','울음소리');self.begin(c)
    for mid in ('move/몸통박치기','move/울음소리'):self.assertTrue(self.observed(c,'사슬묶기',parameters={'move_id':mid}))
    self.assertFalse(self.observed(c,'사슬묶기',parameters={'move_id':'move/울음소리'}))
    self.assertEqual(len(CI.records(c)),2);before=self.actions(c)
    for mid in ('move/몸통박치기','move/울음소리'):self.assertEqual(self.e.use_move(c,self.other,mid),0)
    self.assertEqual(before,self.actions(c))
    with patch.object(self.e,'d20',return_value=18):self.e.use_move(c,self.other,'struggle',set_damage=True)
    self.assertEqual(c.budget['standard'],0);self.valid()
 def test_disabled_both_restores_keep_all_parameters_then_native_item_cures_them(self):
  self.known(self.p,'몸통박치기','울음소리')
  for mid in ('move/몸통박치기','move/울음소리'):self.observed(self.p,'사슬묶기',parameters={'move_id':mid})
  self.e.gm.snapshot('locks');self.e.cure_status(self.p,'사슬묶기');self.e.gm.restore('locks')
  restored=self.restored();p=next(c for c in restored.gm.everyone if c.entity_id==self.p.entity_id)
  self.assertEqual({r['effect']['move_id'] for r in CI.records(p)}, {'move/몸통박치기','move/울음소리'})
  restored.start_round(restored.gm.everyone);restored.start_of_turn(p,initiative_count=20)
  self.assertEqual(restored.use_move(p,p,'move/울음소리'),0)
  self.a.spec['items']['회복약']=1;self.e.use_item(self.a,'회복약',self.p)
  self.assertNotIn('사슬묶기',self.p.conditions);self.assertFalse(CI.records(self.p));self.valid()
 def test_native_suppression_exact_count_and_staggered_reapplication(self):
  self.known(self.a,'트집');self.known(self.p,'도발','몸통박치기');self.begin(self.a)
  with patch.object(self.e,'d20',return_value=18):self.e.use_move(self.a,self.p,'move/트집')
  self.assertIn('억압',self.p.conditions);first=CI.records(self.p)[0]
  self.assertEqual(first['effect_instance']['lifetime'],{'boundary':'initiative_count','round':self.e.round_no+1,'count':20})
  self.e.end_of_turn(self.a);CLOCK.at_count(self.e,10);self.observed(self.p,'억압')
  self.e.start_of_turn(self.p,initiative_count=10);before=self.actions(self.p)
  self.assertEqual(self.e.use_move(self.p,self.other,'move/도발'),0);self.assertEqual(before,self.actions(self.p))
  with patch.object(self.e,'d20',return_value=18):self.e.use_move(self.p,self.other,'move/몸통박치기',set_damage=True)
  self.e.end_of_turn(self.p);self.e.end_round();self.assertEqual(len(CI.records(self.p)),2)
  self.e.start_round(self.e.gm.everyone);CLOCK.at_count(self.e,21);self.assertEqual(len(CI.records(self.p)),2)
  CLOCK.at_count(self.e,20);self.assertEqual(len(CI.records(self.p)),1);self.assertIn('억압',self.p.conditions)
  CLOCK.at_count(self.e,10);self.assertFalse(CI.records(self.p));self.assertNotIn('억압',self.p.conditions);self.valid()
 def test_suppression_restore_and_successor_round_end_use_same_clock(self):
  for kind in ('a','p'):
   self.setUp();self.begin(self.a);c=getattr(self,kind);self.observed(c,'억압');self.e.gm.snapshot('clock')
   self.e.cure_status(c,'억압');self.e.gm.restore('clock');restored=self.restored();rc=next(x for x in restored.gm.everyone if x.entity_id==c.entity_id)
   restored.end_of_turn(next(x for x in restored.gm.everyone if x.entity_id==self.a.entity_id));restored.end_round()
   self.assertIn('억압',rc.conditions);restored.start_round(restored.gm.everyone);restored.end_round()
   self.assertNotIn('억압',rc.conditions);self.assertTrue(restored.validate_state()['valid'])
 def test_native_infatuation_tracks_actual_beloved_and_damage_branches(self):
  self.known(self.a,'헤롱헤롱');self.a.spec['gender']='male';self.p.spec['gender']='female';self.begin(self.a)
  with patch.object(self.e,'d20',return_value=18):self.e.use_move(self.a,self.p,'move/헤롱헤롱')
  self.assertEqual(CI.beloved(self.p),[self.a]);self.e.end_of_turn(self.a)
  for mid in ('struggle','move/물대포'):
   for target,group in ((self.a,False),(self.other,False),(self.other,True)):
    with self.subTest(move=mid,target=target.name,beloved_in_group=group):
     move=dict(self.r.move(mid));move['_actual_targets']=(target,self.a) if group else (target,)
     before=self.e.roll_damage(self.p,target,move,set_damage=True)
     records=self.p.custom_conditions.pop(CI.KEY);self.p.conditions.remove('헤롱헤롱')
     plain=self.e.roll_damage(self.p,target,move,set_damage=True)
     self.p.custom_conditions[CI.KEY]=records;self.p.conditions.add('헤롱헤롱')
     stat='atk' if move['class']=='물리' else 'spa'
     expected=self.p.staged(stat)-self.p.staged(stat)//2 if target is self.a or group else 5
     self.assertEqual(plain-before,expected)
  self.known(self.p,'물대포');self.begin(self.p)
  hp=self.other.hp
  with patch.object(self.e,'d20',return_value=18):self.e.use_move(self.p,self.other,'move/물대포',set_damage=True)
  self.assertLess(self.other.hp,hp);self.assertEqual(self.p.budget['standard'],0);self.valid()
 def test_infatuation_restore_uses_actor_identity_and_cures_on_actual_save(self):
  for kind in ('a','p'):
   self.setUp();c=getattr(self,kind);self.observed(c,'헤롱헤롱',applied_by=self.other);self.e.gm.snapshot('beloved');self.e.cure_status(c,'헤롱헤롱');self.e.gm.restore('beloved')
   restored=self.restored();rc=next(x for x in restored.gm.everyone if x.entity_id==c.entity_id);beloved=next(x for x in restored.gm.everyone if x.entity_id==self.other.entity_id)
   self.assertIs(CI.beloved(rc)[0],beloved);restored.start_round(restored.gm.everyone);restored.start_of_turn(rc,initiative_count=20)
   with patch.object(type(restored),'d20',return_value=16) as roll:restored.end_of_turn(rc)
   self.assertEqual(roll.call_count,1);self.assertNotIn('헤롱헤롱',rc.conditions);self.assertFalse(CI.records(rc));self.assertTrue(restored.validate_state()['valid'])
 def test_shared_cure_recall_faint_and_encounter_boundaries_archive_instances(self):
  for kind in ('a','p'):
   for boundary in ('cure','recall','faint','end'):
    with self.subTest(kind=kind,boundary=boundary):
     self.setUp();c=getattr(self,kind);self.begin(self.a)
     self.observed(c,'사슬묶기',parameters={'move_id':'move/몸통박치기'});self.observed(c,'억압');self.observed(c,'헤롱헤롱',applied_by=self.other)
     self.e.apply_status(c,'실명')
     if boundary=='cure':self.e.apply_effect(self.a,c,{'type':'cure_all_status','target':'target'},20,True,0,'gm/status-cure')
     elif boundary=='recall':self.e.gm.recall(c,reason='actual recall')
     elif boundary=='faint':self.e.gm.faint(c,reason='actual faint')
     else:self.e.end_of_turn(self.a);self.e.end_encounter()
     self.assertFalse(CI.records(c));self.assertIn('실명',c.conditions)
     self.assertEqual(len([r for r in c.spec['effect_instance_history'] if r['effect_instance']['kind']=='condition']),3);self.valid()
 def test_only_timed_status_requires_count_and_suppression_still_allows_struggle(self):
  for condition,options in [('사슬묶기',{'parameters':{'move_id':'move/몸통박치기'}}),('헤롱헤롱',{'applied_by':self.other})]:
   self.observed(self.p,condition,**options)
  self.e.start_round(self.e.gm.everyone);self.e.start_of_turn(self.p)
  self.assertEqual(self.p.budget['standard'],1);self.valid()
  self.setUp();self.begin(self.p);self.observed(self.p,'억압')
  with patch.object(self.e,'d20',return_value=18):self.e.use_move(self.p,self.other,'struggle',set_damage=True)
  self.assertEqual(self.p.budget['standard'],0);self.valid()
 def test_missing_parameters_and_corrupted_references_reject_without_invented_state(self):
  before=self.snap()
  for cond,kw in [('사슬묶기',{}),('헤롱헤롱',{}),('억압',{})]:
   with self.assertRaises(ValueError):self.observed(self.p,cond,**kw)
   self.assertEqual(before,self.snap())
  self.observed(self.p,'헤롱헤롱',applied_by=self.a);CI.records(self.p)[0]['effect']['beloved_id']=self.other.entity_id
  with self.assertRaises(CODEC.StateCodecError):CODEC.dump_engine(self.e)
  self.setUp();self.begin(self.a);self.observed(self.p,'억압');CI.records(self.p)[0]['effect_instance']['lifetime']['round']+=1
  with self.assertRaises(CODEC.StateCodecError):CODEC.dump_engine(self.e)

if __name__=='__main__':unittest.main()
