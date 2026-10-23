"""Native Wallrunner surface approach, jump, falling and shared movement owners."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json,unittest
from engine import Rules,Engine,Combatant
from grid import Grid
import wallrunner as W,movement_actions as M,jump_actions as J
import acquisition_qualification as Q,acquired_features as A,state_grants as G,state_codec as CODEC
import common_checks as C,turn as TURN,environmental_effects as ENV,skill_feature_actions as SF

ROOT=Path(__file__).resolve().parents[1]

class WallrunnerTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='core')
 def setUp(self):
  self.e=Engine(self.r,seed=93);self.e.grid=Grid(25,12)
  self.a=Combatant(self.r,{'id':'trainer/wall','name':'wall','kind':'trainer','size':'medium','level':20,'weight_class':3,
   'stats':dict.fromkeys(['hp','atk','def','spa','spd','spe'],10),'skills':{'곡예':5,'육상':4,'통찰':4},
   'movement_basis':'trainer_base','movement':{'power':6},'edges':[]})
  self.a.pos=(1,1);self.e.everyone=self.e.gm.everyone=[self.a]
 def own(self):return G.transition(self.e,self.a,lambda e,c:c.spec['edges'].append(W.SOURCE))
 def turn(self):self.e.start_round([self.a]);self.e.start_of_turn(self.a)
 def snap(self):return CODEC.dump_engine(self.e)
 def vertical(self,height=5):
  return {'path':[{'position':[1,1],'altitude':z} for z in range(height+1)],'vertical_surface':True,'reason':'GM observed a continuous actual vertical wall and all body clearances'}
 def horizontal(self,distance=5):
  return {'path':[{'position':[1+x,1],'altitude':0} for x in range(distance+1)],'vertical_surface':True,'reason':'GM observed continuous horizontal route along a vertical wall'}
 def jump(self,wall=None,destination=(3,1),**kw):
  opts=dict(jump_id='wall-jump',difficult=False,clear_path=True,reason_text='actual clear wall departure and landing',landing_altitude=5,wall_run=self.vertical() if wall is None else wall)
  opts.update(kw);return self.e.jump(self.a,destination,**opts)
 def test_vertical_rank_limit_launches_from_actual_wall_end_and_one_shift(self):
  self.own();self.turn();before=self.e.rng.getstate()
  with patch.object(A,'owned_rule_count',wraps=A.owned_rule_count) as own,patch.object(Q,'require',wraps=Q.require) as qualified,patch.object(M,'_travel_geometry',wraps=M._travel_geometry) as geometry:
   result=self.jump()
  self.assertTrue(result['landed']);self.assertEqual((self.a.pos,self.a.spec['_movement_altitude']),((3,1),5))
  self.assertEqual((result['wall_run']['distance'],result['wall_run']['maximum'],result['requested']['long_jump']),(5,5,2))
  self.assertGreater(own.call_count,0);self.assertGreater(qualified.call_count,0);self.assertGreaterEqual(geometry.call_count,6)
  self.assertEqual(self.a.budget,{'standard':1,'shift':0,'swift':1});self.assertEqual(before,self.e.rng.getstate())
 def test_horizontal_wall_run_uses_launch_point_for_long_jump_not_original_cell(self):
  self.own();self.turn();out=self.jump(self.horizontal(),(8,1),landing_altitude=0)
  self.assertEqual(self.a.pos,(8,1));self.assertEqual(out['requested']['long_jump'],2);self.assertEqual(out['wall_run']['distance'],5)
 def test_mixed_vertical_horizontal_path_uses_explicit_existing_measurement(self):
  self.own();wall=self.vertical(1);wall['path'][1]={'position':[2,1],'altitude':1,'gm_distance':2}
  wall['path'].append({'position':[2,1],'altitude':2})
  out=self.jump(wall,(4,1),landing_altitude=2);self.assertEqual(out['wall_run']['distance'],3)
 def test_diagonal_path_keeps_turn_parity_in_common_step_cost(self):
  self.own();wall=self.horizontal(2);wall['path']=[{'position':[1+i,1+i],'altitude':0} for i in range(3)]
  self.a._diagonal_steps=1
  out=self.jump(wall,(5,3),landing_altitude=0)
  self.assertEqual((out['wall_run']['distance'],self.a._diagonal_steps),(3,3))
 def test_path_beyond_rank_and_jump_beyond_own_capability_are_atomic(self):
  self.own();self.turn();before=self.snap()
  with self.assertRaises(ValueError):self.jump(self.vertical(6),landing_altitude=6)
  self.assertEqual(self.snap(),before)
  with self.assertRaises(ValueError):self.jump(destination=(4,1))
  self.assertEqual(self.snap(),before)
 def test_missing_actual_vertical_surface_is_pending_without_cost(self):
  self.own();self.turn();wall=self.vertical();wall['vertical_surface']=None;before=self.snap()
  self.assertIsInstance(self.jump(wall),C.PendingDecision);self.assertEqual(self.snap(),before)
 def test_unowned_or_novice_wall_run_does_not_move_or_pay(self):
  self.turn();before=self.snap()
  with self.assertRaises(ValueError):self.jump()
  self.assertEqual(self.snap(),before)
  self.e.gm.set_skill(self.a,'곡예',4,reason='ordinary Adept')
  before=self.snap()
  with self.assertRaisesRegex(ValueError,'Expert Acrobatics'):self.own()
  self.assertEqual(self.snap(),before)
 def test_invalid_origin_discontinuous_path_and_mixed_unmeasured_step_are_atomic(self):
  self.own();self.turn()
  for path in [
   [{'position':[2,1],'altitude':0},{'position':[2,1],'altitude':1}],
   [{'position':[1,1],'altitude':0},{'position':[1,1],'altitude':2}],
   [{'position':[1,1],'altitude':0},{'position':[3,1],'altitude':0}],
   [{'position':[1,1],'altitude':0},{'position':[2,1],'altitude':1}]]:
   wall=self.vertical();wall['path']=path;before=self.snap()
   with self.assertRaises(ValueError):self.jump(wall)
   self.assertEqual(self.snap(),before)
 def test_body_and_wall_blocking_are_checked_before_cost(self):
  self.own();self.turn();self.e.grid.blocking.add((3,1));before=self.snap()
  with self.assertRaises(ValueError):self.jump()
  self.assertEqual(self.snap(),before)
  self.e.grid.blocking.clear();self.e.grid.walls.add(tuple(sorted(((1,1),(2,1)))));wall=self.horizontal(2);before=self.snap()
  with self.assertRaises(ValueError):self.jump(wall,(5,1),landing_altitude=0)
  self.assertEqual(self.snap(),before)
 def test_actual_same_altitude_body_occupancy_blocks_wall_path(self):
  self.own();self.turn()
  b=Combatant(self.r,dict(id='blocker',name='blocker',kind='trainer',size='medium',level=20,stats=dict.fromkeys(['hp','atk','def','spa','spd','spe'],10)))
  b.pos=(1,1);b.spec['_movement_altitude']=3;self.e.everyone.append(b)
  before=self.snap()
  with self.assertRaises(ValueError):self.jump()
  self.assertEqual(self.snap(),before)
 def test_opportunity_interrupt_keeps_shift_and_stops_before_wall_travel_or_jump_roll(self):
  self.own();self.turn();calls=[]
  def stop(e,c,destination,altitude):calls.append((c.pos,altitude));c.hp=0;return False
  with patch.object(M,'departure',side_effect=stop),patch.object(self.e,'skill_roll',wraps=self.e.skill_roll) as rolled:
   self.assertFalse(self.jump(difficult=True,difficulty_skill='곡예',difficulty_dc=5,difficulty_options={'fixed':[6]*5}))
  self.assertEqual(calls,[((1,1),1)]);self.assertEqual(self.a.pos,(1,1));self.assertEqual(self.a.budget['shift'],0)
  self.assertEqual(rolled.call_count,0);self.assertEqual(self.a.spec['_jump_attempts']['wall-jump']['failed'],'wall_run_interrupted')
 def test_failed_jump_retains_actual_wall_origin_and_same_common_gm_consequence(self):
  self.own();self.turn()
  out=self.jump(difficult=True,difficulty_skill='곡예',difficulty_dc=99,difficulty_options={'fixed':[1]*5})
  self.assertIsInstance(out,C.PendingDecision);self.assertEqual((self.a.pos,self.a.spec['_movement_altitude']),((1,1),5))
  self.assertEqual(self.a.budget['shift'],0);self.assertIn('_jump_pending',self.a.spec)
  with self.assertRaises(ValueError):J.resolve_failure(self.e,self.a,decision='invented',reason_text='GM')
  J.resolve_failure(self.e,self.a,decision='land',reason_text='GM established actual landing')
  self.assertEqual(self.a.pos,(3,1))
 def test_late_unobserved_roll_error_rolls_back_actual_wall_and_cost(self):
  self.own();self.turn();before=self.snap()
  with patch.object(J.COMMON,'_staged_rolls',side_effect=ValueError('late calculation')):
   with self.assertRaisesRegex(ValueError,'late calculation'):self.jump(difficult=True,difficulty_skill='곡예',difficulty_dc=9,difficulty_options={'fixed':[3]*5})
  self.assertEqual(self.snap(),before)
 def test_lower_landing_uses_actual_common_fall_height_once(self):
  self.own();self.turn()
  with patch.object(ENV,'fall',wraps=ENV.fall) as fall:out=self.jump(destination=(3,1),landing_altitude=0,gm_distance=7,fall_options={})
  self.assertEqual((self.a.pos,self.a.spec['_movement_altitude']),((3,1),0));self.assertEqual(fall.call_count,1)
  self.assertEqual((out['falling']['meters'],out['falling']['base_high_jump'],out['falling']['same_jump_id']),(5,1,'wall-jump'))
  self.assertEqual(len(self.a.spec['_fall_events']),1);self.assertEqual(self.a.budget['shift'],0)
  with self.assertRaises(ValueError):self.jump(landing_altitude=0,gm_distance=7,fall_options={})
 def test_lower_landing_without_observed_fall_parameters_is_pending_before_cost(self):
  self.own();self.turn();before=self.snap()
  self.assertIsInstance(self.jump(landing_altitude=0,gm_distance=7),C.PendingDecision);self.assertEqual(self.snap(),before)
 def test_fall_cannot_override_actual_jump_identity_height_or_double_boost(self):
  self.own();self.turn()
  for options in ({'meters':0},{'intentional':False},{'high_jump_boost':True}):
   before=self.snap()
   with self.assertRaises(ValueError):self.jump(landing_altitude=0,gm_distance=7,fall_options=options)
   self.assertEqual(self.snap(),before)
 def test_same_actual_jump_boost_reaches_fall_allowance_without_second_boost_roll(self):
  self.own();self.turn()
  out=self.jump(self.vertical(2),landing_altitude=0,apex_height=2,boost='high_jump',boost_options={'fixed':[4]*5},gm_distance=4,fall_options={})
  self.assertTrue(out['checks']['boost'].passed);self.assertEqual(out['falling']['meters'],4)
  self.assertEqual(out['falling']['high_jump'],2);self.assertEqual(out['falling']['checks'],{})
 def test_effective_rank_extends_wall_distance_but_ordinary_prerequisite_remains(self):
  self.e.gm.set_skill(self.a,'곡예',6,reason='Master ordinary Acrobatics');self.own()
  G.transition(self.e,self.a,lambda e,c:(c.spec['edges'].append('거장'),c.spec.__setitem__('edge_choices',{'거장':['곡예']})))
  out=self.jump(self.vertical(8),landing_altitude=8)
  self.assertEqual((out['wall_run']['maximum'],out['wall_run']['distance']),(8,8))
 def test_owned_skill_loss_and_duplicate_acquisition_are_atomic(self):
  self.own();before=self.snap()
  with self.assertRaisesRegex(ValueError,'Expert Acrobatics'):self.e.gm.set_skill(self.a,'곡예',4,reason='actual skill correction')
  self.assertEqual(self.snap(),before)
  with self.assertRaises(ValueError):self.own()
  self.assertEqual(self.snap(),before)
 def test_json_and_gm_restore_keep_acquired_source_and_jump_history_once(self):
  self.own();self.turn();saved=self.e.gm.snapshot();out=self.jump();original=self.snap()
  loaded=CODEC.load_engine(self.r,json.loads(json.dumps(original)))
  actor=next(a for a in loaded.everyone if a.entity_id==self.a.entity_id)
  self.assertTrue(W.validate(actor));self.assertEqual(actor.spec['_jump_attempts']['wall-jump']['wall_run']['distance'],5)
  with self.assertRaises(ValueError):loaded.jump(actor,(3,1),jump_id='wall-jump',difficult=False,clear_path=True,reason_text='cannot replay')
  self.e.gm.restore(saved);self.assertEqual(self.a.pos,(1,1));self.assertNotIn('_jump_attempts',self.a.spec)
 def test_selected_and_duplicate_source_changes_refuse_without_motion(self):
  self.own();self.turn();before=self.snap();selected=self.r._selected_rule
  with patch.object(self.r,'_selected_rule',side_effect=lambda uid,**kw:uid+'/other' if uid==W.SOURCE else selected(uid,**kw)):
   with self.assertRaises(ValueError):self.jump()
  self.assertEqual(self.snap(),before)
  raw=Path.read_bytes
  def changed(path,*a,**kw):return raw(path,*a,**kw)+(b'changed' if path.resolve()==(ROOT/'input/db/edges.csv').resolve() else b'')
  with patch.object(Path,'read_bytes',changed):
   with self.assertRaises(ValueError):self.jump()
  self.assertEqual(self.snap(),before)
 def test_observed_feature_error_resumes_from_same_wall_origin_and_one_shift(self):
  self.own();G.transition(self.e,self.a,lambda e,c:c.spec.setdefault('feats',[]).append(SF.MONKEY));self.turn()
  options=dict(difficult=True,difficulty_skill='곡예',difficulty_dc=5,difficulty_options={'roll_id':'wall-skill','fixed':[1]*5,'feature':SF.MONKEY,'feature_options':{'decision':lambda first:'bad'}})
  with self.assertRaises(ValueError):self.jump(**options)
  self.assertEqual((self.a.pos,self.a.spec['_movement_altitude'],self.a.budget['shift']),((1,1),5,0))
  first=SF.event(self.e,self.a,'wall-skill').first
  loaded=CODEC.load_engine(self.r,json.loads(json.dumps(self.snap())))
  self.e=loaded;self.a=next(a for a in loaded.everyone if a.entity_id=='trainer/wall')
  options['difficulty_options']['feature_options']={'decision':lambda first:False}
  out=self.jump(**options);self.assertTrue(out['landed'])
  self.assertEqual(SF.event(self.e,self.a,'wall-skill').first,first);self.assertEqual(self.a.budget['standard'],1)
  self.assertEqual(self.a._action_history.count('shift'),1)
 def test_observed_falling_feature_error_resumes_same_landed_jump_and_fall(self):
  self.own();G.transition(self.e,self.a,lambda e,c:c.spec.setdefault('feats',[]).append(SF.MONKEY));self.turn()
  options={'acrobatics':True,'acrobatics_injury_policy':'distance','acrobatics_options':{'roll_id':'wall-fall-skill','fixed':[1]*5,'feature':SF.MONKEY,'feature_options':{'decision':lambda first:'bad'}}}
  with self.assertRaises(ValueError):self.jump(landing_altitude=0,gm_distance=7,fall_options=options)
  self.assertEqual((self.a.pos,self.a.spec['_movement_altitude'],self.a.budget['shift']),((3,1),0,0))
  first=SF.event(self.e,self.a,'wall-fall-skill').first;self.assertTrue(self.a.spec['_jump_attempts']['wall-jump']['fall_pending'])
  options['acrobatics_options']['feature_options']={'decision':lambda first:True,'reroll_faces':[3]*5}
  out=self.jump(landing_altitude=0,gm_distance=7,fall_options=options)
  self.assertEqual(SF.event(self.e,self.a,'wall-fall-skill').first,first)
  self.assertEqual(out['falling']['checks']['falling_acrobatics'].dc,12)
  self.assertTrue(out['falling']['checks']['falling_acrobatics'].passed)
  self.assertEqual(len(self.a.spec['_fall_events']),1);self.assertEqual(self.a._action_history.count('shift'),1)
 def test_completed_observed_jump_survives_later_unobserved_fall_input_error(self):
  self.own();G.transition(self.e,self.a,lambda e,c:c.spec.setdefault('feats',[]).append(SF.MONKEY));self.turn()
  options=dict(landing_altitude=0,gm_distance=7,boost='high_jump',boost_options={'roll_id':'wall-complete-boost','fixed':[4]*5,'feature':SF.MONKEY,'feature_options':{'decision':lambda first:False}},fall_options={'acrobatics':True,'acrobatics_injury_policy':'distance','acrobatics_options':{'fixed':[1]}})
  with self.assertRaises(ValueError):self.jump(**options)
  self.assertEqual((self.a.pos,self.a.spec['_movement_altitude'],self.a.budget['shift']),((3,1),0,0))
  first=SF.event(self.e,self.a,'wall-complete-boost').first
  self.assertTrue(self.a.spec['_jump_attempts']['wall-jump']['fall_pending'])
  options['fall_options']['acrobatics_options']={'fixed':[4]*5}
  out=self.jump(**options);self.assertTrue(out['landed'])
  self.assertEqual(SF.event(self.e,self.a,'wall-complete-boost').first,first)
  self.assertEqual(len(self.a.spec['_fall_events']),1);self.assertEqual(self.a._action_history.count('shift'),1)
 def test_literal_csv_duplicate_remains_same_source_not_second_distance(self):
  self.own();value=W.policy(self.r);out=self.jump()
  self.assertEqual((value['minimum_rank'],value['csv_duplicate']),(5,'C2CSV/input/db/edges.csv:R67:main'))
  self.assertEqual(out['wall_run']['maximum'],5)

if __name__=='__main__':unittest.main()

