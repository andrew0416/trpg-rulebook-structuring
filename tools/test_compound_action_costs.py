"""Conjunctive costs through actual feature callers; no leaf-effect coverage claim."""
import copy,hashlib,json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_action_points as _fixture_test_action_points
import action_metadata as META
import action_lifecycle as ACTION
import turn as TURN
import frequency as FREQ
import items as ITEMS
from mechanize_feats import parse_frequency

class CompoundCostTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):_fixture_test_action_points.ActionPointTests.setUpClass()
 def fixture(self,automatic=False):
  helper=_fixture_test_action_points.ActionPointTests();e,a,b,rid=helper.fixture(automatic=automatic,frequency=parse_frequency('2 AP - 기본 행동 + 신속 행동'))
  mm=e.r.feats_mech[rid]
  e.start_round([a,b]);e.start_of_turn(a)
  FREQ.activation_allowed(a,rid,mm['header']['frequency'],engine=e)
  return helper,e,a,b,rid
 def snapshot(self,e,a,b):
  return copy.deepcopy((a.spec,a.budget,a.counters,a.took_standard,
   getattr(a,'_action_history',[]),getattr(a,'_standard_action_round',None),
   getattr(a,'_restricted_action_taken',False),b.hp,b.injuries,b.conditions,e.elapsed_seconds))
 def rec(self,a,automatic):
  return next(x for x in (a.ability_triggers if automatic else a.registry)
              if x.get('_feat') or x.get('type')=='feat_manual')
 def check(self,automatic,case):
  helper,e,a,b,rid=self.fixture(automatic);r=self.rec(a,automatic)
  if case=='missing_standard':a.budget['standard']=0
  elif case=='missing_swift':a.budget['swift']=0
  elif case=='paralysis':a._turn_action_limit={'choose_one_of':['standard','shift']}
  elif case=='sleep':a.conditions.add('잠듦')
  elif case=='frozen':a.conditions.add('얼음')
  elif case=='wrong_turn':e._active_turn_actor=b
  elif case=='ap_short':a.spec['ap_spent']=6
  elif case=='heavy':a.injuries=5
  elif case=='unresolved_effect':r['effects']=[{'type':'unimplemented_compound_fixture'}]
  elif case=='frequency':
   r['frequency']={'raw':'하루 - 기본 행동 + 신속 행동','kind':'daily','uses':1}
   FREQ.consume_activation(a,rid,r['frequency'],engine=e)
  before=self.snapshot(e,a,b)
  helper.fire(e,a,b,rid,automatic)
  if case=='success':
   self.assertEqual(a.budget,{'standard':0,'shift':1,'swift':0})
   self.assertEqual(a.spec['ap_spent'],2);self.assertEqual(b.injuries,1)
   self.assertEqual(a._action_history,[{'kind':'compound','components':['standard','swift']}])
   self.assertTrue(a.took_standard);self.assertEqual(a._standard_action_round,e.round_no)
  else:self.assertEqual(self.snapshot(e,a,b),before)
 def test_parser_recovers_only_exact_legacy_first_component(self):
  for raw in ['임의 - 기본 행동 + 신속 행동','임의 - 기본 행동+신속 행동']:
   freq=parse_frequency(raw);self.assertEqual(freq['action'],'standard')
   self.assertEqual(META.resolve_feature_action({'frequency':freq}),(META.ActionCost(('standard','swift')),''))
   freq['action']='shift';self.assertIsNone(META.resolve_feature_action({'frequency':freq})[0])
 def test_priority_duplicate_and_unknown_are_not_costs(self):
  for raw in ['기본 행동 + 우선','기본 행동 + 기본 행동','기본 행동 + mystery','완전 행동 + 신속 행동','항상 + 자유 행동']:
   self.assertIsNone(META.resolve_feature_action({'frequency':{'raw':'임의 - '+raw,'action':'standard'}})[0])
 def test_full_remains_distinct(self):
  _,e,a,b,_=self.fixture();self.assertTrue(TURN.spend(e,a,'full'))
  self.assertEqual(a.budget,{'standard':0,'shift':0,'swift':1})
  self.assertEqual(a._action_history,['full']);self.assertFalse(a.took_standard)
 def test_explicit_standard_reserved_before_conversion(self):
  _,e,a,b,_=self.fixture();a.budget={'standard':1,'shift':0,'swift':1}
  before=self.snapshot(e,a,b)
  self.assertFalse(TURN.spend(e,a,META.ActionCost(('shift','standard'))))
  self.assertEqual(self.snapshot(e,a,b),before)
 def test_ordinary_standard_conversion_is_retained(self):
  _,e,a,b,_=self.fixture();a.budget={'standard':1,'shift':0,'swift':1}
  self.assertTrue(TURN.spend(e,a,META.ActionCost(('shift','swift'))))
  self.assertEqual(a.budget,{'standard':0,'shift':0,'swift':0})
  self.assertFalse(a.took_standard)
  self.assertEqual(a._action_history,[{'kind':'compound','components':['shift','swift']}])
 def test_failed_first_or_last_component_is_atomic(self):
  for components in [('standard','swift'),('swift','standard')]:
   for missing in ('standard','swift'):
    _,e,a,b,_=self.fixture();a.budget[missing]=0;before=self.snapshot(e,a,b)
    self.assertFalse(TURN.spend(e,a,META.ActionCost(components)))
    self.assertEqual(self.snapshot(e,a,b),before)
 def test_movement_not_inferred_from_shift_cost(self):
  _,e,a,b,_=self.fixture();a.budget={'standard':1,'shift':0,'swift':1}
  self.assertTrue(TURN.spend(e,a,META.ActionCost(('shift','swift'))))
  self.assertFalse(a._regular_shift_movement_used)
 def test_snapshot_restores_single_compound_record(self):
  helper,e,a,b,rid=self.fixture();before=self.snapshot(e,a,b);e.gm.snapshot('compound')
  helper.fire(e,a,b,rid);e.gm.restore('compound');self.assertEqual(self.snapshot(e,a,b),before)
 def test_actual_source_labels_and_stored_headers(self):
  for file,line in [('input/ch03-skills-edges-feats.md',729),('input/ch04-trainer-classes.md',708)]:
   text=(ROOT/file).read_text(encoding='utf-8').splitlines()[line-1]
   self.assertIn('기본 행동',text);self.assertIn('신속 행동',text)
  records=json.loads((ROOT/'data/feats-mech.json').read_text(encoding='utf-8'))
  if isinstance(records,dict) and 'units' in records:records=records['units']
  if isinstance(records,dict):records=[dict(rec,id=rid) for rid,rec in records.items()]
  found=[]
  for rec in records:
   if rec.get('id') in ('feat/집중-명령','feat/응원-문구'):
    found.append(rec['id']);self.assertEqual(META.resolve_feature_action(rec['header'])[0],META.ActionCost(('standard','swift')))
  self.assertEqual(set(found),{'feat/집중-명령','feat/응원-문구'})

