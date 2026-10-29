"""C04-101: source-owned Push Buttons retains Demoralize critical-range expansion."""
from pathlib import Path
from unittest.mock import patch
import sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine
from provocateur_fixture import ProvocateurScene
import provocateur as P
import combat_precision_features as CPF
import training_features as TRAINING
import items

class PushThresholdTests(ProvocateurScene,unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='core')
 def prepare(self,expansion=0,*,push=True,decline=False,injuries=0):
  edges=['edge/호감인']+([CPF.BAD_MOOD] if expansion else [])
  if not push:edges.append(P.DEMO)
  self.setup(edges=edges);self.acquire(P.CLASS)
  if push:self.acquire(P.PUSH,selection={'edge':None} if decline else {'edge':P.DEMO})
  self.acquire(P.QUICK)
  if expansion:self.e.apply_status(self.a,'독')
  if expansion==2:self.e.apply_status(self.a,'저주',applied_by=self.t)
  if injuries:self.e.gm.set_injuries(self.t,value=injuries,reason='actual target injuries')
  self.begin()
  self.assertEqual(CPF.bad_mood_critical_bonus(self.e,self.a),expansion)
 def leer(self,face):
  before=self.t.hp
  with patch.object(Engine,'d20',return_value=face):
   self.e.quick_wit(self.a,self.t,move_id='move/째려보기',set_damage=True)
  row=list(self.e._move_completions.values())[-1]
  self.assertTrue(row['results'][self.t.entity_id]['hit'])
  self.assertEqual(self.a.budget['swift'],0)
  return before-self.t.hp,'취약' in self.t.conditions
 def test_source_owned_expansion_zero_one_two_and_immediately_below(self):
  for expansion,threshold in ((0,18),(1,17),(2,16)):
   for face in (threshold-1,threshold):
    with self.subTest(expansion=expansion,face=face):
     self.prepare(expansion)
     self.assertEqual(self.leer(face),(self.e.tick(self.t),True) if face==threshold else (0,False))
     self.assertEqual(self.a.budget['standard'],1)
 def test_training_order_expands_between_turns_and_expires_when_reserved_cost_is_paid(self):
  self.setup();self.acquire(P.CLASS);self.acquire(P.PUSH)
  # Existing native imported-ownership path validates this Feature and its skill prerequisites.
  self.skills(명령=2);self.a.spec['feats'].append(TRAINING.BRUTAL);items.register_feats(self.e,self.a)
  self.e.start_round(self.e.everyone)
  receipt=self.e.manual_feat(self.a,TRAINING.BRUTAL,self.a)
  self.assertEqual(receipt['communication']['mode'],'self_target_exception')
  self.assertEqual(self.a.pending_action_loss,{'standard':1})
  self.assertEqual(TRAINING.bonus(self.a,'critical'),1)
  move=self.rules.move('move/째려보기')
  for face,expected in ((16,False),(17,True)):
   self.assertEqual(self.e.accuracy_check(self.a,self.t,move,fixed_roll=face)[2],expected)
  self.e.start_of_turn(self.a,initiative_count=30)
  self.assertEqual(self.a.budget['standard'],0);self.assertEqual(TRAINING.bonus(self.a,'critical'),0)
  self.assertFalse(self.e.accuracy_check(self.a,self.t,move,fixed_roll=17)[2])
  self.assertTrue(self.e.accuracy_check(self.a,self.t,move,fixed_roll=18)[2])
 def test_no_push_keeps_demoralize_nineteen_minus_expansion_without_tick(self):
  for expansion,threshold in ((0,19),(1,18),(2,17)):
   for face in (threshold-1,threshold):
    with self.subTest(expansion=expansion,face=face):
     self.prepare(expansion,push=False)
     self.assertEqual(self.leer(face),(0,face==threshold))
 def test_declined_demoralize_has_no_status_crit_even_at_twenty(self):
  self.prepare(2,decline=True)
  self.assertNotIn(P.DEMO,self.a.spec['edges'])
  self.assertEqual(self.leer(20),(0,False))
 def test_nonsocial_status_receives_demoralize_but_no_push_tick(self):
  self.prepare(1)
  before=self.t.hp
  self.use(self.a,self.t,'move/꼬리흔들기',face=17)
  self.assertIn('취약',self.t.conditions);self.assertEqual(self.t.hp,before)
  self.assertEqual(self.a.budget['standard'],0);self.assertEqual(self.a.budget['swift'],1)
 def test_quick_wit_rejection_keeps_state_rng_and_expansion_sources(self):
  self.prepare(2)
  self.reject(lambda:self.e.quick_wit(self.a,self.t,move_id='move/몸통박치기'),'Social')
  self.assertEqual(self.leer(16),(self.e.tick(self.t),True))
 def test_expanded_tick_uses_real_max_hp_and_sources_survive_json_restore(self):
  self.prepare(2,injuries=3)
  self.assertLess(self.t.max_hp,self.t.base_max_hp)
  self.valid();self.restore();self.valid()
  self.assertEqual(self.leer(16),(self.t.base_max_hp//10,True))

if __name__=='__main__':unittest.main()
