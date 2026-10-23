"""Independent native policy/publication/save boundaries for the shared hooks."""
from pathlib import Path
import sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_foundation_crafting_product as _fixture_test_foundation_crafting_product
from engine import Rules
import cleanse_tags as TAG, crafting_products as PRODUCTS
import state_codec as CODEC, skill_feature_actions as SKILLS


class SharedBindingTests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_foundation_crafting_product.ProductTests.setUpClass.__func__)
 actor=_fixture_test_foundation_crafting_product.ProductTests.actor
 def setUp(self):
  _fixture_test_foundation_crafting_product.ProductTests.setUp(self)
  self.a.spec['edges']=[TAG.SOURCE]
  self.a.spec['skills']['오컬트학']=3
  self.work={'source':'gm/observation','paper':True,'prayer':True,'seconds':11,
             'reason':'GM observed prepared paper and prayer for this actual creation'}
 def make(self,event='independent-one',identity='tag:independent-one',faces=None):
  return TAG.craft(self.e,self.a,event_id=event,instance_id=identity,work=self.work,
                   skill_options={'fixed':faces or [1,2,3]})
 def test_native_dynamic_quota_and_published_original_are_shared(self):
  result=self.make();profile=result[TAG.PROFILE]
  native=self.a.spec[PRODUCTS.KEY][result['production_id']]['transformation']
  self.assertIs(native,self.a.spec['resource_transformations'][0])
  self.assertEqual((self.e.elapsed_seconds,profile['level']),(11,6))
  self.assertEqual(SKILLS.event(self.e,self.a,profile['roll_id']).final.total,6)
  before=CODEC.dump_engine(self.e)
  with self.assertRaises(ValueError):self.make('over-cap','tag:over-cap')
  self.assertEqual(CODEC.dump_engine(self.e),before)
  self.a.spec['skills']['오컬트학']=4
  second=self.make('independent-two','tag:independent-two',[1,1,1,1])
  self.assertEqual(second[TAG.PROFILE]['level'],4)
  self.assertEqual(TAG.level(self.e,profile['instance_id']),6)
  before=CODEC.dump_engine(self.e)
  with self.assertRaises(ValueError):self.make('third','tag:third',[1,1,1,1])
  self.assertEqual(CODEC.dump_engine(self.e),before)
 def test_generic_transform_cannot_publish_unbound_tag_and_rolls_back(self):
  recipe=TAG._recipe(self.work)
  product={'mode':'create','instance_ids':['tag:unbound'],'owner_id':self.a.entity_id,
           'state':'intact','attachments':[]}
  before=CODEC.dump_engine(self.e)
  with self.assertRaises(ValueError):
   self.e.craft_recipe(self.a,recipe,product_policy=product,event_id='unbound',reason=self.work['reason'])
  self.assertEqual(CODEC.dump_engine(self.e),before)
 def test_native_save_validates_bound_level_and_cold_restore_original(self):
  result=self.make();profile=result[TAG.PROFILE]
  saved=CODEC.dump_engine(self.e)
  fresh=Rules(str(ROOT),ruleset='core')
  restored=CODEC.load_engine(fresh,saved)
  actor=next(c for c in restored.gm.everyone if c.entity_id==self.a.entity_id)
  native=actor.spec[PRODUCTS.KEY][result['production_id']]['transformation']
  self.assertIs(native,actor.spec['resource_transformations'][0])
  self.assertEqual(TAG.level(restored,profile['instance_id']),6)
  obj=restored._physical_objects[profile['instance_id']]
  obj[TAG.PROFILE]['level']=99
  native['result'][TAG.PROFILE]['level']=99
  with self.assertRaises(ValueError):CODEC.dump_engine(restored)


if __name__=='__main__':unittest.main()
