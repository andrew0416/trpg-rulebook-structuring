"""Observable separate digital damage, programs, data and native-clock recovery."""
from pathlib import Path
from copy import copy,deepcopy
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_foundation_network_connection as _fixture_test_foundation_network_connection
from state_codec import dump_engine,load_engine,StateCodecError
import network_integrity as I,special_entities as S,world_entities as W,roll_context as R,recovery_resolution as REC


class IntegrityTests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_foundation_network_connection.ConnectionTests.setUpClass.__func__)
 trainer=_fixture_test_foundation_network_connection.ConnectionTests.trainer
 def setUp(self):
  _fixture_test_foundation_network_connection.ConnectionTests.setUp(self);self.e.enter_network(self.a,'network',avatar_id='avatar',request_id='entry/a',access_established=True,reason='actual operator network entry')
  self.t=self.trainer(self.poly,'target');self.t.spec['skills'].update({'기술학':4,'집중':3});self.e.gm.add_combatant(self.t,pos=(3,1),side='enemy',reason='actual separate digital target');self.e.end_of_turn(self.a);self.e.start_of_turn(self.t)
  self.e.enter_network(self.t,'network',avatar_id='target-avatar',request_id='entry/t',access_established=True,reason='actual target network entry');self.e.end_of_turn(self.t);self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a)
  self.target=self.e._physical_objects['target-avatar']
 def policy(self,index=0):return json.loads((ROOT/'data/examples/network-integrity.json').read_text(encoding='utf8'))[index]
 def snap(self):return dump_engine(self.e)
 def next_turn(self,actor=None):_fixture_test_foundation_network_connection.ConnectionTests.next_turn(self,actor)
 def run_effect(self,value=None,target='target-avatar',request='digital/1',operator=None,avatar='avatar',fixed=None):
  operator=operator or self.a;value=value or self.policy();options={}
  if value['check'] is not None:
   body=W.actor_index(self.e).get(self.e._physical_objects[target].get('actor_id'));n=R.plan(self.e,operator,value['check']['skill'],purpose=value['check']['purpose'],target=body)['dice_count'];options={'fixed':fixed or [6]*n}
  return self.e.digital_operation(operator,avatar,target,value,request_id=request,reason='actual declared digital consequence',roll_options=options)
 def node(self,uid='core',node_type='server_core',integrity=20,maximum=20,anchor=None):
  row=dict(id=uid,kind='digital_node',location={'kind':'abstract','place_id':'network/root'},node_type=node_type,network_id='network',integrity=integrity,max_integrity=maximum,status='connected',anchor_id=anchor,controller_id=None,defense=8,evasion=2,data_state='intact' if node_type=='server_core' else 'not_applicable',bot_id=None)
  if node_type=='wall_of_thorns':row.update(integrity=25,max_integrity=25)
  if node_type=='data_snare':row.update(integrity=50,max_integrity=50,defense=0,evasion=0)
  S.observe(self.e,row,reason='actual digital node state');return self.e._physical_objects[uid]
 def program(self,uid='program',bind=True):
  rule=next(iter(self.poly.items_mech));W.register_object(self.e,uid,kind='item_instance',item_rule_id=rule,owner_id=self.a.entity_id,location={'kind':'unknown'},reason='actual item template instance declared as digital program')
  if bind:self.e._physical_objects['avatar']['program_ids'].append(uid)
  return {'instance_id':uid,'item_rule_id':rule,'consume':True}
 def test_actual_technology_roll_ignores_ordinary_defense_and_reduction(self):
  physical=(self.a.hp,self.t.hp,self.a.pos,self.t.pos);out=self.run_effect();self.assertEqual(out['check']['faces'],(6,6,6,6));self.assertEqual(out['requested'],24);self.assertEqual(self.target['integrity'],16)
  self.assertEqual((out['derivation']['defense'],out['derivation']['reduction']),(0,0));self.assertEqual(physical,(self.a.hp,self.t.hp,self.a.pos,self.t.pos));self.assertEqual(self.a.budget['standard'],0)
 def test_ordinary_damage_uses_actual_digital_defense_and_temporary_pool_before_integrity(self):
  self.target['temp_integrity']=3;physical=(self.t.hp,self.t.temp_hp);out=self.run_effect(self.policy(1));self.assertEqual(out['requested'],8);self.assertEqual((self.target['integrity'],self.target['temp_integrity']),(35,0));self.assertEqual(physical,(self.t.hp,self.t.temp_hp))
 def test_actual_defensive_feature_focus_is_selected_exception_to_technology(self):
  self.t.spec['edges']=['방어적 해킹'];value=self.policy();value['effect']['defensive_feature']={'source':value['source'],'names':['방어적 해킹','Defensive Hacking'],'skill':'집중'}
  out=self.run_effect(value);self.assertEqual(out['requested'],21);self.assertEqual(out['derivation']['reduction'],3);self.assertEqual(self.target['integrity'],19)
 def test_optional_trainer_digital_stats_control_ordinary_damage_not_physical_stats(self):
  row=deepcopy(self.target);row['optional_trainer_stats']=True;S.observe(self.e,row,reason='actual selected digital trainer stat option');out=self.run_effect(self.policy(1));self.assertEqual(out['derivation']['defense'],9);self.assertEqual(out['requested'],9);self.assertEqual(self.t.stats['def'],10)
 def test_technology_damage_needs_actual_technology_check_not_supplied_total(self):
  value=self.policy();value['check']=None;value['effect']['amount']={'provider':'declared','value':100};before=self.snap()
  with self.assertRaisesRegex(ValueError,'actual native Technology'):self.run_effect(value)
  self.assertEqual(before,self.snap())
 def test_actual_identity_same_network_and_digital_geometry_precede_cost(self):
  before=self.snap()
  with self.assertRaises(ValueError):self.run_effect(operator=copy(self.a))
  with self.assertRaisesRegex(ValueError,'registered'):self.e.digital_operation(self.a,'avatar','missing',self.policy(),request_id='missing',reason='missing actual target')
  value=self.policy();value['range']=6
  with self.assertRaisesRegex(ValueError,'mapped'):self.run_effect(value)
  self.assertEqual(before,self.snap());row=deepcopy(self.target);row['network_id']='other-network';S.observe(self.e,row,reason='actual different network');before=self.snap()
  with self.assertRaisesRegex(ValueError,'same actual network'):self.run_effect()
  self.assertEqual(before,self.snap())
 def test_zero_integrity_ejects_and_waits_for_real_recovery_without_reconnecting(self):
  self.target['integrity']=14;before=self.t.hp;out=self.run_effect();self.assertEqual((self.target['status'],self.target['integrity']),('ejected',0));self.assertEqual(out['ejected'],['target-avatar']);self.assertEqual(self.t.hp,before)
  self.e.end_of_turn(self.a);self.e.start_round(self.e.everyone);self.e.advance_time(9);self.assertEqual(self.target['integrity'],0);self.e.advance_time(1);self.assertEqual((self.target['integrity'],self.target['status']),(1,'ejected'))
  self.e.start_of_turn(self.t);self.e.enter_network(self.t,'network',avatar_id='target-avatar',request_id='reentry',access_established=True,reason='actual recovered reentry');self.assertEqual(self.target['status'],'connected');self.assertEqual(self.target['integrity'],1)
 def test_positive_early_repair_does_not_bypass_recorded_reentry_deadline(self):
  self.target['integrity']=14;self.run_effect();REC.repair_integrity(self.e,'target-avatar',8,source=self.policy()['source'],eligible=True,reason='actual early authorized repair');self.assertEqual(self.target['integrity'],8)
  self.e.end_of_turn(self.a);self.e.start_of_turn(self.t);before=self.snap()
  with self.assertRaisesRegex(ValueError,'interval'):self.e.enter_network(self.t,'network',avatar_id='target-avatar',request_id='early',access_established=True,reason='too early reentry')
  self.assertEqual(before,self.snap())
 def test_existing_integrity_repair_consumer_is_capped_and_never_heals_body_hp(self):
  self.target['integrity']=37;before=self.t.hp;out=self.run_effect(self.policy(3));self.assertEqual(out['applied'],3);self.assertEqual(self.target['integrity'],40);self.assertEqual(self.t.hp,before)
 def test_temporary_program_consumes_actual_instance_once_and_expires_its_contribution(self):
  value=self.policy(2);value['program']=self.program();self.target['temp_integrity']=3;before=(self.t.hp,self.t.temp_hp);out=self.run_effect(value);self.assertEqual(self.target['temp_integrity'],20);self.assertEqual(out['program_id'],'program');self.assertTrue(self.e._physical_objects['program']['consumed'])
  self.assertEqual(self.run_effect(value),out);self.e.advance_time(9);self.assertEqual(self.target['temp_integrity'],20);self.e.advance_time(1);self.assertEqual(self.target['temp_integrity'],3);self.assertEqual(before,(self.t.hp,self.t.temp_hp))
  self.next_turn();before=self.snap()
  with self.assertRaisesRegex(ValueError,'consumed'):self.run_effect(value,request='second')
  self.assertEqual(before,self.snap())
 def test_unbound_physical_item_cannot_supply_digital_program_effect(self):
  value=self.policy(2);value['program']=self.program(bind=False);before=self.snap()
  with self.assertRaisesRegex(ValueError,'avatar-bound'):self.run_effect(value)
  self.assertEqual(before,self.snap())
 def test_consumed_temporary_provider_and_expiration_preserve_remaining_legacy_pool(self):
  self.target['temp_integrity']=3;self.run_effect(self.policy(2));self.e.end_of_turn(self.a);self.e.start_of_turn(self.t)
  value=self.policy(1);value['effect']['amount']['value']=15
  self.run_effect(value,target='target-avatar',operator=self.t,avatar='target-avatar',request='self-digital-hit');self.assertEqual(self.target['temp_integrity'],17)
  self.e.advance_time(10);self.assertEqual(self.target['temp_integrity'],3);self.assertEqual(self.target['integrity'],40)
 def test_ordinary_server_damage_corrupts_data_and_cannot_be_safe_extraction(self):
  core=self.node(integrity=30,maximum=30);out=self.run_effect(self.policy(1),target='core');self.assertEqual(core['data_state'],'corrupted');self.assertEqual(core['integrity'],20)
  self.next_turn();value=self.policy();value['effect']['data_outcome']='extracted';before=self.snap()
  with self.assertRaisesRegex(ValueError,'cannot be certified'):self.run_effect(value,target='core',request='false-extraction')
  self.assertEqual(before,self.snap());self.assertNotEqual(core['data_state'],'extracted')
 def test_technology_finishing_core_safely_extracts_and_disables_anchored_nodes(self):
  core=self.node();wall=self.node('wall','wall_of_thorns',anchor='core');value=self.policy();value['effect']['data_outcome']='extracted';out=self.run_effect(value,target='core')
  self.assertEqual((core['integrity'],core['status'],core['data_state']),(0,'disabled','extracted'));self.assertEqual(wall['status'],'disabled');self.assertEqual(out['ejected'],['core','wall']);self.assertEqual(wall['integrity'],25)
 def test_safe_data_choice_uses_actual_finishing_receipt_and_cannot_repeat_payout(self):
  core=self.node();out=self.run_effect(target='core');self.assertEqual(core['data_state'],'intact');self.next_turn();value=self.policy(4);value['effect']['outcome']='modified';out=self.run_effect(value,target='core',request='choose-data');self.assertEqual(core['data_state'],'modified');self.assertEqual(out['finishing_request_id'],'digital/1');before=self.snap()
  self.assertEqual(self.run_effect(value,target='core',request='choose-data'),out);self.assertEqual(before,self.snap());self.next_turn()
  with self.assertRaisesRegex(ValueError,'finishing receipt'):self.run_effect(value,target='core',request='repeat-data')
 def test_zero_observation_without_technology_producer_is_not_safe_data_permission(self):
  core=self.node();row=deepcopy(core);row.update(integrity=0,status='disabled');S.observe(self.e,row,reason='observed zero without actual producer');before=self.snap()
  with self.assertRaisesRegex(ValueError,'finishing receipt'):self.run_effect(self.policy(4),target='core')
  self.assertEqual(before,self.snap())
 def test_wall_only_technology_and_data_snare_is_not_real_extractable_core(self):
  self.node();wall=self.node('wall','wall_of_thorns',anchor='core');before=self.snap()
  with self.assertRaisesRegex(ValueError,'only Technology'):self.run_effect(self.policy(1),target='wall')
  self.assertEqual(before,self.snap());snare=self.node('snare','data_snare');value=self.policy();value['effect']['data_outcome']='extracted'
  out=self.run_effect(value,target='snare')
  self.assertTrue(out['false_core_revealed']);self.assertEqual(snare['data_state'],'not_applicable');self.assertEqual(snare['integrity'],26)
 def test_explicit_physical_hp_redirection_does_not_eject_positive_integrity(self):
  self.t.hp=5;value=self.policy(1);value['effect'].update(damage_kind='physical_hp',multiplier=[1,2]);out=self.run_effect(value);self.assertEqual(out['physical_after'],1);self.assertEqual(self.target['integrity'],40);self.assertEqual(self.target['status'],'connected')
  self.next_turn();value['id']='authored-stronger-physical-packet';value['effect']['amount']['value']=100;out=self.run_effect(value,request='physical-zero');self.assertEqual(out['requested'],44);self.assertEqual(self.t.hp,-43);self.assertTrue(self.t.fainted);self.assertEqual(self.target['integrity'],40);self.assertEqual(self.target['status'],'connected')
 def test_json_gm_restore_preserves_real_temporary_program_and_recovery_deadline(self):
  self.run_effect(self.policy(2));encoded=self.snap();loaded=load_engine(self.poly,json.loads(json.dumps(encoded,ensure_ascii=False)));self.assertEqual(loaded._physical_objects['target-avatar']['temp_integrity'],20);self.assertEqual(getattr(loaded,I.FIELD)['temporary']['target-avatar']['expires_at'],self.e.elapsed_seconds+10)
  self.e.gm.snapshot('digital');self.e.advance_time(10);self.e.gm.restore('digital',reason='restore actual digital barrier and clock');self.assertEqual(self.e._physical_objects['target-avatar']['temp_integrity'],20)
 def test_late_damage_and_program_consumption_error_roll_back_pools_actions_and_rng(self):
  self.target['integrity']=14;before=self.snap()
  with patch.object(S,'observe_batch',side_effect=RuntimeError('late digital ejection')):
   with self.assertRaises(RuntimeError):self.run_effect()
  self.assertEqual(before,self.snap());value=self.policy(2);value['program']=self.program();before=self.snap()
  with patch.object(W,'finish_physical_use',side_effect=RuntimeError('late actual program consumption')):
   with self.assertRaises(RuntimeError):self.run_effect(value)
  self.assertEqual(before,self.snap())
 def test_tampered_digital_pool_producer_rejects_world_codec_and_gm(self):
  self.run_effect(self.policy(2));getattr(self.e,I.FIELD)['temporary']['target-avatar']['current']=0;self.assertFalse(W.validate_world(self.e)['valid'])
  with self.assertRaises(StateCodecError):self.snap()
  with self.assertRaises(ValueError):self.e.gm.snapshot('bad')
 def test_resigned_temporary_metadata_requires_real_completed_program_provider(self):
  self.run_effect(self.policy(2));state=getattr(self.e,I.FIELD);row=state['temporary']['target-avatar'];row.pop('sha256');row['request_id']='invented-program';state['temporary']['target-avatar']=I._sign(row)
  self.assertFalse(W.validate_world(self.e)['valid'])
  with self.assertRaises(StateCodecError):self.snap()


if __name__=='__main__':unittest.main()
