"""CSV stat/move investment variants use the same native consumers and receipts."""
from pathlib import Path
from copy import deepcopy
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_progression_state as fixtures
from builder import build_pokemon
import pokemon_stat_edges as STAT,pokemon_move_edges as MOVE
class Tests(unittest.TestCase):
 setUpClass=classmethod(fixtures.ProgressionStateTests.setUpClass.__func__)
 add=fixtures.ProgressionStateTests.add
 snap=fixtures.ProgressionStateTests.snap
 restored=fixtures.ProgressionStateTests.restored
 def setUp(self):
  fixtures.ProgressionStateTests.setUp(self)
  self.p=self.add(build_pokemon(self.r,'근육몬',20,moves=[],abilities=[],extra={'trainer_id':self.a.entity_id,'tutor_points':8}))
 def teach(self,n,**kw):return self.e.pokemon_activity(self.a,'teach_edge',target=self.p,edge=f'C2CSV/input/db/poke-edges.csv:R{n}:main',**kw,safe=True)
 def test_all_stat_variants_preserve_choice_cost_and_one_shared_limit(self):
  for n,choice,args in [(20,'atk',{'stat':'공격'}),(20,'spa',{'stat':'특수공격'}),(21,'atk',{}),(22,'spa',{})]:
   with self.subTest(record=n,choice=choice):
    self.setUp();self.teach(n,**args)
    self.assertEqual(STAT.exemptions(self.r,self.p.spec),{choice})
    self.assertEqual((self.p.spec['tutor_points'],self.e.elapsed_seconds),(7,3600))
    self.assertEqual(self.p.spec['learned_poke_edges'][-1]['definition_origin']['record'],n)
    before=self.snap()
    with self.assertRaises(ValueError):self.teach(20,stat='atk')
    self.assertEqual(self.snap(),before)
 def test_wrong_fixed_choice_and_cross_field_reject_atomically(self):
  for n,args in [(21,{'stat':'spa'}),(22,{'stat':'atk'}),(20,{'skill':'육상'}),(30,{'stat':'atk'}),(30,{'move_id':'몸통박치기'})]:
   before=self.snap()
   with self.assertRaises(ValueError):self.teach(n,**args)
   self.assertEqual(self.snap(),before)
 def test_accuracy_three_distinct_moves_and_refund_once_preserve_source(self):
  names=['메가톤펀치','폭발펀치','암석봉인']
  for name in names:
   original=deepcopy(self.r.move(self.r.move_id(name)));self.teach(30,move_id=name)
   self.assertEqual(MOVE.prepare(self.e,self.p,original)['ac'],original['ac']-1)
   self.assertEqual(self.r.move(original['id']),original)
  before=self.snap()
  with self.assertRaises(ValueError):self.teach(30,move_id='돌떨구기')
  self.assertEqual(self.snap(),before)
  self.e.gm.set_level(self.p,19,reason='observed lost level prerequisite')
  self.assertEqual(self.p.spec['tutor_points'],8)
  self.e.gm.set_level(self.p,19,reason='same level observed again')
  self.assertEqual(self.p.spec['tutor_points'],8)
  self.assertTrue(all(r['status']=='refunded' and r['definition_origin']['record']==30 for r in self.p.spec['learned_poke_edges']))
 def test_codec_and_tampered_fixed_choice(self):
  self.teach(21);self.teach(30,move_id='메가톤펀치')
  loaded=self.restored();p=next(c for c in loaded.gm.everyone if c.entity_id==self.p.entity_id)
  self.assertEqual(STAT.exemptions(loaded.r,p.spec),{'atk'})
  self.assertEqual(MOVE.prepare(loaded,p,loaded.r.move('move/메가톤펀치'))['ac'],3)
  p.spec['learned_poke_edges'][0]['stat']='spa'
  with self.assertRaises(ValueError):STAT.exemptions(loaded.r,p.spec)
if __name__=='__main__':unittest.main()
