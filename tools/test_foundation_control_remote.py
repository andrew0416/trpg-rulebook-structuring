"""Actual remote commands, live installations and independent connection loss."""
from pathlib import Path
from copy import copy,deepcopy
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_special_entities as _fixture_test_category2_special_entities
from engine import Engine,Combatant
from builder import build_pokemon
from grid import Grid
from state_codec import dump_engine,load_engine,StateCodecError
import control_remote as M,control_vehicle as V,special_entities as S,world_entities as W,state_grants as G,roll_context as R


class RemoteTests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_special_entities.SpecialTests.setUpClass.__func__)
 trainer=_fixture_test_category2_special_entities.SpecialTests.trainer
 vehicle=_fixture_test_category2_special_entities.SpecialTests.vehicle
 bot=_fixture_test_category2_special_entities.SpecialTests.bot
 digital=_fixture_test_category2_special_entities.SpecialTests.digital
 object=_fixture_test_category2_special_entities.SpecialTests.object
 def setUp(self):
  _fixture_test_category2_special_entities.SpecialTests.setUp(self);self.e.grid=Grid(25,14);self.a.spec['skills'].update({'기술학':4,'집중':4});self.a.pos=(1,1)
  self.t=self.trainer(self.poly,'actual-target');self.t.pos=(12,1);self.e.everyone.append(self.t)
  for uid in ('radio/operator','radio/machine','electronics','weapon/observed-turret'):W.register_object(self.e,uid,location={'kind':'unknown'},reason='actual control hardware')
  self.e.gm.observe_control_device('radio/operator',self.a.entity_id,'supp-polygon/차량-제작-가이드라인',True,reason='actual handheld control installation')
  row=self.vehicle();row.update(location={'kind':'grid','cell':[7,1]},passenger_ids=[],weapon_ids=['weapon/observed-turret']);S.observe(self.e,row,reason='actual remotely controlled vehicle');self.row=self.e._physical_objects['vehicle']
  for uid in ('radio/machine','electronics'):self.e.gm.observe_control_device(uid,'vehicle','supp-polygon/차량-제작-가이드라인',True,reason='actual installed electronic control')
  self.e.begin_encounter(self.e.everyone);self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a)
 def policy(self,index=0):return json.loads((ROOT/'data/examples/control-remote.json').read_text(encoding='utf8'))[index]
 def machine_policy(self,index=0):return json.loads((ROOT/'data/examples/control-vehicle.json').read_text(encoding='utf8'))[index]
 def links(self,devices=None,**values):
  out=dict(devices=['radio/operator','radio/machine'] if devices is None else devices,avatar_id=None,node_id=None,recipient_id=None,communication_source=None,component_id=None);out.update(values);return out
 def connect(self,value=None,links=None,identity='vehicle',operator=None,route='radio'):
  return self.e.connect_remote_control(operator or self.a,identity,value or self.policy(),links or self.links(),route_id=route,connected=True,reason='actual established command connection')
 def move(self,route='radio',identity='vehicle',value=None,path=None,operator=None,request='remote-move',body=True):
  return self.e.operate_machine(operator or self.a,identity,value or self.machine_policy(),command='move',request_id=request,path=path or [[7,1],[8,1],[9,1]],body_eligible=body,reason='actual remote movement',remote_route=route)
 def fire(self,route='radio',operator=None,value=None,request='remote-fire'):
  operator=operator or self.a;value=value or self.machine_policy();weapon=value['weapons'][0];n=R.plan(self.e,operator,weapon['check']['skill'],purpose=weapon['check']['purpose'],target=self.t)['dice_count']
  return self.e.operate_machine(operator,'vehicle',value,command='fire',request_id=request,weapon_id=weapon['id'],target=self.t,body_eligible=False,reason='actual remote installed weapon',remote_route=route,roll_options={'fixed':[6]*n})
 def snap(self):return dump_engine(self.e)
 def pokemon_controller(self):
  p=Combatant(self.poly,build_pokemon(self.poly,'폴리곤',5,name='actual-interface'));p.pos=(1,2);p.spec['skills'].update({'기술학':4,'집중':4});G.grant(p,'capabilities','접속','fixture:interface','fixture')
  self.e.gm.add_combatant(p,pos=p.pos,side='party',reason='actual interface controller');self.e.end_of_turn(self.a);self.e.start_of_turn(p)
  row=deepcopy(self.row);row['driver_id']=p.entity_id;S.observe(self.e,row,reason='actual wired vehicle driver');return p
 def actual_bot(self,controller=None,components=None):
  controller=controller or self.a;row=self.bot();row.update(location={'kind':'grid','cell':[7,4]},controller_id=controller.entity_id)
  if components is not None:row['components']=components;row['complexity']=sum(x['complexity'] for x in components)
  S.observe(self.e,row,reason='actual command target bot');return self.e._physical_objects['bot']
 def test_actual_installed_route_moves_distant_machine_with_existing_action_budget(self):
  before=self.snap()
  with self.assertRaisesRegex(ValueError,'aboard'):self.e.machine_context(self.a,'vehicle',self.machine_policy(),body_eligible=True,reason='physical access still absent')
  self.assertEqual(before,self.snap());self.connect();out=self.move();self.assertTrue(out['passed']);self.assertEqual((W.grid_cell(self.row),self.a.pos),((9,1),(1,1)));self.assertEqual(self.a.budget['standard'],0)
  self.assertEqual(getattr(self.e,V.FIELD)['budgets']['vehicle']['distance'],2)
 def test_missing_device_wrong_host_or_false_connection_never_grants_command(self):
  before=self.snap()
  for links in (self.links(['missing','radio/machine']),self.links(['radio/machine','radio/operator'])):
   with self.assertRaises(ValueError):self.connect(links=links)
   self.assertEqual(before,self.snap())
  with self.assertRaisesRegex(ValueError,'established'):self.e.connect_remote_control(self.a,'vehicle',self.policy(),self.links(),route_id='bad',connected=False,reason='no connection')
  self.assertEqual(before,self.snap())
 def test_actual_interface_identity_and_machine_authority_are_separate(self):
  with self.assertRaises(ValueError):self.connect(operator=copy(self.a))
  self.connect();row=deepcopy(self.row);row['driver_id']=self.t.entity_id;S.observe(self.e,row,reason='actual operator is no longer assigned');before=self.snap()
  with self.assertRaisesRegex(ValueError,'authority'):self.move()
  self.assertEqual(before,self.snap())
 def test_remote_body_and_pilot_qualifications_are_not_implicitly_waived(self):
  self.connect();before=self.snap()
  with self.assertRaisesRegex(ValueError,'body'):self.move(body=False)
  value=self.machine_policy();value['pilot']['requirements'][0]['rank']=6
  with self.assertRaisesRegex(ValueError,'qualification'):self.move(value=value)
  self.assertEqual(before,self.snap())
 def test_range_loss_closes_only_dependent_route_and_command_cost_is_zero(self):
  self.connect();self.a.pos=(24,12);before=self.a.budget.copy()
  with self.assertRaisesRegex(ValueError,'closed'):self.move()
  self.assertEqual(self.a.budget,before);self.assertEqual(self.e.remote_control_routes(self.a)['radio']['status'],'closed');self.assertEqual(W.grid_cell(self.row),(7,1))
 def test_machine_path_cannot_cross_remote_range_mid_command(self):
  value=self.policy();value['range']['maximum']=6;self.connect(value=value);before=self.snap()
  with self.assertRaisesRegex(ValueError,'lose.*range'):self.move()
  self.assertEqual(before,self.snap())
 def test_hardware_removal_revokes_route_but_other_source_route_executes(self):
  self.connect();other=self.policy();other['source']='feat/엔지니어';other['devices']=[];other['id']='independent declared interface';self.connect(value=other,links=self.links([]),route='independent')
  self.e.gm.observe_control_device('radio/machine','vehicle',self.policy()['source'],False,reason='actual radio receiver removed');rows=self.e.remote_control_routes(self.a)
  self.assertEqual((rows['radio']['status'],rows['independent']['status']),('closed','live'));out=self.move(route='independent');self.assertTrue(out['passed'])
 def test_device_disabled_and_capability_source_loss_stop_actual_commands(self):
  value=self.policy();value['capabilities']=['접속'];G.grant(self.a,'capabilities','접속','fixture:remote','fixture');self.connect(value=value)
  G.transition(self.e,self.a,lambda e,c:G.revoke(c,'fixture:remote'));self.assertEqual(self.e.remote_control_routes(self.a)['radio']['status'],'closed')
  self.setUp();self.connect();self.e._physical_objects['radio/machine']['disabled']=True
  with self.assertRaisesRegex(ValueError,'closed'):self.move()
  self.assertEqual(self.e.remote_control_routes(self.a)['radio']['status'],'closed')
 def test_native_wired_one_vehicle_exempts_training_body_and_controls_installed_weapon(self):
  p=self.pokemon_controller();self.e.connect_wired_vehicle(p,'vehicle','electronics',route_id='wired',connected=True,reason='actual direct electronic vehicle connection')
  value=self.machine_policy();value['pilot']['requirements']=[{'kind':'owned','fields':['edges'],'names':['Vehicle Training']}]
  ctx=self.e.machine_context(p,'vehicle',value,body_eligible=False,reason='native interface route',remote_route='wired');self.assertTrue(ctx['control_permission_checked'])
  before=self.t.hp;out=self.fire(route='wired',operator=p,value=value);self.assertEqual(self.t.hp,before-8);self.assertTrue(out['passed'])
  second=self.vehicle('second');second.update(location={'kind':'grid','cell':[7,7]},driver_id=p.entity_id,passenger_ids=[]);S.observe(self.e,second,reason='another real vehicle')
  W.register_object(self.e,'other-electronics',location={'kind':'unknown'},reason='another control port');self.e.gm.observe_control_device('other-electronics','second',value['source'],True,reason='actual second port')
  with self.assertRaisesRegex(ValueError,'limit'):self.e.connect_wired_vehicle(p,'second','other-electronics',route_id='wired-two',connected=True,reason='cannot control two at once')
  with self.assertRaisesRegex(ValueError,'this actual'):M.permission(self.e,p,'second','wired','move')
 def test_native_wired_requires_actual_pokemon_and_current_interface(self):
  before=self.snap()
  with self.assertRaisesRegex(ValueError,'Pokemon'):self.e.connect_wired_vehicle(self.a,'vehicle','electronics',route_id='wired',connected=True,reason='wrong actual kind')
  self.assertEqual(before,self.snap());p=self.pokemon_controller();G.revoke(p,'fixture:interface');p.spec['capabilities']=[];before=self.snap()
  with self.assertRaisesRegex(ValueError,'capability'):self.e.connect_wired_vehicle(p,'vehicle','electronics',route_id='wired',connected=True,reason='missing interface')
  self.assertEqual(before,self.snap())
 def test_commands_are_finite_and_route_id_cannot_switch_machine(self):
  value=self.policy();value['commands']=['move'];self.connect(value=value);before=self.snap()
  with self.assertRaisesRegex(ValueError,'command exceeds'):self.fire()
  with self.assertRaisesRegex(ValueError,'identity changed'):self.connect(value=value,identity='missing',route='radio')
  self.assertEqual(before,self.snap())
 def test_new_names_cannot_change_source_route_limit_or_reopen_closed_connection(self):
  self.connect();value=self.policy();value['id']='renamed';value['maximum']=99
  with self.assertRaisesRegex(ValueError,'source policy'):self.connect(value=value,route='new')
  self.e.disconnect_remote_control(self.a,'radio',reason='actual disconnected');before=self.snap()
  with self.assertRaisesRegex(ValueError,'closed route'):self.connect()
  self.assertEqual(before,self.snap());self.connect(route='reconnected');self.assertEqual(self.e.remote_control_routes(self.a)['reconnected']['status'],'live')
 def test_digital_actual_avatar_and_node_route_execute_and_ejection_stops_it(self):
  bot=self.actual_bot();avatar=self.digital();S.observe(self.e,avatar,reason='actual independent network entry')
  node=dict(id='command-node',kind='digital_node',location={'kind':'abstract','place_id':'network/root'},node_type='active_ice',network_id='network',integrity=30,max_integrity=30,status='connected',anchor_id=None,controller_id=self.a.entity_id,defense=4,evasion=1,data_state='not_applicable',bot_id='bot');S.observe(self.e,node,reason='actual bot control node')
  self.connect(value=self.policy(1),links=self.links([],avatar_id='avatar',node_id='command-node'),identity='bot',route='network')
  out=self.move(route='network',identity='bot',value=self.machine_policy(1),path=[[7,4],[8,4]]);self.assertTrue(out['passed']);self.assertEqual(W.grid_cell(bot),(8,4));self.assertEqual(self.a.pos,(1,1))
  avatar['status']='ejected';S.observe(self.e,avatar,reason='actual network ejection');self.assertEqual(self.e.remote_control_routes(self.a)['network']['status'],'closed')
  before=self.a.budget.copy()
  with self.assertRaisesRegex(ValueError,'closed'):self.move(route='network',identity='bot',value=self.machine_policy(1),path=[[8,4],[9,4]],request='after-ejection')
  self.assertEqual(self.a.budget,before)
 def test_network_route_cannot_bind_foreign_avatar_or_other_bot_node(self):
  self.actual_bot();avatar=self.digital(actor=self.t);S.observe(self.e,avatar,reason='other actual user entry')
  node=dict(id='command-node',kind='digital_node',location={'kind':'abstract','place_id':'network'},node_type='active_ice',network_id='network',integrity=30,max_integrity=30,status='connected',anchor_id=None,controller_id=self.a.entity_id,defense=4,evasion=1,data_state='not_applicable',bot_id='bot');S.observe(self.e,node,reason='actual node');before=self.snap()
  with self.assertRaisesRegex(ValueError,'connection'):self.connect(value=self.policy(1),links=self.links([],avatar_id='avatar',node_id='command-node'),identity='bot',route='network')
  self.assertEqual(before,self.snap())
 def test_actual_wired_core_connects_native_projection_and_component_loss_revokes(self):
  p=self.pokemon_controller()
  for uid in ('part/utility','part/repair','part/core'):W.register_object(self.e,uid,location={'kind':'unknown'},reason='actual bot component')
  components=[{'instance_id':'part/utility','module_id':'basic_utility','complexity':1,'source':'feat/엔지니어','choice':'movement_plus4'},
    {'instance_id':'part/repair','module_id':'repair_nanites','complexity':2,'source':'feat/엔지니어','choice':None},
    {'instance_id':'part/core','module_id':'wired_core','complexity':3,'source':'feat/엔지니어','choice':{'moves':[],'ability':'재생력','controller_id':p.entity_id}}]
  bot=self.actual_bot(p,components);view=S.view(self.e,'bot')['state_view']['component_projection']['wired_projection'];self.assertFalse(view['interface_capability_permission_checked'])
  self.connect(value=self.policy(2),links=self.links(['part/core'],component_id='part/core'),identity='bot',operator=p,route='core')
  view=S.view(self.e,'bot')['state_view']['component_projection']['wired_projection'];self.assertTrue(view['interface_capability_permission_checked']);self.assertEqual(view['actual_remote_route_ids'],['core'])
  self.assertTrue(self.move(route='core',identity='bot',value=self.machine_policy(1),path=[[7,4],[8,4]],operator=p,body=False)['passed']);self.assertFalse(any(x in p.moves for x in ('할퀴기','몸통박치기')))
  row=deepcopy(bot);row['components']=row['components'][:-1];row['complexity']=3;S.observe(self.e,row,reason='actual wired core removed');self.assertEqual(self.e.remote_control_routes(p)['core']['status'],'closed')
 def test_json_gm_restore_replay_keep_actual_machine_route_and_spent_budget(self):
  self.connect();out=self.move();encoded=self.snap();restored=load_engine(self.poly,json.loads(json.dumps(encoded,ensure_ascii=False)));a=W.actor_index(restored)[self.a.entity_id]
  self.assertEqual(restored.remote_control_routes(a)['radio']['machine_id'],'vehicle');self.assertEqual(getattr(restored,V.FIELD)['budgets']['vehicle']['distance'],2);self.assertEqual(restored.operate_machine(a,'vehicle',self.machine_policy(),command='move',request_id='remote-move',path=[[7,1],[8,1],[9,1]],body_eligible=True,reason='actual remote movement',remote_route='radio'),out)
  self.e.gm.snapshot('remote');self.e.disconnect_remote_control(self.a,'radio',reason='later disconnect');self.e.gm.restore('remote',reason='restore actual routes');self.assertEqual(self.e.remote_control_routes(self.a)['radio']['status'],'live');self.assertEqual(getattr(self.e,V.FIELD)['budgets']['vehicle']['distance'],2)
 def test_inoperable_bot_observation_returns_current_wired_permission_and_closes_route(self):
  self.test_actual_wired_core_connects_native_projection_and_component_loss_revokes()
  bot=self.e._physical_objects['bot'];p=W.actor_index(self.e)[bot['controller_id']]
  core={'instance_id':'part/core','module_id':'wired_core','complexity':3,'source':'feat/엔지니어','choice':{'moves':[],'ability':'재생력','controller_id':p.entity_id}}
  row=deepcopy(bot);row['components'].append(core);row['complexity']=6;S.observe(self.e,row,reason='actual reinstalled wired core')
  self.connect(value=self.policy(2),links=self.links(['part/core'],component_id='part/core'),identity='bot',operator=p,route='reconnected-core')
  row=deepcopy(bot);row['hp']=0;out=S.observe(self.e,row,reason='actual inoperable bot')['state_view']['component_projection']['wired_projection']
  self.assertFalse(out['interface_capability_permission_checked']);self.assertEqual(out['actual_remote_route_ids'],[]);self.assertEqual(self.e.remote_control_routes(p)['reconnected-core']['status'],'closed')
 def test_changed_route_evidence_rejects_world_json_and_gm_snapshot(self):
  self.connect();getattr(self.e,M.FIELD)['routes']['radio']['machine_id']='other';self.assertFalse(W.validate_world(self.e)['valid'])
  with self.assertRaises(StateCodecError):self.snap()
  with self.assertRaises(ValueError):self.e.gm.snapshot('bad')
 def test_actual_communication_connection_expiry_closes_only_dependent_control(self):
  row=deepcopy(self.row);row['owner_id']=self.t.entity_id;S.observe(self.e,row,reason='actual command receiver owns vehicle')
  value=json.loads((ROOT/'data/examples/perception-communicate.json').read_text(encoding='utf8'))[0];value.update(capabilities=[],range=None,consent={'kind':'none'},distance_exceptions=[])
  self.assertEqual(self.e.communicate(self.a,self.t,value,'actual control connection',request_id='command-link')['status'],'delivered')
  remote=self.policy();remote.update(transport='communication',dependency='communication',devices=[],range=None)
  self.connect(value=remote,links=self.links([],recipient_id=self.t.entity_id,communication_source=value['source']),route='message-route')
  self.assertTrue(self.move(route='message-route')['passed']);self.e.advance_time(10)
  self.assertEqual(self.e.remote_control_routes(self.a)['message-route']['status'],'closed')
 def test_communication_metadata_without_live_connection_does_not_authorize_control(self):
  remote=self.policy();remote.update(transport='communication',dependency='communication',devices=[],range=None);before=self.snap()
  with self.assertRaisesRegex(ValueError,'communication connection'):self.connect(value=remote,links=self.links([],recipient_id=self.t.entity_id,communication_source='ch03-skills-edges-feats/재주'))
  self.assertEqual(before,self.snap())
 def test_corrupt_gm_remote_candidate_cannot_change_live_machine_or_routes(self):
  self.connect();self.e.gm.snapshot('remote');self.e.disconnect_remote_control(self.a,'radio',reason='live actual disconnection');before=self.snap()
  snapshot=self.e.gm.snapshots['remote'];snapshot['engine'][M.FIELD]['routes']['radio']['machine_id']='other'
  with self.assertRaises(ValueError):self.e.gm.restore('remote',reason='corrupt candidate rejected')
  self.assertEqual(before,self.snap())
 def test_late_remote_move_or_connection_error_restores_whole_native_event(self):
  self.connect();before=self.snap()
  with patch.object(W,'_set_object_location',side_effect=RuntimeError('late remote motion')):
   with self.assertRaises(RuntimeError):self.move()
  self.assertEqual(before,self.snap())
  with patch.object(M,'validate_world',side_effect=[True,RuntimeError('late remote connect')]):
   with self.assertRaises(RuntimeError):self.connect(route='second-route')
  self.assertEqual(before,self.snap())


if __name__=='__main__':unittest.main()
