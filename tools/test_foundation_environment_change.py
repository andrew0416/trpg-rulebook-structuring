"""Real environment mutation, native boundaries, source expiry and rollback."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_foundation_environment_derive as _fixture_test_foundation_environment_derive
import environment_change as EC,environment_derive as ED,environmental_effects as ENV
import movement_actions as MOVE,state_grants as G,state_codec as CODEC,forced_movement as FORCE

class ChangeTests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_foundation_environment_derive.EnvironmentTests.setUpClass.__func__)
 setUp=_fixture_test_foundation_environment_derive.EnvironmentTests.setUp;add=_fixture_test_foundation_environment_derive.EnvironmentTests.add;pokemon=_fixture_test_foundation_environment_derive.EnvironmentTests.pokemon;restored=_fixture_test_foundation_environment_derive.EnvironmentTests.restored;begin=_fixture_test_foundation_environment_derive.EnvironmentTests.begin
 policy=_fixture_test_foundation_environment_derive.EnvironmentTests.policy;region=_fixture_test_foundation_environment_derive.EnvironmentTests.region;bind=_fixture_test_foundation_environment_derive.EnvironmentTests.bind;snap=_fixture_test_foundation_environment_derive.EnvironmentTests.snap
 def start(self):self.region(gravity=1);self.bind()
 def change(self,changes=None,request='change/1',**options):
  return self.e.change_environment('region',changes or {'gravity':2},source=options.pop('source',self.policy()['source']),request_id=request,reason='actual environmental setting changed',**options)
 def test_persistent_gravity_setting_recalculates_actual_native_movement_without_rewriting_actor(self):
  self.start();base=self.a.movement;self.change();self.assertEqual(MOVE.capabilities(self.e,self.a)['land'],base//2)
  self.change({'gravity':0},request='change/2');self.assertTrue(ED.context(self.e,self.a)['zero_gravity']);self.assertEqual(MOVE.capabilities(self.e,self.a)['land'],base)
  self.assertEqual(self.a.movement,base)
 def test_temporary_effect_expires_at_exact_native_clock_split(self):
  self.start();self.change(duration_seconds=20);times=[];advance=ENV.advance
  def observe(e,c):times.append(e.elapsed_seconds);return advance(e,c)
  with patch.object(ENV,'advance',observe):self.e.advance_time(30)
  self.assertIn(20,times);self.assertIn(30,times);self.assertEqual(ED.context(self.e,self.a)['gravity'],1);self.assertEqual(self.e.elapsed_seconds,30)
 def test_independent_source_expiry_preserves_other_source_pressure(self):
  self.start();self.change(duration_seconds=20);self.change({'pressure':0},request='pressure',source='capability/아가미',duration_seconds=40)
  self.e.advance_time(20);actual=ED.context(self.e,self.a);self.assertEqual((actual['gravity'],actual['pressure']),(1,0))
  self.assertEqual(ED.derive(self.e,self.a,'skill','생존',0)['value'],-3)
  self.e.advance_time(20);self.assertEqual(ED.derive(self.e,self.a,'skill','생존',0)['value'],0)
 def test_replacement_retires_only_same_source_and_old_deadline_does_not_return_it(self):
  self.start();self.change(duration_seconds=20);self.e.advance_time(5);self.change({'gravity':3},request='replacement',duration_seconds=10)
  self.assertEqual(self.e._environment_changes['active'],['replacement']);self.e.advance_time(15)
  self.assertEqual(ED.context(self.e,self.a)['gravity'],1);self.assertEqual(self.e._environment_changes['active'],[])
 def test_ongoing_deprivation_clock_is_not_restarted_and_only_protected_injuries_recover(self):
  self.start();self.a.injuries=2;self.change({'air_available':False,'medium':'airless'},timing_policy='grace_boundary')
  self.e.advance_time(30);self.change({'gravity':2},request='gravity');self.e.advance_time(30)
  self.assertEqual(self.a.spec['_respiration']['deprivation_started_at'],0);self.assertEqual(self.a.injuries,3)
  self.change({'air_available':True,'medium':'air'},request='air');self.assertEqual(self.a.injuries,2);self.assertTrue(self.a.spec['_respiration']['breathing'])
 def test_airless_temporary_source_expires_into_actual_breathing_before_injury(self):
  self.start();self.change({'air_available':False,'medium':'airless'},duration_seconds=20,timing_policy='grace_boundary');self.e.advance_time(120)
  self.assertEqual(self.a.injuries,0);self.assertTrue(self.a.spec['_respiration']['breathing']);self.assertIsNone(self.a.spec['_respiration']['deprivation_started_at'])
 def mapped(self,*,right=True):
  base=dict(gravity=1,pressure=1,air_available=True,medium='air')
  self.e.observe_environment('left',base,cells=[[x,y] for x in range(2) for y in range(10)],source=self.policy()['source'],reason='actual left region')
  if right:self.e.observe_environment('right',dict(base,gravity=2,air_available=False,medium='airless'),cells=[[x,y] for x in range(2,20) for y in range(10)],source=self.policy()['source'],reason='actual right region')
  self.bind();self.e.observe_breathing(self.a,air_available=True,medium='air',reason='known initial atmosphere',timing_policy='grace_boundary')
 def test_actual_shift_crosses_region_with_one_cost_and_current_breathing_observation(self):
  self.mapped();self.begin(self.a);self.e.approach(self.a,self.t)
  self.assertEqual(ED.context(self.e,self.a)['region_id'],'right');self.assertFalse(self.a.spec['_respiration']['breathing']);self.assertEqual(self.a.spec['_respiration']['deprivation_started_at'],0)
  self.assertEqual(self.a.budget['shift'],0);self.assertEqual(self.a._action_history.count('shift'),1);self.assertEqual(MOVE.capabilities(self.e,self.a)['land'],self.a.movement//2)
 def test_unknown_destination_region_rolls_back_real_position_action_rng_and_observation(self):
  self.mapped(right=False);self.begin(self.a);before=self.snap();grid=self.e.grid
  with self.assertRaisesRegex(ValueError,'full body'):self.e.approach(self.a,self.t)
  self.assertEqual(self.snap(),before);self.assertIs(self.e.grid,grid)
 def test_forced_displacement_changes_actual_region_without_spending_target_movement(self):
  self.mapped();self.begin(self.a);before=deepcopy(self.a.budget);out=FORCE.displace(self.e,self.t,self.a,direction=(1,0),distance=1,source='maneuver/밀기')
  self.assertEqual(out['moved'],1);self.assertEqual(self.a.budget,before);self.assertEqual(ED.context(self.e,self.a)['region_id'],'right')
 def test_native_groundshaper_sees_staged_terrain_and_preserves_grid_aliases(self):
  self.start();self.t.pos=(2,3);self.bind(self.t);G.grant(self.a,'capabilities','지형변화','test:ground','actual owned capability');self.begin(self.a)
  grid=self.e.grid;rough=grid.rough;boundary=EC.boundary;seen=[]
  def observe(e,event='environment'):
   seen.append(ED.context(e,next(c for c in e.everyone if c.entity_id==self.t.entity_id))['rough']);return boundary(e,event)
  with patch.object(EC,'boundary',observe):self.e.shape_ground(self.a,[{'cell':[2,3],'terrain':'rough'}],reason='actual adjacent terrain')
  self.assertIn(True,seen);self.assertIs(self.e.grid,grid);self.assertIs(self.e.grid.rough,rough);self.assertIn((2,3),rough);self.assertEqual(self.a.budget['standard'],0)
 def test_late_reconciliation_failure_rolls_back_source_and_terrain_action(self):
  self.start();before=self.snap()
  with patch.object(EC,'boundary',side_effect=ValueError('late environment callback')):
   with self.assertRaisesRegex(ValueError,'late environment'):self.change()
  self.assertEqual(self.snap(),before)
  G.grant(self.a,'capabilities','지형변화','test:ground','actual owned capability');self.begin(self.a);before=self.snap();rough=self.e.grid.rough
  with patch.object(EC,'boundary',side_effect=ValueError('late terrain callback')):
   with self.assertRaisesRegex(ValueError,'late terrain'):self.e.shape_ground(self.a,[{'cell':[2,3],'terrain':'rough'}],reason='actual terrain')
  self.assertEqual(self.snap(),before);self.assertIs(self.e.grid.rough,rough);self.assertNotIn((2,3),rough)
 def test_native_weather_replacement_natural_classification_and_deadline_recalculate(self):
  self.start();self.e.gm.observe_natural_weather('rain-like clouds');self.assertEqual(ED.context(self.e,self.a)['weather'],'clear')
  self.e.gm.observe_natural_weather('actual rain',treat_as='rain',reason='mechanical equivalent');self.assertEqual(ED.derive(self.e,self.a,'skill','생존',0)['value'],1)
  self.e.gm.set_weather('sunny',rounds=1,reason='actual replacement');self.assertEqual(ED.derive(self.e,self.a,'skill','생존',0)['value'],0)
  self.e.start_round(self.e.everyone);self.e.end_round();self.assertEqual(ED.context(self.e,self.a)['weather'],'clear');self.assertEqual(self.e._weather_state['history'][-1]['end_reason'],'duration expired')
 def test_unmapped_region_transfer_uses_actual_destination_and_existing_protected_recovery(self):
  self.e.grid=None;base=dict(gravity=1,pressure=1,air_available=True,medium='air')
  self.e.observe_environment('safe',base,source=self.policy()['source'],reason='actual safe region')
  self.e.observe_environment('empty',dict(base,gravity=0,air_available=False,medium='airless'),source=self.policy()['source'],reason='actual airless region')
  self.e.bind_environment(self.a,self.policy(),region_id='safe',reason='actual initial location')
  self.e.transfer_environment(self.a,'empty',reason='actual regional relocation',timing_policy='grace_boundary');self.e.advance_time(60);self.assertEqual(self.a.injuries,1)
  self.e.transfer_environment(self.a,'safe',reason='actual return');self.assertEqual(self.a.injuries,0);self.assertEqual(ED.context(self.e,self.a)['gravity'],1)
 def test_replay_and_json_gm_restore_preserve_remaining_expiry_and_reject_tamper(self):
  self.start();out=self.change(duration_seconds=20);self.e.advance_time(5);before=self.snap()
  self.assertEqual(self.change(duration_seconds=20),out);self.assertEqual(self.snap(),before)
  with self.assertRaisesRegex(ValueError,'changed intent'):self.change(duration_seconds=21)
  self.e.gm.snapshot('environment change');e=self.restored();a=next(c for c in e.everyone if c.entity_id==self.a.entity_id)
  e.advance_time(15);self.assertEqual(ED.context(e,a)['gravity'],1)
  self.e._environment_changes['requests']['change/1']['changes']['gravity']=9
  with self.assertRaises(CODEC.StateCodecError):self.e.export_state()
  self.e.gm.restore('environment change');self.assertEqual(ED.context(self.e,self.a)['gravity'],2);self.e.advance_time(15);self.assertEqual(ED.context(self.e,self.a)['gravity'],1)

if __name__=='__main__':unittest.main()

