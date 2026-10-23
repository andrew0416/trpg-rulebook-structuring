from pathlib import Path
from copy import deepcopy
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_pokemon
import downtime as D,learning_grant as L
from state_codec import dump_engine,load_engine

class LearningGrantTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(ROOT,ruleset='core')
 def spec(self):return build_pokemon(self.r,'잉어킹',14,moves=[],abilities=[])
 def test_native_level_records_route_and_restore(self):
  e=Engine(self.r);c=Combatant(self.r,self.spec());e.everyone=e.gm.everyone=[c]
  D.gain_exp_combatant(e,c,'to next level')
  rows=c.spec['move_learning_log'];self.assertTrue(rows)
  self.assertTrue(all(x['method']=='level_up' and x['paid_tp']==0 and x['lifetime']=='permanent' for x in rows))
  restored=load_engine(self.r,dump_engine(e));self.assertEqual(restored.everyone[0].spec['move_learning_log'],rows)
 def test_pending_and_invalid_choice_do_not_mutate(self):
  s=self.spec();before=deepcopy(s)
  options=D._learnset_moves_upto(self.r,'잉어킹',15,14,spec=dict(s,level=15));self.assertTrue(options)
  kw=dict(candidates=options,method='level_up',source='pokemon/level-up',reason='test route')
  self.assertEqual(L.learn_moves(self.r,s,selected=None,**kw)['status'],'pending');self.assertEqual(s,before)
  with self.assertRaises(ValueError):L.learn_moves(self.r,s,selected=['unknown move'],**kw)
  self.assertEqual(s,before)
 def test_capacity_failure_retains_spec_and_no_receipts(self):
  s=self.spec();before=deepcopy(s)
  from unittest.mock import patch
  import move_state as M
  options=D._learnset_moves_upto(self.r,'잉어킹',15,14,spec=dict(s,level=15))
  with patch.object(M,'validate_spec',side_effect=ValueError('capacity conflict')):
   with self.assertRaisesRegex(ValueError,'capacity conflict'):
    L.learn_moves(self.r,s,candidates=options,selected=options,method='level_up',source='pokemon/level-up',reason='test route')
  self.assertEqual(s,before)
 def test_evolution_records_separate_route_without_rewriting_level_history(self):
  s=build_pokemon(self.r,'이브이',30,moves=[],abilities=[]);old=deepcopy(s.get('move_learning_log',[]))
  self.assertTrue(D.evolve(self.r,s,'샤미드'))
  rows=s['move_learning_log'];self.assertEqual(rows[:len(old)],old)
  self.assertGreater(len(rows),len(old));self.assertTrue(all(x['method']=='evolution' for x in rows[len(old):]))

 def test_corrupt_receipt_or_missing_history_rejected_on_save(self):
  from state_codec import StateCodecError
  e=Engine(self.r);c=Combatant(self.r,self.spec());e.everyone=e.gm.everyone=[c]
  D.gain_exp_combatant(e,c,'to next level');before=deepcopy(c.spec)
  mid=next(iter(c.spec['move_learning']))
  for key,value in [('paid_tp',2),('candidates',[]),('learned_at_level',100),('teacher_id','forged')]:
   c.spec=deepcopy(before);c.spec['move_learning'][mid][key]=value
   with self.assertRaises(StateCodecError):dump_engine(e)
  c.spec=deepcopy(before);c.spec['move_learning_log']=[]
  with self.assertRaises(StateCodecError):dump_engine(e)

if __name__=='__main__':unittest.main()
