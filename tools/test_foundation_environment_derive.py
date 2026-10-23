"""Observable environmental facts, composition, native rolls and breathing."""
from pathlib import Path
from copy import copy,deepcopy
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_body_modes as _fixture_test_category2_body_modes
import environment_derive as ED,movement_actions as MOVE,state_grants as G,state_codec as CODEC
import weather_state as WEATHER

class EnvironmentTests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_body_modes.Tests.setUpClass.__func__)
 add=_fixture_test_category2_body_modes.Tests.add;pokemon=_fixture_test_category2_body_modes.Tests.pokemon;restored=_fixture_test_category2_body_modes.Tests.restored;begin=_fixture_test_category2_body_modes.Tests.begin
 def setUp(self):_fixture_test_category2_body_modes.Tests.setUp(self)
 def policy(self):return json.loads((ROOT/'data/examples/environment-derive.json').read_text(encoding='utf8'))
 def region(self,**changes):
  facts=dict(gravity=2,pressure=1,air_available=True,medium='air');facts.update(changes)
  return self.e.observe_environment('region',facts,source=self.policy()['source'],reason='actual measured region')
 def bind(self,c=None,value=None):return self.e.bind_environment(c or self.a,value or self.policy(),reason='actual actor home gravity and selected environmental declaration')
 def snap(self):return CODEC.dump_engine(self.e)
 def test_native_skill_and_movement_use_live_exact_composition_without_mutating_base(self):
  before=self.e.skill_roll(self.a,'생존',fixed=[3]*4).total;base=MOVE.capabilities(self.e,self.a)['land'];self.region();self.bind()
  self.assertEqual(self.e.skill_roll(self.a,'생존',fixed=[3]*4).total,before-2)
  self.assertEqual(MOVE.capabilities(self.e,self.a)['land'],base//2);self.assertEqual(self.a.movement,base)
  self.assertEqual(ED.derive(self.e,self.a,'movement','land',5)['value'],2)
 def test_actual_gravity_tolerance_exempts_only_declared_skill_evasion_penalties(self):
  self.region(pressure=0);self.bind();G.grant(self.a,'capabilities','GravityTolerance','test:gravity','actual sourced capability')
  self.assertEqual(ED.derive(self.e,self.a,'skill','생존',0)['value'],-3)
  self.assertEqual(ED.derive(self.e,self.a,'evasion','물리',4)['value'],4)
  self.assertEqual(ED.derive(self.e,self.a,'movement','land',6)['value'],3)
  G.revoke(self.a,'test:gravity');self.assertEqual(ED.derive(self.e,self.a,'skill','생존',0)['value'],-5)
 def test_native_accuracy_receives_evasion_penalty(self):
  self.region();self.bind(self.t);move=self.r.move('move/물대포');face=move['ac']+self.t.evasion('특수')-1
  self.assertTrue(self.e.accuracy_check(self.a,self.t,move,fixed_roll=face)[0])
  G.grant(self.t,'capabilities','GravityTolerance','test:gravity','actual sourced capability')
  self.assertFalse(self.e.accuracy_check(self.a,self.t,move,fixed_roll=face)[0])
 def test_unknown_required_fact_rejects_before_rng_and_actual_move_cost(self):
  self.region(gravity=None);self.bind();WEATHER.state(self.e);before=self.snap()
  with self.assertRaisesRegex(ValueError,'unknown'):self.e.skill_roll(self.a,'생존')
  self.assertEqual(self.snap(),before)
  self.bind(self.t);self.t.pos=(2,3);self.begin(self.a);self.e.gm.set_move(self.a,'move/물대포',reason='actual learned move');before=self.snap()
  with self.assertRaisesRegex(ValueError,'unknown'):self.e.use_move(self.a,self.t,'move/물대포')
  self.assertEqual(self.snap(),before)
 def test_actual_home_gravity_weather_and_grid_terrain_are_independent_inputs(self):
  self.region(gravity=2);value=self.policy();value['home_gravity']=2;self.bind(value=value)
  self.assertEqual(ED.context(self.e,self.a)['relative_gravity'],1)
  self.assertEqual(ED.derive(self.e,self.a,'skill','생존',0)['value'],0)
  WEATHER.observe_natural(self.e,description='clouds resembling rain',treat_as=None,reason='appearance only')
  self.assertEqual(ED.derive(self.e,self.a,'skill','생존',0)['value'],0)
  WEATHER.observe_natural(self.e,description='actual rain',treat_as='rain',reason='explicit mechanical equivalent')
  self.e.grid.rough.add(self.a.pos)
  self.assertEqual(ED.derive(self.e,self.a,'skill','생존',0)['value'],2)
 def test_actual_full_body_requires_one_observed_region(self):
  self.e.observe_environment('small',dict(gravity=2,pressure=1,air_available=True,medium='air'),cells=[[1,3]],source=self.policy()['source'],reason='one actual cell')
  self.a.spec['size']='Large';self.bind()
  with self.assertRaisesRegex(ValueError,'full body'):ED.context(self.e,self.a)
 def test_airless_zero_gravity_does_not_confer_breathing_or_weather_immunity(self):
  self.region(gravity=0,pressure=0,air_available=False,medium='airless');self.bind()
  self.assertTrue(ED.context(self.e,self.a)['zero_gravity']);G.grant(self.a,'capabilities','GravityTolerance','test:gravity','actual sourced capability')
  with self.assertRaisesRegex(ValueError,'actual current region'):self.e.observe_breathing(self.a,air_available=True,medium='air',reason='incorrect weather inference')
  self.e.observe_breathing(self.a,air_available=False,medium='airless',reason='actual current region',timing_policy='grace_boundary')
  self.e.advance_time(60);self.assertEqual(self.a.injuries,1)
 def test_gilled_is_limited_to_actual_water_and_protected_suffocation_owner_is_reused(self):
  self.region(air_available=False,medium='water');self.bind();G.grant(self.a,'capabilities','Gilled','test:gills','actual sourced capability')
  self.e.observe_breathing(self.a,air_available=False,medium='water',reason='actual immersion');self.e.advance_time(120);self.assertEqual(self.a.injuries,0)
  G.revoke(self.a,'test:gills');before=self.e.elapsed_seconds
  with self.assertRaises(ValueError):self.e.advance_time(1)
  self.assertEqual(self.e.elapsed_seconds,before)
 def test_declaration_cannot_mislabel_pressure_as_gravity_or_expand_immunity(self):
  for mutate in (lambda v:v['rules'][3].update(family='gravity'),lambda v:v['rules'][2].update(exemption='gravity_tolerance')):
   value=self.policy();mutate(value)
   with self.assertRaises(ValueError):ED.declaration(value)
 def test_registered_actor_and_source_baseline_required_and_json_gm_preserve_current_inputs(self):
  self.region();self.bind();self.e.gm.snapshot('environment');e=self.restored();a=next(c for c in e.everyone if c.entity_id==self.a.entity_id)
  self.assertEqual(ED.context(e,a),ED.context(self.e,self.a));self.assertEqual(MOVE.capabilities(e,a),MOVE.capabilities(self.e,self.a))
  with self.assertRaises(ValueError):ED.context(self.e,copy(self.a))
  self.e._environment_derive['actors'][self.a.entity_id]['declaration']['home_gravity']=9
  with self.assertRaises(CODEC.StateCodecError):self.e.export_state()
  self.e.gm.restore('environment');self.assertEqual(ED.context(self.e,self.a)['home_gravity'],1)
 def test_gm_movement_observation_still_uses_environment_on_registered_actor(self):
  self.region();self.bind();result=self.e.gm.set_movement_capabilities(self.a,{'land':8},basis='current',reason='actual updated land value')
  self.assertEqual(result['land'],4);self.assertEqual(self.a.movement,8)

if __name__=='__main__':unittest.main()