for automatic in (False,True):
 for case in ('success','missing_standard','missing_swift','paralysis','sleep','frozen','wrong_turn','ap_short','heavy','unresolved_effect','frequency'):
  def test(self,automatic=automatic,case=case):self.check(automatic,case)
  setattr(CompoundCostTests,'test_'+('trigger' if automatic else 'manual')+'_'+case,test)

if __name__=='__main__':
 class Result(unittest.TextTestResult):
  def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
  def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':'COMPOUND-'+t._testMethodName,'status':'pass'})
  def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':'COMPOUND-'+t._testMethodName,'status':'fail'})
  def addError(self,t,e):super().addError(t,e);self.rows.append({'id':'COMPOUND-'+t._testMethodName,'status':'error'})
 result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(CompoundCostTests))
 files=['engine/action_metadata.py','engine/turn.py','engine/action_lifecycle.py','engine/items.py','engine/effects.py','tools/test_compound_action_costs.py','tools/synthetic_rule_fixture.py','input/ch03-skills-edges-feats.md','input/ch04-trainer-classes.md','input/ch07-combat.md','data/feats-mech.json']
 report={'scope':'Conjunctive cost interpretation and actual feature dispatch; no leaf or heavy Standard completion claim.','whole_semantic_complete':False,'results':result.rows,'input_hashes':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}}
 (ROOT/'output/compound-action-cost-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 raise SystemExit(0 if result.wasSuccessful() else 1)
