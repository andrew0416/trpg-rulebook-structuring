"""Shared affliction classification, dependency, end and native action consumers."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Engine
import test_category2_team_blessings as _fixture_test_category2_team_blessings
import status_sets as S,state_codec as CODEC,temporary_hp as TEMP,turn as TURN

class StatusFamilyTests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_team_blessings.TeamBlessingTests.setUpClass.__func__)
 known=_fixture_test_category2_team_blessings.TeamBlessingTests.known
 snap=_fixture_test_category2_team_blessings.TeamBlessingTests.snap
 valid=_fixture_test_category2_team_blessings.TeamBlessingTests.valid
 restored=_fixture_test_category2_team_blessings.TeamBlessingTests.restored
 add=_fixture_test_category2_team_blessings.TeamBlessingTests.add
 begin=_fixture_test_category2_team_blessings.TeamBlessingTests.begin
 setUp=_fixture_test_category2_team_blessings.TeamBlessingTests.setUp
 def apply(self,c,*names):
  for name in names:self.assertTrue(self.e.apply_status(c,name),name)
 def action_state(self,c):return deepcopy((c.budget,c.move_uses,c.hp,c.spec.get('items'),self.e.rng.getstate()))
 def test_native_vortex_progress_and_independent_slow_survive_both_restores(self):
  for role in ('a','p'):
   for restoration in ('gm','json'):
    with self.subTest(role=role,restoration=restoration):
     self.setUp();target=getattr(self,role)
     self.apply(target,'둔화');self.known(self.other,'바다회오리')
     self.e.start_round(self.e.gm.everyone);self.e.start_of_turn(self.other,initiative_count=30)
     with patch.object(self.e,'d20',return_value=18):
      self.assertGreater(self.e.use_move(self.other,target,'move/바다회오리',set_damage=True),0)
     self.assertTrue({'조이기','둔화','수렁'}<=target.conditions)
     self.e.end_of_turn(self.other);hp=target.hp
     self.e.start_of_turn(target,initiative_count=20)
     self.assertEqual(target.hp,hp-self.e.tick(target))
     with patch.object(Engine,'d20',return_value=20):self.e.end_of_turn(target)
     self.assertEqual(target.custom_conditions['vortex']['ends'],1)
     if restoration=='gm':
      self.e.gm.snapshot('native-vortex');self.e.cure_status(target,'조이기')
      self.e.gm.restore('native-vortex');engine=self.e
     else:engine=self.restored()
     actual=next(c for c in engine.gm.everyone if c.entity_id==target.entity_id)
     self.assertEqual(actual.custom_conditions['vortex']['ends'],1)
     self.assertEqual(actual.custom_conditions['vortex']['owned'],{'수렁'})
     for roll,ends in ((14,2),(9,None)):
      hp=actual.hp;engine.start_round(engine.gm.everyone);engine.start_of_turn(actual,initiative_count=20)
      self.assertEqual(actual.hp,hp-engine.tick(actual))
      with patch.object(Engine,'d20',return_value=roll):engine.end_of_turn(actual)
      if ends is not None:self.assertEqual(actual.custom_conditions['vortex']['ends'],ends)
     self.assertIn('둔화',actual.conditions)
     self.assertFalse({'조이기','수렁'}&actual.conditions)
     self.assertNotIn('vortex',actual.custom_conditions)
     self.assertTrue(engine.validate_state()['valid'])
 def test_native_ability_status_immunities_follow_actual_moves_and_both_restores(self):
  import state_grants as G
  for role in ('a','p'):
   for ability,condition,move in (('수의베일','화상','도깨비불'),('마이페이스','혼란','이상한빛')):
    with self.subTest(role=role,ability=ability):
     self.setUp();target=getattr(self,role)
     G.replace_baseline(self.e,target,'abilities',[ability]);self.known(self.other,move)
     self.e.start_round(self.e.gm.everyone);self.e.start_of_turn(self.other,initiative_count=30)
     with patch.object(self.e,'d20',return_value=18):self.e.use_move(self.other,target,'move/'+move)
     self.assertNotIn(condition,target.conditions)
     source=self.r.selection.resolve_name(ability,('ability/',))
     self.assertEqual(self.e.immune_to(target,condition),source)
     self.assertTrue(self.e.apply_status(target,'독'))
     self.e.gm.snapshot('native-immunity');G.replace_baseline(self.e,target,'abilities',[])
     self.assertTrue(self.e.apply_status(target,condition));self.e.gm.restore('native-immunity')
     self.assertFalse(self.e.apply_status(target,condition))
     engine=self.restored();actual=next(c for c in engine.gm.everyone if c.entity_id==target.entity_id)
     self.assertEqual(engine.immune_to(actual,condition),source)
     self.assertFalse(engine.apply_status(actual,condition))
     actual.abilities_suppressed=True
     self.assertTrue(engine.apply_status(actual,condition));engine.cure_status(actual,condition)
     actual.abilities_suppressed=False
     self.assertFalse(engine.apply_status(actual,condition))
     G.replace_baseline(engine,actual,'abilities',[])
     self.assertTrue(engine.apply_status(actual,condition));self.assertIn('독',actual.conditions)
     self.assertTrue(engine.validate_state()['valid'])
 def test_native_immunity_lists_and_independent_sources_end_separately(self):
  import state_grants as G
  for role in ('a','p'):
   with self.subTest(role=role):
    self.setUp();target=getattr(self,role)
    G.replace_baseline(self.e,target,'abilities',['수의베일','둔감'])
    G.grant(target,'abilities','수의베일','gm/second-water-veil','gm',rule_id='ability/수의베일')
    G.reconcile(self.e,target)
    for condition in ('화상','난동','헤롱헤롱'):self.assertIsNotNone(self.e.immune_to(target,condition))
    G.replace_baseline(self.e,target,'abilities',['둔감'])
    self.assertFalse(self.e.apply_status(target,'화상'))
    G.set_member(target,'status_immune','화상','gm/independent-burn-immunity')
    G.revoke(target,'gm/second-water-veil',engine=self.e)
    target.abilities_suppressed=True
    self.assertFalse(self.e.apply_status(target,'화상'))
    self.assertTrue(self.e.apply_status(target,'난동'));self.e.cure_status(target,'난동')
    self.assertIsNone(self.e.immune_to(target,'헤롱헤롱'))
    target.abilities_suppressed=False;G.replace_baseline(self.e,target,'abilities',[])
    self.assertFalse(self.e.apply_status(target,'화상'))
    self.assertTrue(self.e.apply_status(target,'난동'))
    self.assertTrue(self.e.validate_state()['valid'])
 def test_one_authoritative_set_has_no_affliction_count_cap_and_both_restore_paths(self):
  names=('화상','독','혼란','저주','난동','잠듦','악몽')
  for c in (self.a,self.p):
   self.apply(c,*names);self.assertEqual(set(S.afflictions(c)),set(names))
   self.assertFalse(self.e.apply_status(c,'화상'));self.assertEqual(len(c.conditions),7)
  self.e.gm.snapshot('afflictions');self.e.cure_status(self.p,'잠듦');self.e.gm.restore('afflictions')
  restored=self.restored()
  for c in restored.gm.everyone:
   if c.entity_id in (self.a.entity_id,self.p.entity_id):self.assertEqual(set(S.afflictions(c)),set(names))
  self.valid();self.assertTrue(restored.validate_state()['valid'])
 def test_actual_full_restore_item_cures_afflictions_not_other_states_or_temporary_hp(self):
  for c in (self.a,self.p):
   self.setUp();c=self.a if c.kind=='trainer' else self.p
   self.a.spec['items']['회복약']=1
   self.apply(c,'화상','혼란','둔화','실명','취약');TEMP.grant(self.e,c,20)
   c.hp-=10;self.e.use_item(self.a,'회복약',c)
   self.assertEqual(c.conditions,{'둔화','실명','취약'});self.assertEqual(c.temp_hp,20)
   self.assertEqual(self.a.spec['items']['회복약'],0);self.valid()
  self.assertEqual(self.r.condition_class('임시-체력'),'resource')
  before=self.snap()
  with self.assertRaises(ValueError):self.e.apply_status(self.a,'임시-체력')
  self.assertEqual(before,self.snap())
 def test_native_cure_dispatch_distinguishes_persistent_from_all_afflictions(self):
  self.apply(self.p,'화상','혼란','둔화')
  self.e.gm.add_condition(self.p,'GM 관측 표식',force=True,reason='opaque observation retained')
  self.e.apply_effect(self.a,self.p,{'type':'cure_status','status':'all persistent','target':'target'},20,True,0,'gm/observed-persistent-cure')
  self.assertEqual(self.p.conditions,{'혼란','둔화','GM 관측 표식'})
  self.e.apply_effect(self.a,self.p,{'type':'cure_all_status','target':'target'},20,True,0,'gm/observed-affliction-cure')
  self.assertEqual(self.p.conditions,{'둔화','GM 관측 표식'});self.valid()
 def test_volatile_recall_encounter_and_faint_boundaries_share_selected_classification(self):
  volatile=[r['mech']['data']['name'] for r in self.r.units.values() if (r.get('mech') or {}).get('schema')=='condition' and r['mech']['data'].get('class')=='volatile']
  for boundary in ('recall','end','faint'):
   for kind in ('a','p'):
    with self.subTest(boundary=boundary,kind=kind):
     self.setUp();c=getattr(self,kind);self.begin(self.other);self.apply(c,'화상','둔화','실명','잠듦');TEMP.grant(self.e,c,20)
     for name in volatile:
      if name not in c.conditions:
       params={'move_id':'move/몸통박치기'} if name=='사슬묶기' else None
       self.assertTrue(self.e.apply_status(c,name,parameters=params,applied_by=self.other),name)
     if boundary=='recall':self.e.gm.recall(c,reason='actual recall boundary')
     elif boundary=='end':self.e.end_of_turn(self.other);self.e.end_encounter()
     else:self.e.gm.faint(c,reason='actual faint boundary')
     self.assertFalse(S.afflictions(c,'volatile'));self.assertIn('실명',c.conditions)
     self.assertEqual('둔화' in c.conditions,boundary!='recall')
     self.assertEqual('화상' in c.conditions,boundary!='faint')
     self.assertEqual(c.temp_hp,0 if boundary=='recall' else 20);self.valid()
 def test_native_bad_sleep_target_gate_and_each_actual_sleep_save_loses_two_ticks(self):
  self.known(self.a,'악몽');self.begin(self.a)
  self.assertFalse(self.e.apply_status(self.p,'악몽'));self.assertNotIn('악몽',self.p.conditions)
  self.apply(self.p,'잠듦')
  with patch.object(self.e,'d20',return_value=18):self.e.use_move(self.a,self.p,'move/악몽')
  self.assertIn('악몽',self.p.conditions);self.assertEqual(self.a.move_uses['move/악몽'],1)
  for face in (1,16):
   self.begin(self.p);hp=self.p.hp
   with patch.object(Engine,'d20',return_value=face) as roller:self.e.end_of_turn(self.p)
   self.assertEqual(roller.call_count,1);self.assertEqual(hp-self.p.hp,2*self.e.tick(self.p))
   self.assertEqual('잠듦' in self.p.conditions,face<16);self.assertEqual('악몽' in self.p.conditions,face<16)
  self.valid()
 def test_bad_sleep_cure_dependency_persistence_and_faint_on_save(self):
  self.apply(self.p,'잠듦','악몽','저주');self.e.gm.snapshot('bad-sleep');restored=self.restored();c=next(x for x in restored.gm.everyone if x.entity_id==self.p.entity_id)
  restored.cure_status(c,'잠듦');self.assertEqual(c.conditions,{'저주'})
  self.e.cure_status(self.p,'잠듦');self.assertEqual(self.p.conditions,{'저주'});self.e.gm.restore('bad-sleep')
  self.p.hp=1;self.begin(self.p)
  with patch.object(Engine,'d20',return_value=16):self.e.end_of_turn(self.p)
  self.assertTrue(self.p.fainted);self.assertFalse(S.afflictions(self.p));self.valid()
  self.setUp();self.p.conditions.add('악몽')
  with self.assertRaises(CODEC.StateCodecError):CODEC.dump_engine(self.e)
 def test_curse_loss_requires_an_actual_standard_not_voluntary_or_forced_inaction(self):
  for kind in ('a','p'):
   for action in ('attack','none','frozen'):
    with self.subTest(kind=kind,action=action):
     self.setUp();c=getattr(self,kind);self.apply(c,'저주');self.begin(c);hp=c.hp
     if action=='attack':
      with patch.object(self.e,'d20',return_value=18):self.e.use_move(c,self.other,'struggle',set_damage=True)
     elif action=='frozen':self.apply(c,'얼음')
     with patch.object(Engine,'d20',return_value=1):self.e.end_of_turn(c)
     self.assertEqual(hp-c.hp,2*self.e.tick(c) if action=='attack' else 0);self.valid()
 def test_native_taunt_applies_rage_and_allows_only_damaging_moves_and_struggle(self):
  self.known(self.a,'도발');self.known(self.p,'울음소리','몸통박치기');self.begin(self.a)
  with patch.object(self.e,'d20',return_value=18):self.e.use_move(self.a,self.p,'move/도발')
  self.assertIn('난동',self.p.conditions);self.begin(self.p);before=self.action_state(self.p)
  self.assertEqual(self.e.use_move(self.p,self.other,'move/울음소리'),0);self.assertEqual(before,self.action_state(self.p))
  self.assertFalse(TURN.spend(self.e,self.p,'standard','non-attack action'));self.assertEqual(before,self.action_state(self.p))
  with patch.object(self.e,'d20',return_value=18):self.e.use_move(self.p,self.other,'move/몸통박치기',set_damage=True)
  self.assertEqual(self.p.budget['standard'],0)
  with patch.object(Engine,'d20',return_value=14) as roller:self.e.end_of_turn(self.p)
  self.assertEqual(roller.call_count,1);self.assertIn('난동',self.p.conditions);self.begin(self.p)
  with patch.object(self.e,'d20',return_value=18):self.e.use_move(self.p,self.other,'struggle',set_damage=True)
  with patch.object(Engine,'d20',return_value=15) as roller:self.e.end_of_turn(self.p)
  self.assertEqual(roller.call_count,1);self.assertNotIn('난동',self.p.conditions);self.valid()
 def test_sleep_suspends_rage_saves_and_restored_rage_still_restricts_native_actions(self):
  for kind in ('a','p'):
   self.setUp();c=getattr(self,kind);self.apply(c,'난동');self.known(c,'울음소리');self.e.gm.snapshot('rage');self.e.cure_status(c,'난동');self.e.gm.restore('rage')
   restored=self.restored();rc=next(x for x in restored.gm.everyone if x.entity_id==c.entity_id)
   restored.start_round(restored.gm.everyone);restored.start_of_turn(rc,initiative_count=20)
   self.assertEqual(restored.use_move(rc,rc,'move/울음소리'),0);self.assertEqual(rc.budget['standard'],1)
   self.apply(c,'잠듦');self.begin(c)
   with patch.object(Engine,'d20',return_value=1) as roller:self.e.end_of_turn(c)
   self.assertEqual(roller.call_count,1);self.assertIn('난동',c.conditions);self.valid()

if __name__=='__main__':unittest.main()
