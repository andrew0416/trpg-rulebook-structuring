"""Shared recipe behavior; fixture data does not claim whole-rule coverage."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_crafting_resource_state as fixtures
import crafting_recipes as RECIPES,crafting_resources as R,crafting_activities as NATIVE
import state_codec as CODEC,world_entities as W,frequency as FREQ


class RecipeTests(unittest.TestCase):
 setUpClass=classmethod(fixtures.CraftingResourceStateTests.setUpClass.__func__)
 setUp=fixtures.CraftingResourceStateTests.setUp
 actor=fixtures.CraftingResourceStateTests.actor
 own=fixtures.CraftingResourceStateTests.own
 restored=fixtures.CraftingResourceStateTests.restored
 def recipe(self,index=0):
  return json.loads((ROOT/'data/examples/crafting-recipes.json').read_text(encoding='utf8'))[index]
 def ready(self,index=0):
  self.own('basic_balls' if index==0 else 'repel_crafter')
  self.a.spec['items']={'몬스터볼 공구함':1,'화학 세트':1}
  self.a.spec['money']=1000;self.a.spec['crafting_scrap']={'몬스터볼':200,'스프레이':200}
  return self.recipe(index)
 def craft(self,recipe,**kw):return self.e.craft_recipe(self.a,recipe,reason='actual reviewed recipe duration',**kw)
 def snapshot(self):return CODEC.dump_engine(self.e)
 def rejected(self,recipe,**kw):
  before=self.snapshot()
  with self.assertRaises(ValueError):self.craft(recipe,**kw)
  self.assertEqual(before,self.snapshot())
 def metadata(self,source,frequency):
  effects,header=self.rules.feat_effects(source)
  record=deepcopy(self.rules.feats_mech.get(source,{'coverage':'full','effects':effects or [],'header':header}))
  record.setdefault('header',{})['frequency']=deepcopy(frequency)
  return patch.dict(self.rules.feats_mech,{source:record})
 def test_two_external_json_recipes_run_same_interface_and_native_output_effect(self):
  first=self.ready();self.own('repel_crafter');second=self.recipe(1)
  for recipe in (first,second):
   result=self.craft(recipe)
   self.assertEqual(result['recipe_id'],recipe['id']);self.assertEqual(result['recipe_definition'],recipe)
   self.assertEqual(self.a.spec['items'][recipe['output']['key']],1)
   self.assertEqual(self.e.activity_job_status(result['job_id'])['status'],'complete')
  self.assertEqual(self.a.spec['money'],800);self.assertEqual(self.e.elapsed_seconds,180)
  self.assertEqual([x['operation'] for x in R.validate(self.a)],['craft_item','craft_item'])
  self.assertEqual(self.a._action_history,['extended','extended'])
  self.assertTrue(self.rules.item_effects(second['output']['item_id'])[0])
 def test_missing_permission_and_tool_and_rank_do_not_pay_or_advance(self):
  recipe=self.ready()
  for field,value in (('edges',[]),('items',{}),('skills',{'기술학':'미숙'})):
   old=self.a.spec[field];self.a.spec[field]=value;self.rejected(recipe);self.a.spec[field]=old
 def test_source_exclusion_and_changed_output_do_not_borrow_native_recipe(self):
  recipe=self.ready();recipe['output']['key']='item/몬스터볼'
  self.rejected(recipe)
  recipe=self.recipe();native=self.rules._selected_rule
  def selected(uid):return 'unselected' if uid==recipe['source'] else native(uid)
  before=self.snapshot()
  with patch.object(self.rules,'_selected_rule',side_effect=selected),self.assertRaises(ValueError):self.craft(recipe)
  self.assertEqual(before,self.snapshot())
 def test_actual_region_observation_and_restore_drive_same_recipe(self):
  recipe=self.ready();recipe['requirements'].append({'id':'region','condition':{'kind':'region','names':['laboratory']},'reason':'actual laboratory region required'})
  self.rejected(recipe);self.a.spec['crafting_location']={'region':'forest','source':'gm/observation','reason':'GM observed actual region'}
  self.rejected(recipe);self.a.spec['crafting_location']['region']='laboratory'
  loaded=self.restored();actor=next(x for x in loaded.gm.everyone if x.entity_id==self.a.entity_id)
  self.assertEqual(loaded.craft_recipe(actor,recipe,reason='same source region')['count'],1)
 def test_skill_substitution_requires_authored_permission_and_actual_provider(self):
  recipe=self.ready();self.a.spec['skills']['기술학']='미숙';self.a.spec['skills']['의학']='숙련'
  self.rejected(recipe)
  original=recipe['requirements'][1]['condition']
  provider={'kind':'all','conditions':[{'kind':'owned','fields':['feats'],'names':['authored:substitute-provider']},{'kind':'skill','skill':'의학','rank':3,'effective':False}]}
  recipe['requirements'][1]['condition']={'kind':'any','conditions':[original,provider]}
  self.rejected(recipe);self.a.spec['feats'].append('authored:substitute-provider')
  self.assertEqual(self.craft(recipe)['qualification']['status'],'qualified')
 def test_only_matching_craft_scrap_is_spent_with_explicit_money_substitution(self):
  recipe=self.ready();self.a.spec['money']=0;self.a.spec['crafting_scrap']={'약':1000}
  self.rejected(recipe,inputs={'cost':{'option':0,'scrap_value':100}})
  self.a.spec['crafting_scrap']['몬스터볼']=100
  result=self.craft(recipe,inputs={'cost':{'option':0,'scrap_value':100}})
  self.assertEqual((result['scrap_spent'],result['money_spent']),(100,0));self.assertEqual(self.a.spec['crafting_scrap']['약'],1000)
 def test_recipe_can_forbid_money_or_scrap_substitution(self):
  recipe=self.ready();recipe['materials'][0]['options'][0]['scrap']=False
  self.rejected(recipe,inputs={'cost':{'option':0,'scrap_value':100}})
  recipe['materials'][0]['options'][0].update(scrap=True,money=False)
  self.rejected(recipe);self.assertEqual(self.craft(recipe,inputs={'cost':{'option':0,'scrap_value':100}})['money_spent'],0)
 def test_shard_count_and_monetary_scrap_cannot_be_same_material_or_payment(self):
  recipe=self.ready();recipe['materials'][0]['options'].append({'kind':'shard','color':'빨강','amount':1})
  self.rejected(recipe)
  recipe=self.recipe();recipe['materials']=[{'id':'shard','options':[{'kind':'shard','color':'빨강','amount':1}]}]
  self.a.spec['shards']={'빨강':1}
  self.rejected(recipe,inputs={'shard':{'option':0,'scrap_value':1}})
  self.a.spec['shards']={};self.rejected(recipe)
 def test_explicit_counted_input_alternative_consumes_only_selected_owned_item(self):
  recipe=self.ready();recipe['materials']=[{'id':'ingredient','options':[
   {'kind':'item','item_id':'item/버치열매','key':'버치열매','amount':2},
   {'kind':'item','item_id':'item/유루열매','key':'유루열매','amount':1}]}]
  self.a.spec['items'].update({'버치열매':1,'유루열매':1});self.rejected(recipe)
  self.craft(recipe,inputs={'ingredient':{'option':1,'scrap_value':0}})
  self.assertEqual((self.a.spec['items']['버치열매'],self.a.spec['items']['유루열매']),(1,0))
 def test_multiple_material_groups_cannot_double_spend_same_actual_balance(self):
  recipe=self.ready();self.a.spec['money']=150
  recipe['materials'].append(dict(deepcopy(recipe['materials'][0]),id='second'))
  self.rejected(recipe);self.a.spec['money']=200
  self.craft(recipe);self.assertEqual(self.a.spec['money'],0)
 def test_batch_count_multiplies_inputs_and_outputs_and_declared_interval_once(self):
  recipe=self.ready();result=self.craft(recipe,count=2)
  self.assertEqual((self.a.spec['money'],self.a.spec['items']['item/몬스터볼-2'],self.e.elapsed_seconds),(800,2,60))
  self.assertEqual(result['materials'][0]['amount'],200)
 def test_specific_source_action_and_daily_frequency_override_default_and_restore(self):
  recipe=self.ready()
  with self.metadata(recipe['source'],{'action':'free','kind':'daily','uses':1,'raw':''}):
   self.craft(recipe);self.assertEqual(self.a._action_history,['free']);self.rejected(recipe)
   loaded=self.restored();actor=next(x for x in loaded.gm.everyone if x.entity_id==self.a.entity_id)
   with self.assertRaises(ValueError):loaded.craft_recipe(actor,recipe,reason='same spent daily source')
   FREQ.new_day(actor);loaded.craft_recipe(actor,recipe,reason='new actual day')
   self.assertEqual(actor._action_history,['free','free'])
 def test_unknown_source_action_or_frequency_never_falls_back(self):
  recipe=self.ready()
  for metadata in ({'action':'static','kind':'static','raw':'항상'},{'action':'free','kind':'unknown','raw':'weekly unknown'}):
   with self.metadata(recipe['source'],metadata):self.rejected(recipe)
 def test_actual_physical_tool_identity_access_and_destroyed_state(self):
  recipe=self.ready();tool=recipe['requirements'][2]['condition'];tool['instance_id']='workshop:tool'
  W.register_object(self.e,tool['instance_id'],location={'kind':'grid','cell':[0,0]},reason='actual workshop tool',kind='item_instance',item_rule_id=tool['item_id'],owner_id=self.a.entity_id)
  self.rejected(recipe);self.a.spec['accessible_equipment']=[tool['instance_id']]
  self.craft(recipe)
  W.finish_physical_use(self.e,self.e._physical_objects[tool['instance_id']],'destroyed',{'source':tool['item_id'],'former_holder_id':self.a.entity_id,'at':self.e.elapsed_seconds,'reason':'actual destroyed workshop tool'})
  self.rejected(recipe)
 def test_another_owned_or_accessible_tool_cannot_be_relabelled_as_recipe_tool(self):
  recipe=self.ready();self.a.spec['items']={'요리 세트':1}
  recipe['requirements'][2]['condition']['names']=['요리 세트'];self.rejected(recipe)
  self.a.spec['items']={};self.a.spec['accessible_equipment']=['요리 세트'];self.rejected(recipe)
 def test_malformed_unknown_fields_and_injected_material_selection_never_mutate(self):
  recipe=self.ready()
  for field,value in (('seconds',True),('id',''),('free_permission',True)):
   bad=deepcopy(recipe);bad[field]=value;self.rejected(bad)
  self.rejected(recipe,count=True);self.rejected(recipe,inputs={'undeclared':{'option':0,'scrap_value':0}})
 def test_late_transform_failure_rolls_back_actual_job_cost_output_frequency_and_history(self):
  recipe=self.ready();before=self.snapshot();native=R.record
  def failure(*a,**kw):native(*a,**kw);raise ValueError('late product ledger failure')
  with patch.object(R,'record',side_effect=failure),self.assertRaises(ValueError):self.craft(recipe)
  self.assertEqual(before,self.snapshot());self.assertFalse(getattr(self.e,'_activity_jobs',{}))
  self.craft(recipe);self.assertEqual(len(R.validate(self.a)),1)
 def test_snapshot_and_durable_restore_keep_recipe_proof_and_continue_native_consumer(self):
  recipe=self.ready();self.e.gm.snapshot('before-recipe');self.craft(recipe)
  loaded=self.restored();actor=next(x for x in loaded.gm.everyone if x.entity_id==self.a.entity_id)
  loaded.pokemon_activity(actor,'craft_item',item='item/몬스터볼-2',minutes=1,reason='same shared native executor')
  self.assertEqual(actor.spec['items']['item/몬스터볼-2'],2);self.assertEqual(len(R.validate(actor)),2)
  self.assertEqual(R.validate(actor)[0]['result']['recipe_definition'],recipe)
  self.e.gm.restore('before-recipe');self.assertNotIn('resource_transformations',self.a.spec);self.assertFalse(getattr(self.e,'_activity_jobs',{}))
 def test_corrupt_saved_recipe_declaration_fails_export_and_restore(self):
  recipe=self.ready();self.craft(recipe);record=R.validate(self.a)[0]
  record['result']['recipe_definition']['materials'][0]['options'][0]['amount']=False
  with self.assertRaises(ValueError):self.snapshot()


if __name__=='__main__':unittest.main()
