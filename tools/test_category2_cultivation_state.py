"""Source-complete crop families, real harvests and durable plant lifetimes."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import sys,json,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category3_crafting as _fixture_test_category3_crafting
import cultivation_state as P,cultivation_growth as GROWTH,crafting_activities as A,state_codec as CODEC,downtime as D

class CultivationStateTests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category3_crafting.CraftTests.setUpClass.__func__)
 setUp=_fixture_test_category3_crafting.CraftTests.setUp
 actor=_fixture_test_category3_crafting.CraftTests.actor
 act=_fixture_test_category3_crafting.CraftTests.act
 own=_fixture_test_category3_crafting.CraftTests.own
 plant_setup=_fixture_test_category3_crafting.CraftTests.plant_setup
 botany=_fixture_test_category3_crafting.CraftTests.botany
 def snap(self):return deepcopy((self.e.elapsed_seconds,self.e.rng.getstate(),[vars(c) for c in self.e.gm.everyone],self.e.log_lines),{id(self.rules):self.rules})
 def restored(self):return CODEC.load_engine(self.rules,json.loads(json.dumps(CODEC.dump_engine(self.e),ensure_ascii=False)))
 def plant(self,name,pid,**kw):
  self.a.spec['items'][name]=self.a.spec['items'].get(name,0)+1
  return self.act('plant_berry',berry=name,plant_id=pid,**kw)

 def test_all_four_harvest_rows_and_every_named_herb_apricorn_use_native_plants(self):
  self.botany('전문')
  groups=[(['버치열매'],3,-1),(['빨간규토리','노랑규토리','파란규토리','초록규토리','담홍규토리','하얀규토리','검은규토리'],2,-2),
          (['자뭉열매','멘탈허브','하양허브','파워풀허브','작은버섯'],3,-2),(['과사열매','부활초','힘의뿌리','큰버섯'],4,-3)]
  expected={}
  for names,die,offset in groups:
   for name in names:
    self.a.spec['items'][name]=1
    self.act('plant_berry',berry=name,plant_id=name,soft_soil=True)
    self.assertEqual(self.a.spec['items'][name],0);expected[name]=(die,offset)
  self.e.advance_time(172800,[self.a])
  # Aromatic Mushroom has a known harvest formula but no cultivation grant
  # in Top Tier Berries. Record an actual existing plant through GM authority.
  self.e.gm.observe_plant(self.a,plant_id='향기버섯',berry='향기버섯',planted_at=0,last_harvest_day=None,soft_soil=True,reason='GM inspected an existing mature wild patch')
  expected['향기버섯']=(4,-3)
  for name,(die,offset) in expected.items():
   with self.subTest(name=name):
    out=self.act('harvest_berry',plant_id=name,fixed=1)
    self.assertEqual((out['face'],out['amount']),(1,max(0,1+offset+1)))
    self.assertEqual(self.a.spec['items'][name],out['amount'])
    self.assertEqual(self.a.spec['plants'][name]['crop']['die'],die)
    with self.assertRaises(ValueError):self.act('harvest_berry',plant_id=name,fixed=die)
  D.new_day(self.a)
  for name,(die,offset) in expected.items():
   out=self.act('harvest_berry',plant_id=name,fixed=die)
   self.assertEqual(out['amount'],max(0,die+offset+1));self.assertEqual(out['receipt']['sequence'],2)
  self.assertEqual(len(P.validate(self.a)),18)

 def test_maturity_soil_protection_and_master_bonus_keep_distinct_source_contributions(self):
  self.botany('전문')
  self.plant('버치열매','ground',soft_soil=True)
  self.plant('버치열매','pot',planter_slot=0,planter_policy='book-literal')
  self.assertEqual(self.rules.item_effects('나무열매플랜터')[1]['price'],2000)
  self.e.advance_time(172799,[self.a]);before=self.snap()
  with self.assertRaises(ValueError):self.act('harvest_berry',plant_id='pot',fixed=3)
  self.assertEqual(before,self.snap());self.e.advance_time(1,[self.a])
  out=self.act('harvest_berry',plant_id='pot',fixed=1,environment_allows_growth=False,soil_quality=-9)
  self.assertEqual((out['amount'],out['receipt']['soil_base'],out['receipt']['site_bonus']),(1,0,1))
  out=self.act('harvest_berry',plant_id='ground',fixed=3,soil_quality=-3)
  self.assertEqual(out['amount'],0);self.assertEqual(out['receipt']['soil_base'],-3)
  D.new_day(self.a);self.a.spec['skills']['생존']='달인'
  out=self.act('harvest_berry',plant_id='ground',fixed=3,soil_quality=0)
  self.assertEqual((out['amount'],out['receipt']['site_bonus'],out['receipt']['feature_bonus']),(4,1,1))
  P.validate(self.a)

 def test_gm_and_durable_restores_keep_daily_attempts_and_yield_is_a_real_consumable(self):
  self.plant_setup();self.a.spec['items']['오랭열매']=1
  self.act('plant_berry',berry='오랭열매',plant_id='p',planter_slot=0,planter_policy='book-literal')
  self.e.advance_time(172800,[self.a]);self.act('harvest_berry',plant_id='p',fixed=2)
  snapshot=self.e.gm.snapshot();loaded=self.restored()
  D.new_day(self.a);self.act('harvest_berry',plant_id='p',fixed=3)
  self.e.gm.restore(snapshot)
  for e in (self.e,loaded):
   a=next(c for c in e.gm.everyone if c.entity_id==self.a.entity_id)
   with self.assertRaises(ValueError):e.pokemon_activity(a,'harvest_berry',plant_id='p',fixed=3)
   self.assertEqual(a.spec['items']['오랭열매'],2)
   out=e.use_item(a,'오랭열매',a,duration_minutes=1,duration_reason='actual harvested berry intake')
   self.assertEqual(out['status'],'digestion_buff_gained');self.assertEqual(a.spec['items']['오랭열매'],1)
   D.new_day(a);e.pokemon_activity(a,'harvest_berry',plant_id='p',fixed=1)
   self.assertEqual(a.spec['items']['오랭열매'],2);self.assertEqual(len(P.validate(a)['p']['harvest_history']),2)

 def test_unknown_cultivation_permission_is_not_invented_by_gm_observation(self):
  self.botany('달인');self.a.spec['items']['향기버섯']=1;before=self.snap()
  with self.assertRaisesRegex(ValueError,'acquisition source'):self.act('plant_berry',berry='향기버섯',plant_id='unknown',soft_soil=True)
  self.assertEqual(before,self.snap());self.e.advance_time(172800,[self.a])
  self.e.gm.observe_plant(self.a,plant_id='observed',berry='향기버섯',planted_at=0,last_harvest_day=None,reason='GM identified an existing outdoor plant')
  out=self.act('harvest_berry',plant_id='observed',fixed=4)
  self.assertEqual(out['amount'],2);self.assertEqual(self.a.spec['items']['향기버섯'],3)
  before=self.snap()
  with self.assertRaises(ValueError):self.e.gm.observe_plant(self.a,plant_id='observed',berry='향기버섯',planted_at=0,last_harvest_day=None,reason='cannot reset history')
  self.assertEqual(before,self.snap())

 def test_sheet_planter_retains_four_actual_plants_and_session_clock_through_restore_and_protected_harvest(self):
  from engine import Engine
  self.e=Engine(self.rules,session_frequency=True,defer_session_refresh=True)
  self.e.gm.everyone=[self.a,self.p];self.e.begin_session('sheet:0',[self.a]);self.plant_setup()
  for n in range(4):self.act('plant_berry',berry='버치열매',plant_id='sheet:'+str(n),planter_slot=0,planter_policy='sheet-current')
  self.assertEqual(self.a.spec['items']['버치열매'],1)
  self.e.advance_time(172800,[self.a]);before=self.snap()
  with self.assertRaises(ValueError):self.act('harvest_berry',plant_id='sheet:0',fixed=1)
  self.assertEqual(before,self.snap())
  self.e.begin_session('sheet:1',[self.a]);self.e.begin_session('sheet:2',[self.a])
  snapshot=self.e.gm.snapshot();loaded=self.restored();self.e.gm.restore(snapshot)
  for e in (self.e,loaded):
   actor=next(c for c in e.gm.everyone if c.entity_id==self.a.entity_id)
   self.assertEqual(len(P.validate(actor)),4)
   for plant in actor.spec['plants'].values():
    self.assertEqual(plant['planter_policy'],'sheet-current')
    self.assertEqual(plant['growth']['definition']['maturity'],{'clock':'sessions','amount':3})
   with self.assertRaises(ValueError):e.pokemon_activity(actor,'harvest_berry',plant_id='sheet:0',fixed=1)
   e.begin_session('sheet:3',[actor])
   out=e.pokemon_activity(actor,'harvest_berry',plant_id='sheet:0',fixed=1,environment_allows_growth=False,soil_quality=-9)
   self.assertEqual((out['amount'],out['receipt']['soil_base'],out['receipt']['site_bonus']),(1,0,1))
   self.assertTrue(out['protected']);self.assertEqual(actor.spec['items']['나무열매플랜터'],1)
   self.assertTrue(e.validate_state()['valid'])

 def test_bad_species_formula_capacity_and_harvest_receipts_fail_native_and_both_save_boundaries(self):
  self.plant_setup();self.plant('버치열매','p',planter_slot=0,planter_policy='book-literal');self.e.advance_time(172800,[self.a]);self.act('harvest_berry',plant_id='p',fixed=2)
  baseline=deepcopy(self.a.spec)
  def duplicate(s):
   other=deepcopy(s['plants']['p']);other['id']='second';other['harvest_history']=[];other['last_harvest_day']=None;s['plants']['second']=other
  for mutate in (lambda s:s['plants']['p']['crop'].update(die=20),lambda s:s['plants']['p'].update(planted_at=True),lambda s:s['plants']['p'].update(last_harvest_day=99),lambda s:s['plants']['p']['harvest_history'][0].update(amount=99),duplicate):
   self.a.spec.clear();self.a.spec.update(deepcopy(baseline));mutate(self.a.spec);before=self.snap()
   with self.assertRaises(ValueError):self.act('harvest_berry',plant_id='p',fixed=1)
   self.assertEqual(before,self.snap());self.assertFalse(self.e.validate_state()['valid'])
   with self.assertRaises(ValueError):CODEC.dump_engine(self.e)
  self.a.spec.clear();self.a.spec.update(baseline)
  self.a.spec['plants']['p']['crop']['die']=20
  # Create the deliberately malformed external payload while bypassing only
  # export validation; the real public loader must reject it on its own.
  with patch.object(P,'validate',return_value={}),patch.object(GROWTH,'validate_world',return_value=True):saved=CODEC.dump_engine(self.e)
  before=self.snap()
  with self.assertRaises(ValueError):CODEC.load_engine(self.rules,saved)
  self.assertEqual(before,self.snap())

 def test_bad_inventory_rejects_before_rng_and_late_plant_failure_refunds_seed(self):
  self.plant_setup();self.plant('버치열매','p',soft_soil=True);self.e.advance_time(172800,[self.a]);self.a.spec['items']['버치열매']=True;before=self.snap()
  with self.assertRaises(ValueError):self.act('harvest_berry',plant_id='p')
  self.assertEqual(before,self.snap());self.a.spec['items']['버치열매']=2
  original=P.validate
  def fail(actor):
   result=original(actor)
   if 'failed' in result:raise ValueError('injected post-plant failure')
   return result
  before=self.snap()
  with patch.object(P,'validate',side_effect=fail):
   with self.assertRaisesRegex(ValueError,'post-plant'):self.act('plant_berry',berry='버치열매',plant_id='failed',soft_soil=True)
  self.assertEqual(before,self.snap())

if __name__=='__main__':unittest.main()
