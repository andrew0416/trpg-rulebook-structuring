"""SPOL-004 exact ordinary/robotic physical selection and native consumers."""
from copy import copy,deepcopy
from pathlib import Path
import json
import tempfile
import unittest
import test_category2_optional_physical_equipment as _fixture_test_category2_optional_physical_equipment
from engine import Rules
import capability_actions as LOAD
import csv_item_capability_contracts as CAPABILITIES
import items as ITEMS
import movement_actions as MOVEMENT
import optional_physical_equipment as OPTIONAL
import state_grants as GRANTS
import world_entities as WORLD

ROOT=Path(__file__).resolve().parents[1]


class SpaceSuitTests(_fixture_test_category2_optional_physical_equipment.OptionalPhysicalEquipmentTests):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='all')

 def suit(self,e,c,uid,variant):
  WORLD.register_object(e,uid,kind='item_instance',item_rule_id='item/우주복',owner_id=c.entity_id,
      location={'kind':'unknown'},reason='actual owned SPOL004 suit')
  # Observation of an already selected physical variant, not a new purchase.
  e._physical_objects[uid][OPTIONAL.STATE]={'schema_version':1,'space_suit_variant':variant}
  ITEMS.register_item(e,c,'item/우주복',source_instance_id=uid)
  return next(x for x in c.registry if x.get('type')=='optional_physical_equipment' and x.get('instance_id')==uid)

 def test_recorded_robotic_variant_changes_the_actual_registered_weight_cost_and_hazard_protection(self):
  for variant,weight,extra,hazard in [('ordinary',200,0,False),('robotic',100,2000,True)]:
   with self.subTest(variant=variant):
    e,c,_,_=self.fixture();row=self.suit(e,c,'spacesuit/'+variant,variant)
    self.assertEqual(row['weight_lb'],weight)
    self.assertEqual(row['additional_cost'],extra)
    self.assertEqual(row['space_suit_variant'],variant)
    self.assertIn('진공면역',GRANTS.effective_capabilities(c))
    self.assertEqual(CAPABILITIES.has(c,'함정면역'),hazard)
    expected=None if hazard else 'high'
    self.assertEqual(CAPABILITIES.toxic_environment(c,'high',{'high':['harm']})['effective'],expected)
    self.assertEqual(MOVEMENT.capabilities(e,c,environment=False).get('levitate'),4)
    obj=e._physical_objects[row['instance_id']]
    self.assertAlmostEqual(obj['weight_kg'],weight*0.45359237)
    c.spec.setdefault('movement',{})['power']=6;c.spec['power_basis']='current'
    result=LOAD.set_carried(e,c,[{'id':obj['id'],'weight_kg':obj['weight_kg']}],'carry exact actual suit weight')
    self.assertAlmostEqual(result['weight_kg'],weight*0.45359237)
    e.gm.snapshot('suit');loaded=self.restored(e);q=next(x for x in loaded.everyone if x.entity_id==c.entity_id)
    self.assertEqual(next(x for x in q.registry if x.get('instance_id')==obj['id'])['weight_lb'],weight)
    self.assertEqual(CAPABILITIES.has(q,'함정면역'),hazard)
    key=next(key for key,value in q._item_reg.items() if value.get('instance_id')==obj['id'])
    ITEMS.unregister_item(loaded,q,registration_key=key)
    self.assertNotIn('진공면역',GRANTS.effective_capabilities(q));self.assertFalse(CAPABILITIES.has(q,'함정면역'))
    self.assertNotEqual(MOVEMENT.capabilities(loaded,q,environment=False).get('levitate'),4)
    self.assertAlmostEqual(loaded._physical_objects[obj['id']]['weight_kg'],weight*0.45359237)
    self.assertTrue(loaded.validate_state()['valid'])

 def test_invalid_recorded_variant_is_rejected_before_physical_equip_or_grants(self):
  e,c,_,_=self.fixture();uid='spacesuit/invalid'
  WORLD.register_object(e,uid,kind='item_instance',item_rule_id='item/우주복',owner_id=c.entity_id,
      location={'kind':'unknown'},reason='actual owned invalid variant observation')
  e._physical_objects[uid][OPTIONAL.STATE]={'schema_version':1,'space_suit_variant':'invented'}
  before=deepcopy((c.spec,c.registry,e._physical_objects,e.rng.getstate()))
  with self.assertRaises(ValueError):ITEMS.register_item(e,c,'item/우주복',source_instance_id=uid)
  self.assertEqual((c.spec,c.registry,e._physical_objects,e.rng.getstate()),before)

 def test_actual_suit_vacuum_immunity_reaches_public_exposure_clock_and_withdrawal(self):
  import environmental_capabilities as ENVIRONMENT
  for variant in ('ordinary','robotic'):
   with self.subTest(variant=variant):
    e,c,_,_=self.fixture();self.suit(e,c,'spacesuit/native-vacuum/'+variant,variant)
    declaration=json.loads((ROOT/'data/examples/environment-derive.json').read_text(encoding='utf-8'))
    e.observe_environment('suit-vacuum',dict(gravity=1,pressure=0,air_available=False,medium='airless'),
        source=declaration['source'],reason='actual zero-pressure suit exposure region')
    e.bind_environment(c,declaration,reason='actual suit wearer environmental baseline')
    row=e.observe_vacuum_exposure(c,exposure_id='suit-vacuum/protected',exposed=True,reason='actual equipped suit exposure')
    self.assertIsNone(row['interval_seconds']);e.advance_time(10)
    self.assertEqual(c.injuries,0)
    self.assertFalse(c.spec[ENVIRONMENT.KEY]['vacuum_exposures']['suit-vacuum/protected']['pending'])
    e.observe_vacuum_exposure(c,exposure_id='suit-vacuum/protected',exposed=False,reason='close actual protected exposure')
    e=self.restored(e);c=next(q for q in e.everyone if q.entity_id==c.entity_id)
    uid='spacesuit/native-vacuum/'+variant
    key=next(k for k,v in c._item_reg.items() if v.get('instance_id')==uid)
    ITEMS.unregister_item(e,c,registration_key=key)
    row=e.observe_vacuum_exposure(c,exposure_id='suit-vacuum/unprotected',exposed=True,reason='actual suit source withdrawn')
    self.assertEqual(row['interval_seconds'],10);e.advance_time(10)
    pending=c.spec[ENVIRONMENT.KEY]['vacuum_exposures']['suit-vacuum/unprotected']['pending']
    self.assertEqual(len(pending),1)
    e.resolve_vacuum_injury_check(c,check_id=next(iter(pending)),injury_delta=1,reason='actual failed unprotected exposure check')
    self.assertEqual(c.injuries,1);self.assertTrue(e.validate_state()['valid']);self.restored(e)


 def test_public_variant_observation_requires_actual_owner_idle_object_and_persists_mass(self):
  e,c,other,_=self.fixture();uid='spacesuit/observed'
  WORLD.register_object(e,uid,kind='item_instance',item_rule_id='item/우주복',owner_id=c.entity_id,
      location={'kind':'unknown'},reason='actual owned suit before physical equip')
  before=deepcopy((c.spec,c.registry,e._physical_objects,e.rng.getstate()))
  for owner,variant,reason in [(other,'robotic','wrong owner'),(c,'invented','bad variant'),(c,'robotic','')]:
   with self.assertRaises(ValueError):OPTIONAL.configure_space_suit(e,owner,uid,variant,reason=reason)
   self.assertEqual((c.spec,c.registry,e._physical_objects,e.rng.getstate()),before)
  OPTIONAL.configure_space_suit(e,c,uid,'robotic',reason='observed robotic-era upgrade on owned suit')
  self.assertEqual(e._physical_objects[uid][OPTIONAL.STATE]['space_suit_variant'],'robotic')
  self.assertAlmostEqual(e._physical_objects[uid]['weight_kg'],45.359237)
  ITEMS.register_item(e,c,'item/우주복',source_instance_id=uid)
  before=deepcopy((c.spec,c.registry,e._physical_objects,e.rng.getstate()))
  with self.assertRaises(ValueError):OPTIONAL.configure_space_suit(e,c,uid,'ordinary',reason='cannot reconfigure equipped suit')
  self.assertEqual((c.spec,c.registry,e._physical_objects,e.rng.getstate()),before)
  e.gm.snapshot('robotic');loaded=self.restored(e)
  self.assertEqual(loaded._physical_objects[uid][OPTIONAL.STATE]['space_suit_variant'],'robotic')
  loaded._physical_objects[uid]['weight_kg']=90.718474
  self.assertFalse(loaded.validate_state()['valid'])

 def test_warm_policy_still_checks_actual_source_bytes_and_returns_an_independent_copy(self):
  selected=copy(self.r);cached=OPTIONAL.policy(selected)
  cached['rows']['item/우주복']['weight_lb']=1
  self.assertEqual(OPTIONAL.definition(selected,'item/우주복')['weight_lb'],200)
  with tempfile.TemporaryDirectory(prefix='optional-physical-source-') as tmp:
   root=Path(tmp);selected.root=str(root)
   rel='data/verification/category2-optional-clause-status.json';p=root/rel;p.parent.mkdir(parents=True)
   p.write_bytes((Path(self.r.root)/rel).read_bytes())
   source_files={row['file'] for item in OPTIONAL.policy(self.r)['rows'].values() for row in item['source']}
   source_files.add('input/db/inventory.csv')  # actual selected item definition, additional to clause prose
   for rel in source_files:
    p=root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((Path(self.r.root)/rel).read_bytes())
   self.assertEqual(OPTIONAL.definition(selected,'item/우주복')['weight_lb'],200)
   rel=next(x['file'] for x in OPTIONAL.policy(self.r)['rows']['item/우주복']['source'])
   p=root/rel;p.write_bytes(p.read_bytes()+b'\n')
   with self.assertRaisesRegex(ValueError,'source changed'):OPTIONAL.definition(selected,'item/우주복')


if __name__=='__main__':unittest.main()
