"""Public observation is durable across invalid UI responses in two consumers."""
from pathlib import Path
from copy import deepcopy
from datetime import datetime,timezone
import hashlib,json,random,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from test_category3_contest_skill_features import Sequence
import test_category3_contest_skill_features as _fixture_test_category3_contest_skill_features
import test_category3_contest_features as _fixture_test_category3_contest_features
import contest_features as F
import observed_resolution as OBS
import action_points as AP
class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):_fixture_test_category3_contest_skill_features.Tests.setUpClass();_fixture_test_category3_contest_features.Tests.setUpClass()
 def skill(self):
  t=_fixture_test_category3_contest_skill_features.Tests();t.fixture('슬기로움',F.MISTAKES);return t
 def contest(self):
  t=_fixture_test_category3_contest_features.Tests();t.setUp();t.e.rng=random.Random(11);return t
 def pending_skill(self,t,**options):
  options={'fixed':None,'reroll_faces':None,'decision':lambda check:'invalid','roll_id':'skill-attempt',**options}
  with self.assertRaises(ValueError):t.mistakes(dc=99,**options)
  return t.e._ap_rolls['skill-attempt'][OBS.KEY]
 def perform(self,t,kind='coordinator',**options):
  opts={'spend_stat_dice':1,('reroll_decision' if kind=='coordinator' else 'flourish_decision'):lambda preview:'invalid','attempt_id':'appeal-attempt'};opts.update(options)
  return t.e.perform(t.cs[0],'연속자르기','근사함',[],False,**opts)
 def test_mistakes_invalid_response_preserves_first_rng_and_ap_completion(self):
  t=self.skill();t.e.boost_roll(t.t,t.p,roll_id='skill-attempt',kind='skill');before=t.e.rng.getstate();ap=AP.available(t.t);seen=[]
  record=self.pending_skill(t,decision=lambda check:seen.append(check) or 'invalid')
  self.assertEqual(len(seen),1);self.assertNotEqual(t.e.rng.getstate(),before);self.assertEqual(t.e._ap_rolls['skill-attempt']['state'],'resolved');self.assertEqual(record['state'],'pending');self.assertEqual(t.used(F.MISTAKES),0);self.assertEqual(AP.available(t.t),ap)
  current=t.e.rng.getstate();out=t.mistakes(dc=99,fixed=None,reroll_faces=None,decision=lambda check:False,roll_id='skill-attempt')
  self.assertEqual(out['check'],seen[0]);self.assertEqual(current,t.e.rng.getstate());self.assertEqual(record['state'],'complete');self.assertFalse(out['rerolled'])
 def test_mistakes_callback_exception_keeps_same_observation(self):
  t=self.skill();seen=[]
  def unavailable(check):seen.append(check);raise RuntimeError('UI disconnected')
  with self.assertRaises(RuntimeError):t.mistakes(dc=99,fixed=None,decision=unavailable,roll_id='skill-attempt')
  self.assertEqual(t.e._ap_rolls['skill-attempt'][OBS.KEY]['state'],'pending');out=t.mistakes(dc=99,fixed=None,decision=lambda check:False,roll_id='skill-attempt');self.assertEqual(out['check'],seen[0])
 def test_mistakes_original_faces_dc_modifiers_and_identity_cannot_change(self):
  t=self.skill();record=self.pending_skill(t);before=t.e.rng.getstate()
  for changes in ({'fixed':[6]*3},{'dc':12},{'mods':5},{'roll_id':'another'}):
   opts={'dc':99,'fixed':None,'reroll_faces':None,'decision':lambda check:False,'roll_id':'skill-attempt'};opts.update(changes)
   with self.assertRaises(ValueError):t.mistakes(**opts)
  self.assertEqual(before,t.e.rng.getstate());self.assertEqual(record['state'],'pending')
 def test_mistakes_generated_identity_resumes_pending_and_reports_same_id(self):
  t=self.skill();seen=[]
  with self.assertRaises(ValueError):t.mistakes(decision=lambda check:seen.append(check) or 'bad')
  key=next(k for k,v in t.e._ap_rolls.items() if OBS.KEY in v)
  out=t.mistakes(decision=lambda check:False);self.assertEqual(out['roll_id'],key);self.assertEqual(out['check'],seen[0]);self.assertEqual(len(t.e._ap_rolls),1)
 def test_mistakes_reroll_preserves_original_rank_ap_helper_and_bonus_once(self):
  t=self.skill();t.e.boost_roll(t.t,t.p,roll_id='skill-attempt',kind='skill')
  opts={'dc':99,'roll_id':'skill-attempt','fixed':[1]*3,'mods':2,'helper_rank':4,'penalty_count':1,'fixed_penalties':[1],'reroll_penalties':[1]}
  with self.assertRaises(ValueError):t.mistakes(**opts,decision=lambda check:'bad')
  first=t.e._ap_rolls['skill-attempt'][OBS.KEY]['observation']['first'];t.p.spec['skills']['육상']=6;t.p.spec['poffins']=['슬기로움']*6
  out=t.mistakes(**opts,reroll_faces=[2]*3,decision=lambda check:True)
  self.assertEqual(out['first_roll'],first);self.assertEqual(out['roll'].rank,3);self.assertEqual(out['roll'].modifier,first.modifier+5);self.assertEqual(out['poffin_bonus'],5);self.assertEqual(t.used(F.MISTAKES),1)
 def test_mistakes_private_bad_reroll_keeps_first_and_does_not_spend_feature(self):
  t=self.skill();t.e.rng=Sequence([1,1,1,0,2,2])
  with self.assertRaises(ValueError):t.mistakes(fixed=None,reroll_faces=None,roll_id='skill-attempt')
  first=t.e._ap_rolls['skill-attempt'][OBS.KEY]['observation']['first'];self.assertEqual(t.e.rng.faces,[0,2,2]);self.assertEqual(t.used(F.MISTAKES),0)
  out=t.mistakes(fixed=None,roll_id='skill-attempt');self.assertEqual(out['first_roll'],first);self.assertEqual(t.e.rng.faces,[0,2,2]);self.assertEqual(t.used(F.MISTAKES),1)
 def test_mistakes_late_permission_failure_leaves_decision_pending(self):
  t=self.skill();seen=[]
  def interrupt(check):seen.append(check);t.t.conditions.add('잠듦');return True
  with self.assertRaises(ValueError):t.mistakes(decision=interrupt,roll_id='skill-attempt')
  self.assertEqual(t.used(F.MISTAKES),0);self.assertEqual(t.e._ap_rolls['skill-attempt'][OBS.KEY]['state'],'pending')
  out=t.mistakes(decision=lambda check:False,roll_id='skill-attempt');self.assertEqual(out['check'],seen[0]);self.assertFalse(out['rerolled'])
 def test_mistakes_preflight_invalid_faces_and_permission_have_no_observation(self):
  for kind in ('faces','permission'):
   t=self.skill();before=t.e.rng.getstate()
   if kind=='permission':t.t.conditions.add('잠듦')
   with self.assertRaises(ValueError):t.mistakes(fixed=None,reroll_faces=[2] if kind=='faces' else None)
   self.assertEqual(t.e.rng.getstate(),before);self.assertFalse(t.e._ap_rolls);self.assertEqual(t.used(F.MISTAKES),0)
 def test_mistakes_snapshot_restores_pending_observation_with_live_actors(self):
  t=self.skill();self.pending_skill(t);t.e.gm.snapshot('observed');t.mistakes(dc=99,fixed=None,reroll_faces=None,decision=lambda check:False,roll_id='skill-attempt');t.e.gm.restore('observed')
  record=t.e._ap_rolls['skill-attempt'][OBS.KEY];self.assertIs(record['participants'][0],t.t);self.assertIs(record['participants'][1],t.p);self.assertEqual(record['state'],'pending')
  out=t.mistakes(dc=99,fixed=None,reroll_faces=None,decision=lambda check:False,roll_id='skill-attempt');self.assertEqual(out['first_roll'],record['observation']['first'])
 def test_completed_skill_identity_cannot_reapply_result_or_feature(self):
  t=self.skill();t.mistakes(roll_id='skill-attempt');state=t.e.rng.getstate();used=t.used(F.MISTAKES)
  with self.assertRaises(ValueError):t.mistakes(roll_id='skill-attempt')
  self.assertEqual(state,t.e.rng.getstate());self.assertEqual(t.used(F.MISTAKES),used)
 def test_each_contest_callback_preserves_first_rng_stat_dice_and_move(self):
  for kind in ('coordinator','flourish'):
   t=self.contest();seen=[];before=t.e.rng.getstate();callback='reroll_decision' if kind=='coordinator' else 'flourish_decision'
   with self.assertRaises(ValueError):self.perform(t,kind,**{callback:lambda preview:seen.append(preview) or 'bad'})
   c=t.cs[0];record=t.e._performance_observations['appeal-attempt'][OBS.KEY]
   self.assertEqual(c.stat_dice['근사함'],3);self.assertEqual(c.last_move,'move/연속자르기');self.assertNotEqual(t.e.rng.getstate(),before);self.assertEqual(record['state'],'pending');self.assertEqual(c.appeal,0);self.assertEqual(AP.available(t.ts[0]),AP.maximum(t.ts[0]))
   before=t.e.rng.getstate();self.perform(t,kind,**{callback:lambda preview:False})
   self.assertEqual(t.e.rng.getstate(),before);self.assertEqual(c.stat_dice['근사함'],3);self.assertEqual((c.appeal,c.fumble),t.e.score(seen[0]['rolls'],False));self.assertEqual(record['state'],'complete');self.assertFalse(t.e._coordinator_used|t.e._flourish_used)
 def test_contest_cannot_change_move_spend_faces_feature_or_attempt_id(self):
  t=self.contest()
  with self.assertRaises(ValueError):self.perform(t)
  before=t.e.rng.getstate()
  for changes in ({'spend_stat_dice':0},{'fixed_rolls':[6]*5},{'attempt_id':'another'},{'reroll_decision':None}):
   with self.assertRaises(ValueError):self.perform(t,**changes)
  with self.assertRaises(ValueError):t.e.perform(t.cs[0],'헤롱헤롱','귀여움',[],False)
  self.assertEqual(before,t.e.rng.getstate());self.assertEqual(t.cs[0].stat_dice['근사함'],3)
 def test_contest_callback_exception_and_implicit_identity_resume(self):
  t=self.contest();seen=[]
  def disconnected(preview):seen.append(preview);raise RuntimeError('UI disconnected')
  with self.assertRaises(RuntimeError):self.perform(t,attempt_id=None,reroll_decision=disconnected)
  before=t.e.rng.getstate();self.perform(t,attempt_id=None,reroll_decision=lambda preview:False)
  self.assertEqual(before,t.e.rng.getstate());self.assertEqual(len(t.e._performance_observations),1);self.assertEqual(next(iter(t.e._performance_observations.values()))[OBS.KEY]['state'],'complete')
 def test_contest_new_reroll_cost_and_final_scoring_commit_once(self):
  for kind in ('coordinator','flourish'):
   t=self.contest();callback='reroll_decision' if kind=='coordinator' else 'flourish_decision';faces=[1,2,1,6,3]
   with self.assertRaises(ValueError):self.perform(t,kind,fixed_rolls=faces)
   t.e.rng=Sequence([6]*5 if kind=='coordinator' else [1,6]);self.perform(t,kind,fixed_rolls=faces,**{callback:lambda preview:True})
   expected=[6]*5 if kind=='coordinator' else [1,2,6,6,3];self.assertEqual((t.cs[0].appeal,t.cs[0].fumble),t.e.score(expected,False));self.assertEqual(t.cs[0].stat_dice['근사함'],3);self.assertEqual(t.ts[0].spec.get('ap_spent',0),int(kind=='flourish'));self.assertEqual(t.ts[0]._action_history,['free'])
   self.assertEqual(len(t.e._coordinator_used if kind=='coordinator' else t.e._flourish_used),1)
   with self.assertRaises(ValueError):self.perform(t,kind,fixed_rolls=faces,**{callback:lambda preview:True})
 def test_contest_late_ap_unavailability_does_not_cancel_original_appeal(self):
  t=self.contest();seen=[]
  def spent_elsewhere(preview):seen.append(preview);t.ts[0].spec['ap_spent']=AP.maximum(t.ts[0]);return True
  with self.assertRaises(ValueError):self.perform(t,'flourish',flourish_decision=spent_elsewhere)
  before=t.e.rng.getstate();self.perform(t,'flourish',flourish_decision=lambda preview:False)
  self.assertEqual(before,t.e.rng.getstate());self.assertEqual((t.cs[0].appeal,t.cs[0].fumble),t.e.score(seen[0]['rolls'],False));self.assertEqual(t.cs[0].stat_dice['근사함'],3);self.assertFalse(t.e._flourish_used)
 def test_contest_known_invalid_input_and_permission_do_not_observe(self):
  for kind in ('faces','permission'):
   t=self.contest();before=t.e.rng.getstate();original=deepcopy(vars(t.cs[0]))
   if kind=='permission':t.ts[0].conditions.add('잠듦')
   with self.assertRaises(ValueError):self.perform(t,fixed_rolls=[1] if kind=='faces' else None)
   self.assertEqual(before,t.e.rng.getstate());self.assertEqual(vars(t.cs[0]),original);self.assertFalse(t.e._performance_observations)
 def test_public_decision_cannot_reenter_the_same_observed_attempt(self):
  t=self.skill()
  def reenter(check):return t.mistakes(roll_id='skill-attempt')
  with self.assertRaises(ValueError):t.mistakes(roll_id='skill-attempt',decision=reenter)
  self.assertEqual(t.e._ap_rolls['skill-attempt'][OBS.KEY]['state'],'pending')
  out=t.mistakes(roll_id='skill-attempt',decision=lambda check:False);self.assertFalse(out['rerolled'])
 def test_original_feature_source_scopes_unchanged(self):
  rows=json.loads((ROOT/'data/verification/category3-register.json').read_text(encoding='utf-8'))['entries']
  for row in rows:
   if row['id'] not in ('C3-EX-061','C3-EX-064'):continue
   for a in row['source_snapshot']['source_anchors']:
    excerpt='\n'.join((ROOT/a['file']).read_text(encoding='utf-8-sig').splitlines()[a['start_line']-1:a['end_line']]);self.assertEqual(excerpt,a['excerpt']);self.assertEqual(hashlib.sha256(excerpt.encode()).hexdigest(),a['excerpt_sha256'])
  source=(ROOT/'input/ch08-contests.md').read_text(encoding='utf-8');self.assertIn('그 콘테스트에서 다시 사용되지 않을 수 있습니다',source)
if __name__=='__main__':
 class Result(unittest.TextTestResult):
  def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
  def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':t._testMethodName,'status':'pass'})
  def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':t._testMethodName,'status':'fail'})
  def addError(self,t,e):super().addError(t,e);self.rows.append({'id':t._testMethodName,'status':'error'})
 result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 paths=sorted(str(p.relative_to(ROOT)).replace('\\','/') for p in (ROOT/'engine').glob('*.py'))+['tools/test_observed_resolution_contract.py','tools/test_category3_contest_skill_features.py','tools/test_category3_contest_features.py','input/ch04-trainer-classes.md','input/ch08-contests.md','data/contest-rules.json','data/adjudication-guidance.json']
 report={'generated_at':datetime.now(timezone.utc).isoformat(),'successful':result.wasSuccessful(),'scope':['observed_resolution_contract'],'affected_scopes':['C3-EX-061','C3-EX-064'],'not_new_clause_completion':True,'results':result.rows,'input_hashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}}
 (ROOT/'output/observed-resolution-contract-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 raise SystemExit(not result.wasSuccessful())
