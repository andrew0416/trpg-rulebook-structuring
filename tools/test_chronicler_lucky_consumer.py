"""Targeted Profiling ignores an Ability, never the actual Lucky Chant pool."""
from pathlib import Path
from unittest.mock import patch
import sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_chronicler_source_crit_revision as FIX
from engine import Rules,Engine
import chronicler as CH
import ability_transitions as AB
import blessing_effects as B
import effects_ext as EXT
import move_completion as COMPLETE
import action_points as AP

class ChroniclerLuckyConsumerTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')
 def test_native_lucky_pool_blocks_profiled_critical_damage_once(self):
  case=FIX.ChroniclerSourceCritTests();case.rules=self.rules;case.setup()
  try:
   case.whole();case.archive_subject(case.b,'pokemon','actual armored profile guarded by Lucky Chant')
   case.e.gm.set_ability(case.b,'조가비갑옷/전투무장',reason='actual selected Defensive Shell Armor')
   case.e.gm.set_move(case.b,'move/주술',reason='actual known Lucky Chant')
   case.communication();case.combat(case.b,count=30)
   self.assertEqual(case.b.budget['standard'],1)
   case.use(case.b,case.b,'move/주술',face=20)
   self.assertEqual(case.b.budget['standard'],0)
   guards=B.beneficiaries(case.e,case.b,'team_critical_guard')
   self.assertEqual(len(guards),1)
   owner,guard=guards[0];self.assertIs(owner,case.b);self.assertEqual(guard['source'],'move/주술');self.assertEqual(B.remaining(guard),3)
   case.e.end_of_turn(case.b);case.e.end_round();case.combat(case.t,count=30)
   ap=AP.available(case.t)
   CH.profile_order(case.e,case.t,case.p)
   self.assertEqual(AP.available(case.t),ap-2);self.assertEqual(case.t.budget['standard'],0)
   case.e.end_of_turn(case.t);case.e.start_of_turn(case.p,initiative_count=20)
   self.assertTrue(AB.active(case.b,'ability/조가비갑옷-전투무장'))
   self.assertTrue(CH.defensive_ignored(case.e,case.p,case.b,case.e.r.move('move/전광석화')))
   case.e.rulings.add_answer('team_blessing',True,reason='actual beneficiary accepts the nonability critical guard')
   observations=[];native=EXT.crit_hook
   def observed(engine,actor,target,move,hit,crit,**options):
    before=B.remaining(guard);answer=native(engine,actor,target,move,hit,crit,**options)
    if actor is case.p and target is case.b:observations.append((hit,crit,answer,before,B.remaining(guard)))
    return answer
   hp=case.b.hp
   with patch.object(EXT,'crit_hook',side_effect=observed):
    damage=case.use(case.p,case.b,'move/전광석화',face=20)
   self.assertEqual(observations,[(True,True,False,3,2)])
   self.assertEqual((damage,hp-case.b.hp),(11,11))
   self.assertEqual(case.p.budget['standard'],0)
   self.assertEqual(B.remaining(guard),2)
   case.restore();case.valid()
   restored=B.beneficiaries(case.e,case.b,'team_critical_guard')
   self.assertEqual(len(restored),1);self.assertIs(restored[0][0],case.b)
   self.assertEqual((restored[0][1]['source'],B.remaining(restored[0][1])),('move/주술',2))
   before=(case.b.hp,case.p.budget.copy(),B.remaining(restored[0][1]))
   COMPLETE.refresh(case.e)
   self.assertEqual((case.b.hp,case.p.budget,B.remaining(restored[0][1])),before)
  finally:case.doCleanups()
