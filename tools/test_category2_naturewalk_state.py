"""Source-listed Naturewalk terrains reach actual movement, accuracy and saves."""
from copy import deepcopy
import unittest
import test_category2_body_modes as _fixture_test_category2_body_modes
from grid import Grid
import movement_actions as M,state_grants as G

class Tests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_body_modes.Tests.setUpClass.__func__)
 setUp=_fixture_test_category2_body_modes.Tests.setUp
 add=_fixture_test_category2_body_modes.Tests.add
 pokemon=_fixture_test_category2_body_modes.Tests.pokemon
 restored=_fixture_test_category2_body_modes.Tests.restored
 begin=_fixture_test_category2_body_modes.Tests.begin
 def grant(self,c,value,source='fixture:naturewalk'):G.grant(c,'capabilities',value,source,'fixture')
 def test_original_korean_and_canonical_english_multi_terrain_grammar(self):
  for c in (self.a,self.p):
   baseline=M.naturewalk_terrains(self.e,c)
   for name in ('자연걸음(숲과 초원)','자연걸음(숲, 초원)','Naturewalk(forest and grassland)','Nature Walk (forest AND grassland)','Naturewalk(forest/grassland)'):
    self.grant(c,name)
    self.assertEqual(M.naturewalk_terrains(self.e,c),baseline|frozenset(('forest','grassland')))
    G.revoke(c,'fixture:naturewalk')
   for name in ('grassland','wetland','해변','민물','타이가'):
    self.grant(c,'Naturewalk('+name+')');M.observe_cell_terrain(self.e,[(3,2)],[name],'actual terrain')
    self.assertTrue(M.ordinary_terrain(self.e,c,(3,2)));G.revoke(c,'fixture:naturewalk')
 def test_explicit_selection_unknown_cells_and_independent_sources(self):
  self.grant(self.p,'자연걸음(숲)');self.grant(self.p,'자연걸음(초원)','fixture:second')
  M.observe_cell_terrain(self.e,[(3,2)],['숲','초원'],'mixed observed terrain')
  self.assertTrue(M.ordinary_terrain(self.e,self.p,(3,2)));self.assertFalse(M.ordinary_terrain(self.e,self.p,(4,2)))
  G.revoke(self.p,'fixture:second');self.assertFalse(M.ordinary_terrain(self.e,self.p,(3,2)))
  G.revoke(self.p,'fixture:naturewalk')
  for value in ('자연걸음','Naturewalk()','Naturewalk(unknown)','Nature Walk forest'):
   self.grant(self.p,value)
   with self.assertRaises(ValueError):M.naturewalk_terrains(self.e,self.p)
   G.revoke(self.p,'fixture:naturewalk')
 def test_native_movement_accuracy_and_both_restores_follow_live_terrain_selection(self):
  for actor in ('a','p'):
   self.setUp();c=getattr(self,actor);other=self.p if actor=='a' else self.a
   self.e.grid=Grid(1,6,slow={(0,1),(0,2),(0,3)},rough={(0,5)})
   c.pos=(0,0);other.pos=(0,4);other.on_field=False;self.t.pos=(0,5)
   self.e.gm.set_movement_capabilities(c,{'land':3},basis='current',reason='actual current land speed')
   self.grant(c,'Naturewalk(forest and grassland)')
   M.observe_cell_terrain(self.e,[(0,y) for y in range(1,6)],['forest'],'actual forest corridor')
   self.begin(c);self.e.gm.snapshot('forest walk')
   e=self.restored();loaded=next(a for a in e.everyone if a.entity_id==c.entity_id);target=next(a for a in e.everyone if a.entity_id==self.t.entity_id)
   e.approach(loaded,target);self.assertEqual(loaded.pos,(0,3))
   self.e.approach(c,self.t);self.assertEqual(c.pos,(0,3))
   move=self.r.move('move/물대포');face=move['ac']+self.t.evasion('특수')
   self.assertTrue(self.e.accuracy_check(c,self.t,move,fixed_roll=face)[0])
   self.e.gm.restore('forest walk');G.revoke(c,'fixture:naturewalk')
   self.assertFalse(self.e.accuracy_check(c,self.t,move,fixed_roll=face)[0])
   self.e.approach(c,self.t);self.assertEqual(c.pos,(0,1))
   self.assertEqual(self.e.grid.slow,{(0,1),(0,2),(0,3)})

if __name__=='__main__':unittest.main()
