"""Shared injury provenance, no-new-injury intervals, AP recovery and true HP basis."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_team_blessings as _fixture_test_category2_team_blessings
import injury_recovery as I,downtime as D,action_points as AP,effects_ext as EXT
import environmental_effects as ENV,state_fields as F,state_codec as CODEC,world_entities as W,common_checks as C
from builder import build_pokemon

class InjuryRecoveryTests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_team_blessings.TeamBlessingTests.setUpClass.__func__)
 known=_fixture_test_category2_team_blessings.TeamBlessingTests.known; snap=_fixture_test_category2_team_blessings.TeamBlessingTests.snap; valid=_fixture_test_category2_team_blessings.TeamBlessingTests.valid; restored=_fixture_test_category2_team_blessings.TeamBlessingTests.restored
 add=_fixture_test_category2_team_blessings.TeamBlessingTests.add; begin=_fixture_test_category2_team_blessings.TeamBlessingTests.begin; setUp=_fixture_test_category2_team_blessings.TeamBlessingTests.setUp
 def injure(self,c,n=2):self.e.gm.set_injuries(c,value=n,reason='actual observed injury')
 def ap_heal(self,c=None,minutes=2):
  return self.e.recover_injury(c or self.a,source='trainer_ap',duration_minutes=minutes,reason='GM duration of actual Extended recovery')
 def test_natural_recovery_needs_actual_twenty_four_hours_without_requiring_rest(self):
  for role in ('a','p'):
   self.setUp();c=getattr(self,role);self.injure(c)
   self.e.advance_time(86399,[c]);self.assertEqual(self.e.recover_injury(c),0)
   self.e.advance_time(1,[c]);self.assertEqual(self.e.recover_injury(c),1);self.assertEqual(c.injuries,1)
   self.assertEqual(self.e.recover_injury(c),0);D.new_day(c);self.assertEqual(self.e.recover_injury(c),0)
   self.e.advance_time(86400,[c]);self.assertEqual(self.e.recover_injury(c),1);self.assertEqual(c.injuries,0);self.valid()
 def test_every_shared_actual_gain_resets_the_window_instead_of_using_injured_today(self):
  for route in ('gm','effect','damage','suffocation'):
   with self.subTest(route=route):
    self.setUp();c=self.p;self.injure(c,1);self.e.advance_time(86000,[c])
    if route=='gm':self.e.gm.set_injuries(c,delta=1,reason='another actual injury')
    elif route=='effect':EXT.h_injury(self.e,c,c,{'value':1},{})
    elif route=='damage':self.e.take_damage(c,(c.base_max_hp+1)//2)
    else:
     self.e.observe_breathing(c,air_available=False,medium='airless',reason='actual deprivation',timing_policy='completed_round_after_grace')
     self.e.advance_time(70,[c]);self.e.observe_breathing(c,air_available=True,medium='air',reason='actual breathing')
    row=c.spec[I.CLOCK];self.assertEqual(row['known_seconds'],0);self.assertTrue(row['last_injury_source'])
    self.e.advance_time(400,[c]);self.assertEqual(self.e.recover_injury(c),0);self.valid()
 def test_split_extended_rests_share_actual_clock_and_new_injury_resets_it(self):
  self.injure(self.p,3);D.extended_rest(self.e,self.p,12);self.assertEqual(self.p.injuries,3)
  D.extended_rest(self.e,self.p,12);self.assertEqual(self.p.injuries,2)
  self.injure(self.p,3);D.extended_rest(self.e,self.p,23);self.assertEqual(self.p.injuries,3)
  self.e.gm.set_injuries(self.p,delta=1,reason='late new injury');D.extended_rest(self.e,self.p,1)
  self.assertEqual(self.p.injuries,4);self.assertEqual(I.healed_today(self.p),1);self.valid()
 def test_unknown_birth_round_is_not_credited_as_a_full_known_interval(self):
  self.begin(self.a);self.injure(self.p,1);self.e.end_encounter(round_elapsed_seconds=10)
  self.assertEqual(self.p.spec[I.CLOCK]['known_seconds'],0)
  self.e.advance_time(86399,[self.p]);self.assertEqual(self.e.recover_injury(self.p),0)
  self.e.advance_time(1,[self.p]);self.assertEqual(self.e.recover_injury(self.p),1);self.valid()
 def test_native_ap_recovery_spends_drained_not_normal_ap_and_requires_actual_duration(self):
  self.injure(self.a,2);AP.spend(self.a,1);before=self.snap()
  self.assertIsInstance(self.e.recover_injury(self.a,source='trainer_ap'),C.PendingDecision);self.assertEqual(self.snap(),before)
  start=self.e.elapsed_seconds;result=self.ap_heal()
  self.assertEqual((result['recovered'],result['ap_drained'],self.a.injuries),(1,2,1))
  self.assertEqual(self.e.elapsed_seconds-start,120);self.assertEqual((self.a.spec['ap_spent'],self.a.spec['ap_removed']),(1,2))
  self.assertEqual(self.a._action_history[-1],'extended')
  before=self.snap()
  with self.assertRaises(ValueError):self.ap_heal(self.p)
  self.assertEqual(self.snap(),before);D.extended_rest(self.e,self.a,4);self.assertEqual(self.a.spec['ap_removed'],0);self.valid()
 def test_natural_and_ap_recovery_share_daily_limit_without_consuming_failed_cost(self):
  self.injure(self.a,3);self.e.advance_time(86400,[self.a]);self.assertEqual(self.e.recover_injury(self.a),1)
  self.ap_heal();self.ap_heal();self.assertEqual((self.a.injuries,I.healed_today(self.a)),(0,3))
  self.injure(self.a,1);before=self.snap();self.assertIs(self.ap_heal(),False);self.assertEqual(self.snap(),before)
  D.new_day(self.a);self.assertEqual(self.ap_heal()['recovered'],1);self.assertEqual(I.healed_today(self.a),1);self.valid()
 def test_suffocation_provenance_blocks_ordinary_ap_and_gm_deletion_then_breathing_cures(self):
  self.e.observe_breathing(self.a,air_available=False,medium='airless',reason='actual deprivation',timing_policy='completed_round_after_grace')
  self.e.advance_time(70,[self.a]);before=self.snap();self.assertEqual(self.a.injuries,1)
  self.assertIs(self.ap_heal(),False);self.assertEqual(self.snap(),before)
  with self.assertRaises(ValueError):self.e.gm.set_injuries(self.a,value=0,reason='cannot erase protected provenance')
  self.assertEqual(self.snap(),before)
  self.e.observe_breathing(self.a,air_available=True,medium='air',reason='air restored')
  self.assertEqual((self.a.injuries,I.healed_today(self.a)),(0,0));self.valid()
 def test_gm_and_durable_restore_keep_the_same_clock_and_ap_receipts(self):
  self.injure(self.a,3);self.e.advance_time(82800,[self.a]);snapshot=self.e.gm.snapshot('injury')
  loaded=self.restored();c=W.actor_index(loaded)[self.a.entity_id];loaded.advance_time(3600,[c])
  self.assertEqual(loaded.recover_injury(c),1)
  result=loaded.recover_injury(c,source='trainer_ap',duration_minutes=1,reason='actual Extended recovery')
  self.assertEqual(result['recovered'],1);self.assertTrue(loaded.validate_state()['valid'])
  loaded_again=type(self.e).import_state(self.r,loaded.export_state());self.assertTrue(loaded_again.validate_state()['valid'])
  self.e.advance_time(3600,[self.a]);self.e.recover_injury(self.a);self.e.gm.restore(snapshot)
  self.assertEqual(self.a.injuries,3);self.assertEqual(self.a.spec[I.CLOCK]['known_seconds'],82800);self.valid()
 def test_ap_post_clock_failure_rolls_back_resources_time_and_life_state(self):
  self.injure(self.a,2);before=self.snap()
  with patch.object(I,'heal',side_effect=ValueError('injected post-clock failure')):
   with self.assertRaises(ValueError):self.ap_heal()
  self.assertEqual(self.snap(),before)
  self.e.apply_status(self.a,'잠듦');before=self.snap();self.assertIs(self.ap_heal(),False);self.assertEqual(self.snap()[:-1],before[:-1])
  self.e.cure_status(self.a,'잠듦')
  AP.spend(self.a,AP.available(self.a));before=self.snap();self.assertIs(self.ap_heal(),False);self.assertEqual(self.snap(),before)
 def test_injury_ceiling_rounds_combined_true_maximum_ratio_without_reducing_current_hp(self):
  for c in (self.a,self.p):
   F.base_patch(c,{'stats':{**c.stats,'hp':23}},reason='actual nondivisible maximum HP')
   base=c.base_max_hp;self.assertNotEqual(base%10,0);self.e.gm.set_hp(c,value=base,reason='actual full HP')
   for n in (1,2,3,4):
    self.injure(c,n);self.assertEqual(c.max_hp,(base*(10-n))//10);self.assertEqual(c.hp,base)
    self.assertEqual(self.e.heal(c,1,source_kind='ordinary_item'),0);self.assertEqual(self.e.tick(c),base//10)
   self.e.gm.set_hp(c,value=base,reason='explicit GM HP observation');self.assertEqual(c.hp,base)
  self.valid()
 def test_native_growth_hp_rescaling_uses_true_maximum_before_and_after_change(self):
  c=self.add(build_pokemon(self.r,'이브이',1,moves=[],abilities=[]));self.injure(c,3)
  c.hp=c.max_hp;before=c.hp;old=c.base_max_hp;old_cap=c.max_hp
  D.gain_exp_combatant(self.e,c,'to next level')
  self.assertEqual(c.hp,(before*c.base_max_hp)//old);self.assertNotEqual(c.hp,(before*c.max_hp)//old_cap)
  self.assertEqual(c.injuries,3);self.valid()
 def test_invalid_clock_and_respiration_evidence_is_rejected_by_durable_validation(self):
  self.injure(self.p,1);self.e.observe_breathing(self.p,air_available=False,medium='airless',reason='actual deprivation')
  saved=deepcopy(self.p.spec)
  mutations=[lambda c:c.spec[I.CLOCK].update(known_seconds=True),lambda c:c.spec[I.CLOCK].update(known_seconds=86400),
    lambda c:c.spec[I.CLOCK].update(birth_round=self.e.round_no+1),
    lambda c:c.spec['_respiration'].update(air_available=1),lambda c:c.spec['_respiration'].update(protected_injuries=1),
    lambda c:c.spec['_respiration'].update(observed_at=self.e.elapsed_seconds+1)]
  for mutate in mutations:
   self.p.spec.clear();self.p.spec.update(deepcopy(saved));mutate(self.p)
   with self.assertRaises(CODEC.StateCodecError):CODEC.dump_engine(self.e)
  self.p.spec.clear();self.p.spec.update(saved);self.valid()

if __name__=='__main__':unittest.main()
