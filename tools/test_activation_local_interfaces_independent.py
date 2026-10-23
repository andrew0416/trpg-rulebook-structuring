from pathlib import Path
import sys,unittest,json,hashlib
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
import common_checks as C
import turn as T
from engine import Rules,Engine,Combatant
class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='core')
 def pair(self,kind='trainer'):
  e=Engine(self.rules,seed=7)
  a=Combatant(self.rules,dict(name='actor',kind=kind,level=10,stats={s:20 for s in ['hp','atk','def','spa','spd','spe']},abilities=[],moves=['struggle'],types=[]))
  b=Combatant(self.rules,dict(name='target',kind='pokemon',level=10,stats={s:20 for s in ['hp','atk','def','spa','spd','spe']},abilities=[],moves=['struggle'],types=[]))
  e.everyone=e.gm.everyone=[a,b];e.start_round([a,b]);e.start_of_turn(a);return e,a,b
 def test_ROOT_07_no_roll_uses_no_rng(self):
  e,a,b=self.pair();before=e.rng.getstate();out=e.common_action(a,mode='no_roll',outcome='success',description='GM permits trivial traversal');self.assertIsInstance(out,C.ActionOutcome);self.assertIsNone(out.check);self.assertEqual(e.rng.getstate(),before)
 def test_ROOT_08_integer_comparison_oracle(self):
  for total in range(-12,25):
   for dc in range(-10,24):
    r=C.against_dc(C.SkillRoll(1,(1,),modifier=total-1),dc)
    self.assertEqual((r.passed,r.margin),(dc<=total,total-dc))
 def test_ROOT_10_status_quo_ties(self):
  for a,b,w in [(4,5,'defender'),(5,5,'defender'),(6,5,'challenger')]:
   self.assertEqual(C.opposed(C.SkillRoll(1,(a,)),C.SkillRoll(1,(b,))),w)
 def test_ROOT_11_team_required_not_actual_count(self):
  rolls=[C.SkillRoll(1,(6,)),C.SkillRoll(1,(6,)),C.SkillRoll(1,(1,))]
  r=C.team(rolls,6,2);self.assertEqual((r.total,r.dc,r.passed),(13,12,True));self.assertEqual(C.team(rolls,6,3).passed,False)
 def test_ROOT_12_helper_rank_source_boundaries(self):
  for rank,bonus in [(3,1),(4,2),(5,2),(6,3)]:self.assertEqual(C.SkillRoll(1,(2,),helper_rank=rank).total,2+bonus)
  for rank in [1,2]:
   with self.assertRaises(ValueError):C.SkillRoll(1,(2,),helper_rank=rank)
 def test_ROOT_17_extended_complexity(self):
  for factor,expected in [(2,14),(3,21),(4,28),(5,35)]:self.assertEqual(C.extended([],7,factor,4,False).dc,expected)
 def test_ROOT_19_limit_final_equality_and_exhaustion(self):
  good=C.extended([C.SkillRoll(3,(2,2,2))],3,2,3,True);self.assertEqual((good.status,good.attempt_limit),('complete',1))
  bad=C.extended([C.SkillRoll(3,(1,1,1))],3,2,3,True);self.assertEqual(bad.status,'exhausted')
  with self.assertRaises(ValueError):C.extended([C.SkillRoll(3,(2,2,2)),C.SkillRoll(3,(1,1,1))],3,2,3,True)
 def test_ROOT_23_dice_count_and_base_rank(self):
  for rank in range(1,7):
   self.assertEqual(C.SkillRoll(rank,(6,)*rank).total,6*rank)
   with self.assertRaises(ValueError):C.SkillRoll(rank,(6,)*(rank+1))
  e,a,b=self.pair();a.spec['skills']={};self.assertEqual(e.skill_roll(a,'unset',fixed=[2,3]).rank,2)
 def test_ROOT_26_penalty_separate_subtraction(self):
  r=C.SkillRoll(2,(2,3),penalties=(6,6));self.assertEqual((r.rank,r.faces,r.total),(2,(2,3),-7))
 def test_AE_C09_swift_funded_by_standard(self):
  e,a,b=self.pair();a.budget={'standard':1,'shift':1,'swift':0};self.assertTrue(T.spend(e,a,'swift'));self.assertEqual(a.budget,{'standard':0,'shift':1,'swift':0});self.assertEqual(a._action_history,['swift'])
 def test_AE_C10_shift_movement_restriction(self):
  e,a,b=self.pair();self.assertTrue(T.spend(e,a,'shift',movement=True));before=dict(a.budget);self.assertFalse(T.spend(e,a,'shift',movement=True));self.assertEqual(a.budget,before);self.assertTrue(T.spend(e,a,'shift',movement=False))
  e,a,b=self.pair('pokemon');a.budget['shift']=0;self.assertFalse(T.spend(e,a,'shift',movement=True));self.assertTrue(T.spend(e,a,'shift',movement=False))
 def test_AE_C11_full_requires_both_resources(self):
  e,a,b=self.pair();self.assertTrue(T.spend(e,a,'full'));self.assertEqual(a.budget,{'standard':0,'shift':0,'swift':1})
  e,a,b=self.pair();a.budget['shift']=0;before=dict(a.budget);self.assertFalse(T.spend(e,a,'full'));self.assertEqual(a.budget,before)
 def test_AE_C13_natural_extremes_native_accuracy(self):
  e,a,b=self.pair();move=e.r.move('struggle');self.assertFalse(e.accuracy_check(a,b,move,fixed_roll=1)[0]);self.assertTrue(e.accuracy_check(a,b,move,fixed_roll=20)[0])
class Result(unittest.TextTestResult):
 def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
 def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':'ACTIVATION-LOCAL-'+t._testMethodName,'status':'pass'})
 def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':'ACTIVATION-LOCAL-'+t._testMethodName,'status':'fail'})
 def addError(self,t,e):super().addError(t,e);self.rows.append({'id':'ACTIVATION-LOCAL-'+t._testMethodName,'status':'error'})
if __name__=='__main__':
 r=unittest.TextTestRunner(verbosity=1,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests));files=['engine/engine.py','engine/common_checks.py','engine/turn.py','engine/action_lifecycle.py','input/ch06-gameplay.md','input/ch07-combat.md','tools/test_activation_local_interfaces_independent.py'];report={'results':r.rows,'tests_run':r.testsRun,'scope':'11 explicit-input local boundary witnesses plus team unequal-outcome and natural-roll baseline controls that do not close team equality or natural override. No whole interface proof. 1258 integer pairs finite comparator oracle.','input_hashes':{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set([ROOT/f for f in files]+list((ROOT/'engine').glob('*.py'))+list((ROOT/'data').glob('*.json'))+list((ROOT/'output/entities').glob('*.json'))))}}
 (ROOT/'output/activation-local-independent-tests.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8');sys.exit(not r.wasSuccessful())
