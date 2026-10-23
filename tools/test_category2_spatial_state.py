"""Core p231-232: bodies, contact and weighted flanking share one geometry."""
from pathlib import Path
from copy import deepcopy
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from grid import Grid
import body_state as B,state_fields as F,state_codec as CODEC,turn as T,movement_actions as M

class SpatialStateTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='core')
 def setUp(self):
  self.e=Engine(self.r,123);self.e.grid=Grid(20,20);self.e.everyone=self.e.gm.everyone=[]
 def actor(self,name,pos,size='Medium',kind='pokemon',side='foes'):
  c=Combatant(self.r,dict(name=name,kind=kind,level=10,stats={s:20 for s in F.STATS},types=[],moves=[],abilities=[],pos=pos,size=size,movement={'land':4}))
  c.side=side;self.e.everyone.append(c);return c
 def target(self,pos=(5,5),size='Medium',kind='trainer'):return self.actor('target',pos,size,kind,'party')
 def test_all_default_sizes_and_explicit_body_shapes_share_occupancy(self):
  for kind in ('trainer','pokemon'):
   for size,n in [('Small',1),('Medium',1),('Large',4),('Huge',9),('Gigantic',16)]:
    self.setUp();c=self.target(size=size,kind=kind);self.assertEqual(len(B.cells(c,require_complete=True)),n)
  self.e.gm.set_footprint(c,[(x,y) for x in range(8) for y in range(2)],reason='observed serpentine body')
  view=self.e.spatial_state(c);self.assertEqual(len(view['body']['cells']),16);self.assertTrue(view['body']['geometry_complete'])
 def test_native_contact_includes_large_body_edge_diagonal_but_not_cardinal(self):
  a=self.target(size='Large');b=self.actor('b',(7,7));self.assertTrue(self.e.adjacent(a,b));self.assertFalse(self.e.adjacent(a,b,cardinal=True))
  self.assertIn(b,T.adjacent_enemies(self.e,a));b.pos=(7,6);self.assertTrue(self.e.adjacent(a,b,cardinal=True))
  b.pos=(8,6);self.assertFalse(self.e.adjacent(a,b))
 def test_all_five_original_flanking_diagrams(self):
  # Coordinates transcribed from the actual printed232 diagrams, not implementation output.
  examples=[('Medium',(1,1),[('Medium',(1,0)),('Medium',(0,2))],True),
   ('Medium',(1,1),[('Medium',(1,0)),('Medium',(0,1))],False),
   ('Large',(1,0),[('Medium',(0,1)),('Medium',(3,0)),('Medium',(2,2))],True),
   ('Large',(1,0),[('Medium',(0,1)),('Large',(3,0))],True),
   ('Large',(0,0),[('Huge',(2,0))],False)]
  for size,pos,foes,expected in examples:
   with self.subTest(example=(size,pos,foes)):
    self.setUp();c=self.target(pos,size)
    for i,(fsize,fpos) in enumerate(foes):self.actor(str(i),fpos,fsize)
    self.assertIs(B.flanking(self.e,c)['flanked'],expected)
 def test_all_selected_foes_must_be_pairwise_nonadjacent_and_sizes_change_threshold(self):
  c=self.target(size='Large');a=self.actor('a',(4,5));b=self.actor('b',(4,6));d=self.actor('d',(7,5))
  self.assertFalse(B.flanking(self.e,c)['flanked']) # three bodies, but two touch.
  b.pos=(5,7);self.assertTrue(B.flanking(self.e,c)['flanked'])
  # Larger foes contribute only their actual contact cells, never their full area.
  d.spec['size']='Huge';state=B.flanking(self.e,c);self.assertEqual(next(r['weight'] for r in state['foes'] if r['entity_id']==d.entity_id),3)
  for size,positions in [('Huge',[(4,4),(6,4),(8,4),(4,6)]),('Gigantic',[(4,4),(6,4),(9,4),(9,7),(6,9)])]:
   self.setUp();c=self.target(size=size);foes=[self.actor(str(i),pos) for i,pos in enumerate(positions)]
   self.assertTrue(B.flanking(self.e,c)['flanked']);foes[-1].on_field=False;self.assertFalse(B.flanking(self.e,c)['flanked'])
 def test_single_large_body_duplicate_reference_and_allied_body_cannot_supply_two_foes(self):
  c=self.target();a=self.actor('a',(6,5),'Huge');self.e.everyone.append(a)
  self.assertFalse(B.flanking(self.e,c)['flanked']);b=self.actor('b',(4,5),side='party');self.assertFalse(B.flanking(self.e,c)['flanked'])
  b.side='foes';self.assertTrue(B.flanking(self.e,c)['flanked']);b.on_field=False;self.assertFalse(B.flanking(self.e,c)['flanked'])
 def test_derived_state_updates_after_movement_capture_and_shape_change(self):
  c=self.target();a=self.actor('a',(4,5));b=self.actor('b',(6,5));self.assertTrue(self.e.spatial_state(c)['flanking']['flanked'])
  b.pos=(4,6);self.assertFalse(B.flanking(self.e,c)['flanked']);b.pos=(6,5);b.captured=True;self.assertFalse(B.flanking(self.e,c)['flanked'])
  b.captured=False;self.e.gm.set_footprint(b,[(0,0),(-2,1)],reason='explicit irregular body touches other foe')
  self.assertFalse(B.flanking(self.e,c)['flanked'])
 def test_actual_accuracy_uses_flanking_once_and_zero_evasion_stays_zero(self):
  c=self.target();a=self.actor('a',(4,5));b=self.actor('b',(6,5));move=self.r.move('move/몸통박치기')
  face=move['ac']+c.evasion(move['class'])-1;self.assertTrue(1<face<20)
  b.on_field=False;self.assertFalse(self.e.accuracy_check(a,c,move,fixed_roll=face)[0])
  b.on_field=True;self.assertTrue(self.e.accuracy_check(a,c,move,fixed_roll=face)[0]);self.assertEqual(self.e.spatial_evasion_penalty(c),-2)
  c.conditions.add('취약');self.assertEqual(c.evasion(move['class'],conditional_bonus=-2),0)
 def test_native_range_and_approach_use_edge_not_anchor(self):
  a=self.target((8,6));b=self.actor('b',(5,5),'Huge');move=self.r.move('move/몸통박치기')
  self.assertEqual(self.e.targets_in_range(a,move,[a,b],b),[b]);T.reset_budget(self.e,a);before=deepcopy(a.budget)
  self.e.approach(a,b);self.assertEqual(a.pos,(8,6));self.assertEqual(a.budget,before)
  b.pos=(2,5);self.e.approach(a,b);self.assertEqual(a.pos[0],5);self.assertTrue(self.e.adjacent(a,b))
 def test_large_mover_cannot_pass_a_gap_that_only_fits_its_anchor(self):
  self.e.grid=Grid(8,4,blocking=[(4,y) for y in (0,2,3)])
  a=self.target((1,1),'Large');b=self.actor('b',(6,1));T.reset_budget(self.e,a)
  self.e.approach(a,b);self.assertEqual(a.pos,(1,1));self.assertEqual(a.budget['shift'],0)
 def test_departure_from_large_body_is_based_on_actual_contact(self):
  from unittest.mock import patch
  c=self.target((8,6));foe=self.actor('foe',(5,5),'Huge')
  with patch.object(T,'trigger_aoo') as attack:
   M.departure(self.e,c,(8,7),0);attack.assert_not_called()
   M.departure(self.e,c,(9,7),0);attack.assert_called_once();self.assertEqual(attack.call_args.args[-1],[foe])
 def test_unknown_geometry_stays_pending_and_accuracy_does_not_roll(self):
  c=self.target();a=self.actor('a',(4,5));b=self.actor('b',(6,5));b.spec['size']=None
  self.assertIsNone(B.flanking(self.e,c)['flanked']);before=self.e.rng.getstate()
  with self.assertRaises(ValueError):self.e.accuracy_check(a,c,self.r.move('move/몸통박치기'))
  self.assertEqual(self.e.rng.getstate(),before)
  a.moves.append('move/몸통박치기');T.reset_budget(self.e,a);budget=deepcopy(a.budget)
  with self.assertRaises(ValueError):self.e.use_move(a,c,'move/몸통박치기')
  self.assertEqual(a.budget,budget);self.assertEqual(self.e.rng.getstate(),before)
  with self.assertRaises(ValueError):self.e.adjacent(a,b)
  self.e.gm.set_footprint(b,[(0,0)],reason='observed body');b.spec['size']='Medium';self.assertTrue(B.flanking(self.e,c)['flanked'])
 def test_gm_and_durable_restore_recompute_same_source_owned_geometry(self):
  c=self.target(size='Large');a=self.actor('a',(4,5));b=self.actor('b',(7,5),'Large');before=deepcopy(self.e.spatial_state(c));snap=self.e.gm.snapshot('spatial')
  b.pos=(14,14);self.e.gm.restore(snap);self.assertEqual(self.e.spatial_state(c),before)
  e=Engine.import_state(self.r,self.e.export_state());target=next(x for x in e.everyone if x.entity_id==c.entity_id)
  self.assertEqual(e.spatial_state(target),before);self.assertTrue(e.validate_state()['valid'])
 def test_overlapping_foes_cannot_count_as_two_nonadjacent_bodies(self):
  c=self.target(size='Large');a=self.actor('a',(7,5),'Large');b=self.actor('b',(7,5),'Large')
  self.assertIsNone(B.flanking(self.e,c)['flanked'])

if __name__=='__main__':unittest.main()
