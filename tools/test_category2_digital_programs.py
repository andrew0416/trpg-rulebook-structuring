"""Actual source-bound programs, false-core receipts and restored consumers."""
from copy import copy,deepcopy
from pathlib import Path
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_foundation_network_integrity as fixtures
import digital_programs as D,network_integrity as I,special_entities as S,world_entities as W
from state_codec import dump_engine,load_engine,StateCodecError


class DigitalProgramTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  fixtures.IntegrityTests.setUpClass.__func__(cls)
 trainer=fixtures.IntegrityTests.trainer
 setUp=fixtures.IntegrityTests.setUp
 next_turn=fixtures.IntegrityTests.next_turn
 run_effect=fixtures.IntegrityTests.run_effect
 node=fixtures.IntegrityTests.node
 policy=fixtures.IntegrityTests.policy
 snap=fixtures.IntegrityTests.snap
 def shield(self,uid='shield',bind=True,owner=None):
  rule=D.definition(self.e,'net_shield')['id']
  W.register_object(self.e,uid,kind='item_instance',item_rule_id=rule,
                    owner_id=owner or self.a.entity_id,location={'kind':'unknown'},
                    reason='actual possessed digital Net Shield program')
  if bind:self.e._physical_objects['avatar']['program_ids'].append(uid)
  return uid
 def use_shield(self,uid='shield',request='shield/use'):
  return D.net_shield(self.e,self.a,'avatar',uid,action='standard',request_id=request,
                       reason='actual source-bound digital protection')
 def snare(self):
  D.observe_data_snare(self.e,self.a,'avatar','snare',reason='actual installed malicious false-core data')
  return self.e._physical_objects['snare']
 def intrude(self,operator=None,avatar='avatar',request='snare/intrude'):
  value=self.policy();value['effect']['data_outcome']='extracted'
  return self.run_effect(value,target='snare',operator=operator,avatar=avatar,request=request)
 def test_net_shield_uses_the_exact_actual_program_and_keeps_physical_pools_separate(self):
  self.shield();self.a.temp_hp=11;self.e._physical_objects['avatar']['temp_integrity']=3
  physical=(self.a.hp,self.a.temp_hp,deepcopy(self.a.location));out=self.use_shield()
  self.assertEqual((out['source'],out['program_id'],out['applied']),('digital-program/net-shield','shield',17))
  self.assertEqual(self.e._physical_objects['avatar']['temp_integrity'],20)
  self.assertTrue(self.e._physical_objects['shield']['consumed']);self.assertEqual(self.a.budget['standard'],0)
  self.assertEqual(physical,(self.a.hp,self.a.temp_hp,self.a.location));before=self.snap()
  self.assertEqual(self.use_shield(),out);self.assertEqual(before,self.snap())
  self.next_turn();before=self.snap()
  with self.assertRaisesRegex(ValueError,'consumed'):self.use_shield(request='shield/reuse')
  self.assertEqual(before,self.snap())
 def test_net_shield_requires_bound_owned_program_and_rejects_generic_or_physical_items(self):
  self.shield(bind=False);before=self.snap()
  with self.assertRaisesRegex(ValueError,'avatar-bound'):self.use_shield()
  self.assertEqual(before,self.snap());self.e._physical_objects['avatar']['program_ids'].append('shield')
  self.e._physical_objects['shield']['owner_id']=self.t.entity_id;before=self.snap()
  with self.assertRaisesRegex(ValueError,'unavailable'):self.use_shield()
  self.assertEqual(before,self.snap());self.e._physical_objects['shield']['owner_id']=self.a.entity_id
  generic=fixtures.IntegrityTests.program(self,uid='generic');before=self.snap()
  with self.assertRaisesRegex(ValueError,'avatar-bound'):self.use_shield('generic')
  self.assertEqual(before,self.snap())
  with self.assertRaises(ValueError):D.net_shield(self.e,copy(self.a),'avatar','shield',action='standard',request_id='alias',reason='copied identity')
  value=self.policy(2);value.update(id='native/net-shield/shield',source='digital-program/net-shield')
  value['program']={'instance_id':'shield','item_rule_id':'digital-program/net-shield','consume':True}
  value['effect'].update(amount=99,seconds=None);before=self.snap()
  with self.assertRaisesRegex(ValueError,'20 temporary'):self.run_effect(value,target='avatar')
  self.assertEqual(before,self.snap())
 def test_net_shield_restores_durationless_provider_and_ends_when_absorbed(self):
  self.shield();out=self.use_shield()
  self.assertEqual(out['after'],20);self.assertEqual(out['applied'],20)
  encoded=self.snap();self.e.gm.snapshot('shield');self.e.advance_time(1)
  self.e.gm.restore('shield',reason='restore actual consumed program and barrier')
  restored=load_engine(self.poly,json.loads(json.dumps(encoded,ensure_ascii=False)))
  for e in (self.e,restored):
   self.assertEqual(e._physical_objects['avatar']['temp_integrity'],20)
   self.assertIsNone(getattr(e,I.FIELD)['temporary']['avatar']['expires_at'])
   self.assertTrue(e._physical_objects['shield']['consumed'])
  self.e.end_of_turn(self.a);self.e.start_of_turn(self.t)
  value=self.policy(1);value['effect']['amount']['value']=32
  physical=self.a.temp_hp;self.run_effect(value,target='avatar',operator=self.t,avatar='target-avatar',request='barrier/damage')
  self.assertEqual(self.a.temp_hp,physical);self.assertNotIn('avatar',getattr(self.e,I.FIELD)['temporary'])
  self.next_turn();self.shield('replacement');self.use_shield('replacement','replacement/use')
  self.assertEqual(self.e._physical_objects['avatar']['temp_integrity'],20)
 def test_net_shield_preserves_larger_pool_and_saved_grant_requires_consumption(self):
  self.shield();self.e._physical_objects['avatar']['temp_integrity']=35;out=self.use_shield()
  self.assertEqual((out['after'],out['applied']),(35,0))
  self.assertNotIn('avatar',getattr(self.e,I.FIELD)['temporary'])
  self.assertEqual(self.e._physical_objects['avatar']['temp_integrity'],35)
  self.e._physical_objects['shield']['consumed']=False
  self.assertFalse(W.validate_world(self.e)['valid'])
  with self.assertRaises(StateCodecError):self.snap()
  with self.assertRaises(ValueError):self.e.gm.snapshot('unconsumed-grant')
 def test_data_snare_redirects_intrusion_to_real_integrity_and_is_recognized_per_user(self):
  snare=self.snare();core=self.node();physical=(self.a.hp,self.t.hp)
  self.assertEqual((snare['integrity'],snare['max_integrity'],snare['defense'],snare['evasion']),(50,50,0,0))
  out=self.intrude();self.assertTrue(out['false_core_revealed']);self.assertEqual(snare['integrity'],50);self.assertEqual(self.e._physical_objects['avatar']['integrity'],16)
  self.assertEqual(snare['data_state'],'not_applicable');self.assertEqual(core['data_state'],'intact')
  self.assertNotIn('snare',getattr(self.e,I.FIELD)['data_permissions'])
  self.assertEqual(D.known_data_snares(self.e,self.a,'avatar'),{'snare':'snare/intrude'})
  self.assertEqual(D.known_data_snares(self.e,self.t,'target-avatar'),{})
  before=self.snap();self.assertEqual(self.intrude(),out);self.assertEqual(before,self.snap())
  self.next_turn();before=self.snap()
  with self.assertRaisesRegex(ValueError,'recognized false core'):self.intrude(request='known-snare')
  self.assertEqual(before,self.snap())
  self.e.end_of_turn(self.a);self.e.start_of_turn(self.t)
  self.intrude(operator=self.t,avatar='target-avatar',request='target/snare-intrude')
  self.assertEqual(snare['integrity'],50);self.assertEqual(self.e._physical_objects['target-avatar']['integrity'],16)
  self.next_turn();value=self.policy(1);value['effect']['amount']['value']=50
  damage=self.run_effect(value,target='snare',request='ordinary/snare-destruction')
  self.assertEqual(damage['requested'],50);self.assertEqual(damage['derivation']['reduction'],0)
  self.assertEqual((snare['integrity'],snare['status']),(0,'disabled'));self.assertEqual(physical,(self.a.hp,self.t.hp))
  self.assertEqual(core['data_state'],'intact')
 def test_false_core_recognition_survives_json_and_gm_restore_without_real_data_permission(self):
  self.snare();self.intrude();encoded=self.snap();self.e.gm.snapshot('false-core')
  self.next_turn();self.run_effect(self.policy(1),target='snare',request='discarded-damage')
  self.e.gm.restore('false-core',reason='restore actual false-core identity and recognized user')
  restored=load_engine(self.poly,json.loads(json.dumps(encoded,ensure_ascii=False)))
  for e in (self.e,restored):
   a=W.actor_index(e)[self.a.entity_id]
   self.assertEqual(D.known_data_snares(e,a,'avatar'),{'snare':'snare/intrude'})
   self.assertEqual(e._physical_objects['snare']['integrity'],50);self.assertEqual(e._physical_objects['avatar']['integrity'],16)
   self.assertNotIn('snare',getattr(e,I.FIELD)['data_permissions'])
  before=self.snap()
  with self.assertRaisesRegex(ValueError,'cannot reset'):self.snare()
  self.assertEqual(before,self.snap())
 def test_late_program_consumption_or_snare_destruction_rolls_back_all_actual_state(self):
  self.shield();before=self.snap()
  with patch.object(W,'finish_physical_use',side_effect=RuntimeError('late program failure')):
   with self.assertRaisesRegex(RuntimeError,'late program'):self.use_shield()
  self.assertEqual(before,self.snap());self.snare();row=deepcopy(self.e._physical_objects['snare']);row['integrity']=20
  S.observe(self.e,row,reason='actual prior packet damage');before=self.snap()
  with patch.object(I,'_node_end',side_effect=RuntimeError('late false-core destruction')):
   with self.assertRaisesRegex(RuntimeError,'late false-core'):self.run_effect(self.policy(1),target='snare',request='ordinary/late-destruction')
  self.assertEqual(before,self.snap());self.assertEqual(D.known_data_snares(self.e,self.a,'avatar'),{})
 def test_false_core_cannot_claim_real_data_or_forged_recognition_in_saved_state(self):
  self.snare();row=deepcopy(self.e._physical_objects['snare']);row['data_state']='intact';before=self.snap()
  with self.assertRaisesRegex(ValueError,'false core'):S.observe(self.e,row,reason='invalid real-data claim')
  self.assertEqual(before,self.snap());self.run_effect(self.policy(1),target='snare')
  state=getattr(self.e,I.FIELD);saved=state['requests']['digital/1'];saved.pop('sha256')
  saved['result'].update(false_core_revealed=True,attempted_data_outcome='extracted');state['requests']['digital/1']=I._sign(saved)
  self.assertFalse(W.validate_world(self.e)['valid'])
  with self.assertRaises(StateCodecError):self.snap()
  with self.assertRaises(ValueError):self.e.gm.snapshot('forged-recognition')


if __name__=='__main__':unittest.main()
