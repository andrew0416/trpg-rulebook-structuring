"""Actual teaching and slot consumers for one selected owned Connection Ability."""
from pathlib import Path
from unittest.mock import patch
import json,unittest
from engine import Rules
from builder import build_pokemon
import test_category2_progression_state as _fixture_test_category2_progression_state
import advanced_connection as C,move_state as M,state_grants as G,state_codec as CODEC

ROOT=Path(__file__).resolve().parents[1]

class AdvancedConnectionTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(ROOT,ruleset='all')
 add=_fixture_test_category2_progression_state.ProgressionStateTests.add
 snap=_fixture_test_category2_progression_state.ProgressionStateTests.snap
 def setUp(self):
  _fixture_test_category2_progression_state.ProgressionStateTests.setUp(self)
  self.p=self.add(build_pokemon(self.r,'잉어킹',20,abilities=['기부자'],
   moves=['프레젠트','튀어오르기','몸통박치기','바둥바둥','돌진','전광석화'],extra={'trainer_id':self.a.entity_id,'tutor_points':4}))
 def teach(self,ability='기부자',**options):
  return self.e.pokemon_activity(self.a,'teach_edge',target=self.p,edge=C.SOURCE,ability=ability,safe=True,**options)
 def baseline(self,field,values):return G.transition(self.e,self.p,lambda e,c:G.set_baseline(c,field,values))
 def test_actual_hour_cost_choice_and_existing_slot_calculator_enable_one_more_known_move(self):
  import learning_slots as S
  start=self.e.elapsed_seconds
  with patch.object(S,'occupancy',wraps=S.occupancy) as shared:
   out=self.teach();self.baseline('moves',[*self.p.spec['moves'],'방어'])
   state=M.describe(self.r,self.p.spec)
  self.assertTrue(shared.called);self.assertEqual((out['point_cost'],out['definition_origin']['record'],self.p.spec['tutor_points'],self.e.elapsed_seconds-start),(1,29,3,3600))
  self.assertEqual((len(state['known']),state['slot_count']),(7,6));self.assertEqual(set(state['exempt']),{self.r.move_id('프레젠트')})
  self.assertEqual(C.records(self.p.spec)[0]['ability'],out['ability'])
 def test_unowned_nonconnection_missing_cost_owner_and_duplicate_refuse_atomically(self):
  for case in ('unowned','nonconnection','missing','cost','owner','duplicate'):
   self.setUp()
   if case=='cost':self.p.spec['tutor_points']=0
   elif case=='owner':self.p.spec['trainer_id']=self.p.entity_id
   elif case=='duplicate':self.teach()
   before=self.snap()
   with self.assertRaises(ValueError):self.teach('꿀도둑' if case=='unowned' else '단순' if case=='nonconnection' else None if case=='missing' else '기부자')
   self.assertEqual(self.snap(),before)
 def test_loss_requires_free_slot_then_refunds_once_without_deleting_other_moves(self):
  self.teach();self.baseline('moves',[*self.p.spec['moves'],'방어']);before=self.snap()
  with self.assertRaisesRegex(ValueError,'forgotten-move'):self.baseline('abilities',[])
  self.assertEqual(self.snap(),before)
  self.baseline('moves',[x for x in self.p.spec['moves'] if x not in ('방어',self.r.move_id('방어'))])
  remaining=list(self.p.moves);self.baseline('abilities',[])
  self.assertEqual(self.p.moves,remaining);self.assertEqual(self.p.spec['tutor_points'],4)
  self.assertEqual(C.records(self.p.spec)[0]['status'],'refunded');self.assertEqual(M.describe(self.r,self.p.spec)['slot_count'],6)
  G.transition(self.e,self.p,lambda e,c:None);self.assertEqual(self.p.spec['tutor_points'],4)
 def test_missing_linked_move_is_not_learned_or_a_fake_exemption(self):
  # The Connection Move cannot be forgotten while Giver is owned (official PTU 1.05 p.310), so
  # the missing-Move state comes from an imported sheet, not from forgetting Present.
  self.p=self.add(build_pokemon(self.r,'잉어킹',20,abilities=['기부자'],
   moves=['튀어오르기','몸통박치기','바둥바둥','돌진','전광석화'],extra={'trainer_id':self.a.entity_id,'tutor_points':4}))
  before=list(self.p.moves);self.teach();self.assertEqual(self.p.moves,before)
  self.assertEqual(M.describe(self.r,self.p.spec)['exempt'],{})
 def test_suppression_and_json_restore_preserve_actual_ownership_and_one_exemption(self):
  self.teach();G.transition(self.e,self.p,lambda e,c:setattr(c,'abilities_suppressed',True))
  restored=CODEC.load_engine(self.r,json.loads(json.dumps(CODEC.dump_engine(self.e))))
  target=next(c for c in restored.everyone if c.entity_id==self.p.entity_id)
  self.assertEqual(target.spec['tutor_points'],3);self.assertEqual(M.describe(self.r,target.spec)['slot_count'],5)
  self.assertEqual(len(C.records(target.spec)),1);self.assertTrue(target.abilities_suppressed)
 def test_invalid_receipt_cannot_restore_or_change_selected_cost(self):
  self.teach();state=CODEC.dump_engine(self.e)
  C.records(self.p.spec)[0]['point_cost']=0
  with self.assertRaises(ValueError):CODEC.dump_engine(self.e)
  restored=CODEC.load_engine(self.r,json.loads(json.dumps(state)))
  self.assertEqual(restored.everyone[-1].spec['tutor_points'],3)

if __name__=='__main__':unittest.main()
