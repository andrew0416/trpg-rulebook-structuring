"""Category 2 identity/relations/physical-location integration; not whole-scope proof."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
from grid import Grid
import world_entities as W
import pokemon_party as P
import capability_actions as CAP
import state_grants as G


class WorldTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='core')
 def actor(self,uid,kind='trainer',owner=None):
  spec={'id':uid,'name':'same-name','kind':kind,'level':5,'stats':dict(hp=10,atk=10,**{'def':10},spa=10,spd=10,spe=10),'pos':(1,1),'movement':{'land':5,'power':6},'skills':{'육상':2},'moves':[],'abilities':[]}
  if owner is not None:spec['trainer_id']=owner.spec['id']
  return Combatant(self.r,spec)
 def test_lifecycle_flags_distinguish_disabled_suppressed_and_false_destruction(self):
  obj={'destroyed':False,'disabled':True,'suppressed':{'source':'fixture'}}
  self.assertEqual(W.physical_lifecycle(obj),{'consumed':False,'destroyed':False,'disabled':True,'suppressed':True})
  W.require_usable_object(obj)
  obj['destroyed']=True
  with self.assertRaisesRegex(ValueError,'destroyed'):W.require_usable_object(obj)
  obj['consumed']={'source':'fixture'}
  with self.assertRaisesRegex(ValueError,'distinct terminal'):W.physical_lifecycle(obj)

 def test_terminal_record_requires_actual_detached_instance(self):
  W.register_object(self.e,'object/terminal',location={'kind':'unknown'},reason='observed')
  obj=self.e._physical_objects['object/terminal']
  evidence={'source':'explicit destruction','former_holder_id':self.a.entity_id}
  with self.assertRaisesRegex(ValueError,'actual registered'):
   W.finish_physical_use(self.e,deepcopy(obj),'destroyed',evidence)
  obj['equipped_by']=self.a.entity_id;before=deepcopy(obj)
  with self.assertRaisesRegex(ValueError,'release active'):
   W.finish_physical_use(self.e,obj,'destroyed',evidence)
  self.assertEqual(obj,before);obj.pop('equipped_by')
  result=W.finish_physical_use(self.e,obj,'destroyed',evidence)
  result['source']='caller mutation'
  self.assertEqual(obj['destroyed']['source'],'explicit destruction')
  with self.assertRaisesRegex(ValueError,'destroyed'):
   W.finish_physical_use(self.e,obj,'consumed',{'source':'item/test','by_actor_id':self.a.entity_id,'at':0})

 def setUp(self):
  self.e=Engine(self.r,42);self.a=self.actor('trainer/a');self.b=self.actor('trainer/b');self.p=self.actor('pokemon/p','pokemon',self.a)
  self.e.everyone=self.e.gm.everyone=[self.a,self.b,self.p];self.e.grid=Grid(20,20)
 def policies(self):
  P.configure(self.e,self.a,mode='standard',reason='campaign storage chosen',roster=[self.p],storage={'kind':'center','id':'center/a'})
  P.configure(self.e,self.b,mode='standard',reason='campaign storage chosen',roster=[],storage={'kind':'professor','id':'prof/b'})
 def test_same_name_distinct_entities_and_alias_roster(self):
  self.assertEqual(len(W.actor_index(self.e)),3)
  self.e._time_actors=[self.p,self.p]
  self.assertTrue(W.validate_world(self.e)['valid'])
 def test_duplicate_id_off_field_reference_is_rejected(self):
  duplicate=self.actor('pokemon/p','pokemon',self.a);duplicate.on_field=False
  self.e.delayed=[{'target':duplicate}]
  with self.assertRaises(ValueError):W.actor_index(self.e)
  self.assertIn('duplicate_actor_id',[i['code'] for i in W.validate_world(self.e)['issues']])
 def test_actor_only_reachable_from_native_skill_event_is_in_world(self):
  from skill_feature_actions import SkillEvent
  self.e.everyone=self.e.gm.everyone=[self.a,self.b]
  self.e._ap_rolls={'observed':{'skill_event':SkillEvent(self.p,'skill/test',(),(),None)}}
  self.assertIs(W.actor_index(self.e)[self.p.entity_id],self.p)
  duplicate=self.actor('pokemon/p','pokemon',self.a);self.e.delayed=[{'target':duplicate}]
  with self.assertRaises(ValueError):W.actor_index(self.e)
 def test_missing_owner_and_controller_are_distinct_findings(self):
  self.p.spec['trainer_id']='missing';self.p.spec['controller']={'kind':'actor','id':'missing-control'}
  codes={i['code'] for i in W.validate_world(self.e)['issues']}
  self.assertTrue({'dangling_owner','dangling_controller'}<=codes)
 def test_unknown_or_abstract_never_invents_distance(self):
  self.a.location={'kind':'unknown'}
  self.assertIsNone(W.distance_known(self.a,self.b))
  with self.assertRaises(ValueError):W.grid_cell(self.a)
  W.observe_location(self.e,self.a,{'kind':'abstract','place_id':'forest/west'},reason='GM mapped abstract region')
  self.assertEqual(W.location_of(self.a),{'kind':'abstract','place_id':'forest/west'})
  self.assertIsNone(W.distance_known(self.a,self.b))
  with self.assertRaises(ValueError):_=self.a.pos
 def test_maps_do_not_share_distance_without_relationship(self):
  self.a.location={'kind':'grid','cell':(1,1),'map_id':'one'}
  self.b.location={'kind':'grid','cell':(1,1),'map_id':'two'}
  self.assertIsNone(W.distance_known(self.a,self.b))
 def test_controller_changes_no_owner_side_or_entitlement(self):
  before=(self.p.spec['trainer_id'],self.p.side,self.p.on_field,self.p.took_standard)
  W.set_controller(self.e,self.p,{'kind':'actor','id':self.b.spec['id']},reason='explicit temporary GM control')
  self.assertEqual(before,(self.p.spec['trainer_id'],self.p.side,self.p.on_field,self.p.took_standard))
  self.assertEqual(self.p.spec['controller']['id'],self.b.spec['id'])
 def test_object_and_actor_identity_spaces_do_not_collide(self):
  with self.assertRaises(ValueError):W.register_object(self.e,self.a.spec['id'],location={'kind':'unknown'},weight_kg=2,reason='crate')
  self.assertFalse(self.e._physical_objects)
 def test_two_item_instances_keep_same_rule_distinct(self):
  rule=next(iter(self.r.items_mech))
  for uid in ('item-instance/1','item-instance/2'):
   W.register_object(self.e,uid,kind='item_instance',item_rule_id=rule,owner_id=self.a.spec['id'],location={'kind':'unknown'},reason='observed actual owned copy')
  self.assertEqual(len(self.e._physical_objects),2)
  self.assertTrue(W.validate_world(self.e)['valid'])
 def test_equipment_instance_relative_location_and_holder_are_consistent(self):
  import items
  W.register_object(self.e,'claw',kind='item_instance',item_rule_id='item/선제공격손톱',owner_id=self.a.entity_id,location={'kind':'unknown'},reason='physical claw')
  items.register_item(self.e,self.a,'선제공격손톱',source_instance_id='claw')
  row=self.e._physical_objects['claw'];self.assertEqual(row['equipped_by'],self.a.entity_id)
  self.a.pos=(4,4);self.assertEqual(W.effective_location(self.e,row)['cell'],(4,4));self.assertTrue(W.validate_world(self.e)['valid'])
  with self.assertRaises(ValueError):W.observe_location(self.e,row,{'kind':'grid','cell':(9,9)},reason='cannot independently relocate held gear')
  row['equipped_by']=self.b.entity_id
  self.assertIn('equipment_instance_mismatch',{i['code'] for i in W.validate_world(self.e)['issues']})
 def test_commit_of_same_registry_does_not_clear_live_instances(self):
  W.register_object(self.e,'crate',location={'kind':'unknown'},reason='crate');row=self.e._physical_objects['crate']
  W.commit_objects(self.e,self.e._physical_objects)
  self.assertIs(row,self.e._physical_objects['crate']);self.assertEqual(row['id'],'crate')
 def test_carry_connects_registry_and_release_does_not_invent_ground(self):
  self.e.gm.set_physical_object('crate',weight_kg=5,position=(2,1),reason='observed crate')
  self.e.gm.set_carried_objects(self.a,[{'id':'crate','weight_kg':5}],reason='crate lifted')
  row=self.e._physical_objects['crate']
  self.assertEqual(row['carrier_id'],self.a.spec['id']);self.assertNotIn('pos',row)
  self.a.pos=(4,3);self.assertEqual(W.effective_location(self.e,row)['cell'],(4,3))
  self.assertTrue(W.validate_world(self.e)['valid'])
  self.e.gm.set_carried_objects(self.a,[],reason='released without observed landing')
  row=self.e._physical_objects['crate'];self.assertNotIn('carrier_id',row);self.assertEqual(W.location_of(row)['kind'],'unknown')
 def test_second_carrier_fails_before_load_or_registry_mutation(self):
  self.e.gm.set_carried_objects(self.a,[{'id':'crate','weight_kg':5}],reason='first carrier')
  before=deepcopy((self.b.spec,self.e._physical_objects))
  with self.assertRaises(ValueError):self.e.gm.set_carried_objects(self.b,[{'id':'crate','weight_kg':5}],reason='contradictory second carrier')
  self.assertEqual(before,(self.b.spec,self.e._physical_objects))
 def test_unmapped_drag_fails_before_resource_or_random(self):
  W.register_object(self.e,'crate',location={'kind':'unknown'},weight_kg=150,reason='known object, location unknown')
  before=(deepcopy(self.a.spec),self.e.rng.getstate())
  with self.assertRaises(ValueError):CAP.drag_object(self.e,self.a,object_id='crate',destination=(2,2),action_cost='shift',reason='attempt',round_id='r')
  self.assertEqual(before,(self.a.spec,self.e.rng.getstate()))
 def test_transfer_keeps_identity_owner_controller_side_separate(self):
  self.policies();self.p.spec['controller']={'kind':'player','id':'player/alice'};before=(self.p.entity_id,self.p.side,deepcopy(self.p.spec['controller']))
  out=P.transfer(self.e,self.a,target=self.p,new_owner=self.b,reason='agreed actual trade',request_id='trade/1')
  self.assertEqual(before,(self.p.entity_id,self.p.side,self.p.spec['controller']))
  self.assertEqual(self.p.spec['trainer_id'],self.b.spec['id']);self.assertNotIn(self.p.entity_id,self.a.spec['pokemon_registry'])
  self.assertIn(self.p.entity_id,self.b.spec['pokemon_registry']);self.assertFalse(self.p.on_field)
  self.assertTrue(W.validate_world(self.e)['valid'])
  P.require_participation(self.e,self.p)
  self.assertEqual(P.transfer(self.e,self.a,target=self.p,new_owner=self.b,reason='agreed actual trade',request_id='trade/1'),out)
 def test_transfer_overflow_goes_to_real_storage(self):
  self.policies();P.configure(self.e,self.b,mode='custom',limit=0,reason='no travelling slots',roster=[],storage={'kind':'center','id':'remote'})
  P.transfer(self.e,self.a,target=self.p,new_owner=self.b,reason='actual trade',request_id='trade/1')
  self.assertEqual(self.p.spec['party_location']['location'],'storage')
  with self.assertRaises(ValueError):P.require_participation(self.e,self.p)
 def test_transfer_releases_only_former_owner_grants_and_refunds_once(self):
  self.policies();self.p.spec['tutor_points']=3
  G.grant(self.p,'moves','move/몸통박치기','owner/training','feature',owner_id=self.a.entity_id,lifetime='your_pokemon',rule_id='test/source',tutor_points=2)
  G.grant(self.p,'moves','move/몸통박치기','independent/machine','machine')
  G.grant(self.p,'moves','move/울음소리','owner/other','feature',owner_id=self.a.entity_id,lifetime='owner_bound',rule_id='test/source',tutor_points=1)
  P.transfer(self.e,self.a,target=self.p,new_owner=self.b,reason='actual trade',request_id='trade/1')
  self.assertEqual(self.p.spec['tutor_points'],6);self.assertIn('move/몸통박치기',self.p.moves);self.assertNotIn('move/울음소리',self.p.moves)
  P.transfer(self.e,self.a,target=self.p,new_owner=self.b,reason='actual trade',request_id='trade/1')
  self.assertEqual(self.p.spec['tutor_points'],6)
 def test_native_grooming_owner_effect_is_removed_but_daily_history_survives(self):
  self.policies();self.a.spec['edges']=['edge/미용사'];self.a.spec['skills'].update({'포켓몬학':3,'일반 지식':3});self.a.spec['items']={'미용사 킷':1}
  self.e.pokemon_activity(self.a,'groom',targets=[self.p],safe=True);self.p.spec['experience_training_day']=0
  self.assertEqual(self.p.spec['grooming']['trainer_id'],self.a.entity_id)
  receipt=P.transfer(self.e,self.a,target=self.p,new_owner=self.b,reason='actual trade',request_id='trade/1')
  self.assertNotIn('grooming',self.p.spec);self.assertNotIn('training_credit',self.p.spec)
  self.assertEqual(self.p.spec['experience_training_day'],0)
  self.assertIn('grooming',receipt['cleanup']['legacy_owner_effects_removed'])
 def test_untracked_owner_effect_blocks_atomic_transfer(self):
  self.policies();self.p.spec['pushed_skill']={'trainer_id':self.a.entity_id,'skill':'육상','source':'old/training'}
  before=deepcopy((self.a.spec,self.b.spec,self.p.spec))
  with self.assertRaises(ValueError):P.transfer(self.e,self.a,target=self.p,new_owner=self.b,reason='trade',request_id='trade/1')
  self.assertEqual(before,(self.a.spec,self.b.spec,self.p.spec));self.assertFalse(getattr(self.e,'_world_relation_receipts',{}))
 def test_off_field_owner_can_resolve_through_clock_graph(self):
  self.policies();self.e.everyone=self.e.gm.everyone=[self.p];self.e._time_actors=[self.a,self.b]
  P.require_participation(self.e,self.p)
  self.assertTrue(W.validate_world(self.e)['valid'])
 def test_observation_and_carry_preserve_actual_object_references(self):
  self.e.gm.set_physical_object('crate',weight_kg=5,position=(2,1),reason='observed crate')
  registry=self.e._physical_objects;instance=registry['crate']
  self.a.custom_conditions['observed_object']=instance;self.e.delayed=[{'object':instance}]
  self.e.gm.set_physical_object('crate',weight_kg=6,position=(3,1),reason='new observation')
  self.assertIs(self.e._physical_objects,registry);self.assertIs(registry['crate'],instance)
  self.assertEqual(self.e.delayed[0]['object']['weight_kg'],6)
  self.e.gm.set_carried_objects(self.a,[{'id':'crate','weight_kg':6}],reason='lifted')
  self.assertIs(registry['crate'],instance);self.assertIs(self.a.custom_conditions['observed_object'],instance)
  self.assertEqual(self.e.delayed[0]['object']['carrier_id'],self.a.entity_id)
  self.e.gm.set_carried_objects(self.a,[],reason='released')
  self.assertIs(registry['crate'],instance);self.assertNotIn('carrier_id',instance)
 def test_world_check_invokes_actor_structural_contract(self):
  self.p.temp_hp=-1
  self.assertIn('actor_state',{i['code'] for i in W.validate_world(self.e)['issues']})
 def test_repeat_snapshot_restores_carry_and_transfer_graph(self):
  self.policies();self.e.gm.set_carried_objects(self.a,[{'id':'crate','weight_kg':5}],reason='actual carrier')
  self.e.gm.snapshot('before-world')
  for _ in range(2):
   P.transfer(self.e,self.a,target=self.p,new_owner=self.b,reason='trade',request_id='trade/1')
   self.e.gm.set_carried_objects(self.a,[],reason='drop')
   self.e.gm.restore('before-world')
   self.assertEqual(self.p.spec['trainer_id'],self.a.entity_id)
   self.assertEqual(self.e._physical_objects['crate']['carrier_id'],self.a.entity_id)
   self.assertFalse(getattr(self.e,'_world_relation_receipts',{}))
   self.assertTrue(W.validate_world(self.e)['valid'])

if __name__=='__main__':unittest.main()
