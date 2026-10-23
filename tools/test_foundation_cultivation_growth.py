"""Shared growth examples; their timing values are authored, not rule credits."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_cultivation_state as fixtures
import cultivation_growth as G,world_entities as W,state_codec as CODEC,downtime as D,items as I
from engine import Engine


class GrowthTests(unittest.TestCase):
 setUpClass=classmethod(fixtures.CultivationStateTests.setUpClass.__func__)
 setUp=fixtures.CultivationStateTests.setUp
 actor=fixtures.CultivationStateTests.actor
 act=fixtures.CultivationStateTests.act
 own=fixtures.CultivationStateTests.own
 plant_setup=fixtures.CultivationStateTests.plant_setup
 restored=fixtures.CultivationStateTests.restored
 def definition(self,index=0):
  return json.loads((ROOT/'data/examples/cultivation-growth.json').read_text(encoding='utf8'))[index]
 def setup_growth(self,session=False):
  if session:
   self.e=Engine(self.rules,session_frequency=True,defer_session_refresh=True);self.e.gm.everyone=[self.a,self.p];self.e.begin_session('s0',[self.a])
  self.plant_setup();self.a.spec['items'].update({'버치열매':5,'유루열매':5,'비료':5})
  self.e.observe_cultivation_site(self.a,'actual:site',capacity=2,soil_quality=0,soft_soil=True,allows_growth=True,reason='GM inspected the actual two-plant patch')
 def plant_growth(self,value=None,pid='plant:first',**kw):
  return self.e.plant_growth(self.a,value or self.definition(),plant_id=pid,site_id='actual:site',reason='actual admitted seed and site',**kw)
 def snapshot(self):return CODEC.dump_engine(self.e)
 def test_external_declarations_use_actual_seed_body_site_and_world_clocks(self):
  self.setup_growth(session=True);one=self.plant_growth();two=self.plant_growth(self.definition(1),pid='plant:second')
  self.assertEqual((self.a.spec['items']['버치열매'],self.a.spec['items']['유루열매']),(4,4))
  for result in (one,two):
   plant=self.a.spec['plants'][result['plant']['id']]
   self.assertIs(plant,self.e._physical_objects[plant['id']])
   self.assertEqual(W.entity_identity(self.e,plant['id'])['owner_id'],self.a.entity_id)
  self.assertEqual(self.e.growth_status(self.a,'plant:first')['remaining'],10)
  self.assertEqual(self.e.growth_status(self.a,'plant:second')['remaining'],2)
 def test_missing_seed_permission_soil_or_space_rejects_before_mutation(self):
  self.setup_growth()
  for mutation in ('seed','permission','soil','capacity'):
   before=self.snapshot();value=self.definition()
   if mutation=='seed':value['seed']['key']='item/버치열매'
   elif mutation=='permission':value['requirements'][0]['condition']['names']=['unacquired:gardener']
   elif mutation=='soil':
    self.e._physical_objects['actual:site']['growth_site']['soft_soil']=False;before=self.snapshot()
   else:value['site']['capacity']=3
   with self.assertRaises(ValueError):self.plant_growth(value)
   self.assertEqual(before,self.snapshot())
   self.e._physical_objects['actual:site']['growth_site']['soft_soil']=True
 def test_capacity_and_global_identity_cannot_duplicate_seed_or_plant_body(self):
  self.setup_growth();self.plant_growth();self.plant_growth(pid='plant:second');before=self.snapshot()
  for pid in ('plant:third',self.p.entity_id,'actual:site','plant:first'):
   with self.assertRaises(ValueError):self.plant_growth(pid=pid)
   self.assertEqual(before,self.snapshot())
 def test_seconds_maturity_uses_exact_elapsed_clock(self):
  self.setup_growth();self.plant_growth();D.new_day(self.a)
  self.assertFalse(self.e.growth_status(self.a,'plant:first')['mature'])
  self.e.advance_time(9,[self.a]);self.assertEqual(self.e.growth_status(self.a,'plant:first')['remaining'],1)
  self.e.advance_time(1,[self.a]);self.assertTrue(self.e.growth_status(self.a,'plant:first')['ready'])
 def test_session_maturity_requires_enabled_session_clock_and_real_boundaries(self):
  self.setup_growth();before=self.snapshot()
  with self.assertRaises(ValueError):self.plant_growth(self.definition(1))
  self.assertEqual(before,self.snapshot());self.setUp();self.setup_growth(session=True);self.plant_growth(self.definition(1))
  self.e.advance_time(172800,[self.a]);self.assertEqual(self.e.growth_status(self.a,'plant:first')['remaining'],2)
  for n in (1,2):
   self.e.begin_session('s'+str(n),[self.a]);self.assertEqual(self.e.growth_status(self.a,'plant:first')['remaining'],2-n)
 def test_actual_environment_and_site_changes_do_not_invent_growth_permission(self):
  self.setup_growth();self.plant_growth();self.e.advance_time(10,[self.a])
  self.e.observe_cultivation_site(self.a,'actual:site',capacity=2,soil_quality=-2,soft_soil=True,allows_growth=False,reason='GM inspected blocked growth')
  out=self.e.growth_status(self.a,'plant:first');self.assertTrue(out['mature']);self.assertFalse(out['ready']);self.assertEqual(out['soil_quality'],-1)
  before=self.snapshot()
  with self.assertRaises(ValueError):self.e.observe_cultivation_site(self.a,'actual:site',capacity=1,soil_quality=0,soft_soil=True,allows_growth=True,reason='cannot silently discard source capacity')
  self.assertEqual(before,self.snapshot())
 def test_native_growth_keeps_book_and_sheet_maturity_variants(self):
  self.setup_growth();self.act('plant_berry',berry='버치열매',plant_id='native',planter_slot=0,planter_policy='book-literal')
  self.assertEqual(self.a.spec['plants']['native']['growth']['definition']['maturity'],{'clock':'seconds','amount':172800})
  self.setUp();self.setup_growth(session=True)
  self.act('plant_berry',berry='버치열매',plant_id='native',planter_slot=0,planter_policy='sheet-current')
  self.assertEqual(self.a.spec['plants']['native']['growth']['definition']['maturity'],{'clock':'sessions','amount':3})
 def test_native_harvest_reads_actual_growth_site_before_rng_and_output(self):
  self.setup_growth();self.act('plant_berry',berry='버치열매',plant_id='native',planter_slot=0,planter_policy='book-literal')
  self.e.advance_time(172800,[self.a])
  site_id=self.a.spec['plants']['native']['growth']['site_id'];self.e._physical_objects[site_id]['disabled']=True
  before=self.snapshot()
  with self.assertRaises(ValueError):self.act('harvest_berry',plant_id='native',fixed=3)
  self.assertEqual(before,self.snapshot())
 def test_owned_planter_unit_cannot_create_two_sites_or_unprotected_growth(self):
  self.setup_growth();value=self.definition()
  value['site'].update(kind='planter',capacity=1,tool={'item_id':'item/나무열매플랜터','key':'나무열매플랜터'},max_owned=1,protected=True,require_soft_soil=False)
  tool={'item_id':'item/나무열매플랜터','key':'나무열매플랜터','slot':0}
  self.e.observe_cultivation_site(self.a,'actual:pot',capacity=1,soil_quality=0,soft_soil=False,allows_growth=False,reason='actual owned portable grower',tool=tool)
  self.e.plant_growth(self.a,value,plant_id='pot:plant',site_id='actual:pot',slot=0,reason='actual planter planting')
  self.e.advance_time(10,[self.a]);self.assertTrue(self.e.growth_status(self.a,'pot:plant')['ready'])
  before=self.snapshot()
  with self.assertRaises(ValueError):self.e.observe_cultivation_site(self.a,'forged:pot',capacity=1,soil_quality=0,soft_soil=False,allows_growth=True,reason='same counted unit cannot become a second site',tool=tool)
  self.assertEqual(before,self.snapshot())
 def test_fertilizer_exact_seconds_expiry_cap_and_actual_count(self):
  self.setup_growth();self.plant_growth()
  for _ in range(2):self.e.fertilize_growth(self.a,'plant:first',reason='actual one-unit application')
  self.assertEqual(self.a.spec['items']['비료'],3);self.assertEqual(self.e.growth_status(self.a,'plant:first')['soil_quality'],3)
  before=self.snapshot()
  with self.assertRaises(ValueError):self.e.fertilize_growth(self.a,'plant:first',reason='saturated soil rejects')
  self.assertEqual(before,self.snapshot());self.e.advance_time(9,[self.a])
  self.assertEqual(self.e.growth_status(self.a,'plant:first')['fertilizer_bonus'],2)
  self.e.advance_time(1,[self.a]);self.assertEqual(self.e.growth_status(self.a,'plant:first')['fertilizer_bonus'],0)
 def test_day_and_session_fertilizer_lifetimes_do_not_borrow_seconds(self):
  self.setup_growth(session=True);value=self.definition();value['fertilizer']=G.native_fertilizer()
  self.plant_growth(value);self.e.apply_mulch(self.a,'plant:first',reason='actual native one-day fertilizer')
  self.e.advance_time(86400,[self.a]);self.assertEqual(self.e.growth_status(self.a,'plant:first')['fertilizer_bonus'],1)
  D.new_day(self.a);self.assertEqual(self.e.growth_status(self.a,'plant:first')['fertilizer_bonus'],0)
  self.plant_growth(self.definition(1),pid='plant:sessions')
  self.e.fertilize_growth(self.a,'plant:sessions',reason='actual session-lifetime fertilizer')
  self.e.advance_time(86400,[self.a]);self.assertEqual(self.e.growth_status(self.a,'plant:sessions')['fertilizer_bonus'],1)
  self.e.begin_session('s1',[self.a]);self.assertEqual(self.e.growth_status(self.a,'plant:sessions')['fertilizer_bonus'],0)
 def test_real_physical_fertilizer_is_consumed_once(self):
  self.setup_growth();self.plant_growth()
  W.register_object(self.e,'real:fertilizer',location={'kind':'unknown'},reason='actual fertilizer unit',kind='item_instance',item_rule_id='item/비료',owner_id=self.a.entity_id)
  I.equip_held(self.e,self.a,'item/비료',source_instance_id='real:fertilizer')
  self.e.fertilize_growth(self.a,'plant:first',reason='actual physical application',held_selection='real:fertilizer')
  self.assertIn('consumed',self.e._physical_objects['real:fertilizer']);self.assertEqual(self.a.spec['items']['비료'],5)
  before=self.snapshot()
  with self.assertRaises(ValueError):self.e.fertilize_growth(self.a,'plant:first',reason='cannot spend consumed unit',held_selection='real:fertilizer')
  self.assertEqual(before,self.snapshot())
 def test_restore_preserves_actual_body_alias_and_next_maturity_and_fertilizer_deadline(self):
  self.setup_growth();self.plant_growth();self.e.fertilize_growth(self.a,'plant:first',reason='actual fertilizer')
  self.e.advance_time(9,[self.a]);self.e.gm.snapshot('growing');loaded=self.restored()
  self.e.advance_time(1,[self.a]);self.e.gm.restore('growing')
  for e in (self.e,loaded):
   actor=next(c for c in e.gm.everyone if c.entity_id==self.a.entity_id)
   self.assertIs(actor.spec['plants']['plant:first'],e._physical_objects['plant:first'])
   self.assertEqual(e.growth_status(actor,'plant:first')['remaining'],1)
   e.advance_time(1,[actor]);self.assertEqual(e.growth_status(actor,'plant:first')['fertilizer_bonus'],0)
 def test_late_growth_validation_failure_restores_seed_and_all_new_bodies(self):
  self.setup_growth();before=self.snapshot();native=G.validate_world
  def fail(e,index):
   native(e,index)
   if any(a.spec.get('plants') for a in index.values()):raise ValueError('late growth failure')
  with patch.object(G,'validate_world',side_effect=fail),self.assertRaises(ValueError):self.plant_growth()
  self.assertEqual(before,self.snapshot())
 def test_changed_seed_maturity_or_copied_body_cannot_be_saved(self):
  self.setup_growth();self.plant_growth();plant=self.a.spec['plants']['plant:first'];original=deepcopy(plant)
  for mutation in ('seed','maturity','owner','alias'):
   plant.clear();plant.update(deepcopy(original))
   if mutation=='seed':plant['growth']['seed_payment']['count']=2
   elif mutation=='maturity':plant['growth']['definition']['maturity']['amount']=1
   elif mutation=='owner':plant['owner_id']=self.p.entity_id
   else:self.a.spec['plants']['plant:first']=deepcopy(plant)
   with self.assertRaises(ValueError):self.snapshot()
   self.a.spec['plants']['plant:first']=plant


if __name__=='__main__':unittest.main()
