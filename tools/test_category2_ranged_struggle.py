"""Shared Basic Ranged Attacks investments and actual native consumers."""
import unittest
from copy import deepcopy
from unittest.mock import patch
from tools import test_category2_move_edge_state as fixtures
import ranged_struggle as R
import struggle_capabilities as S
import state_grants as G
import state_fields as F
import weapon_actions as W
from grid import Grid

class RangedTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):fixtures.MoveEdgeStateTests.setUpClass()
 def setUp(self):
  self.f=fixtures.MoveEdgeStateTests();self.f.setUp();self.f.p.spec['capabilities']=list(S.DEFINITIONS)
 def teach(self,edge=R.SOURCE,capability='불쏘시개',**kw):
  f=self.f;return f.e.pokemon_activity(f.a,'teach_edge',target=f.p,edge=edge,capability=capability,**kw,safe=True)
 def prepared(self,name='불쏘시개'):
  f=self.f;return S.prepare(f.e,f.p,f.r.move('struggle'),{'capability':name,'special':True})
 def test_csv_variants_share_distinct_investments_and_only_selected_ranges(self):
  f=self.f
  for n,name in [(44,'불쏘시개'),(45,'물줄기'),(46,'냉동고'),(48,'구체화'),(49,'재퍼')]:
   self.teach(f'C2CSV/input/db/poke-edges.csv:R{n}:main',None)
   self.assertEqual(W.range_spec(f.e,self.prepared(name))['origin'],6)
  self.assertEqual(W.range_spec(f.e,self.prepared('세찬바람'))['origin'],'melee')
  self.teach('C2CSV/input/db/poke-edges.csv:R43:main','세찬바람')
  self.assertEqual((f.p.spec['tutor_points'],f.e.elapsed_seconds),(2,21600))
  self.assertEqual(W.range_spec(f.e,f.r.move('struggle'))['origin'],'melee')
  restored=f.restored();p=next(x for x in restored.gm.everyone if x.entity_id==f.p.entity_id)
  self.assertEqual(p.spec['learned_poke_edges'],f.p.spec['learned_poke_edges']);R.validate(p)
 def test_duplicate_fixed_choice_missing_capability_and_level_rejections_are_atomic(self):
  f=self.f;self.teach()
  for edge,cap in [(R.SOURCE,'불쏘시개'),('C2CSV/input/db/poke-edges.csv:R44:main','물줄기')]:
   before=f.snap()
   with self.assertRaises(ValueError):self.teach(edge,cap)
   self.assertEqual(f.snap(),before)
  G.replace_baseline(f.e,f.p,'capabilities',[]);before=f.snap()
  with self.assertRaises(ValueError):self.teach(capability='물줄기')
  self.assertEqual(f.snap(),before)
  f.e.gm.set_level(f.p,19,reason='actual observed level');before=f.snap()
  with self.assertRaises(ValueError):self.teach(capability='물줄기')
  self.assertEqual(f.snap(),before)
 def test_loss_refunds_once_and_does_not_reactivate_when_capability_returns(self):
  f=self.f;self.teach();self.teach(capability='재퍼')
  G.replace_baseline(f.e,f.p,'capabilities',['재퍼'])
  self.assertEqual(f.p.spec['tutor_points'],7)
  self.assertEqual([x['status'] for x in R.records(f.p)],['refunded','active'])
  G.replace_baseline(f.e,f.p,'capabilities',list(S.DEFINITIONS))
  self.assertEqual(W.range_spec(f.e,self.prepared())['origin'],'melee')
  f.e.gm.set_level(f.p,19,reason='actual level correction')
  self.assertEqual(f.p.spec['tutor_points'],8)
  f.e.gm.set_level(f.p,18,reason='second level correction')
  self.assertEqual(f.p.spec['tutor_points'],8)
 def test_training_credit_missing_balance_and_owner_are_real(self):
  f=self.f;before=f.snap()
  with self.assertRaises(ValueError):self.teach(from_grooming=True)
  self.assertEqual(f.snap(),before)
  f.p.spec['tutor_points']=0;before=f.snap()
  with self.assertRaises(ValueError):self.teach()
  self.assertEqual(f.snap(),before)
  f.p.spec['tutor_points']=8;f.p.spec['trainer_id']='other';before=f.snap()
  with self.assertRaises(ValueError):self.teach()
  self.assertEqual(f.snap(),before)
  f.p.spec['trainer_id']=f.a.entity_id;f.a.spec['edges']=['미용사'];f.a.spec['items']['미용사 킷']=1
  f.e.pokemon_activity(f.a,'groom',targets=[f.p],safe=True)
  self.teach(from_grooming=True);self.teach(capability='재퍼',from_grooming=True)
  self.assertEqual((f.e.elapsed_seconds,f.p.spec['tutor_points']),(3600,6))
 def test_granted_capability_loss_and_unselected_source(self):
  f=self.f;f.p.spec['capabilities']=[]
  G.grant(f.p,'capabilities','불쏘시개','test-source','test')
  self.teach();self.assertEqual(f.p.spec['tutor_points'],7)
  G.transition(f.e,f.p,lambda se,st:G.revoke(st,'test-source',engine=se))
  self.assertEqual(f.p.spec['tutor_points'],8)
  old=f.r.selection.excluded.get(R.SOURCE);f.r.selection.excluded[R.SOURCE]='exclude_units'
  try:
   before=f.snap()
   with self.assertRaises(ValueError):self.teach()
   self.assertEqual(f.snap(),before)
  finally:
   if old is None:f.r.selection.excluded.pop(R.SOURCE,None)
   else:f.r.selection.excluded[R.SOURCE]=old
 def test_actual_six_metre_attack_and_seven_metre_direct_refusal(self):
  f=self.f;self.teach();f.e.grid=Grid(15,4);f.p.pos=(0,0);f.t.pos=(6,0)
  f.e.start_round([f.p,f.t]);f.e.start_of_turn(f.p)
  self.assertEqual(f.e.targets_in_range(f.p,self.prepared(),[f.p,f.t],f.t),[f.t])
  f.t.pos=(7,0);self.assertEqual(f.e.targets_in_range(f.p,self.prepared(),[f.p,f.t],f.t),[])
  before=f.snap()
  self.assertEqual(f.e.use_move(f.p,f.t,'struggle',struggle_choice={'capability':'불쏘시개','special':True}),0)
  self.assertEqual(f.snap(),before)
  f.t.pos=(6,0);hp=f.t.hp
  with patch.object(f.e.rng,'randint',return_value=10):f.e.use_move(f.p,f.t,'struggle',set_damage=True,struggle_choice={'capability':'불쏘시개','special':True})
  self.assertLess(f.t.hp,hp);self.assertEqual(f.p.budget['standard'],0)

if __name__=='__main__':unittest.main()
