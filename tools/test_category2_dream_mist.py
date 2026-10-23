"""Native Dream Mist stock -> Melee AC6 -> sleep origin -> dream viewing."""
from copy import deepcopy
import unittest
import test_category2_body_modes as _fixture_test_category2_body_modes
import test_category2_medicine_stock as _fixture_test_category2_medicine_stock
import state_grants as G,dream_state as D

class Tests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_body_modes.Tests.setUpClass.__func__)
 setUp=_fixture_test_category2_body_modes.Tests.setUp
 add=_fixture_test_category2_body_modes.Tests.add
 pokemon=_fixture_test_category2_body_modes.Tests.pokemon
 restored=_fixture_test_category2_body_modes.Tests.restored
 begin=_fixture_test_category2_body_modes.Tests.begin
 held=_fixture_test_category2_medicine_stock.MedicineStockTests.held
 def prepare(self,actor=None):
  actor=actor or self.a;actor.pos=(1,3);self.t.pos=(2,3)
  actor.spec.setdefault('items',{})['item/꿈안개-1']=4;G.grant(self.p,'capabilities','Dream Reader','fixture:dream','fixture');self.begin(actor)
 def use(self,natural=20,actor=None,**kw):return self.e.use_item(actor or self.a,'item/꿈안개-1',self.t,fixed_accuracy=natural,**kw)
 def test_actual_use_spends_standard_and_stock_then_shares_and_restores(self):
  self.prepare();out=self.use(accepted=False)
  self.assertTrue(out['hit']);self.assertTrue(out['status_applied']);self.assertEqual(self.a.spec['items']['item/꿈안개-1'],3)
  self.assertEqual(self.a.budget['standard'],0);self.assertIsNone(getattr(self.t,'pending_action_loss',None))
  self.assertEqual(self.t.spec[D.KEY]['active']['source'],out['source'])
  self.e.gm.observe_dream(self.t,'a sleeping forest',reason='observed dream after actual item attack')
  view=self.e.read_dream(self.p,self.t,share=True);self.e.gm.snapshot('mist');e=self.restored();idx={c.entity_id:c for c in e.everyone}
  self.assertEqual(e.read_dream(idx[self.p.entity_id],idx[self.t.entity_id],share=True),view)
  self.assertEqual(idx[self.a.entity_id].spec['items']['item/꿈안개-1'],3)
  self.e.cure_status(self.t,'잠듦');self.e.gm.restore('mist');self.assertEqual(self.e.read_dream(self.p,self.t,share=True),view)
 def test_actual_ac_evasion_boundary_natural_one_and_twenty(self):
  self.prepare();need=6+self.t.evasion('변화')
  for face,expected in [(need-1,False),(need,True),(1,False),(20,True)]:
   with self.subTest(face=face):
    self.e.cure_status(self.t,'잠듦');self.begin(self.a)
    out=self.use(face);self.assertEqual(out['hit'],expected);self.assertEqual('잠듦' in self.t.conditions,expected)
  self.assertEqual(self.a.spec['items']['item/꿈안개-1'],0)
 def test_out_of_reach_no_stock_and_invalid_options_do_not_pay_or_roll(self):
  self.prepare()
  def snap():return deepcopy((self.a.spec,self.a.budget,self.t.spec,self.t.conditions,self.e.rng.getstate()))
  for option in ['range','stock','face','free']:
   oldpos=self.t.pos;oldstock=self.a.spec['items']['item/꿈안개-1']
   if option=='range':self.t.pos=(8,3)
   if option=='stock':self.a.spec['items']['item/꿈안개-1']=0
   before=snap()
   with self.assertRaises(ValueError):self.use(0 if option=='face' else 20,free=option=='free')
   self.assertEqual(snap(),before);self.t.pos=oldpos;self.a.spec['items']['item/꿈안개-1']=oldstock
 def test_actual_sleep_immunity_still_spends_item_but_cannot_share(self):
  self.prepare();self.e.gm.set_ability(self.t,'불면',reason='actual acquired sleep immunity')
  out=self.use();self.assertTrue(out['hit']);self.assertFalse(out['status_applied'])
  self.assertNotIn('잠듦',self.t.conditions);self.assertEqual(self.a.spec['items']['item/꿈안개-1'],3)
  with self.assertRaises(ValueError):self.e.read_dream(self.p,self.t,share=True)
 def test_pokemon_physical_stock_is_consumed_without_debiting_quantity(self):
  self.prepare(self.p);self.held(self.p,'item/꿈안개-1','mist-bottle')
  out=self.use(actor=self.p,held_selection='mist-bottle')
  self.assertTrue(out['status_applied']);self.assertEqual(out['payment']['kind'],'held_instance')
  self.assertIn('consumed',self.e._physical_objects['mist-bottle']);self.assertEqual(self.p.spec['items']['item/꿈안개-1'],4)
  serial=self.t.spec[D.KEY]['serial'];self.begin(self.p)
  with self.assertRaises(ValueError):self.use(actor=self.p,held_selection='mist-bottle')
  self.assertEqual(self.t.spec[D.KEY]['serial'],serial)

if __name__=='__main__':unittest.main()
