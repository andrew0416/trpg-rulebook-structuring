"""Independent next-batch driver contract tests. No original project imports."""
from pathlib import Path
import sys,unittest,json,hashlib,copy
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'engine'))
from encounter import run_encounter
import heavy_injury_adapter as H
import turn as TURN

def cave_summary(e,p,w):
 event=e._heavy_events[e._heavy_pending]
 return dict(actor_names=[x.name for x in p+w],weather_tick=any('모래바람: ' in x for x in e.log_lines),
   producer=event['producer'],target=event['target'].name,attacker=event['attacker'].name,
   before=event['before'],after=event['observed_after'],amount=event['amount'],
   status=event['status'],driver=e._heavy_driver_result,round=e.round_no,seconds=e.elapsed_seconds,
   active=e.encounter_active,active_attacker=e._active_turn_actor is event['attacker'],
   result_line=any(x.startswith('결과:') or x=='## 결과' for x in e.log_lines),
   round_start=e.round_start_seconds,event_id=e._heavy_pending,
   unresolved_count=sum(x['status']=='pending' for x in e._heavy_events.values()))

def assert_cave(t,s):
 t.assertEqual(s['actor_names'],['민호','새싹','거품','주뱃','꼬마돌','꼬렛'])
 t.assertTrue(s['weather_tick']);t.assertEqual(s['producer'],'Engine.resolve_attack_damage')
 t.assertEqual((s['attacker'],s['target'],s['amount']),('새싹','주뱃',50))
 t.assertEqual((s['before']['hp'],s['before']['injuries'],s['before']['real_max_hp']),(31,2,49))
 t.assertEqual((s['after']['hp'],s['after']['injuries']),(-19,5))
 t.assertIn('기절',s['after']['conditions']);t.assertEqual(s['status'],'pending')
 t.assertEqual(s['driver']['status'],'incomplete');t.assertEqual(s['driver']['event_id'],s['event_id'])
 t.assertFalse(s['driver']['automatic_resume']);t.assertEqual(s['unresolved_count'],1)
 t.assertEqual((s['round'],s['seconds'],s['round_start']),(3,20,20))
 t.assertTrue(s['active']);t.assertTrue(s['active_attacker']);t.assertFalse(s['result_line'])

class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.e,cls.p,cls.w=run_encounter(str(ROOT),'data/encounters/cave.json',write=False)
 def test_001_exact_cave_pending_preserves_builder_and_clock_contract(self):
  assert_cave(self,cave_summary(self.e,self.p,self.w))
 def test_002_pending_prevents_automatic_clock_or_round_continuation(self):
  e=self.e;before=cave_summary(e,self.p,self.w)
  for action in [lambda:e.start_round(self.p+self.w),e.end_round,lambda:e.advance_time(10),lambda:e.end_of_turn(e._active_turn_actor)]:
   with self.assertRaises(H.HeavyPending):action()
   self.assertEqual(cave_summary(e,self.p,self.w),before)
 def test_003_real_light_battle_retains_normal_completion(self):
  e,p,w=run_encounter(str(ROOT),'tests/fixtures/light-completion.json',write=False)
  self.assertIsNone(e._heavy_pending);self.assertFalse(e.encounter_active)
  self.assertTrue(all(x.injuries<5 for x in p+w));self.assertTrue(all(x.fainted for x in w))
  self.assertTrue(any(not x.fainted for x in p));self.assertGreater(e.round_no,1)
  self.assertTrue(any(x.startswith('결과: 파티 승리') for x in e.log_lines))
  self.assertGreater(len(e._heavy_events),1)
  self.assertTrue(all(x['status']=='not_applicable' for x in e._heavy_events.values()))
 def test_004_actual_priority_selection_is_observed_without_order_claim(self):
  e,p,w=run_encounter(str(ROOT),'tests/fixtures/priority-declaration.json',write=False)
  self.assertTrue(TURN.has_priority(e,p[0],e.r.move('move/전광석화')))
  self.assertTrue(any(x.startswith('우선 선언: priority-declarer') for x in e.log_lines))
  self.assertEqual(p[0].move_uses.get('move/전광석화'),1);self.assertIsNone(e._heavy_pending)
 def test_005_incomplete_oracle_rejects_weakened_contracts(self):
  base=cave_summary(self.e,self.p,self.w)
  mutations=[lambda x:x.update(weather_tick=False),lambda x:x.update(actor_names=x['actor_names'][:-1]),
   lambda x:x['before'].update(injuries=3),lambda x:x['after'].update(injuries=4),
   lambda x:x.update(seconds=30),lambda x:x.update(result_line=True),
   lambda x:x.update(active=False),lambda x:x['driver'].update(status='complete'),
   lambda x:x['driver'].update(event_id='unrelated'),lambda x:x.update(active_attacker=False)]
  for i,mutate in enumerate(mutations):
   with self.subTest(mutation=i):
    candidate=copy.deepcopy(base);mutate(candidate)
    with self.assertRaises(AssertionError):assert_cave(self,candidate)
class Results(unittest.TextTestResult):
 def __init__(self,*a,**k):super().__init__(*a,**k);self.rows=[]
 def addSuccess(self,t):super().addSuccess(t);self.rows.append(dict(id='HEAVY-ENCOUNTER-'+t._testMethodName,status='pass'))
 def addFailure(self,t,e):super().addFailure(t,e);self.rows.append(dict(id='HEAVY-ENCOUNTER-'+t._testMethodName,status='fail',detail=self._exc_info_to_string(e,t)))
 def addError(self,t,e):super().addError(t,e);self.rows.append(dict(id='HEAVY-ENCOUNTER-'+t._testMethodName,status='error',detail=self._exc_info_to_string(e,t)))
if __name__=='__main__':
 result=unittest.TextTestRunner(verbosity=2,resultclass=Results).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 paths=list((ROOT/'engine').glob('*.py'))+list((ROOT/'tests/fixtures').glob('*.json'))+[Path(__file__),ROOT/'data/encounters/cave.json',ROOT/'input/ch07-combat.md']
 report=dict(generated_at=datetime.now(timezone.utc).isoformat(),tests_run=result.testsRun,results=result.rows,input_hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},scope='Partial driver contracts plus ten oracle-rejection mutations; priority declaration observed, no league/priority ordering proof',semantic_closure=False)
 (ROOT/'output/heavy-encounter-contract-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
 sys.exit(0 if result.wasSuccessful() else 1)
