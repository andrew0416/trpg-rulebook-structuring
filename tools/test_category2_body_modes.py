"""Shared voluntary size state on real budgets, evasion, targeting and saves."""
from pathlib import Path
from copy import deepcopy
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_progression_state as _fixture_test_category2_progression_state
from grid import Grid
import body_modes as MODE,body_state as BODY,state_grants as G,turn as TURN,state_codec as CODEC

class Tests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_progression_state.ProgressionStateTests.setUpClass.__func__)
 add=_fixture_test_category2_progression_state.ProgressionStateTests.add
 pokemon=_fixture_test_category2_progression_state.ProgressionStateTests.pokemon
 restored=_fixture_test_category2_progression_state.ProgressionStateTests.restored
 def setUp(self):
  _fixture_test_category2_progression_state.ProgressionStateTests.setUp(self);self.e.grid=Grid(20,10);self.a.pos=(1,3);self.p=self.pokemon();self.p.pos=(3,3);self.t=self.pokemon();self.t.pos=(7,3)
  self.e.gm.observe_loyalty(self.p,6,reason='known obedience');self.e.gm.observe_loyalty(self.t,6,reason='known obedience')
 def begin(self,c):
  if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)
  self.e.start_round(self.e.everyone);self.e.start_of_turn(c,initiative_count=20)
 def known(self,c,name):self.e.gm.set_move(c,'move/'+name,reason='actual learned capability source')
 def mode(self,c,mode,ratio,offsets=None):
  return self.e.change_body_mode(c,mode,size_ratio=ratio,offsets=offsets or [(0,0)],reason='GM observes scaled occupied body cells')
 def normal(self,c):return self.e.change_body_mode(c,'normal',reason='return to unchanged original body')
 def test_both_entity_kinds_scale_preserve_weight_and_return_with_source_cost(self):
  for c in (self.a,self.p):
   self.known(c,'성장');c.spec['height_m']=2.0;before=(c.weight_class,c.spec.get('weight_kg'),c.spec['size'])
   self.begin(c);ev=c.evasion('물리');out=self.mode(c,'inflate',1.25)
   self.assertEqual(out['height_m'],2.5);self.assertEqual(out['size_ratio'],1.25);self.assertEqual(c.budget['standard'],0)
   self.assertEqual((c.weight_class,c.spec.get('weight_kg'),c.spec['size']),before);self.assertEqual(c.evasion('물리'),max(0,ev-1))
   self.normal(c);self.assertEqual(c.budget['shift'],0);self.assertEqual(BODY.projection(c)['size_ratio'],1);self.assertEqual(c.evasion('물리'),ev)
 def test_shrink_blocks_standard_full_compound_and_downgrade_but_can_return(self):
  from action_metadata import ActionCost
  self.known(self.p,'작아지기');self.p.spec['height_m']=2.0;weight=self.p.weight_class;self.begin(self.p);ev=self.p.evasion('물리');self.mode(self.p,'shrink',0.25)
  self.assertEqual(BODY.projection(self.p)['height_m'],0.5);self.assertEqual(self.p.weight_class,weight)
  self.assertEqual(self.p.evasion('물리'),min(9,ev+4));self.begin(self.p);before=dict(self.p.budget)
  self.assertFalse(TURN.spend(self.e,self.p,'standard','forbidden'));self.assertFalse(TURN.spend(self.e,self.p,'full','forbidden'))
  self.assertFalse(TURN.spend(self.e,self.p,ActionCost(('standard','swift')),'forbidden compound'));self.assertEqual(self.p.budget,before)
  self.assertTrue(TURN.spend(self.e,self.p,'swift','allowed swift'));self.assertFalse(TURN.spend(self.e,self.p,'swift','forbidden downgrade'))
  budget=dict(self.p.budget);self.assertFalse(TURN.spend(self.e,self.p,ActionCost(('shift','swift')),'compound downgrade'));self.assertEqual(self.p.budget,budget)
  self.normal(self.p);self.assertEqual(self.p.budget['standard'],0);self.assertEqual(self.p.evasion('물리'),ev)
 def test_inflated_body_blocks_direct_and_area_targeting_and_moves_with_actor(self):
  surf=self.r.move('move/파도타기');self.assertIn(self.t,self.e.targets_in_range(self.a,surf,self.e.everyone,self.t))
  self.known(self.p,'비축하기');self.begin(self.p);self.mode(self.p,'inflate',1.25)
  self.known(self.a,'물대포');self.begin(self.a);before=(deepcopy(self.a.budget),deepcopy(self.a.move_uses),self.e.rng.getstate())
  self.assertFalse(BODY.in_range(self.e,self.a,self.t,10))
  targets=self.e.targets_in_range(self.a,surf,self.e.everyone,self.t);self.assertIn(self.p,targets);self.assertNotIn(self.t,targets)
  with self.assertRaisesRegex(ValueError,'inflated'):self.e.use_move(self.a,self.t,'move/물대포')
  with self.assertRaisesRegex(ValueError,'inflated'):self.e.use_move_on(self.a,self.t,'move/물대포',self.e.everyone)
  with self.assertRaisesRegex(ValueError,'inflated'):self.e.use_move_on(self.a,self.t,'move/파도타기',self.e.everyone)
  self.assertEqual((self.a.budget,self.a.move_uses,self.e.rng.getstate()),before)
  self.assertIn(self.p,self.e.targets_in_range(self.a,self.r.move('move/물대포'),self.e.everyone,self.p))
  self.p.pos=(3,5);self.assertTrue(BODY.in_range(self.e,self.a,self.t,10));self.assertEqual(self.e.grid.blocking,set())
  self.assertIn(self.t,self.e.targets_in_range(self.a,surf,self.e.everyone,self.t))
 def test_invalid_ratio_missing_capability_and_occupied_return_are_atomic(self):
  self.begin(self.p);before=deepcopy((self.p.spec,self.p.budget))
  with self.assertRaises(ValueError):self.mode(self.p,'inflate',1.25)
  self.assertEqual((self.p.spec,self.p.budget),before);self.known(self.p,'성장')
  for ratio in (1,1.251,True,float('nan')):
   before=deepcopy((self.p.spec,self.p.budget))
   with self.assertRaises(ValueError):self.mode(self.p,'inflate',ratio)
   self.assertEqual((self.p.spec,self.p.budget),before)
  with self.assertRaises(ValueError):self.mode(self.p,'inflate',1.25,[(0,0),(4,0)])
  self.assertNotIn(MODE.KEY,self.p.spec)
  self.p.spec['size']='Large';self.known(self.p,'작아지기');self.mode(self.p,'shrink',0.25);self.begin(self.p);self.a.pos=(4,3)
  budget=dict(self.p.budget)
  with self.assertRaises(ValueError):self.normal(self.p)
  self.assertEqual(self.p.budget,budget);self.assertEqual(self.p.spec[MODE.KEY]['mode'],'shrink')
 def test_footprint_projection_restoration_and_encounter_end_keep_mode(self):
  self.known(self.p,'성장');original=BODY.cells(self.p);self.begin(self.p);self.mode(self.p,'inflate',1.2,[(0,0),(0,1)])
  self.assertEqual(BODY.cells(self.p),{(3,3),(3,4)});self.e.end_of_turn(self.p);self.e.end_encounter(self.e.everyone)
  self.assertIn(MODE.KEY,self.p.spec);self.e.gm.snapshot('inflated')
  restored=self.restored();p=next(c for c in restored.everyone if c.entity_id==self.p.entity_id)
  self.assertEqual(BODY.cells(p),{(3,3),(3,4)});self.assertEqual(p.spec[MODE.KEY]['size_ratio'],1.2)
  self.begin(self.p);self.normal(self.p);self.assertEqual(BODY.cells(self.p),original)
  self.e.gm.restore('inflated');self.assertEqual(BODY.cells(self.p),{(3,3),(3,4)})
 def test_capability_loss_does_not_trap_active_body_and_corruption_rejects(self):
  self.known(self.p,'작아지기');self.begin(self.p);self.mode(self.p,'shrink',0.5)
  self.e.gm.set_move(self.p,'move/작아지기',add=False,reason='forgotten while shrunk');self.begin(self.p);self.normal(self.p)
  self.assertNotIn(MODE.KEY,self.p.spec);self.known(self.p,'성장');self.begin(self.p);self.mode(self.p,'inflate',1.25)
  self.p.spec[MODE.KEY]['size_ratio']=2
  with self.assertRaises(CODEC.StateCodecError):self.e.export_state()
 def test_shrunk_actor_cannot_use_native_standard_move_or_spend_frequency(self):
  self.known(self.p,'작아지기');self.known(self.p,'물대포');self.begin(self.p);self.mode(self.p,'shrink',0.25);self.begin(self.p)
  before=(self.t.hp,dict(self.p.budget),deepcopy(self.p.move_uses),self.e.rng.getstate())
  self.e.use_move(self.p,self.t,'move/물대포')
  self.assertEqual((self.t.hp,self.p.budget,self.p.move_uses,self.e.rng.getstate()),before)
 def test_reference_only_move_grants_use_learning_not_active_move_effects(self):
  for name,cap in [('비축하기','팽창성'),('변신','형상변환자'),('냄새구별','추적자')]:
   self.known(self.a,name);self.assertIn(cap,G.effective_capabilities(self.a));self.assertFalse(self.a.move_uses)
   self.e.gm.set_move(self.a,'move/'+name,add=False,reason='forget reference-only capability source');self.assertNotIn(cap,G.effective_capabilities(self.a))

if __name__=='__main__':unittest.main()
