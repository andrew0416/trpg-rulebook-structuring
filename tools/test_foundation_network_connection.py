"""Actual digital action/anchor transitions and dependent Integrity consequences."""
from pathlib import Path
from copy import copy,deepcopy
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_special_entities as _fixture_test_category2_special_entities
from engine import Engine,Rules
from grid import Grid
from state_codec import dump_engine,load_engine,StateCodecError
import network_connection as N,special_entities as S,world_entities as W,state_grants as G


class ConnectionTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.poly=Rules(str(ROOT),ruleset='polygon')
 trainer=_fixture_test_category2_special_entities.SpecialTests.trainer
 bot=_fixture_test_category2_special_entities.SpecialTests.bot
 def setUp(self):
  self.e=Engine(self.poly,24);self.e.grid=Grid(20,12);self.a=self.trainer(self.poly);self.a.spec['skills'].update({'기술학':4,'집중':2});self.e.everyone=self.e.gm.everyone=[self.a]
  W.register_object(self.e,'network',location={'kind':'grid','cell':[7,1]},reason='actual accessible network server')
  W.register_object(self.e,'other-network',location={'kind':'grid','cell':[7,8]},reason='actual distinct network')
  self.e.begin_encounter([self.a]);self.e.start_round([self.a]);self.e.start_of_turn(self.a)
 def policy(self,index=0):return json.loads((ROOT/'data/examples/network-connection.json').read_text(encoding='utf8'))[index]
 def enter(self,actor=None,value=None,avatar='avatar',network='network',request='enter',**options):
  return self.e.enter_network(actor or self.a,network,value or self.policy(),avatar_id=avatar,request_id=request,access_established=True,reason='actual established network entry',**options)
 def snap(self):return dump_engine(self.e)
 def next_turn(self,actor=None):
  actor=actor or self.a;active=self.e._active_turn_actor
  if active is not None:self.e.end_of_turn(active)
  self.e.start_round(self.e.everyone);self.e.start_of_turn(actor)
 def child(self,identity='child',value=None,avatar=None,anchor='avatar',network='network'):
  c=self.trainer(self.poly,identity);c.spec['skills'].update({'기술학':1,'집중':1});self.e.gm.add_combatant(c,pos=(2,1),side='party',reason='actual allied network user')
  if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)
  self.e.start_of_turn(c);self.enter(c,value=value,avatar=avatar or identity+'/avatar',request='enter/'+identity,network=network,entry_basis='anchor',anchor_id=anchor,anchor_allied=True);return c
 def test_spol065_native_defaults_keep_real_clock_anchor_capacity_and_restored_ejection(self):
  physical=(self.a.hp,deepcopy(self.a.location),self.a.stats.copy())
  out=self.e.enter_network(self.a,'network',avatar_id='avatar',request_id='native-enter',access_established=True,reason='SPOL-065 actual independent native entry')
  self.assertEqual((out['status'],self.a.budget['standard']),('connected',0));self.assertEqual(physical,(self.a.hp,self.a.location,self.a.stats))
  children=[self.child('native-child/'+str(i),value=N.native()) for i in range(4)]
  overflow=self.trainer(self.poly,'native-overflow');overflow.spec['skills']['기술학']=1;self.e.gm.add_combatant(overflow,pos=(3,1),side='party',reason='actual fifth allied applicant')
  self.e.end_of_turn(self.e._active_turn_actor);self.e.start_of_turn(overflow);before=self.snap()
  with self.assertRaisesRegex(ValueError,'capacity'):
   self.e.enter_network(overflow,'network',avatar_id='overflow/avatar',request_id='native-overflow',access_established=True,reason='SPOL-065 fifth dependent',entry_basis='anchor',anchor_id='avatar',anchor_allied=True)
  self.assertEqual(before,self.snap());self.e._physical_objects['native-child/0/avatar']['temp_integrity']=7
  before_time=self.e.elapsed_seconds;self.e.advance_time(3);self.assertEqual(self.e.elapsed_seconds,before_time+3)
  self.assertTrue(all(self.e._physical_objects[c.entity_id+'/avatar']['integrity']==25 for c in children))
  saved=self.snap();self.e.gm.snapshot('native-network');self.e.exit_network(self.a,'avatar',request_id='discarded-ejection',reason='later ejection to restore',forced=True);self.e.gm.restore('native-network',reason='restore actual native anchor graph')
  restored=load_engine(self.poly,json.loads(json.dumps(saved,ensure_ascii=False)))
  for e in (self.e,restored):
   index=W.actor_index(e);a=index[self.a.entity_id];bodies={c.entity_id:(c.hp,deepcopy(c.location),c.budget.copy()) for c in index.values()}
   result=e.exit_network(a,'avatar',request_id='native-forced-exit',reason='SPOL-065 native forced anchor ejection',forced=True)
   self.assertEqual(len(result['changes']),5)
   for c in children:
    row=e._physical_objects[c.entity_id+'/avatar'];self.assertEqual((row['status'],row['integrity']),('ejected',13))
   self.assertEqual(e._physical_objects['native-child/0/avatar']['temp_integrity'],7)
   self.assertEqual(bodies,{c.entity_id:(c.hp,c.location,c.budget) for c in index.values()});self.assertEqual(e.elapsed_seconds,before_time+3)
   encoded=dump_engine(e);self.assertEqual(e.exit_network(a,'avatar',request_id='native-forced-exit',reason='SPOL-065 native forced anchor ejection',forced=True),result);self.assertEqual(encoded,dump_engine(e))
 def test_real_entry_and_exit_spend_standard_without_changing_physical_body(self):
  physical=(self.a.hp,self.a.location.copy(),self.a.stats.copy());out=self.enter();row=self.e._physical_objects['avatar']
  self.assertEqual((out['status'],row['integrity'],self.a.budget['standard']),('connected',40,0));self.assertEqual(physical,(self.a.hp,self.a.location,self.a.stats))
  self.next_turn();out=self.e.exit_network(self.a,'avatar',request_id='exit',reason='actual voluntary departure');self.assertEqual(row['status'],'disconnected');self.assertEqual(self.a.budget['standard'],0);self.assertEqual(out['changes'][0]['loss'],0)
 def test_actual_identity_network_and_established_access_are_required_before_cost(self):
  before=self.snap()
  with self.assertRaises(ValueError):self.enter(copy(self.a))
  with self.assertRaisesRegex(ValueError,'registered'):self.enter(network='missing')
  with self.assertRaisesRegex(ValueError,'established'):self.e.enter_network(self.a,'network',self.policy(),avatar_id='avatar',request_id='no',access_established=False,reason='missing network access')
  self.assertEqual(before,self.snap())
 def test_unqualified_actual_actor_needs_real_allied_connected_anchor(self):
  self.a.spec['skills']['기술학']=3;before=self.snap()
  with self.assertRaisesRegex(ValueError,'qualification'):self.enter()
  with self.assertRaisesRegex(ValueError,'allied'):self.enter(entry_basis='anchor',anchor_id='missing',anchor_allied=False)
  self.assertEqual(before,self.snap())
 def test_current_source_owned_interface_and_owned_edge_are_distinct_entry_bases(self):
  self.a.spec['skills']['기술학']=1;G.grant(self.a,'capabilities','접속','fixture:interface','fixture');out=self.enter(entry_basis='interface');self.assertEqual(out['basis'],'interface');self.assertEqual(self.e._physical_objects['avatar']['max_integrity'],25)
  self.setUp();self.a.spec['skills']['기술학']=1;self.a.spec['poke_edges']=['디지털-아바타'];self.assertEqual(self.enter(entry_basis='digital_avatar_edge')['basis'],'digital_avatar_edge')
 def test_local_access_and_authored_values_use_same_entry_consumer(self):
  value=self.policy(1);before=self.snap()
  with self.assertRaisesRegex(ValueError,'local'):self.enter(value=value)
  self.assertEqual(before,self.snap());self.a.pos=(6,1);out=self.enter(value=value);self.assertEqual(out['action'],'standard');self.assertEqual(W.grid_cell(self.a),(6,1))
 def test_one_actual_actor_cannot_have_two_connected_avatars_or_reuse_foreign_identity(self):
  self.enter();before=self.snap()
  with self.assertRaisesRegex(ValueError,'two connected'):self.enter(avatar='other-avatar',request='second')
  self.assertEqual(before,self.snap());c=self.trainer(self.poly,'other-user');c.spec['skills']['기술학']=4;self.e.gm.add_combatant(c,pos=(3,1),side='party',reason='actual other network user');self.e.end_of_turn(self.a);self.e.start_of_turn(c);before=self.snap()
  with self.assertRaisesRegex(ValueError,'another body'):self.enter(c,request='foreign')
  self.assertEqual(before,self.snap())
 def test_virtuoso_native_anchor_accepts_eighth_and_rejects_ninth_atomically(self):
  import skill_modifiers as SKILL
  self.e.gm.set_level(self.a,30,reason='actual level30 trainer before Virtuoso acquisition')
  self.e.gm.set_skill(self.a,'기술학',6,reason='actual Master Technology')
  G.transition(self.e,self.a,lambda e,a:a.spec.update(
   edges=[*a.spec.get('edges',[]),'edge/거장'],edge_choices={'edge/거장':['기술학']}))
  self.assertEqual((SKILL.rank(self.e.r,self.a,'기술학')[2],SKILL.effective_rank(self.e.r,self.a,'기술학')),(6,8))
  self.enter(value=N.native())
  children=[self.child('virtuoso-child/'+str(i),value=N.native()) for i in range(8)]
  self.assertEqual(len([row for row in self.e._physical_objects.values()
   if row.get('kind')=='digital_avatar' and row.get('anchor_id')=='avatar' and row.get('status')=='connected']),8)
  self.assertTrue(all(self.e._physical_objects[c.entity_id+'/avatar']['status']=='connected' for c in children))
  overflow=self.trainer(self.poly,'virtuoso-overflow');overflow.spec['skills']['기술학']=1
  self.e.gm.add_combatant(overflow,pos=(3,1),side='party',reason='actual ninth allied applicant')
  self.e.end_of_turn(self.e._active_turn_actor);self.e.start_of_turn(overflow);before=self.snap()
  with self.assertRaisesRegex(ValueError,'capacity'):
   self.enter(overflow,value=N.native(),avatar='virtuoso-overflow/avatar',request='virtuoso-overflow',
    entry_basis='anchor',anchor_id='avatar',anchor_allied=True)
  self.assertEqual(before,self.snap())
 def test_actual_anchor_rank_capacity_counts_connected_allies_and_releases_on_exit(self):
  self.enter()
  for i in range(4):self.child('child/'+str(i))
  c=self.trainer(self.poly,'overflow');c.spec['skills']['기술학']=1;self.e.gm.add_combatant(c,pos=(3,1),side='party',reason='actual overflow user');self.e.end_of_turn(self.e._active_turn_actor);self.e.start_of_turn(c);before=self.snap()
  with self.assertRaisesRegex(ValueError,'capacity'):self.enter(c,avatar='overflow/avatar',request='overflow',entry_basis='anchor',anchor_id='avatar',anchor_allied=True)
  self.assertEqual(before,self.snap());first=self.e._physical_objects['child/0/avatar'];owner=W.actor_index(self.e)[first['actor_id']]
  self.e.exit_network(owner,first['id'],request_id='eject-one',reason='actual forced ally ejection',forced=True)
  self.assertEqual(self.enter(c,avatar='overflow/avatar',request='after-slot-release',entry_basis='anchor',anchor_id='avatar',anchor_allied=True)['status'],'connected')
 def test_declared_smaller_anchor_capacity_cannot_be_bypassed_by_native_rank(self):
  value=self.policy(1);value['access']={'kind':'observed','maximum':None};self.enter(value=value);self.child()
  c=self.trainer(self.poly,'overflow');c.spec['skills']['기술학']=1;self.e.gm.add_combatant(c,pos=(3,1),side='party',reason='actual second dependent');self.e.end_of_turn(self.e._active_turn_actor);self.e.start_of_turn(c)
  with self.assertRaisesRegex(ValueError,'capacity'):self.enter(c,avatar='overflow/avatar',request='overflow',entry_basis='anchor',anchor_id='avatar',anchor_allied=True)
 def test_other_network_and_proposed_anchor_cycle_reject_before_actions(self):
  self.enter();c=self.child();before=self.snap()
  with self.assertRaisesRegex(ValueError,'cycle'):self.enter(self.a,request='cycle',entry_basis='anchor',anchor_id='child/avatar',anchor_allied=True)
  self.assertEqual(before,self.snap());self.e.exit_network(c,'child/avatar',request_id='leave-child',reason='forced current child departure',forced=True);self.next_turn(c);before=self.snap()
  with self.assertRaisesRegex(ValueError,'same network'):self.enter(c,avatar='child/avatar',network='other-network',request='wrong-network',entry_basis='anchor',anchor_id='avatar',anchor_allied=True)
  self.assertEqual(before,self.snap())
 def test_forced_anchor_ejection_changes_every_dependent_and_integrity_atomically(self):
  self.enter();c=self.child();child=self.e._physical_objects['child/avatar'];child['temp_integrity']=7;physical=(self.a.hp,c.hp,self.a.pos,c.pos);budgets=(self.a.budget.copy(),c.budget.copy())
  out=self.e.exit_network(self.a,'avatar',request_id='eject-anchor',reason='actual forced anchor ejection',forced=True)
  self.assertEqual((self.e._physical_objects['avatar']['status'],child['status']),('ejected','ejected'));self.assertEqual((child['integrity'],child['temp_integrity']),(13,7));self.assertEqual(len(out['changes']),2)
  self.assertEqual(physical,(self.a.hp,c.hp,self.a.pos,c.pos));self.assertEqual(budgets,(self.a.budget,c.budget));before=self.snap()
  self.assertEqual(self.e.exit_network(self.a,'avatar',request_id='eject-anchor',reason='actual forced anchor ejection',forced=True),out);self.assertEqual(before,self.snap())
 def test_authored_fraction_and_voluntary_dependent_policy_change_real_results(self):
  value=self.policy(1);value['access']={'kind':'observed','maximum':None};self.enter(value=value);c=self.child(value=value);child=self.e._physical_objects['child/avatar']
  self.e.exit_network(self.a,'avatar',request_id='forced',reason='authored quarter ejection',forced=True);self.assertEqual(child['integrity'],19)
  self.setUp();self.enter(value=value);self.child(value=value);self.next_turn();self.e.exit_network(self.a,'avatar',request_id='voluntary',reason='authored dependent disconnection');self.assertEqual(self.e._physical_objects['child/avatar']['status'],'disconnected');self.assertEqual(self.e._physical_objects['child/avatar']['integrity'],25)
 def test_native_voluntary_anchor_exit_cannot_strand_connected_dependents(self):
  self.enter();self.child();self.next_turn();before=self.snap()
  with self.assertRaisesRegex(ValueError,'dependents'):self.e.exit_network(self.a,'avatar',request_id='exit',reason='cannot strand current child')
  self.assertEqual(before,self.snap())
 def test_reentry_preserves_actual_integrity_and_zero_cannot_refill_itself(self):
  self.enter();row=self.e._physical_objects['avatar'];row['integrity']=17;self.e.exit_network(self.a,'avatar',request_id='eject',reason='actual forced departure',forced=True);self.next_turn();self.enter(request='reentry');self.assertEqual(row['integrity'],17)
  self.e.exit_network(self.a,'avatar',request_id='again',reason='actual forced departure again',forced=True);row['integrity']=0;self.next_turn();before=self.snap()
  with self.assertRaisesRegex(ValueError,'recover positive'):self.enter(request='zero-reentry')
  self.assertEqual(before,self.snap())
 def test_request_replay_and_new_declaration_cannot_change_identity_or_cost_policy(self):
  out=self.enter();before=self.snap();self.assertEqual(self.enter(),out);self.assertEqual(before,self.snap())
  with self.assertRaisesRegex(ValueError,'changed intent'):self.enter(avatar='other',request='enter')
  self.e.exit_network(self.a,'avatar',request_id='eject',reason='actual departure',forced=True);value=self.policy();value['id']='renamed';value['entry_action']='swift';before=self.snap()
  with self.assertRaisesRegex(ValueError,'policy'):self.enter(value=value,request='cheap-reentry')
  self.assertEqual(before,self.snap())
 def test_program_and_optional_stats_require_real_instances_and_actor_kind(self):
  before=self.snap()
  with self.assertRaisesRegex(ValueError,'object reference'):self.enter(program_ids=['nonexistent-program'])
  self.assertEqual(before,self.snap());out=self.enter(optional_trainer_stats=True);self.assertEqual(S.view(self.e,'avatar')['state_view']['digital_stats']['atk'],12);self.assertEqual(self.a.stats['atk'],10)
 def test_json_and_gm_restore_preserve_anchor_graph_and_real_spent_actions(self):
  self.enter();self.child();encoded=self.snap();restored=load_engine(self.poly,json.loads(json.dumps(encoded,ensure_ascii=False)));self.assertEqual(restored._physical_objects['child/avatar']['anchor_id'],'avatar');self.assertEqual(W.actor_index(restored)[self.a.entity_id].budget['standard'],0)
  self.e.gm.snapshot('network');self.e.exit_network(self.a,'avatar',request_id='eject',reason='later actual ejection',forced=True);self.e.gm.restore('network',reason='restore real connected graph');self.assertEqual(self.e._physical_objects['child/avatar']['status'],'connected');self.assertEqual(self.a.budget['standard'],0)
 def test_late_entry_and_ejection_error_rolls_back_every_link_pool_and_action(self):
  before=self.snap()
  with patch.object(S,'observe',side_effect=RuntimeError('late network entry')):
   with self.assertRaises(RuntimeError):self.enter()
  self.assertEqual(before,self.snap());self.enter();self.child();before=self.snap()
  with patch.object(S,'observe_batch',side_effect=RuntimeError('late dependent ejection')):
   with self.assertRaises(RuntimeError):self.e.exit_network(self.a,'avatar',request_id='eject',reason='late actual ejection',forced=True)
  self.assertEqual(before,self.snap())
 def test_execution_record_tampering_rejects_world_json_and_gm(self):
  self.enter();getattr(self.e,N.FIELD)['requests']['enter']['result']['actor_id']='other';self.assertFalse(W.validate_world(self.e)['valid'])
  with self.assertRaises(StateCodecError):self.snap()
  with self.assertRaises(ValueError):self.e.gm.snapshot('bad')
 def test_reentry_keeps_existing_program_identity_and_optional_stats(self):
  rule=next(iter(self.poly.items_mech));W.register_object(self.e,'program-instance',kind='item_instance',item_rule_id=rule,owner_id=self.a.entity_id,location={'kind':'unknown'},reason='actual item instance bound as authored program')
  self.enter(program_ids=['program-instance'],optional_trainer_stats=True);self.e.exit_network(self.a,'avatar',request_id='eject',reason='actual departure',forced=True);self.next_turn();self.enter(request='again')
  row=self.e._physical_objects['avatar'];self.assertEqual(row['program_ids'],['program-instance']);self.assertTrue(row['optional_trainer_stats'])
 def test_native_observation_cannot_bypass_declared_smaller_anchor_capacity(self):
  value=self.policy(1);value['access']={'kind':'observed','maximum':None};self.enter(value=value);self.child()
  c=self.trainer(self.poly,'other');c.spec['skills']['기술학']=1;self.e.gm.add_combatant(c,pos=(4,1),side='party',reason='actual other user');before=self.snap()
  row=deepcopy(self.e._physical_objects['child/avatar']);row.update(id='other/avatar',actor_id=c.entity_id)
  with self.assertRaisesRegex(ValueError,'declared anchor capacity'):S.observe(self.e,row,reason='cannot bypass declared live capacity')
  self.assertEqual(before,self.snap())
 def test_forced_anchor_departure_closes_dependent_actual_remote_machine_command(self):
  self.enter();c=self.child();bot=self.bot();bot.update(location={'kind':'grid','cell':[7,4]},controller_id=c.entity_id);S.observe(self.e,bot,reason='actual dependent-controlled bot')
  node=dict(id='command-node',kind='digital_node',location={'kind':'abstract','place_id':'network/root'},node_type='active_ice',network_id='network',integrity=30,max_integrity=30,status='connected',anchor_id=None,controller_id=c.entity_id,defense=4,evasion=1,data_state='not_applicable',bot_id='bot');S.observe(self.e,node,reason='actual dependent node')
  value=json.loads((ROOT/'data/examples/control-remote.json').read_text(encoding='utf8'))[1];value['requirements']=[]
  binding=dict(devices=[],avatar_id='child/avatar',node_id='command-node',recipient_id=None,communication_source=None,component_id=None)
  self.e.connect_remote_control(c,'bot',value,binding,route_id='dependent-command',connected=True,reason='actual dependent avatar command path')
  machine=json.loads((ROOT/'data/examples/control-vehicle.json').read_text(encoding='utf8'))[1];machine['pilot']['requirements']=[]
  out=self.e.operate_machine(c,'bot',machine,command='move',request_id='before-eject',path=[[7,4],[8,4]],body_eligible=True,reason='actual dependent command',remote_route='dependent-command');self.assertTrue(out['passed'])
  self.e.exit_network(self.a,'avatar',request_id='forced-parent',reason='actual anchor ejection',forced=True);self.assertEqual(self.e.remote_control_routes(c)['dependent-command']['status'],'closed');before=self.snap()
  with self.assertRaisesRegex(ValueError,'closed'):self.e.operate_machine(c,'bot',machine,command='move',request_id='after-eject',path=[[8,4],[9,4]],body_eligible=True,reason='actual later dependent command',remote_route='dependent-command')
  self.assertEqual(before,self.snap())
 def test_forced_exit_can_complete_after_current_interface_source_is_withdrawn(self):
  self.a.spec['skills']['기술학']=1;G.grant(self.a,'capabilities','접속','fixture:interface','fixture');self.enter(entry_basis='interface')
  G.transition(self.e,self.a,lambda e,c:G.revoke(c,'fixture:interface'));self.e.exit_network(self.a,'avatar',request_id='forced',reason='actual interface loss ejection',forced=True)
  self.assertEqual(self.e._physical_objects['avatar']['status'],'ejected');self.assertTrue(W.validate_world(self.e)['valid'])


if __name__=='__main__':unittest.main()
