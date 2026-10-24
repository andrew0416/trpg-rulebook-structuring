"""Native highest-capability retreat through the actual shared paid path."""
import json
from pathlib import Path
from unittest.mock import patch
import unittest
from engine import Rules
import test_category2_breather as VOLUNTARY
import breather as B,common_checks as C,condition_recovery as RECOVERY
import effects_ext as EXT,movement_actions as M,state_codec as CODEC
import state_grants as G,stamina as STAMINA,temporary_hp as TEMP

ROOT=Path(__file__).resolve().parents[1]

class NonlandBreatherTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='core')
 def setUp(self):
  VOLUNTARY.BreatherTests.setUp(self)
  G.transition(self.e,self.a,lambda e,c:c.spec['edges'].append(STAMINA.SOURCE))
  TEMP.grant(self.e,self.a,12)
 def movement(self,**values):
  return self.e.gm.set_movement_capabilities(self.a,dict(land=4,**values),basis='current',
      reason='GM observes actual current movement capabilities')
 def options(self,**changes):return VOLUNTARY.BreatherTests.options(self,**changes)
 def take(self,**changes):return self.e.take_breather(self.a,**self.options(**changes))
 def air(self,*nodes):
  return [{'position':position,'altitude':altitude,**({} if distance is None else {'gm_distance':distance})}
          for position,altitude,distance in nodes]
 def test_sky_actual_3d_route_has_one_full_and_only_surface_entry_effects(self):
  self.movement(sky=5);self.e.apply_status(self.a,'혼란')
  path=self.air(((2,2),0,None),((3,2),0,None),((3,2),1,None),
                ((4,2),1,None),((5,2),0,1),((6,2),0,None))
  entered=[];original=EXT.on_enter_cell
  with patch.object(M,'follow_paid_path',wraps=M.follow_paid_path) as follow,patch.object(EXT,'on_enter_cell',side_effect=lambda e,c,p,**kw:(entered.append((p,c.spec.get('_movement_altitude',0),c.temp_hp)),original(e,c,p,**kw))[-1]):
   result=self.take(path=path,movement_mode='sky')
  self.assertTrue(result['completed']);self.assertEqual(result['movement']['distance'],5)
  self.assertEqual((self.a.pos,self.a.spec['_movement_altitude'],self.a.airborne),((6,2),0,False))
  self.assertEqual(entered,[((3,2),0,12),((5,2),0,12),((6,2),0,12)])
  self.assertEqual((self.a.temp_hp,follow.call_count,self.a._action_history.count('full')),(5,1,1))
  self.assertEqual(self.a.budget,{'standard':0,'shift':0,'swift':1});self.assertNotIn('혼란',self.a.conditions)
  before=CODEC.dump_engine(self.e);self.assertEqual(self.take(path=path,movement_mode='sky'),result)
  self.assertEqual(CODEC.dump_engine(self.e),before)
  with self.assertRaisesRegex(ValueError,'declaration'):self.take(path=path,movement_mode='levitate')
 def test_swim_uses_slowed_highest_capability_and_existing_terrain_policy(self):
  self.movement(swim=6);self.e.apply_status(self.a,'둔화')
  self.e.grid.slow.update({(3,2),(4,2),(5,2)})
  result=self.take(path=[(2,2),(3,2)],movement_mode='swim')
  self.assertTrue(result['completed'])
  self.assertEqual((result['movement']['distance'],result['movement']['mode'],self.a.pos),(2,'수중',(3,2)))
  self.assertEqual((self.a.temp_hp,self.a._action_history.count('full')),(5,1));self.assertNotIn('둔화',self.a.conditions)
 def test_levitate_height_and_unmeasured_mixed_route_fail_before_cost_or_save(self):
  self.movement(levitate=6);before=CODEC.dump_engine(self.e)
  invalid=[
   self.air(((2,2),0,None),((2,2),1,None),((2,2),2,None),((2,2),3,None),((2,2),4,None)),
   self.air(((2,2),0,None),((3,2),1,None))]
  for path in invalid:
   with self.subTest(path=path):
    with self.assertRaises(ValueError):self.take(path=path,movement_mode='levitate')
    self.assertEqual(CODEC.dump_engine(self.e),before)
  path=self.air(((2,2),0,None),((2,2),1,None),((2,2),2,None),((2,2),3,None))
  result=self.take(path=path,movement_mode='levitate')
  self.assertTrue(result['completed']);self.assertEqual(result['movement']['altitude'],3);self.assertTrue(self.a.airborne)
 def test_actual_higher_mode_is_required_and_unmapped_modes_do_not_fall_back_to_walking(self):
  self.movement(sky=6,teleport=8);before=CODEC.dump_engine(self.e)
  for mode in (None,'land','sky'):
   with self.subTest(mode=mode):
    self.assertIsInstance(self.take(movement_mode=mode),C.PendingDecision)
    self.assertEqual(CODEC.dump_engine(self.e),before)
  # Teleport now has a native transfer producer; missing surface observation
  # is pending, while a multi-cell walking route is an invalid transfer.
  self.assertIsInstance(self.take(movement_mode='teleport',path=[(2,2),(6,2)]),C.PendingDecision)
  self.assertEqual(CODEC.dump_engine(self.e),before)
  with self.assertRaisesRegex(ValueError,'one actual origin and destination'):self.take(movement_mode='teleport')
  self.assertEqual(CODEC.dump_engine(self.e),before)
  with self.assertRaisesRegex(ValueError,'unknown'):self.take(movement_mode='invented')
  self.assertEqual(CODEC.dump_engine(self.e),before)
 def test_interrupted_aerial_prefix_survives_json_restore_without_full_save_or_previous_legs(self):
  self.movement(sky=5)
  path=self.air(((2,2),0,None),((2,2),1,None),((3,2),1,None),
                ((4,2),1,None),((5,2),1,None),((6,2),1,None))
  options=self.options(path=path,movement_mode='sky');departure=M.departure
  def obstruct(e,c,q,altitude):
   permitted=departure(e,c,q,altitude)
   if c.entity_id==self.a.entity_id and c.pos==(3,2):e.grid.blocking.add((4,2))
   return permitted
  with patch.object(M,'departure',side_effect=obstruct):
   with self.assertRaisesRegex(ValueError,'interrupted'):self.e.take_breather(self.a,**options)
  self.assertEqual((self.a.pos,self.a.spec['_movement_altitude'],self.a.temp_hp),((3,2),1,12))
  restored=CODEC.load_engine(self.r,json.loads(json.dumps(CODEC.dump_engine(self.e))))
  current=next(c for c in restored.everyone if c.entity_id==self.a.entity_id);restored.grid.blocking.remove((4,2))
  departed=[];departure=M.departure
  def observe(e,c,q,altitude):
   departed.append((c.pos,c.spec['_movement_altitude'],q,altitude));return departure(e,c,q,altitude)
  with patch.object(RECOVERY,'saving_check',side_effect=AssertionError('actual save cannot replay')),patch.object(M,'departure',side_effect=observe):
   result=restored.take_breather(current,**options)
  self.assertTrue(result['completed']);self.assertEqual(result['movement']['distance'],5)
  self.assertEqual([row[0] for row in departed],[(3,2),(4,2),(5,2)])
  self.assertEqual((current.temp_hp,current._action_history.count('full'),current.spec['_movement_altitude']),(5,1,1))
  self.assertEqual(restored.take_breather(current,**options),result)
 def test_vertical_departure_uses_actual_opportunity_attack_before_recovery(self):
  self.movement(sky=5);self.b.aoo_used=False
  path=self.air(((2,2),0,None),((2,2),1,None),((2,2),2,None),((3,2),2,None))
  with patch.object(self.e,'use_move',wraps=self.e.use_move) as attack:
   result=self.take(path=path,movement_mode='sky')
  self.assertTrue(result['completed']);self.assertEqual(attack.call_count,1)
  self.assertTrue(self.b.aoo_used);self.assertEqual((self.a.temp_hp,self.a.spec['_movement_altitude']),(5,2))
 def test_aerial_diagonals_preserve_the_actual_clock_and_do_not_reset_each_leg(self):
  self.movement(sky=5)
  path=self.air(((2,2),0,None),((2,2),1,None),((3,3),1,None),((4,4),1,None),((5,4),1,None))
  result=self.take(path=path,movement_mode='sky')
  self.assertTrue(result['completed']);self.assertEqual(result['movement']['distance'],5)
  self.assertEqual((self.a.pos,self.a._diagonal_steps,self.a.spec['_movement_altitude']),((5,4),2,1))
 def test_native_aerial_entry_reuses_paid_path_and_keeps_actual_shift_cost(self):
  self.movement(sky=6)
  with patch.object(M,'follow_paid_path',wraps=M.follow_paid_path) as follow:
   result=self.e.aerial_move(self.a,(4,2),mode='sky',altitude=1,gm_distance=3,reason_text='actual observed aerial destination')
  self.assertEqual((result['distance'],result['altitude'],follow.call_count),(3,1,1))
  self.assertEqual((self.a.budget['standard'],self.a.budget['shift'],self.a.temp_hp),(1,0,12))
 def test_unmeasured_curse_3d_distance_holds_without_planar_cure_or_cost(self):
  self.movement(sky=6);self.e.apply_status(self.a,'저주',source='move/저주',applied_by=self.b)
  path=self.air(((2,2),0,None),((2,2),1,None));before=CODEC.dump_engine(self.e)
  self.assertIsInstance(self.take(path=path,movement_mode='sky'),C.PendingDecision)
  self.assertEqual(CODEC.dump_engine(self.e),before)

if __name__=='__main__':unittest.main()
