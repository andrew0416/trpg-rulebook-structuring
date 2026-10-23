"""Actual breach producers, patch/structure distinction and native repair costs."""
from pathlib import Path
from copy import copy,deepcopy
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_foundation_repair_restore as _fixture_test_foundation_repair_restore
from state_codec import dump_engine,load_engine,StateCodecError
import repair_breach as B,special_entities as S,world_entities as W,control_remote as REMOTE

class BreachTests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_foundation_repair_restore.RepairTests.setUpClass.__func__)
 trainer=_fixture_test_foundation_repair_restore.RepairTests.trainer
 bot=_fixture_test_foundation_repair_restore.RepairTests.bot
 vehicle=_fixture_test_foundation_repair_restore.RepairTests.vehicle
 def setUp(self):
  _fixture_test_foundation_repair_restore.RepairTests.setUp(self);row=self.vehicle();row.update(hp=60,breaches=0,patched_breaches=0,location={'kind':'grid','cell':[2,1]});self.a.pos=(2,1);S.observe(self.e,row,reason='actual undamaged occupied vehicle');self.car=self.e._physical_objects['vehicle']
 def policy(self,index=0):return json.loads((ROOT/'data/examples/repair-breach.json').read_text(encoding='utf8'))[index]
 def snap(self):return dump_engine(self.e)
 def damage(self,amount=16,value=None,event='damage/1'):
  return self.e.damage_vehicle(self.a,'vehicle',amount,value or self.policy(),event_id=event,reason='actual resolved incoming vehicle HP damage')
 def repair_hp(self,cost=8):return self.e.repair_vehicle(self.a,'vehicle',cost=cost,seconds=60,request_id='hp/'+str(self.e.elapsed_seconds),accessible=True,reason='actual repair period')
 def emergency(self,request='emergency/1'):
  return self.e.emergency_repair_vehicle(self.a,'vehicle',source='feat/긴급-수리',request_id=request,reason='actual emergency repair',roll_options={'fixed':[6]*4})
 def turn(self):
  self.a.spec['feats']=['feat/긴급-수리'];self.e.begin_encounter([self.a]);self.e.start_round([self.a]);self.e.start_of_turn(self.a)
 def test_actual_exact_quarter_crossing_and_large_single_hit_are_separate(self):
  out=self.damage(15);self.assertEqual((self.car['hp'],self.car['breaches']),(45,1));self.assertEqual(out['marker_interval'],[1,1]);self.assertEqual(self.car['max_hp'],60);self.assertNotIn('injuries',self.car)
  self.setUp();out=self.damage(30);self.assertEqual((out['marker_breaches'],out['single_hit_breaches'],out['created']),(2,1,3));self.assertEqual((self.car['hp'],self.car['breaches']),(30,3));self.assertFalse(out['state']['occupants_protected']);self.assertEqual(out['exposure']['exposed_passenger_ids'],[self.a.entity_id]);self.assertEqual(self.a.hp,50)
 def test_fractional_marker_uses_exact_ratio_and_boundary_is_not_rounded_to_integer_hp(self):
  self.car['hp']=self.car['max_hp']=58;out=self.damage(14);self.assertEqual(out['created'],0);out=self.damage(1,event='damage/2');self.assertEqual(out['marker_interval'],[1,1]);self.assertEqual((self.car['hp'],self.car['breaches']),(43,1))
 def test_repeat_and_once_policies_survive_actual_hp_repair_and_recross(self):
  for index,expected in [(0,2),(1,1)]:
   self.setUp();value=self.policy(index);self.damage(value=value);self.repair_hp();self.assertEqual(self.car['hp'],60);out=self.damage(value=value,event='damage/2');self.assertEqual(self.car['breaches'],expected);self.assertEqual(out['marker_breaches'],expected-1)
 def test_authored_fifth_markers_and_max_combination_use_same_actual_event(self):
  out=self.damage(30,value=self.policy(2));self.assertEqual(out['marker_breaches'],2);self.assertEqual(out['created'],2);self.assertEqual(self.car['breaches'],2)
 def test_same_damage_event_replays_without_additional_hp_or_breaches(self):
  out=self.damage(30);before=self.snap();self.assertEqual(self.damage(30),out);self.assertEqual(before,self.snap())
  with self.assertRaisesRegex(ValueError,'changed intent'):self.damage(31)
  self.assertEqual(before,self.snap())
 def test_emergency_patch_restores_hp_and_protection_but_not_structural_capacity(self):
  self.damage(50);self.assertEqual((self.car['hp'],self.car['breaches']),(10,4));self.turn();out=self.emergency();self.assertEqual((self.car['hp'],self.car['breaches'],self.car['patched_breaches']),(34,4,1));self.assertEqual([x['applied'] for x in out['restored']],[24,1]);self.assertFalse(S.vehicle_view(self.car)['operable']);self.assertEqual(self.a.budget['standard'],0);self.assertEqual(self.car['max_hp'],60)
  self.car.update(breaches=3,patched_breaches=1);self.assertTrue(self.e.vehicle_exposure('vehicle')['protected']);self.assertEqual(S.vehicle_view(self.car)['breaches_for_capacity'],3)
 def test_structural_repair_consumes_100_per_breach_and_removes_selected_real_subset(self):
  self.car.update(hp=20,breaches=4,patched_breaches=2)
  out=self.e.repair_breaches(self.a,'vehicle',count=1,seconds=90,subset='unpatched_first',request_id='structure/1',accessible=True,reason='actual permanent structure repair')
  self.assertEqual((self.car['breaches'],self.car['patched_breaches'],self.car['hp']),(3,2,20));self.assertEqual(self.a.spec['money'],400);self.assertEqual(self.e.elapsed_seconds,90);self.assertTrue(S.vehicle_view(self.car)['operable']);self.assertEqual(out['restored'][0]['subset'],'unpatched_first')
  self.e.repair_breaches(self.a,'vehicle',count=1,seconds=30,subset='patched_first',request_id='structure/2',accessible=True,reason='actual patched structural damage replaced')
  self.assertEqual((self.car['breaches'],self.car['patched_breaches']),(2,1));self.assertEqual(self.a.spec['money'],300)
 def test_structure_not_patch_repair_has_an_actual_positive_period_and_subset(self):
  value=B.structural_policy(1,60,'patched_first');value['seconds']=0;value['action']='standard';self.car['breaches']=1;before=self.snap()
  with self.assertRaisesRegex(ValueError,'positive repair period'):self.e.restore_object(self.a,'vehicle',value,request_id='no-time',reason='missing real structural repair time',accessible=True)
  self.assertEqual(before,self.snap())
  with self.assertRaisesRegex(ValueError,'selection'):B.structural_policy(1,60,'invented')
 def test_destruction_by_hp_or_capacity_is_actual_terminal_and_cannot_be_repaired(self):
  out=self.damage(180);self.assertTrue(self.car['destroyed']);self.assertEqual(self.car['hp'],-120);self.assertFalse(out['state']['operable']);before=self.snap()
  with self.assertRaisesRegex(ValueError,'destroyed'):self.repair_hp()
  self.assertEqual(before,self.snap())
  self.setUp();self.car['breaches']=7;out=self.damage(15);self.assertTrue(self.car['destroyed']);self.assertEqual(self.car['hp'],45);self.assertEqual(out['after_breaches'],8)
 def test_new_name_cannot_change_vehicle_breach_policy_or_marker_history(self):
  self.damage();value=self.policy();value.update(id='new-name',repeated_crossing='once');before=self.snap()
  with self.assertRaisesRegex(ValueError,'policy cannot change'):self.damage(value=value,event='renamed')
  self.assertEqual(before,self.snap())
 def test_actual_identity_vehicle_and_repair_qualification_precede_mutation(self):
  before=self.snap()
  with self.assertRaises(ValueError):self.e.damage_vehicle(copy(self.a),'vehicle',16,self.policy(),event_id='copy',reason='copied producer')
  with self.assertRaisesRegex(ValueError,'vehicle'):self.e.damage_vehicle(self.a,'bot',16,self.policy(),event_id='wrong',reason='wrong target kind')
  self.assertEqual(before,self.snap());self.damage();self.e.begin_encounter([self.a]);self.e.start_round([self.a]);self.e.start_of_turn(self.a);before=self.snap()
  with self.assertRaisesRegex(ValueError,'qualification'):self.emergency()
  self.assertEqual(before,self.snap())
 def test_native_compartment_totals_use_actual_current_section_patch_and_structure_state(self):
  other=deepcopy(self.car);other['id']='section/2';other['passenger_ids']=[];S.observe(self.e,other,reason='actual second vehicle section')
  S.observe(self.e,{'id':'ship','kind':'vehicle_sections','location':{'kind':'unknown'},'section_ids':['vehicle','section/2'],'owner_id':self.a.entity_id},reason='actual compartment ship')
  self.damage(50);view=S.validate_record(self.e,self.e._physical_objects['ship']);self.assertEqual(view['combined_breaches'],4)
  self.car['patched_breaches']=3;self.assertEqual(S.validate_record(self.e,self.e._physical_objects['ship'])['combined_breaches'],4)
  self.car['destroyed']=True;self.assertEqual(S.validate_record(self.e,self.e._physical_objects['ship'])['combined_breaches'],12)
 def test_json_gm_restore_keep_damage_marker_history_and_real_patch_or_structure(self):
  self.damage(value=self.policy(1));self.repair_hp();saved=self.snap();loaded=load_engine(self.poly,json.loads(json.dumps(saved,ensure_ascii=False)));actor=W.actor_index(loaded)[self.a.entity_id];out=loaded.damage_vehicle(actor,'vehicle',16,self.policy(1),event_id='damage/2',reason='actual resolved incoming vehicle HP damage');self.assertEqual(out['marker_breaches'],0)
  self.e.gm.snapshot('before');self.damage(value=self.policy(1),event='damage/2');self.e.gm.restore('before',reason='restore actual HP and crossing event');self.assertEqual(self.e._physical_objects['vehicle']['hp'],60);self.assertEqual(len(getattr(self.e,B.FIELD)['events']),1)
 def test_late_vehicle_or_route_failure_rolls_back_hp_breaches_history_and_routes(self):
  before=self.snap()
  with patch.object(REMOTE,'boundary',side_effect=RuntimeError('late route close')):
   with self.assertRaises(RuntimeError):self.damage(30)
  self.assertEqual(before,self.snap())
 def test_resigned_marker_history_without_actual_events_cannot_be_saved(self):
  self.damage();state=getattr(self.e,B.FIELD);state['history']['vehicle']=B._sign({'target_id':'vehicle','intervals':[[1,3]]});self.assertFalse(W.validate_world(self.e)['valid'])
  with self.assertRaises(StateCodecError):self.snap()
  with self.assertRaises(ValueError):self.e.gm.snapshot('bad')
 def test_actual_capacity_damage_closes_existing_remote_vehicle_commands(self):
  from test_foundation_control_remote import RemoteTests
  remote=RemoteTests('test_actual_installed_route_moves_distant_machine_with_existing_action_budget');remote.poly=self.poly;remote.setUp();remote.connect()
  remote.e.damage_vehicle(remote.a,'vehicle',15,self.policy(),event_id='actual-disable',reason='actual damage crossed capacity');self.assertFalse(S.vehicle_view(remote.row)['operable']);before=dump_engine(remote.e)
  with self.assertRaises(ValueError):remote.move(request='after-disable')
  self.assertEqual(before,dump_engine(remote.e))
 def test_native_structural_quantity_and_resigned_created_count_require_actual_damage(self):
  self.damage();before=self.snap()
  with self.assertRaisesRegex(ValueError,'available breaches'):self.e.repair_breaches(self.a,'vehicle',count=2,seconds=60,subset='patched_first',request_id='too-many',accessible=True,reason='missing actual structural damage')
  self.assertEqual(before,self.snap());state=getattr(self.e,B.FIELD);row=state['events']['damage/1'];row.pop('sha256');row['result'].update(created=2,after_breaches=2);state['events']['damage/1']=B._sign(row);self.assertFalse(W.validate_world(self.e)['valid'])

if __name__=='__main__':unittest.main()
