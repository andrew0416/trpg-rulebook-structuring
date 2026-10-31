"""Exact Chef permission uses committed acquisition and native meal consumers."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import hashlib,json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_crafting_resource_state as _fixture_test_category2_crafting_resource_state
import crafting_activities as C,crafting_resources as R,state_codec as CODEC


class ChefRecipePermissionTests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_crafting_resource_state.CraftingResourceStateTests.setUpClass.__func__)
 setUp=_fixture_test_category2_crafting_resource_state.CraftingResourceStateTests.setUp
 actor=_fixture_test_category2_crafting_resource_state.CraftingResourceStateTests.actor
 act=_fixture_test_category2_crafting_resource_state.CraftingResourceStateTests.act
 own=_fixture_test_category2_crafting_resource_state.CraftingResourceStateTests.own
 def ready(self,rank='달인'):
  self.own('basic_cooking');self.a.spec['classes']=[C.CHEF_CLASS]
  self.a.spec['items']['요리 세트']=1;self.a.spec['money']=1000
  self.a.spec['skills']['직감']=rank
 def craft(self,item='맛있는물',**kw):
  return self.act('craft_item',item=item,minutes=1,reason='actual Chef Extended recipe',**kw)
 def snapshot(self):
  # Observe invalid input without asking the save validator to bless it.
  # Retain the complete declared authority graph, including Rules/RNG/receipts.
  encoder=CODEC._Encoder(self.e);root=encoder.value(self.e)
  return deepcopy({'root':root,'nodes':encoder.nodes,'rules':CODEC.rules_fingerprint(self.rules)})
 def rejected(self,item='맛있는물'):
  before=self.snapshot()
  with self.assertRaises(ValueError):self.craft(item)
  self.assertEqual(before,self.snapshot())
 def test_exact_book_permission_and_four_native_products_reach_actual_drinking(self):
  excerpt='\n'.join((ROOT/'input/ch04-trainer-classes.md').read_text(encoding='utf-8-sig').splitlines()[1882:1885])
  self.assertEqual(hashlib.sha256(excerpt.encode()).hexdigest(),'685f3e7a2473d3b06c795abee15a358b987d3a4222de13f9ab05cc458c97bcd4')
  unit=self.rules.selection.units[C.CHEF_CLASS]
  self.assertEqual((unit['kind'],unit['source']['file'],unit['source']['lines']),('entity:class','ch04-trainer-classes.md',[1884,1884]))
  expected={'맛있는물':(3,40,20),'미네랄사이다':(4,65,30),'후르츠밀크':(5,125,50),'튼튼밀크':(6,250,80)}
  self.assertEqual(C.MEAL_RECIPES,{name:(rank,price) for name,(rank,price,_) in expected.items()})
  for item,(rank,price,healing) in expected.items():
   with self.subTest(item=item):
    self.setUp();self.ready({3:'초보',4:'숙련',5:'전문',6:'달인'}[rank]);self.a.spec['money']=price;self.p.hp=1
    result=self.craft(item)
    self.assertEqual((result['money_spent'],self.a.spec['money'],self.a.spec['items'][item]),(price,0,1))
    self.assertIn(C.CHEF_CLASS,result['recipe_sources']);self.assertIn(C.CHEF_CLASS,R.validate(self.a)[-1]['sources'])
    self.assertEqual(result['qualification']['status'],'qualified')
    self.assertEqual(self.e.activity_job_status(result['job_id'])['status'],'complete')
    used=self.e.use_item(self.a,item,self.p,duration_minutes=1,duration_reason='actual crafted drink intake')
    self.assertEqual(used['healed'],min(healing,self.p.max_hp-1));self.assertEqual(self.a.spec['items'][item],0)
    self.assertEqual(self.e.elapsed_seconds,120);self.assertEqual(self.a._action_history,['extended']);self.assertEqual(self.p._action_history,['extended'])
 def test_actual_class_identity_and_existing_acquisition_aliases_share_one_permission(self):
  for field in ('classes','feats'):
   for name in (C.CHEF_CLASS,'요리사','Chef'):
    with self.subTest(field=field,name=name):
     self.setUp();self.ready();self.a.spec['classes']=[];self.a.spec[field]=[name]
     result=self.craft();self.assertIn(C.CHEF_CLASS,result['recipe_sources']);self.assertEqual(self.a.spec['items']['맛있는물'],1)
 def test_live_class_edge_rank_and_tool_requirements_fail_without_any_payment_or_time(self):
  self.ready()
  for field,value in (('classes',[]),('classes','class/요리사'),('edges',[]),('skills',{'직감':'미숙'}),('items',{})):
   with self.subTest(field=field,value=value):
    original=deepcopy(self.a.spec[field]);self.a.spec[field]=value
    self.rejected();self.a.spec[field]=original
  self.a.spec['skills']['직감']='초보';self.rejected('미네랄사이다')
  self.a.spec['skills']['직감']='숙련';self.rejected('후르츠밀크')
  self.a.spec['skills']['직감']='전문';self.rejected('튼튼밀크')
 def test_selected_class_source_and_source_bytes_are_rechecked_before_commit(self):
  self.ready();native=self.rules._selected_rule
  for uid in (C.CHEF_CLASS,C.CHEF_SOURCE):
   with self.subTest(uid=uid),patch.object(type(self.rules),'_selected_rule',new=lambda rules,value,*args,uid=uid,**kw: 'unselected' if value==uid else native(value,*args,**kw)):
    self.rejected()
  unit=self.rules.selection.units[C.CHEF_CLASS]
  with patch.dict(unit,{'source':dict(unit['source'],sha256='0'*64)}):self.rules.touch('selection');self.rejected()
  self.rules.touch('selection')
 def test_external_recipe_metadata_uses_the_same_generic_class_permission_consumer(self):
  self.ready()
  recipe=C._recipe(self.e,self.a,'맛있는물',item_id='item/맛있는물',inventory_key='item/맛있는물',seconds=60)
  recipe.update(id='external:reviewed-chef-permission',source=C.CHEF_CLASS)
  # The declared source/owned condition is consumed without the native
  # four-output dispatch. Other declared recipe conditions remain required.
  result=self.e.craft_recipe(self.a,recipe,reason='generic declared Chef recipe')
  self.assertEqual(result['recipe_source'],C.CHEF_CLASS);self.assertIn(C.CHEF_CLASS,result['recipe_sources'])
  self.assertEqual(self.a.spec['items']['item/맛있는물'],1)
  self.a.spec['classes']=[];before=self.snapshot()
  with self.assertRaises(ValueError):self.e.craft_recipe(self.a,recipe,reason='withdrawn generic Chef permission')
  self.assertEqual(before,self.snapshot())
 def test_withdrawal_stops_future_recipes_and_keeps_already_made_item_usable(self):
  self.ready();self.craft();record=deepcopy(R.validate(self.a));self.a.spec['classes']=[]
  self.rejected();self.assertEqual(R.validate(self.a),record);self.p.hp=1
  self.e.use_item(self.a,'맛있는물',self.p,duration_minutes=1,duration_reason='independent finished product')
  self.assertEqual(self.a.spec['items']['맛있는물'],0);self.assertEqual(self.p.hp,21)
  self.a.spec['classes']=[C.CHEF_CLASS];self.assertEqual(self.craft()['count'],1)
 def test_another_actual_trainer_cannot_borrow_the_chef_acquisition(self):
  self.ready();other=self.actor('other-chef','trainer');self.e.gm.everyone.append(other)
  other.spec.update(items={'요리 세트':1},edges=deepcopy(self.a.spec['edges']),money=1000,classes=[])
  before=self.snapshot()
  with self.assertRaises(ValueError):self.e.pokemon_activity(other,'craft_item',item='맛있는물',minutes=1,reason='same kitchen is not a class acquisition')
  self.assertEqual(before,self.snapshot());self.assertEqual(self.a.spec['money'],1000)
 def test_snapshot_and_durable_restore_keep_permission_provenance_and_recheck_withdrawal(self):
  self.ready();before=self.e.gm.snapshot();self.craft()
  loaded=CODEC.load_engine(self.rules,CODEC.dump_engine(self.e));actor=next(c for c in loaded.gm.everyone if c.entity_id==self.a.entity_id)
  target=next(c for c in loaded.gm.everyone if c.entity_id==self.p.entity_id)
  self.assertIn(C.CHEF_CLASS,R.validate(actor)[-1]['sources']);loaded.pokemon_activity(actor,'craft_item',item='미네랄사이다',minutes=1,reason='restored actual class')
  target.hp=1;loaded.use_item(actor,'미네랄사이다',target,duration_minutes=1,duration_reason='restored native product');self.assertEqual(target.hp,31)
  actor.spec['classes']=[];state=CODEC.dump_engine(loaded)
  with self.assertRaises(ValueError):loaded.pokemon_activity(actor,'craft_item',item='맛있는물',minutes=1,reason='restored withdrawn class')
  self.assertEqual(CODEC.dump_engine(loaded),state)
  self.e.gm.restore(before);self.assertNotIn('resource_transformations',self.a.spec);self.assertEqual(self.a.spec['classes'],[C.CHEF_CLASS]);self.assertEqual(self.a.spec['money'],1000)
  self.assertEqual(self.craft()['count'],1)
 def test_late_native_record_failure_restores_item_cost_clock_rng_jobs_and_acquisition(self):
  self.ready();native=R.record;before=self.snapshot()
  def fail(*a,**kw):native(*a,**kw);raise ValueError('actual late transformation ledger failure')
  with patch.object(R,'record',side_effect=fail),self.assertRaises(ValueError):self.craft()
  self.assertEqual(before,self.snapshot());self.assertNotIn('resource_transformations',self.a.spec)
  self.assertEqual(self.craft()['count'],1)


if __name__=='__main__':unittest.main()
