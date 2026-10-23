"""Actual machine bodies, operators, movement and declared weapon consumers."""
from pathlib import Path
from copy import copy,deepcopy
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_special_entities as _fixture_test_category2_special_entities
from engine import Engine
from grid import Grid
from state_codec import dump_engine,load_engine,StateCodecError
import control_vehicle as V,special_entities as S,world_entities as W,roll_context as R


class VehicleTests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_special_entities.SpecialTests.setUpClass.__func__)
 trainer=_fixture_test_category2_special_entities.SpecialTests.trainer
 vehicle=_fixture_test_category2_special_entities.SpecialTests.vehicle
 bot=_fixture_test_category2_special_entities.SpecialTests.bot
 def setUp(self):
  _fixture_test_category2_special_entities.SpecialTests.setUp(self);self.e.grid=Grid(20,12);self.a.spec['skills'].update({'기술학':4,'집중':4,'곡예':3})
  self.t=self.trainer(self.poly,'actual-target');self.t.pos=(8,2);self.e.everyone.append(self.t)
  W.register_object(self.e,'weapon/observed-turret',location={'kind':'unknown'},reason='actual installed weapon')
  row=self.vehicle();row.update(location={'kind':'grid','cell':[1,1]},weapon_ids=['weapon/observed-turret'])
  S.observe(self.e,row,reason='actual shared vehicle');self.row=self.e._physical_objects['vehicle']
  self.e.begin_encounter(self.e.everyone);self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a)
 def policy(self,index=0):return json.loads((ROOT/'data/examples/control-vehicle.json').read_text(encoding='utf8'))[index]
 def snap(self):return dump_engine(self.e)
 def move(self,path=None,value=None,operator=None,request='drive'):
  operator=operator or self.a;path=path or [[1,1],[2,1],[3,1],[4,1]]
  return self.e.operate_machine(operator,'vehicle',value or self.policy(),command='move',request_id=request,path=path,body_eligible=True,reason='actual continuous driving path')
 def fire(self,value=None,operator=None,request='fire',fixed=None):
  operator=operator or self.a;value=value or self.policy();weapon=value['weapons'][0];count=R.plan(self.e,operator,weapon['check']['skill'],purpose=weapon['check']['purpose'],target=self.t)['dice_count']
  return self.e.operate_machine(operator,'vehicle',value,command='fire',request_id=request,weapon_id=weapon['id'],target=self.t,
    body_eligible=True,reason='actual installed weapon operation',roll_options={'fixed':fixed or [6]*count})
 def crew(self,identity='actual-gunner'):
  c=self.trainer(self.poly,identity);c.pos=self.a.pos;c.spec['skills'].update({'집중':3,'기술학':3});self.e.gm.add_combatant(c,pos=c.pos,side='party',reason='actual gunner joins encounter')
  row=deepcopy(self.row);row['passenger_ids'].append(c.entity_id);S.observe(self.e,row,reason='actual added occupant');return c
 def test_spol052_vehicle_state_keeps_actual_driver_passenger_and_separate_weapon_after_restore(self):
  gunner=self.crew();stats=deepcopy(self.row['stats']);self.assertEqual(set(stats),{'hp','def','spd'})
  ctx=self.e.machine_context(self.a,'vehicle',self.policy(),body_eligible=True,reason='SPOL-052 actual driver relation')
  self.assertEqual(ctx['initiative']['value'],self.a.staged('spe'));self.assertEqual(ctx['speed'],self.row['overland'])
  self.move();self.e.end_of_turn(self.a);self.e.start_of_turn(gunner);before=self.t.hp;out=self.fire(operator=gunner)
  self.assertTrue(out['passed']);self.assertEqual((out['weapon_id'],out['operator_id']),('weapon/observed-turret',gunner.entity_id));self.assertEqual(self.t.hp,before-8)
  saved=self.snap();self.e.gm.snapshot('native-vehicle');self.e.gm.set_hp(self.t,value=1,reason='later state');self.e.gm.restore('native-vehicle',reason='restore actual vehicle and occupants')
  for e in (self.e,load_engine(self.poly,json.loads(json.dumps(saved,ensure_ascii=False)))):
   row=e._physical_objects['vehicle'];index=W.actor_index(e)
   self.assertEqual(row['stats'],stats);self.assertNotIn('spe',row['stats']);self.assertEqual(row['driver_id'],self.a.entity_id)
   self.assertEqual(row['passenger_ids'],[self.a.entity_id,gunner.entity_id]);self.assertEqual(row['weapon_ids'],['weapon/observed-turret'])
   self.assertNotEqual(row['id'],e._physical_objects[row['weapon_ids'][0]]['id']);self.assertEqual(index[gunner.entity_id].budget['standard'],0)
   self.assertEqual(index[self.a.entity_id].pos,index[gunner.entity_id].pos);self.assertTrue(W.validate_world(e)['valid'])
 def test_actual_machine_speed_driver_initiative_and_passenger_position_are_distinct(self):
  ctx=self.e.machine_context(self.a,'vehicle',self.policy(),body_eligible=True,reason='actual physically eligible driver')
  self.assertEqual(ctx['speed'],7);self.assertEqual(ctx['initiative']['value'],self.a.staged('spe'));self.assertTrue(ctx['control_permission_checked'])
  out=self.move();self.assertEqual((out['distance'],out['remaining']),(3,4));self.assertEqual(W.grid_cell(self.row),(4,1));self.assertEqual(self.a.pos,(4,1));self.assertEqual(self.a.budget['standard'],0)
 def test_source_and_actual_operator_body_qualification_precede_cost(self):
  before=self.snap()
  for operator,eligible in ((copy(self.a),True),(self.a,False),(self.a,None)):
   with self.assertRaises(ValueError):self.e.machine_context(operator,'vehicle',self.policy(),body_eligible=eligible,reason='actual body eligibility')
   self.assertEqual(before,self.snap())
  value=self.policy();value['pilot']['requirements'][0]['rank']=6
  with self.assertRaisesRegex(ValueError,'qualification'):self.move(value=value)
  self.assertEqual(before,self.snap())
 def test_capability_or_driver_id_does_not_create_a_missing_machine(self):
  before=self.snap()
  with self.assertRaisesRegex(ValueError,'actual registered'):self.e.machine_context(self.a,'nonexistent',self.policy(),body_eligible=True,reason='missing body')
  self.assertEqual(before,self.snap());self.assertFalse(S.view(self.e,'vehicle')['state_view']['combat_adapter_available'])
 def test_current_disabled_destroyed_or_capacity_machine_cannot_act(self):
  for change in ({'hp':0},{'destroyed':True},{'breaches':4}):
   self.setUp();row=deepcopy(self.row);row.update(change);S.observe(self.e,row,reason='actual inoperable machine');before=self.snap()
   with self.assertRaisesRegex(ValueError,'cannot act'):self.move()
   self.assertEqual(before,self.snap())
 def test_actual_assigned_pilot_and_all_passenger_bodies_are_required(self):
  c=self.crew();before=self.snap()
  with self.assertRaisesRegex(ValueError,'authority'):self.move(operator=c)
  self.assertEqual(before,self.snap());c.pos=(7,7);before=self.snap()
  with self.assertRaisesRegex(ValueError,'passenger bodies'):self.move()
  self.assertEqual(before,self.snap())
 def test_whole_machine_footprint_wall_and_map_edge_preflight_are_atomic(self):
  value=self.policy();value['body']['offsets']=[[0,0],[0,1]];self.e.grid.blocking.add((2,2));before=self.snap()
  with self.assertRaisesRegex(ValueError,'whole body'):self.move(value=value)
  self.assertEqual(before,self.snap());self.e.grid.blocking.clear();self.e.grid.walls.add(tuple(sorted(((1,2),(2,2)))))
  with self.assertRaisesRegex(ValueError,'wall'):self.move(value=value)
  self.assertEqual(self.a.budget['standard'],1)
 def test_movement_basis_can_select_actual_pilot_or_authored_values(self):
  for provider,authored in (('pilot',None),('declared',3)):
   self.setUp();value=self.policy();value['movement'].update(provider=provider,value=authored)
   ctx=self.e.machine_context(self.a,'vehicle',value,body_eligible=True,reason='chosen movement basis')
   self.assertEqual(ctx['speed'],self.a.movement if provider=='pilot' else 3)
 def test_same_operator_cannot_move_and_fire_without_declared_current_exception(self):
  self.move();self.a.budget['standard']=1;before=self.snap()
  with self.assertRaisesRegex(ValueError,'separate gunner'):self.fire()
  self.assertEqual(before,self.snap())
 def test_separate_actual_gunner_uses_shared_machine_budget_and_own_action(self):
  gunner=self.crew();self.move();self.e.end_of_turn(self.a);self.e.start_of_turn(gunner);before=self.t.hp
  out=self.fire(operator=gunner);self.assertTrue(out['passed']);self.assertEqual(self.t.hp,before-8);self.assertEqual(gunner.budget['standard'],0)
  self.assertEqual(getattr(self.e,V.FIELD)['budgets']['vehicle']['actions']['standard'],2);gunner.budget['standard']=1;before=self.snap()
  with self.assertRaisesRegex(ValueError,'shared action'):self.fire(operator=gunner,request='again')
  self.assertEqual(before,self.snap())
 def test_current_expert_override_uses_swift_and_preserves_standard_for_weapon(self):
  self.a.spec['skills']['집중']=5;out=self.move();self.assertEqual(out['action'],'swift');self.assertEqual(self.a.budget['swift'],0);self.assertEqual(self.a.budget['standard'],1)
  self.assertTrue(self.fire()['passed']);self.assertEqual(self.a.budget['standard'],0)
 def test_shared_remaining_distance_does_not_reset_with_new_request_or_operator_turn(self):
  self.move();self.a.budget['standard']=1;before=self.snap();path=[[4,1],[5,1],[6,1],[7,1],[8,1],[9,1]]
  with self.assertRaisesRegex(ValueError,'distance exhausted'):self.move(path=path,request='another')
  self.assertEqual(before,self.snap());self.e.end_of_turn(self.a);self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a)
  self.assertEqual(self.move(path=path,request='next-round')['remaining'],2)
 def test_policy_rename_cannot_increase_shared_capacity_mid_run(self):
  self.move();value=self.policy();value.update(id='renamed');value['actions']['standard']=99;before=self.snap()
  with self.assertRaisesRegex(ValueError,'shared machine policy'):self.move(path=[[4,1],[5,1]],value=value,request='changed')
  self.assertEqual(before,self.snap())
 def test_failed_real_weapon_check_spends_action_but_never_applies_damage(self):
  before=self.t.hp;out=self.fire(fixed=[1]*4);self.assertFalse(out['passed']);self.assertIsNotNone(out['check']);self.assertEqual(self.t.hp,before);self.assertEqual(self.a.budget['standard'],0)
 def test_uninstalled_weapon_or_out_of_range_target_rejects_before_roll(self):
  row=deepcopy(self.row);row['weapon_ids']=[];S.observe(self.e,row,reason='actual removed weapon');before=self.snap()
  with self.assertRaisesRegex(ValueError,'installed'):self.fire()
  self.assertEqual(before,self.snap());self.setUp();self.t.pos=(18,10);before=self.snap()
  with self.assertRaisesRegex(ValueError,'range'):self.fire()
  self.assertEqual(before,self.snap())
 def test_bot_current_components_supply_own_body_speed_and_weapon_identity(self):
  row=self.bot();row.update(location={'kind':'grid','cell':[2,1]},controller_id=self.a.entity_id)
  W.register_object(self.e,'component/observed-combat',location={'kind':'unknown'},reason='actual installed bot component')
  row.update(complexity=1,components=[{'instance_id':'component/observed-combat','complexity':1,'source':'actual/combat-component','module_id':'basic_combat','choice':['몸통박치기','웅크리기']}])
  S.observe(self.e,row,reason='actual configured bot');value=self.policy(1)
  ctx=self.e.machine_context(self.a,'bot',value,body_eligible=True,reason='actual local control');self.assertEqual(ctx['speed'],6);self.assertEqual(ctx['initiative']['value'],10)
  self.t.pos=(7,1);before=self.t.hp
  out=self.e.operate_machine(self.a,'bot',value,command='fire',request_id='bot-fire',weapon_id='component/observed-combat',target=self.t,
   body_eligible=True,reason='actual bot component use',roll_options={'fixed':[6]*4})
  self.assertTrue(out['passed']);self.assertEqual(self.t.hp,before-4);self.assertEqual(out['damage_kind'],'hp_loss');self.assertNotIn('move/몸통박치기',self.a.moves)
 def test_replay_and_json_gm_restore_keep_actual_machine_aliases_and_used_budget(self):
  self.a.custom_conditions['machine_ref']=self.row;out=self.move();saved=self.snap();self.assertEqual(self.move(),out);self.assertEqual(saved,self.snap())
  loaded=load_engine(self.poly,json.loads(json.dumps(saved,ensure_ascii=False)));a=W.actor_index(loaded)[self.a.entity_id]
  self.assertIs(a.custom_conditions['machine_ref'],loaded._physical_objects['vehicle']);self.assertEqual(loaded.operate_machine(a,'vehicle',self.policy(),command='move',request_id='drive',path=[[1,1],[2,1],[3,1],[4,1]],body_eligible=True,reason='actual continuous driving path'),out)
  snapshot=self.e.gm.snapshot();self.e.gm.set_hp(self.t,value=1,reason='changed state');self.e.gm.restore(snapshot)
  self.assertIs(self.a.custom_conditions['machine_ref'],self.e._physical_objects['vehicle']);self.assertEqual(getattr(self.e,V.FIELD)['budgets']['vehicle']['distance'],3)
 def test_late_machine_movement_and_weapon_failure_roll_back_world_budget_and_rng(self):
  before=self.snap()
  with patch.object(W,'_set_object_location',side_effect=ValueError('late machine movement')):
   with self.assertRaisesRegex(ValueError,'late machine movement'):self.move()
  self.assertEqual(before,self.snap())
  with patch.object(Engine,'_take_damage',side_effect=ValueError('late machine weapon')):
   with self.assertRaisesRegex(ValueError,'late machine weapon'):self.fire()
  self.assertEqual(before,self.snap())
 def test_changed_request_intent_and_tampered_saved_budget_are_rejected(self):
  self.move();before=self.snap()
  with self.assertRaisesRegex(ValueError,'changed intent'):self.move(path=[[4,1],[5,1]],request='drive')
  self.assertEqual(before,self.snap());getattr(self.e,V.FIELD)['budgets']['vehicle']['distance']=0
  self.assertFalse(self.e.validate_state()['valid'])
  with self.assertRaises(StateCodecError):self.e.export_state()
  with self.assertRaisesRegex(ValueError,'changed'):self.e.gm.snapshot('bad machine state')
 def test_actual_machine_body_blocks_ordinary_actor_placement(self):
  import body_state as BODY
  self.t.spec['size']='Medium';self.a.spec['size']='Medium';value=self.policy();value['body']['offsets']=[[0,0],[0,1]]
  self.move(value=value)
  self.assertFalse(BODY.can_place(self.e,self.t,(4,2)))
  self.assertFalse(BODY.can_place(self.e,self.t,(4,2),altitude=0))
  self.assertTrue(BODY.can_place(self.e,self.t,(5,2)))
 def test_corrupt_gm_machine_candidate_is_rejected_before_live_restore(self):
  self.move();name=self.e.gm.snapshot('valid machine');before=self.snap()
  self.e.gm.snapshots[name]['engine'][V.FIELD]['budgets']['vehicle']['distance']=0
  with self.assertRaisesRegex(ValueError,'changed'):self.e.gm.restore(name)
  self.assertEqual(before,self.snap())


if __name__=='__main__':unittest.main()
