"""Live sensory immunity and qualitative body facts on real actor state."""
from copy import deepcopy
import unittest
import test_category2_body_modes as _fixture_test_category2_body_modes
import capability_traits as TRAITS,state_grants as G,survivalist_features as V
import skill_modifiers as S,combat_timing as CLOCK

class Tests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_body_modes.Tests.setUpClass.__func__)
 setUp=_fixture_test_category2_body_modes.Tests.setUp
 add=_fixture_test_category2_body_modes.Tests.add
 pokemon=_fixture_test_category2_body_modes.Tests.pokemon
 restored=_fixture_test_category2_body_modes.Tests.restored
 begin=_fixture_test_category2_body_modes.Tests.begin
 def grant(self,c,name,source='fixture:trait'):G.grant(c,'capabilities',name,source,'fixture')
 def light(self,c,value):V.observe_environment(self.e,c,terrains=['cave'],light=value,reason='GM actual light')
 def test_blindsense_blocks_ordinary_total_and_external_blindness_for_both_kinds(self):
  for c in (self.a,self.p):
   for name in ('맹인 감각','맹인감각','Blindsense'):
    self.grant(c,name)
    for cond in TRAITS.BLINDNESS:
     self.assertFalse(self.e.apply_status(c,cond,source='fixture:external',parameters={'cause':'external'}))
     self.assertNotIn(cond,c.conditions);self.assertEqual(self.e.immune_to(c,cond),'capability/맹인-감각')
    view=self.e.capability_traits(c);self.assertTrue(view['darkvision']);self.assertFalse(view['visual_reading']);self.assertFalse(view['color_discrimination'])
    G.revoke(c,'fixture:trait')
   self.assertTrue(self.e.apply_status(c,'실명'));self.e.cure_status(c,'실명')
 def test_darkvision_only_removes_darkness_not_external_blindness(self):
  for c in (self.a,self.p):
   self.grant(c,'암흑시야')
   for light in ('low_light','complete_darkness'):
    self.light(c,light);self.assertEqual(V.vision(self.e,c),('none',False))
    self.assertFalse(self.e.apply_status(c,'실명',parameters={'cause':'darkness'}))
   self.e.gm.snapshot('darkvision')
   restored=self.restored();actor=next(x for x in restored.everyone if x.entity_id==c.entity_id)
   self.assertEqual(V.vision(restored,actor),('none',False))
   self.assertFalse(restored.apply_status(actor,'실명',parameters={'cause':'darkness'}))
   G.revoke(c,'fixture:trait');self.assertEqual(V.vision(self.e,c),('total',False))
   self.e.gm.restore('darkvision');self.assertFalse(self.e.apply_status(c,'실명',parameters={'cause':'darkness'}))
   self.assertTrue(self.e.apply_status(c,'실명',parameters={'cause':'external'}));self.assertEqual(V.vision(self.e,c),('ordinary',False))
   self.e.cure_status(c,'실명');self.assertTrue(self.e.apply_status(c,'실명'));self.e.cure_status(c,'실명')
   self.assertFalse(self.e.capability_traits(c)['blindsense'])
 def test_native_dirty_trick_distinguishes_blindsense_and_darkvision(self):
  for name,success in (('Blindsense',False),('Darkvision',True)):
   self.setUp();self.p.pos=(2,3);self.grant(self.p,name);self.begin(self.a)
   na=S.rank(self.r,self.a,'은신')[2];nb=S.rank(self.r,self.p,'은신')[2]
   result=self.e.dirty_trick(self.a,self.p,'blind',fixed_accuracy=20,challenger_options={'fixed':[6]*na},defender_options={'fixed':[1]*nb})
   self.assertEqual(result,success);self.assertEqual('실명' in self.p.conditions,success)
   if not success:self.assertFalse(CLOCK.records(self.p))
   self.assertEqual(self.a.budget['standard'],0)
 def test_granted_darkvision_permits_actual_rough_terrain_movement_without_phantom_roll(self):
  self.light(self.p,'complete_darkness');self.e.grid.rough.update({(4,3),(5,3)});self.begin(self.p)
  before=(self.p.pos,dict(self.p.budget),self.e.rng.getstate())
  with self.assertRaises(ValueError):self.e.approach(self.p,self.t)
  self.assertEqual((self.p.pos,self.p.budget,self.e.rng.getstate()),before)
  self.grant(self.p,'Darkvision');rng=self.e.rng.getstate();self.e.approach(self.p,self.t)
  self.assertNotEqual(self.p.pos,before[0]);self.assertEqual(self.p.budget['shift'],0);self.assertEqual(self.e.rng.getstate(),rng)
  G.revoke(self.p,'fixture:trait');self.assertEqual(V.vision(self.e,self.p),('total',False))
 def test_independent_sources_snapshot_and_json_recompute_traits(self):
  self.grant(self.p,'맹인 감각');self.grant(self.p,'맹인 감각','fixture:other');self.light(self.p,'complete_darkness')
  self.e.gm.snapshot('senses');e=self.restored();p=next(c for c in e.everyone if c.entity_id==self.p.entity_id)
  self.assertFalse(e.apply_status(p,'실명'));self.assertEqual(V.vision(e,p),('none',False))
  G.revoke(self.p,'fixture:trait');self.assertFalse(self.e.apply_status(self.p,'실명'))
  G.revoke(self.p,'fixture:other');self.assertTrue(self.e.apply_status(self.p,'실명'))
  self.e.gm.restore('senses');self.assertNotIn('실명',self.p.conditions);self.assertTrue(self.e.capability_traits(self.p)['blindsense'])
 def test_thermal_descriptions_remain_qualitative_and_do_not_create_damage_or_resistance(self):
  for c in (self.a,self.p):
   initial=(c.hp,c.max_hp,c.types,c.damage_reduction,c.evasion('물리'))
   for name,expected in (('차가움',['cold']),('Heater',['warm'])):
    self.grant(c,name);view=self.e.capability_traits(c)
    self.assertEqual(view['thermal_descriptions'],expected);self.assertIsNone(view['temperature']);self.assertIsNone(view['contact_damage'])
    self.assertEqual((c.hp,c.max_hp,c.types,c.damage_reduction,c.evasion('물리')),initial)
    e=self.restored();loaded=next(a for a in e.everyone if a.entity_id==c.entity_id)
    self.assertEqual(e.capability_traits(loaded),view)
    self.e.gm.snapshot('thermal');G.revoke(c,'fixture:trait');self.assertEqual(self.e.capability_traits(c)['thermal_descriptions'],[])
    self.e.gm.restore('thermal');self.assertEqual(self.e.capability_traits(c),view);G.revoke(c,'fixture:trait')
  self.grant(self.p,'Chilled');self.grant(self.p,'따끈따끈','fixture:other')
  self.assertEqual(self.e.capability_traits(self.p)['thermal_descriptions'],['cold','warm'])
 def test_invalid_blindness_cause_is_rejected_before_any_status_mutation(self):
  for params in ({'cause':'guess'},{'cause':'darkness','value':1},{},'darkness'):
   before=(deepcopy(self.p.conditions),self.e.rng.getstate())
   with self.assertRaises(ValueError):self.e.apply_status(self.p,'실명',parameters=params)
   self.assertEqual((self.p.conditions,self.e.rng.getstate()),before)

if __name__=='__main__':unittest.main()
