"""Independent compound cost caller tests; payloads isolate common contracts, not leaf effects."""
from pathlib import Path
import copy,hashlib,json,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from synthetic_rule_fixture import register_synthetic
from mechanize_feats import parse_frequency
import action_metadata as M,items as I,effects as FX,frequency as F,turn as T

class Independent(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.rules=Rules(str(ROOT),ruleset='core')
  register_synthetic(cls.rules,'feat/compound-independent',name='explicit compound cost isolation')
 def fixture(self,automatic=False,raw='장면 x1 - 기본 행동 + 신속 행동',effects=None):
  r=self.rules;rid='feat/compound-independent';header={'frequency':parse_frequency(raw)}
  payload=[{'type':'cost','ap':2},{'type':'injury','value':1,'target':'target'}] if effects is None else effects
  if automatic:payload=[{'type':'trigger','text':'사용자가 기술을 사용할 때'}]+payload
  r.feats_mech[rid]={'name':rid,'coverage':'full','header':header,'effects':payload}
  e=Engine(r,seed=29)
  def actor(n):return Combatant(r,{'name':n,'kind':'trainer','level':10,'stats':{x:30 for x in ('hp','atk','def','spa','spd','spe')},'abilities':[],'moves':[],'types':[]})
  a,b=actor('A'),actor('B');e.everyone=e.gm.everyone=[a,b];a.spec['feats']=[rid]
  I.register_feats(e,a);e.start_round([a,b]);e.start_of_turn(a);F.activation_allowed(a,rid,header['frequency'],engine=e)
  return e,a,b,rid
 def fire(self,e,a,b,rid,automatic):
  return FX.fire_event(e,a,{'event':'on_move_use','move':{'name':'isolation'}},b) if automatic else I.manual_feat(e,a,rid,b)
 def state(self,e,a,b):return copy.deepcopy((a.spec,b.spec,a.budget,a.hp,b.hp,a.injuries,b.injuries,a.conditions,a._action_history,a.took_standard,getattr(a,'_standard_action_round',None),getattr(a,'_restricted_action_taken',False),a.counters,b.counters,e.rng.getstate(),e.elapsed_seconds))
 def test_actual_source_header_legacy_truncation_recovers_both_costs(self):
  _,h=self.rules.feat_effects('feat/집중-명령');cost,problem=M.resolve_feature_action(h)
  self.assertFalse(problem);self.assertEqual(cost.components,('standard','swift'))
  for raw in ('임의 - 기본 행동+신속 행동','임의 - 기본 행동 + 신속 행동'):
   self.assertEqual(M.resolve_feature_action({'frequency':parse_frequency(raw)})[0].components,('standard','swift'))
 def test_conflict_and_unknown_timing_do_not_authorize(self):
  for raw,declared in [('임의 - 기본 행동+신속 행동','free'),('임의 - 기본 행동+신속 행동','shift'),('임의 - 기본 행동+우선','standard'),('임의 - 기본 행동+신속 행동+방해','standard'),('임의 - 기본 행동+기본 행동','standard')]:
   self.assertIsNone(M.resolve_feature_action({'frequency':{'raw':raw,'action':declared}})[0])
 def test_duplicate_and_empty_components_are_not_deduplicated(self):
  for terms in [('standard','standard'),('standard',''),('full','swift')]:
   with self.assertRaises(ValueError):M.ActionCost(terms)
 def test_full_type_stays_separate(self):
  full,_=M.resolve_feature_action({'frequency':parse_frequency('임의 - 완전 행동')});self.assertEqual(full,'full')
  e,a,b,rid=self.fixture();a.budget={'standard':1,'shift':1,'swift':0}
  self.assertTrue(T.spend(e,a,full));self.assertEqual(a.budget,{'standard':0,'shift':0,'swift':0});self.assertEqual(a._action_history,['full'])
 def test_lower_cost_funding_order_is_not_action_count(self):
  # Engineering resource-algebra control; this does not grant extra gameplay actions.
  for components in [('shift','swift'),('swift','shift')]:
   e,a,b,rid=self.fixture();a.budget={'standard':1,'shift':0,'swift':1}
   self.assertTrue(T.spend(e,a,M.ActionCost(components)))
   self.assertEqual(a.budget,{'standard':0,'shift':0,'swift':0});self.assertFalse(a.took_standard);self.assertEqual(len(a._action_history),1)
 def test_explicit_standard_reserved_before_conversion(self):
  for components in [('standard','swift'),('swift','standard')]:
   e,a,b,rid=self.fixture();a.budget={'standard':1,'shift':1,'swift':0};before=self.state(e,a,b)
   self.assertFalse(T.spend(e,a,M.ActionCost(components)));self.assertEqual(self.state(e,a,b),before)
 def test_actual_callers_hold_late_unknown_priority_and_true_conflict(self):
  for automatic in (False,True):
   for raw,action in [('장면 x1 - 기본 행동+신속 행동+우선','standard'),('장면 x1 - 기본 행동+신속 행동','free')]:
    e,a,b,rid=self.fixture(automatic)
    records=a.ability_triggers if automatic else a.registry
    record=next(x for x in records if x.get('_feat') or x.get('type')=='feat_manual')
    record['activation_header']['frequency'].update(raw=raw,action=action)
    before=self.state(e,a,b);self.fire(e,a,b,rid,automatic);self.assertEqual(self.state(e,a,b),before)
 def test_snapshot_restore_preserves_compound_record_and_single_frequency(self):
  e,a,b,rid=self.fixture();e.gm.snapshot('before');self.fire(e,a,b,rid,False)
  expected=self.state(e,a,b);e.gm.snapshot('after');e.gm.restore('before');self.fire(e,a,b,rid,False)
  self.assertEqual(self.state(e,a,b),expected);e.gm.restore('after');self.assertEqual(self.state(e,a,b),expected)

for automatic in (False,True):
 for case in ('success','missing_swift','missing_standard','shift_zero','ap_short','exhausted','paralysis','sleep_selfcure','frozen','fainted','other_turn','heavy','unknown_effect'):
  def test(self,automatic=automatic,case=case):
   effects=[{'type':'cure_status','status':['잠듦'],'target':'self'}] if case=='sleep_selfcure' else ([{'type':'unresolved_fixture_effect'}] if case=='unknown_effect' else None)
   e,a,b,rid=self.fixture(automatic,effects=effects)
   if case=='missing_swift':a.budget['swift']=0
   elif case=='missing_standard':a.budget['standard']=0
   elif case=='shift_zero':a.budget['shift']=0
   elif case=='ap_short':a.spec['ap_spent']=6
   elif case=='exhausted':F.consume_activation(a,rid,{'kind':'scene','uses':1},engine=e)
   elif case=='paralysis':a._turn_action_limit={'choose_one_of':['standard','shift']}
   elif case=='sleep_selfcure':a.conditions.add('잠듦')
   elif case=='frozen':a.conditions.add('얼음')
   elif case=='fainted':a.hp=0
   elif case=='other_turn':e.end_of_turn(a);e.start_of_turn(b)
   elif case=='heavy':a.injuries=5;a.hp=50
   before=self.state(e,a,b);self.fire(e,a,b,rid,automatic)
   if case in ('success','shift_zero'):
    self.assertEqual(a.budget,{'standard':0,'shift':0 if case=='shift_zero' else 1,'swift':0})
    self.assertEqual(a.spec.get('ap_spent'),2);self.assertEqual(b.injuries,1)
    self.assertEqual(F.state(a)['activations'][rid]['used'],1);self.assertTrue(a.took_standard)
    self.assertEqual(a._action_history,[{'kind':'compound','components':['standard','swift']}])
   else:
    self.assertEqual(self.state(e,a,b),before)
    if case=='heavy':self.assertTrue(any('중상' in x and '보류' in x for x in e.log_lines))
  setattr(Independent,'test_'+('trigger_' if automatic else 'manual_')+case,test)

if __name__=='__main__':
 class Result(unittest.TextTestResult):
  def __init__(self,*a,**k):super().__init__(*a,**k);self.rows=[]
  def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':'COMPOUND-INDEPENDENT-'+t._testMethodName,'status':'pass'})
  def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':'COMPOUND-INDEPENDENT-'+t._testMethodName,'status':'fail','detail':self._exc_info_to_string(e,t)})
  def addError(self,t,e):super().addError(t,e);self.rows.append({'id':'COMPOUND-INDEPENDENT-'+t._testMethodName,'status':'error','detail':self._exc_info_to_string(e,t)})
 r=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(Independent))
 paths=[Path(__file__),ROOT/'tools/mechanize_feats.py',ROOT/'tools/synthetic_rule_fixture.py']+list((ROOT/'engine').glob('*.py'))+list((ROOT/'data').glob('*.json'))+list((ROOT/'output/entities').glob('*.json'))+[ROOT/'output/ruleunits.jsonl',ROOT/'output/source-audit/2026-10-10/xlsx-cells.json']
 report={'results':r.rows,'input_hashes':{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},'scope':'Common cost dispatch with synthetic isolated effects; no named feature effects or generic heavy consequence completion.','semantic_closure':False,'whole_rulebook_complete':False}
 (ROOT/'output/compound-action-independent-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 raise SystemExit(not r.wasSuccessful())
