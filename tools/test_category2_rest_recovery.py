"""Classified group activities, shared recovery allowances and durable boundaries."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import sys,unittest,json
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_team_blessings as _fixture_test_category2_team_blessings
import downtime as D,rest_intervals as REST,injury_recovery as I,action_points as AP,frequency as F
import effects_ext as EXT,state_codec as CODEC,world_entities as W
from engine import Engine

class RestRecoveryTests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_team_blessings.TeamBlessingTests.setUpClass.__func__)
 known=_fixture_test_category2_team_blessings.TeamBlessingTests.known; snap=_fixture_test_category2_team_blessings.TeamBlessingTests.snap; valid=_fixture_test_category2_team_blessings.TeamBlessingTests.valid; restored=_fixture_test_category2_team_blessings.TeamBlessingTests.restored
 add=_fixture_test_category2_team_blessings.TeamBlessingTests.add; begin=_fixture_test_category2_team_blessings.TeamBlessingTests.begin; setUp=_fixture_test_category2_team_blessings.TeamBlessingTests.setUp
 def activity(self,minutes,*,actors=None,rest=True,rest_id=None):
  return self.e.gm.observe_activity(actors or [self.a,self.p],minutes,qualifies_as_rest=rest,
       reason='GM classified the actual physical and mental activity',rest_id=rest_id)
 def test_one_shared_clock_and_independent_rest_blocks_for_both_actor_kinds(self):
  self.a.hp=self.p.hp=1;start=self.e.elapsed_seconds
  self.activity(15,rest_id='same-bout');self.assertEqual((self.a.hp,self.p.hp),(1,1))
  rows=self.activity(15,rest_id='same-bout')
  self.assertEqual(self.e.elapsed_seconds-start,1800)
  for c,row in zip((self.a,self.p),rows):
   self.assertEqual(c.hp,1+c.base_max_hp//16);self.assertEqual(c.spec['rested_minutes_today'],30)
   self.assertEqual(row['source'],'combat/resting');self.assertTrue(row['qualifies_as_rest'])
  self.valid()
 def test_gm_nonrest_activity_advances_time_without_credit_and_breaks_continuity(self):
  self.a.hp=self.p.hp=1;self.activity(15,rest_id='bout');self.activity(10,rest=False)
  for c in (self.a,self.p):
   self.assertNotIn('rest_interval',c.spec);self.assertEqual(c.spec['rested_minutes_today'],15)
   self.assertFalse(c.spec[REST.ACTIVITIES][-1]['qualifies_as_rest'])
  self.activity(15,rest_id='bout');self.assertEqual((self.a.hp,self.p.hp),(1,1))
  self.activity(15,rest_id='bout')
  for c in (self.a,self.p):self.assertEqual(c.hp,1+c.base_max_hp//16)
  self.valid()
 def test_eight_hour_budget_uses_true_maximum_and_only_new_day_refreshes(self):
  for c in (self.a,self.p):c.hp=1;c.injuries=1
  self.activity(30,rest_id='first')
  for c in (self.a,self.p):self.assertEqual(c.hp,1+c.base_max_hp//16)
  self.activity(450,rest_id='first');self.e.lose_hp(self.a,5);self.e.lose_hp(self.p,5)
  before=[c.hp for c in (self.a,self.p)];self.activity(30,rest_id='second')
  self.assertEqual([c.hp for c in (self.a,self.p)],before)
  for c in (self.a,self.p):D.new_day(c)
  self.activity(30,rest_id='next-day')
  for c,hp in zip((self.a,self.p),before):self.assertEqual(c.hp,min(c.max_hp,hp+c.base_max_hp//16))
  self.valid()
 def test_heavy_injury_gate_recovers_at_four_without_refunding_used_rest_time(self):
  for c in (self.a,self.p):c.hp=1;c.injuries=5
  self.activity(30,rest_id='heavy');self.assertEqual((self.a.hp,self.p.hp),(1,1))
  for c in (self.a,self.p):self.assertEqual(I.heal(self.e,c,1,source='feature_observed_recovery'),1)
  self.activity(30,rest_id='eligible')
  for c in (self.a,self.p):
   self.assertEqual(c.injuries,4);self.assertEqual(c.hp,1+c.base_max_hp//16)
   self.assertEqual(c.spec['rested_minutes_today'],60)
  self.valid()
 def test_four_hour_milestone_cures_persistent_restores_drained_ap_and_checks_daily_origin(self):
  AP.spend(self.a,1);AP.spend(self.a,2,{'frequency':{'raw':'2 AP 제거'}})
  for c in (self.a,self.p):self.e.apply_status(c,'독')
  self.known(self.p,'아침햇살');self.begin(self.p);self.e.use_move(self.p,self.p,'move/아침햇살');self.e.end_encounter(round_elapsed_seconds=10)
  self.assertEqual(F.move_frequency(self.e,'move/아침햇살',self.p)[0],'daily')
  self.activity(239,rest_id='night');self.assertEqual(self.a.spec['ap_removed'],2);self.assertIn('독',self.p.conditions)
  self.activity(1,rest_id='night');self.assertEqual(self.a.spec['ap_removed'],0);self.assertEqual(self.a.spec['ap_spent'],1)
  self.assertFalse({'독'}&self.p.conditions);self.assertGreater(self.p.move_uses['move/아침햇살'],0)
  D.new_day(self.a);D.new_day(self.p);self.activity(240,rest_id='next-night')
  self.assertEqual(self.p.move_uses.get('move/아침햇살',0),0)
  self.p.move_uses['move/아침햇살']=1;self.p.spec['move_uses']=dict(self.p.move_uses);F.state(self.p)['moves'].pop('move/아침햇살',None)
  self.activity(240,rest_id='unknown-origin');self.assertEqual(self.p.move_uses['move/아침햇살'],1);self.valid()
 def test_drained_ap_split_rest_and_owner_survive_gm_and_json_restore(self):
  AP.spend(self.a,2,{'frequency':{'raw':'2 AP 제거'}})
  AP.spend(self.a,1)
  owner_id=self.a.entity_id;maximum=AP.maximum(self.a)
  self.activity(239,actors=[self.a],rest_id='drain-rest')
  self.assertEqual(self.a.spec['ap_removed'],2)
  self.assertEqual(AP.available(self.a),maximum-3)
  self.e.gm.snapshot('drain-before-completion')
  loaded=CODEC.load_engine(self.r,json.loads(json.dumps(CODEC.dump_engine(self.e))))
  clone=next(c for c in loaded.gm.everyone if c.entity_id==owner_id)
  for engine,actor in ((self.e,self.a),(loaded,clone)):
   self.assertEqual(actor.spec['ap_removed'],2)
   self.assertEqual(actor.spec['rest_interval']['total_minutes'],239)
   engine.gm.observe_activity([actor],1,qualifies_as_rest=True,
       reason='same actual uninterrupted rest completes',rest_id='drain-rest')
   self.assertEqual(actor.spec['ap_removed'],0)
   self.assertEqual(actor.spec['ap_spent'],1)
   self.assertEqual(AP.available(actor),maximum-1)
   self.assertTrue(engine.validate_state()['valid'])
  self.e.gm.restore('drain-before-completion')
  self.assertIs(next(c for c in self.e.gm.everyone if c.entity_id==owner_id),self.a)
  self.assertEqual(self.a.spec['ap_removed'],2)
  self.assertEqual(self.a.spec['rest_interval']['total_minutes'],239)
  self.activity(1,actors=[self.a],rest_id='drain-rest')
  self.assertEqual(self.a.spec['ap_removed'],0);self.valid()
 def test_scene_day_and_interrupted_rest_cannot_recover_drain_or_repeat_milestone(self):
  AP.spend(self.a,2,{'frequency':{'raw':'2 AP 제거'}})
  AP.spend(self.a,1)
  self.e.end_scene([self.a,self.p]);D.new_day(self.a)
  self.assertEqual(self.a.spec['ap_removed'],2)
  self.assertEqual(self.a.spec['ap_spent'],0)
  self.activity(239,actors=[self.a],rest_id='interrupted-drain')
  self.activity(1,actors=[self.a],rest=False)
  self.activity(1,actors=[self.a],rest_id='new-drain-rest')
  self.assertEqual(self.a.spec['ap_removed'],2)
  self.assertEqual(self.a.spec['rest_interval']['total_minutes'],1)
  self.activity(239,actors=[self.a],rest_id='new-drain-rest')
  self.assertEqual(self.a.spec['ap_removed'],0)
  AP.spend(self.a,1,{'frequency':{'raw':'1 AP 제거'}})
  self.activity(1,actors=[self.a],rest_id='new-drain-rest')
  self.assertEqual(self.a.spec['ap_removed'],1)
  self.valid()
 def test_daily_injury_cap_combines_feature_center_and_actual_bandage_recovery(self):
  self.a.spec['items']['붕대']=2
  for c in (self.a,self.p):c.injuries=6
  self.e.use_item(self.a,'붕대',self.p,count=1,duration_minutes=1,duration_reason='actual application interval')
  EXT.h_heal_injury(self.e,self.a,self.p,{'value':1,'target':'target'},{'healing_source_kind':'feature'})
  self.e.advance_time(21600,[self.p]);self.assertEqual(I.healed_today(self.p),2);self.assertEqual(self.p.injuries,4)
  D.pokemon_center(self.e,self.p);self.assertEqual(I.healed_today(self.p),3);self.assertEqual(self.p.injuries,3)
  EXT.h_heal_injury(self.e,self.a,self.p,{'value':3,'target':'target'},{'healing_source_kind':'feature'});self.assertEqual(self.p.injuries,3)
  self.assertEqual(I.healed_today(self.a),0);D.new_day(self.p);D.pokemon_center(self.e,self.p)
  self.assertEqual(self.p.injuries,0);self.assertEqual(I.healed_today(self.p),3);self.valid()
 def test_both_restore_paths_preserve_classification_remainders_and_budget(self):
  self.a.hp=self.p.hp=1;self.activity(29,rest_id='saved');snapshot=self.e.gm.snapshot('rest')
  loaded=self.restored();group=[W.actor_index(loaded)[c.entity_id] for c in (self.a,self.p)]
  loaded.gm.observe_activity(group,1,qualifies_as_rest=True,reason='same actual rest continues',rest_id='saved')
  for c in group:self.assertEqual(c.hp,1+c.base_max_hp//16);self.assertEqual(c.spec['rested_minutes_today'],30)
  again=Engine.import_state(self.r,loaded.export_state());self.assertTrue(again.validate_state()['valid'])
  self.activity(1,rest_id='saved');self.e.gm.restore(snapshot)
  self.assertEqual(self.a.spec['rest_interval']['carry_minutes'],29);self.assertEqual(len(self.a.spec[REST.ACTIVITIES]),1)
  self.activity(1,rest_id='saved');self.assertEqual(self.a.hp,1+self.a.base_max_hp//16);self.valid()
 def test_failed_group_activity_is_atomic_and_invalid_classification_spends_nothing(self):
  before=self.snap()
  for value in (None,1,'rest'):
   with self.assertRaises(ValueError):self.e.gm.observe_activity([self.a,self.p],30,qualifies_as_rest=value,reason='observed')
   self.assertEqual(self.snap(),before)
  with self.assertRaises(ValueError):self.e.gm.observe_activity([self.a,self.p],30,qualifies_as_rest=True,reason='')
  with patch.object(Engine,'heal',side_effect=ValueError('post-clock injected failure')):
   with self.assertRaises(ValueError):self.activity(30,rest_id='rollback')
  self.assertEqual(self.snap(),before)
 def test_malformed_durable_rest_and_injury_evidence_cannot_be_exported(self):
  self.activity(15,rest_id='actual');saved=deepcopy(self.p.spec)
  mutations=[lambda c:c.spec['rest_interval'].update(carry_minutes=30),
   lambda c:c.spec.update(rested_minutes_today=True),
   lambda c:c.spec['rest_interval'].update(end_seconds=self.e.elapsed_seconds+1),
   lambda c:c.spec[REST.ACTIVITIES][0].update(qualifies_as_rest=1),
   lambda c:c.spec[REST.ACTIVITIES][0].update(end=1),
   lambda c:c.spec.update(injuries_healed_today=-1),
   lambda c:c.spec.update(injury_healing_history=[{'source':'feature','count':True,'known_elapsed_seconds':0}])]
  for mutate in mutations:
   self.p.spec.clear();self.p.spec.update(deepcopy(saved));mutate(self.p)
   with self.assertRaises(CODEC.StateCodecError):CODEC.dump_engine(self.e)
  self.p.spec.clear();self.p.spec.update(saved);self.valid()

if __name__=='__main__':unittest.main()
