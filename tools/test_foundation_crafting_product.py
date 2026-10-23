"""Actual product invariants; authored examples are not literal rule credits."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_foundation_crafting_recipe as fixtures
import crafting_products as P,crafting_resources as R,items as I,world_entities as W,state_codec as CODEC
import acquisition_receipts as RECEIPTS


class ProductTests(unittest.TestCase):
 setUpClass=classmethod(fixtures.RecipeTests.setUpClass.__func__)
 setUp=fixtures.RecipeTests.setUp
 actor=fixtures.RecipeTests.actor
 own=fixtures.RecipeTests.own
 recipe=fixtures.RecipeTests.recipe
 ready=fixtures.RecipeTests.ready
 craft=fixtures.RecipeTests.craft
 snapshot=fixtures.RecipeTests.snapshot
 restored=fixtures.RecipeTests.restored
 def policy(self,owner=None,seconds=600,ownership='any_holder',identity='crafted:goggles'):
  value=json.loads((ROOT/'data/examples/crafting-product-policy.json').read_text(encoding='utf8'))
  value['instance_ids']=[identity];value['owner_id']=(owner or self.a).entity_id
  value['attachments'][0].update(seconds=seconds,ownership=ownership)
  return value
 def made(self,owner=None,seconds=600,ownership='any_holder'):
  recipe=self.ready();recipe['output']={'item_id':'item/방진고글','key':'item/방진고글'}
  policy=self.policy(owner,seconds,ownership);result=self.craft(recipe,product_policy=policy,event_id='make-one')
  return recipe,policy,result
 def equip(self,actor=None,identity='crafted:goggles',item='item/방진고글'):
  return I.equip_held(self.e,actor or self.a,item,source_instance_id=identity)
 def test_native_quantity_retains_same_actual_work_and_transformation_proof(self):
  recipe=self.ready();result=self.craft(recipe,event_id='ordinary')
  row=self.a.spec[P.KEY][result['production_id']]
  self.assertIs(row['transformation'],self.a.spec['resource_transformations'][0])
  self.assertEqual(self.e.activity_job_status(result['job_id'])['worked_seconds'],60)
  receipts=RECEIPTS.read(self.e,self.a);receipt=next(x for x in receipts if x['basis']=='native_crafting_product')
  self.assertEqual((receipt['provider_id'],receipt['completed_at']),(self.a.entity_id,60))
  self.assertEqual(receipt['native_record']['result']['count'],1)
 def test_physical_output_replaces_quantity_and_retains_actual_maker_attachment(self):
  recipe,policy,result=self.made();self.assertEqual(self.a.spec['items']['item/방진고글'],0)
  obj=self.e._physical_objects['crafted:goggles'];self.assertEqual(obj['crafting_origin']['maker_id'],self.a.entity_id)
  self.assertEqual(obj['crafting_origin']['attachments'][0]['effects'],[{'type':'save_mod','value':2}])
  self.equip();self.assertEqual(self.a.save_mod,2)
  self.assertEqual(result['product_instance_ids'],['crafted:goggles']);P.validate_world(self.e,W.actor_index(self.e))
 def test_two_physical_outputs_have_distinct_ids_and_no_extra_inventory_copy(self):
  recipe=self.ready();policy=self.policy();policy['instance_ids'].append('crafted:goggles:2')
  result=self.craft(recipe,count=2,product_policy=policy)
  self.assertEqual(len(result['product_instance_ids']),2);self.assertEqual(self.a.spec['items']['item/몬스터볼-2'],0)
  self.assertIsNot(self.e._physical_objects[policy['instance_ids'][0]],self.e._physical_objects[policy['instance_ids'][1]])
 def test_same_event_after_restore_returns_proof_without_cost_time_or_new_copy(self):
  recipe,policy,result=self.made();loaded=self.restored();actor=next(x for x in loaded.gm.everyone if x.entity_id==self.a.entity_id)
  before=CODEC.dump_engine(loaded)
  replay=loaded.craft_recipe(actor,recipe,product_policy=policy,event_id='make-one',reason='actual reviewed recipe duration')
  self.assertEqual(replay,result);self.assertEqual(before,CODEC.dump_engine(loaded))
  changed=deepcopy(recipe);changed['seconds']+=1
  with self.assertRaises(ValueError):loaded.craft_recipe(actor,changed,product_policy=policy,event_id='make-one',reason='actual reviewed recipe duration')
 def test_existing_identity_or_duplicate_instance_selection_rejects_before_work(self):
  recipe,policy,result=self.made();before=self.snapshot()
  with self.assertRaises(ValueError):self.craft(recipe,product_policy=policy,event_id='duplicate-output')
  self.assertEqual(before,self.snapshot())
  policy['instance_ids']=['new','new']
  with self.assertRaises(ValueError):self.craft(recipe,count=2,product_policy=policy)
  self.assertEqual(before,self.snapshot())
 def test_missing_actual_maker_permission_rejects_before_cost_and_output(self):
  recipe=self.ready();policy=self.policy();policy['attachments'][0]['requirement']['names']=['maker:unacquired']
  before=self.snapshot()
  with self.assertRaises(ValueError):self.craft(recipe,product_policy=policy)
  self.assertEqual(before,self.snapshot())
 def test_maker_bonus_expiry_uses_actual_clock_and_preserves_base_item_and_origin(self):
  self.made(seconds=10);self.equip();self.assertEqual(self.a.save_mod,2)
  self.e.advance_time(9,[self.a]);self.assertEqual(self.a.save_mod,2)
  self.e.advance_time(1,[self.a]);self.assertEqual(self.a.save_mod,0)
  self.assertTrue(I.equipment_options(self.a));self.assertTrue(self.e._physical_objects['crafted:goggles']['crafting_origin']['attachments'])
 def test_any_holder_attachment_moves_with_real_item_and_keeps_creator(self):
  self.made(owner=self.p,seconds=None);self.equip(self.p);self.assertEqual(self.p.save_mod,2)
  I.transfer_equipment(self.e,self.p,self.q,'crafted:goggles',consent_by=(self.p,))
  self.assertEqual((self.p.save_mod,self.q.save_mod),(0,2))
  self.assertEqual(self.e._physical_objects['crafted:goggles']['crafting_origin']['maker_id'],self.a.entity_id)
 def test_original_owner_and_creator_only_policies_do_not_become_portable_permissions(self):
  self.made(owner=self.p,ownership='original_owner');self.equip(self.p)
  I.transfer_equipment(self.e,self.p,self.q,'crafted:goggles',consent_by=(self.p,))
  self.assertEqual((self.p.save_mod,self.q.save_mod),(0,0))
  self.setUp();self.made(owner=self.p,ownership='creator_only');self.equip(self.p)
  self.assertEqual(self.p.save_mod,0)
 def test_snapshot_json_and_source_removal_keep_the_product_and_independent_bonus(self):
  recipe,policy,result=self.made();self.equip();self.e.gm.snapshot('maker-equipped')
  I.unregister_item(self.e,self.a,'item/방진고글');self.assertEqual(self.a.save_mod,0)
  self.e.gm.restore('maker-equipped');self.assertEqual(self.a.save_mod,2)
  loaded=self.restored();actor=next(x for x in loaded.gm.everyone if x.entity_id==self.a.entity_id)
  row=actor.spec[P.KEY][result['production_id']]
  self.assertIs(row['transformation'],actor.spec['resource_transformations'][0]);self.assertEqual(actor.save_mod,2)
  I.unregister_item(loaded,actor,'item/방진고글');self.assertEqual(actor.save_mod,0)
 def test_repair_consumes_new_cost_but_preserves_identity_maker_and_original_deadline(self):
  recipe,policy,result=self.made(seconds=200);obj=self.e._physical_objects['crafted:goggles']
  origin=deepcopy(obj['crafting_origin']);obj['disabled']=True
  repair={'mode':'repair','instance_ids':['crafted:goggles'],'owner_id':self.a.entity_id,'state':'intact','attachments':[]}
  self.craft(recipe,product_policy=repair,event_id='repair-one')
  self.assertIs(self.e._physical_objects['crafted:goggles'],obj);self.assertFalse(obj['disabled'])
  self.assertEqual(obj['crafting_origin'],origin);self.assertEqual(self.a.spec['items']['item/방진고글'],0)
  self.assertEqual((self.a.spec['money'],self.e.elapsed_seconds),(800,120));self.assertEqual(len(obj['crafting_repairs']),1)
  before=self.snapshot()
  with self.assertRaises(ValueError):self.craft(recipe,product_policy=repair,event_id='repair-again')
  self.assertEqual(before,self.snapshot())
 def test_physical_dismantle_consumes_same_body_once_and_preserves_origin(self):
  self.made();self.equip()
  result=self.e.pokemon_activity(self.a,'dismantle',item='item/방진고글',held_selection='crafted:goggles')
  obj=self.e._physical_objects['crafted:goggles'];self.assertIn('consumed',obj);self.assertIn('crafting_origin',obj)
  self.assertEqual(result['category'],'패션 도구');self.assertGreater(self.a.spec['crafting_scrap']['패션 도구'],0)
  self.assertEqual(self.a.save_mod,0);before=self.snapshot()
  with self.assertRaises(ValueError):self.e.pokemon_activity(self.a,'dismantle',item='item/방진고글',held_selection='crafted:goggles')
  self.assertEqual(before,self.snapshot())
 def ingredient(self):
  W.register_object(self.e,'real:ingredient',location={'kind':'unknown'},reason='actual owned ingredient',kind='item_instance',item_rule_id='item/상처약',owner_id=self.a.entity_id)
  I.equip_held(self.e,self.a,'item/상처약',source_instance_id='real:ingredient')
  return {'id':'ingredient','options':[{'kind':'item','item_id':'item/상처약','key':'item/상처약','amount':1}]}
 def test_actual_physical_ingredient_is_consumed_and_cannot_pay_another_recipe(self):
  recipe=self.ready();recipe['materials']=[self.ingredient()]
  inputs={'ingredient':{'option':0,'scrap_value':0,'instances':['real:ingredient']}}
  self.craft(recipe,inputs=inputs)
  self.assertEqual(self.e._physical_objects['real:ingredient']['consumed']['by_actor_id'],self.a.entity_id)
  self.assertEqual(self.a.spec['items']['item/몬스터볼-2'],1);before=self.snapshot()
  with self.assertRaises(ValueError):self.craft(recipe,inputs=inputs)
  self.assertEqual(before,self.snapshot())
 def test_same_physical_ingredient_cannot_pay_two_groups_in_one_transaction(self):
  recipe=self.ready();first=self.ingredient();recipe['materials']=[first,dict(deepcopy(first),id='second')]
  inputs={key:{'option':0,'scrap_value':0,'instances':['real:ingredient']} for key in ('ingredient','second')}
  before=self.snapshot()
  with self.assertRaises(ValueError):self.craft(recipe,inputs=inputs)
  self.assertEqual(before,self.snapshot());self.assertNotIn('consumed',self.e._physical_objects['real:ingredient'])
 def test_late_production_failure_restores_inputs_jobs_identity_output_and_maker_effects(self):
  recipe=self.ready();policy=self.policy();before=self.snapshot();native=P.publish
  def failure(*args,**kw):native(*args,**kw);raise ValueError('late production failure')
  with patch.object(P,'publish',side_effect=failure),self.assertRaises(ValueError):self.craft(recipe,product_policy=policy)
  self.assertEqual(before,self.snapshot());self.assertFalse(getattr(self.e,'_physical_objects',{}))
 def test_forged_maker_copied_body_and_detached_receipt_reject_save(self):
  recipe,policy,result=self.made();obj=self.e._physical_objects['crafted:goggles'];old=obj['crafting_origin']['maker_id']
  obj['crafting_origin']['maker_id']=self.p.entity_id
  with self.assertRaises(ValueError):self.snapshot()
  obj['crafting_origin']['maker_id']=old;copy=deepcopy(obj);copy['id']='forged:copy';self.e._physical_objects[copy['id']]=copy
  with self.assertRaises(ValueError):self.snapshot()
  self.e._physical_objects.pop(copy['id']);row=self.a.spec[P.KEY][result['production_id']];row['transformation']=deepcopy(row['transformation'])
  with self.assertRaises(ValueError):self.snapshot()


if __name__=='__main__':unittest.main()
