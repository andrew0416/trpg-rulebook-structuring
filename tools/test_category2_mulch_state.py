"""One-unit Mulch affects actual soil, per-plant harvests and selected daily expiry."""
from copy import deepcopy
import unittest
import test_category2_cultivation_state as _fixture_test_category2_cultivation_state
import cultivation_state as P,downtime as D,state_codec as CODEC

class Tests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_cultivation_state.CultivationStateTests.setUpClass.__func__)
 setUp=_fixture_test_category2_cultivation_state.CultivationStateTests.setUp
 actor=_fixture_test_category2_cultivation_state.CultivationStateTests.actor
 act=_fixture_test_category2_cultivation_state.CultivationStateTests.act
 own=_fixture_test_category2_cultivation_state.CultivationStateTests.own
 plant_setup=_fixture_test_category2_cultivation_state.CultivationStateTests.plant_setup
 botany=_fixture_test_category2_cultivation_state.CultivationStateTests.botany
 plant=_fixture_test_category2_cultivation_state.CultivationStateTests.plant
 restored=_fixture_test_category2_cultivation_state.CultivationStateTests.restored
 def mulch(self,pid,soil=0):return self.e.apply_mulch(self.a,pid,soil_quality=soil,reason='observed application to identified plant')
 def prepare(self,**kw):
  self.plant_setup()
  if kw:self.plant('버치열매','p',**kw)
  self.e.advance_time(172800,[self.a])
  if not kw:self.e.gm.observe_plant(self.a,plant_id='p',berry='버치열매',planted_at=0,last_harvest_day=None,reason='existing mature plant on observed poor soil')
  self.a.spec['items']['비료']=10
 def test_absolute_soil_cap_handles_poor_soil_and_day_expiry(self):
  self.prepare()
  for n in range(5):self.assertEqual(self.mulch('p',-3)['after_soil'],-2+n)
  self.assertEqual(self.a.spec['items']['비료'],5)
  before=deepcopy(self.a.spec)
  with self.assertRaises(ValueError):self.mulch('p',-3)
  self.assertEqual(self.a.spec,before)
  out=self.act('harvest_berry',plant_id='p',soil_quality=-3,fixed=1)
  self.assertEqual((out['soil_bonus'],out['amount'],out['receipt']['mulch_bonus']),(2,2,5))
  D.new_day(self.a);out=self.act('harvest_berry',plant_id='p',soil_quality=-3,fixed=1)
  self.assertEqual((out['amount'],out['receipt']['mulch_bonus']),(0,0));P.validate(self.a)
 def test_planter_and_soft_soil_keep_site_bonus_and_one_more_unit(self):
  for options in ({'soft_soil':True},{'planter_slot':0,'planter_policy':'book-literal'}):
   self.setUp();self.prepare(**options);self.mulch('p')
   with self.assertRaises(ValueError):self.mulch('p')
   out=self.act('harvest_berry',plant_id='p',fixed=1,environment_allows_growth=bool(options.get('soft_soil')))
   self.assertEqual((out['amount'],out['receipt']['site_bonus'],out['receipt']['mulch_bonus']),(2,1,1))
 def test_both_restores_preserve_payment_expiry_and_historical_harvest(self):
  self.prepare();self.mulch('p');out=self.act('harvest_berry',plant_id='p',fixed=2)
  self.mulch('p');P.validate(self.a) # Later application does not rewrite an earlier harvest.
  self.e.gm.snapshot('mulched');e=self.restored();a=next(c for c in e.gm.everyone if c.entity_id==self.a.entity_id)
  self.assertEqual(a.spec['plants'],self.a.spec['plants']);self.assertEqual(a.spec['items']['비료'],8)
  D.new_day(self.a);self.e.gm.restore('mulched');self.assertEqual(self.a.spec['items']['비료'],8)
  self.assertEqual(self.a.spec['plants']['p']['harvest_history'][0],out['receipt'])
  D.new_day(a);self.assertEqual(P.mulch_bonus(a,a.spec['plants']['p'],a.spec['frequency_state']['day'],0)[0],0)
  self.a.spec['plants']['p']['mulch_applications'][0]['payment']['count']=True
  with self.assertRaises(CODEC.StateCodecError):self.e.export_state()
 def test_no_stock_wrong_plant_or_saturated_soil_do_not_mutate(self):
  self.prepare();self.a.spec['items']['비료']=0;before=deepcopy(self.a.spec)
  with self.assertRaises(ValueError):self.mulch('p')
  self.assertEqual(self.a.spec,before);self.a.spec['items']['비료']=2;before=deepcopy(self.a.spec)
  for pid,soil in (('absent',0),('p',2),('p',True)):
   with self.assertRaises(ValueError):self.mulch(pid,soil)
   self.assertEqual(self.a.spec,before)

 def test_pokemon_owned_observed_plant_uses_same_stock_and_daily_state(self):
  self.e.advance_time(172800,[self.p])
  self.e.gm.observe_plant(self.p,plant_id='pokemon-plant',berry='버치열매',planted_at=0,last_harvest_day=None,reason='existing plant controlled by this Pokemon')
  self.p.spec['items']['비료']=1
  row=self.e.apply_mulch(self.p,'pokemon-plant',reason='actual one-unit application')
  self.assertEqual(row['payment'],{'kind':'quantity','item_id':'item/비료','count':1})
  self.assertEqual(self.p.spec['items']['비료'],0)
  self.assertEqual(P.mulch_bonus(self.p,self.p.spec['plants']['pokemon-plant'],0,0)[0],1)
  D.new_day(self.p);self.assertEqual(P.mulch_bonus(self.p,self.p.spec['plants']['pokemon-plant'],1,0)[0],0)

if __name__=='__main__':unittest.main()
