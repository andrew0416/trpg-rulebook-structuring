"""Shared harvest behavior and important source/state boundaries."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_foundation_cultivation_growth as fixtures
import cultivation_harvest as H,cultivation_state as P,crafting_products as PRODUCTS
import state_codec as CODEC,acquisition_receipts as RECEIPTS,downtime as D


class HarvestTests(unittest.TestCase):
 setUpClass=classmethod(fixtures.GrowthTests.setUpClass.__func__)
 setUp=fixtures.GrowthTests.setUp
 actor=fixtures.GrowthTests.actor
 act=fixtures.GrowthTests.act
 own=fixtures.GrowthTests.own
 plant_setup=fixtures.GrowthTests.plant_setup
 restored=fixtures.GrowthTests.restored
 setup_growth=fixtures.GrowthTests.setup_growth
 plant_growth=fixtures.GrowthTests.plant_growth
 definition=fixtures.GrowthTests.definition
 snapshot=fixtures.GrowthTests.snapshot
 def policy(self,index=0):
  return json.loads((ROOT/'data/examples/cultivation-harvest.json').read_text(encoding='utf8'))[index]
 def ready(self,session=False):
  self.setup_growth(session=session);self.plant_growth();self.e.advance_time(10,[self.a])
 def harvest(self,value=None,**kw):
  return self.e.harvest_growth(self.a,value or self.policy(),plant_id='plant:first',**kw)
 def test_external_policy_commits_scoped_roll_opportunity_quantity_and_production(self):
  self.ready();before=self.a.spec['items']['버치열매'];out=self.harvest(fixed=[2],event_id='one')
  self.assertEqual((out['amount'],self.a.spec['items']['버치열매']),(4,before+4))
  receipt=out['receipt'];self.assertEqual(receipt['roll']['faces'],[2]);self.assertTrue(receipt['period_consumed'])
  self.assertEqual(receipt['contributions'],[{'id':'declared-gardener','source':'edge/원예가','value':2,'actor_id':self.a.entity_id}])
  product=self.a.spec[PRODUCTS.KEY][out['production_id']]
  self.assertIs(product['transformation'],self.a.spec['resource_transformations'][0])
  self.assertTrue(any(r['receipt_id']==out['production_id'] for r in RECEIPTS.read(self.e,self.a)))
 def test_actual_rng_matches_the_declared_dice_and_advances_once(self):
  self.ready();value=self.policy(1);rng=deepcopy(self.e.rng)
  faces=[rng.randint(1,4) for _ in range(2)];out=self.harvest(value)
  self.assertEqual(out['faces'],faces);self.assertEqual(out['amount'],max(0,sum(faces)-5));self.assertEqual(self.e.rng.getstate(),rng.getstate())
 def test_invalid_eligibility_and_observations_consume_no_rng_or_opportunity(self):
  self.setup_growth();self.plant_growth();before=self.snapshot()
  with self.assertRaises(ValueError):self.harvest(fixed=[2])
  self.assertEqual(before,self.snapshot());self.e.advance_time(10,[self.a])
  for fixed in ([0],[4],[1,2],[True]):
   before=self.snapshot()
   with self.assertRaises(ValueError):self.harvest(fixed=fixed)
   self.assertEqual(before,self.snapshot())
  before=self.snapshot();out=self.harvest(environment_allows_growth=False,fixed=[2])
  self.assertIsInstance(out,H.C.PendingDecision);self.assertEqual(before,self.snapshot())
 def test_daily_limit_and_zero_native_yield_use_the_actual_calendar(self):
  self.ready();value=self.policy();value['contributions']=[];value['roll']['offset']=-10
  out=self.harvest(value,fixed=[1]);self.assertEqual(out['amount'],0);self.assertTrue(out['receipt']['period_consumed'])
  before=self.snapshot()
  with self.assertRaises(ValueError):self.harvest(value,fixed=[3])
  self.assertEqual(before,self.snapshot());self.e.advance_time(86400,[self.a])
  with self.assertRaises(ValueError):self.harvest(value,fixed=[3])
  D.new_day(self.a);self.assertEqual(self.harvest(value,fixed=[3])['amount'],0)
 def test_zero_retry_policy_and_two_opportunities_in_one_seconds_period(self):
  self.ready();value=self.policy(1)
  zero=self.harvest(value,fixed=[1,1]);self.assertEqual(zero['amount'],0);self.assertFalse(zero['receipt']['period_consumed'])
  for _ in range(2):self.assertEqual(self.harvest(value,fixed=[4,4])['amount'],3)
  before=self.snapshot()
  with self.assertRaises(ValueError):self.harvest(value,fixed=[4,4])
  self.assertEqual(before,self.snapshot());self.e.advance_time(10,[self.a])
  self.assertEqual(self.harvest(value,fixed=[4,4])['amount'],3)
 def test_session_period_advances_only_at_real_enabled_session_boundaries(self):
  self.ready(session=True);value=self.policy();value['period']={'clock':'sessions','span':1,'limit':1}
  self.harvest(value,fixed=[1]);self.e.advance_time(86400,[self.a]);before=self.snapshot()
  with self.assertRaises(ValueError):self.harvest(value,fixed=[1])
  self.assertEqual(before,self.snapshot());self.e.begin_session('s1',[self.a]);self.harvest(value,fixed=[1])
  self.setUp();self.ready();before=self.snapshot()
  with self.assertRaises(ValueError):self.harvest(value,fixed=[1])
  self.assertEqual(before,self.snapshot())
 def test_policy_change_cannot_refresh_an_already_used_plant_period(self):
  self.ready();value=self.policy();self.harvest(value,fixed=[1]);before=self.snapshot()
  for field in ('limit','clock','offset'):
   changed=deepcopy(value)
   if field=='limit':changed['period']['limit']=2
   elif field=='clock':changed['period']['clock']='seconds'
   else:changed['roll']['offset']=99
   with self.assertRaises(ValueError):self.harvest(changed,fixed=[1])
   self.assertEqual(before,self.snapshot())
 def test_contributions_require_actual_acquisition_and_selected_sources(self):
  self.ready();value=self.policy();value['contributions'][0]['condition']['names']=['unacquired:gardener']
  out=self.harvest(value,fixed=[2]);self.assertEqual(out['amount'],2);self.assertEqual(out['receipt']['contributions'],[])
  self.setUp();self.ready();before=self.snapshot();value=self.policy();value['output']['key']='item/유루열매'
  with self.assertRaises(ValueError):self.harvest(value,fixed=[2])
  self.assertEqual(before,self.snapshot())
 def test_fertilizer_prefix_and_exact_expiry_do_not_rewrite_prior_harvest(self):
  self.setup_growth();self.plant_growth();self.e.advance_time(9,[self.a])
  self.e.fertilize_growth(self.a,'plant:first',reason='actual one-unit fertilizer');self.e.advance_time(1,[self.a])
  value=self.policy(1);value['roll']['offset']=0
  first=self.harvest(value,fixed=[1,1]);self.assertEqual(first['amount'],4)
  self.e.fertilize_growth(self.a,'plant:first',reason='later fertilizer cannot alter the earlier observation')
  P.validate(self.a);self.assertEqual(self.a.spec['plants']['plant:first']['harvest_history'][0],first['receipt'])
  self.e.advance_time(10,[self.a]);out=self.harvest(value,fixed=[1,1])
  self.assertEqual(out['amount'],3);self.assertEqual(out['receipt']['mulch_bonus'],0)
 def test_completed_event_replay_after_restore_never_rerolls_or_recreates_yield(self):
  self.ready();value=self.policy();out=self.harvest(value,fixed=[2],event_id='one');loaded=self.restored()
  actor=next(c for c in loaded.gm.everyone if c.entity_id==self.a.entity_id);before=CODEC.dump_engine(loaded)
  replay=loaded.harvest_growth(actor,value,plant_id='plant:first',fixed=[2],event_id='one')
  self.assertEqual(replay,out);self.assertEqual(before,CODEC.dump_engine(loaded))
  with self.assertRaises(ValueError):loaded.harvest_growth(actor,value,plant_id='plant:first',fixed=[3],event_id='one')
 def test_gm_and_json_restore_retain_used_period_real_body_and_product_receipt(self):
  self.ready();value=self.policy(1);out=self.harvest(value,fixed=[4,4]);self.harvest(value,fixed=[4,4])
  self.e.gm.snapshot('harvested');loaded=self.restored();self.e.advance_time(10,[self.a]);self.e.gm.restore('harvested')
  for e in (self.e,loaded):
   actor=next(c for c in e.gm.everyone if c.entity_id==self.a.entity_id)
   self.assertIs(actor.spec['plants']['plant:first'],e._physical_objects['plant:first'])
   self.assertIs(actor.spec[PRODUCTS.KEY][out['production_id']]['transformation'],actor.spec['resource_transformations'][0])
   with self.assertRaises(ValueError):e.harvest_growth(actor,value,plant_id='plant:first',fixed=[4,4])
 def test_native_consumer_uses_same_executor_and_zero_consumption_policy(self):
  self.setup_growth();self.act('plant_berry',berry='버치열매',plant_id='native',soft_soil=True);self.e.advance_time(172800,[self.a])
  out=self.act('harvest_berry',plant_id='native',fixed=1,soil_quality=-10)
  self.assertEqual(out['amount'],0);self.assertTrue(out['receipt']['period_consumed'])
  self.assertIn(out['production_id'],self.a.spec[PRODUCTS.KEY]);before=self.snapshot()
  with self.assertRaises(ValueError):self.act('harvest_berry',plant_id='native',fixed=3)
  self.assertEqual(before,self.snapshot())
 def test_late_product_failure_restores_rng_stock_period_and_both_receipts(self):
  self.ready();before=self.snapshot();native=PRODUCTS.publish
  def failure(*args,**kw):native(*args,**kw);raise ValueError('late harvest product failure')
  with patch.object(PRODUCTS,'publish',side_effect=failure),self.assertRaises(ValueError):self.harvest()
  self.assertEqual(before,self.snapshot());self.assertFalse(self.a.spec['plants']['plant:first']['harvest_history'])
 def test_retained_native_receipt_roundtrips_and_joins_new_period_policy(self):
  self.setup_growth();self.act('plant_berry',berry='버치열매',plant_id='native',soft_soil=True);self.e.advance_time(172800,[self.a])
  self.act('harvest_berry',plant_id='native',fixed=3)
  plant=self.a.spec['plants']['native'];row=plant['harvest_history'][0];plant.pop('harvest_policy')
  for key in ('actor_id','roll','fertilizer_count_at_harvest','contributions','growth_context','harvest_definition','period','period_consumed','production_id'):row.pop(key)
  record=self.a.spec['resource_transformations'][0];result=record['result']
  record['result']={key:deepcopy(result[key]) for key in ('activity','plant_id','face','soil_bonus','amount','protected')}
  record['result']['receipt']=deepcopy(row);self.a.spec.pop(PRODUCTS.KEY)
  loaded=self.restored();actor=next(c for c in loaded.gm.everyone if c.entity_id==self.a.entity_id)
  with self.assertRaises(ValueError):loaded.pokemon_activity(actor,'harvest_berry',plant_id='native',fixed=3)
  D.new_day(actor);out=loaded.pokemon_activity(actor,'harvest_berry',plant_id='native',fixed=3)
  self.assertEqual(out['amount'],row['amount']);self.assertEqual(len(actor.spec['plants']['native']['harvest_history']),2)
  CODEC.load_engine(self.rules,CODEC.dump_engine(loaded))
 def test_forged_faces_period_yield_source_and_detached_plant_receipt_reject_save(self):
  self.ready();out=self.harvest(fixed=[2]);receipt=self.a.spec['plants']['plant:first']['harvest_history'][0];old=deepcopy(receipt)
  for field in ('face','period','amount','source','type'):
   receipt.clear();receipt.update(deepcopy(old))
   if field=='face':receipt['roll']['faces']=[3]
   elif field=='period':receipt['period']['index']=99
   elif field=='amount':receipt['amount']=99
   elif field=='source':receipt['contributions'][0]['source']='edge/몬스터볼'
   else:receipt['period']['span']=True
   with self.assertRaises(ValueError):self.snapshot()
  receipt.clear();receipt.update(old);record=self.a.spec['resource_transformations'][0];record['result']['receipt']=dict(deepcopy(receipt),amount=99)
  with self.assertRaises(ValueError):self.snapshot()


if __name__=='__main__':unittest.main()
