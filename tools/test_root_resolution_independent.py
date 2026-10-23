"""Independent model oracles; no natural-language source certification."""
import sys,json,hashlib,unittest,itertools
from pathlib import Path
from dataclasses import replace
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from engine import root_resolution as R
T,F=R.TRUE,R.FALSE
U=R.Predicate(R.Truth.UNKNOWN,'unknown-evidence')
def c(id='a',aspect='x',value=1,**kw):return R.Clause(id,aspect,value,**kw)
def law(aspect='x',kind='exclusive',**kw):return R.CompositionLaw(aspect,kind,'model-law',**kw)
def edge(a,b,guard=T):return R.Override(a,b,'x',guard,'edge-'+a+b)
def req(cs=None,**kw):
 d=dict(event_id='event-1',event_kind='test-model',profile_hash='profile-1',catalog_hash='catalog-1',context_hash='context-1',clauses=tuple(cs or []),candidate_closure=T,laws=(law(),))
 d.update(kw);return R.ResolutionRequest(**d)
def run(cs=None,**kw):return R.resolve(req(cs,**kw))
def codes(v):return {x.code for x in v.obligations}
class Independent(unittest.TestCase):
 def ready(self,r,value=None):
  self.assertEqual(r.tag,'ModelReady');self.assertFalse(r.gameplay_certified);self.assertFalse(r.receipt['source_ready'])
  if value is not None:self.assertEqual(R.plain(r.aspects[0].value),value)
 def test_01_single_ready(self):self.ready(run([c(value=7)]),7)
 def test_02_all_false_excluded(self):
  r=run([c(selected=F)]);self.assertEqual(r.tag,'Excluded');self.assertEqual(r.aspects,());self.assertFalse(r.receipt['source_ready'])
 def test_03_strong_kleene_all_positions(self):
  for values in itertools.permutations([T,F,U]):self.assertEqual(R.conjunction(*values).truth,R.Truth.FALSE)
  self.assertEqual(R.conjunction(T,U).truth,R.Truth.UNKNOWN)
  for key in ('selected','scope','premises'):
   kwargs={'selected':U,'scope':U,'premises':U};kwargs[key]=F
   self.ready(run([c('known',value=7),c('excluded',**kwargs)]),7)
 def test_04_relevant_unknown_pending(self):self.assertIn('unknown_applicability',codes(run([c(),c('b',value=2,scope=U)])))
 def test_05_transitive_active_chain(self):
  r=run([c('a'),c('b',value=2),c('c',value=3)],overrides=(edge('a','b'),edge('b','c')));self.ready(r,3);self.assertEqual(r.aspects[0].dominated,('a','b'))
 def test_06_inactive_intermediate_never_carries_edge(self):
  for key in ('selected','scope','premises'):
   r=run([c('a'),c('b',value=2,**{key:F}),c('c',value=3)],overrides=(edge('a','b'),edge('b','c')));self.assertEqual(r.tag,'Pending');self.assertIn('composition_unresolved',codes(r))
 def test_07_direct_witness_survives_inactive_intermediate(self):self.ready(run([c('a'),c('b',selected=F),c('c',value=3)],overrides=(edge('a','b'),edge('b','c'),edge('a','c'))),3)
 def test_08_false_guard_no_dominance(self):self.assertEqual(run([c('a'),c('b',value=2)],overrides=(edge('a','b',F),)).tag,'Pending')
 def test_09_unknown_material_edge_pending(self):self.assertIn('unknown_override_influence',codes(run([c('a'),c('b',value=2)],overrides=(edge('a','b',U),))))
 def test_10_irrelevant_unknown_edge_known_alternate_path(self):
  r=run([c('a'),c('b',value=2),c('c',value=3)],overrides=(edge('a','b'),edge('b','c'),edge('a','c',U)));self.ready(r,3);self.assertIn('edge-ac',r.receipt['ignored_unknown_edges_by_maxima_noninfluence'])
 def test_11_true_cycle_rejected(self):self.assertIn('cyclic_override_relation',codes(run([c('a'),c('b')],overrides=(edge('a','b'),edge('b','a')))))
 def test_12_false_cycle_edge_ignored(self):self.ready(run([c('a'),c('b',value=2)],overrides=(edge('a','b'),edge('b','a',F))),2)
 def test_13_clause_edge_permutations(self):
  for cs in itertools.permutations([c('a'),c('b',value=2),c('c',value=3)]):
   for es in itertools.permutations([edge('a','b'),edge('b','c')]):self.ready(run(cs,overrides=es),3)
 def test_14_equal_assignment_requires_explicit_idempotence(self):
  self.assertEqual(run([c('a'),c('b')]).tag,'Pending');self.ready(run([c('a'),c('b')],laws=(law(idempotent=True),)),1)
 def test_15_conflicting_equal_priority_no_winner(self):self.assertEqual(run([c('newest'),c('older',value=2)],laws=(law(idempotent=True),)).tag,'Pending')
 def test_16_exact_addition_source_example(self):self.ready(run([c('a',value=20),c('b',value=30)],laws=(law(kind='additive'),)),50)
 def test_17_exact_rational_addition(self):self.ready(run([c('a',value={'numerator':1,'denominator':3}),c('b',value={'numerator':1,'denominator':6})],laws=(law(kind='additive'),)),{'numerator':1,'denominator':2})
 def test_18_every_declared_numeric_operator_positive(self):
  for kind,want in [('product',6),('minimum',2),('maximum',3)]:self.ready(run([c('a',value=2),c('b',value=3)],laws=(law(kind=kind),)),want)
 def test_19_sequence_and_union_positive(self):
  self.ready(run([c('a',value='first'),c('b',value='second')],laws=(law(kind='sequence',contributor_order=('b','a')),)),['second','first'])
  self.ready(run([c('a',value=[1,2]),c('b',value=[2,3])],laws=(law(kind='set_union',idempotent=True),)),[1,2,3])
 def test_20_missing_and_unknown_laws_pending(self):
  for ls in [(),(law(kind='unregistered'),),(law(guard=U),)]:self.assertEqual(run([c()],laws=ls).tag,'Pending')
 def test_21_aspect_locality(self):
  r=run([c('a'),c('b',value=2),c('a-other','y',9)],overrides=(edge('a','b'),),laws=(law(),law('y')));self.ready(r);self.assertEqual({p.aspect:p.value for p in r.aspects},{'x':2,'y':9})
 def test_22_disjoint_write_ready(self):
  cs=[c('a','x',1,footprint=R.Footprint(writes=(('actors','a','hp'),))),c('b','y',2,footprint=R.Footprint(writes=(('actors','b','hp'),)))]
  self.ready(run(cs,laws=(law(),law('y'))))
 def test_23_read_write_and_parent_path_conflict(self):
  for rhs in [R.Footprint(reads=(('actors','a','hp'),)),R.Footprint(writes=(('actors','a','hp'),))]:
   cs=[c('a','x',footprint=R.Footprint(writes=(('actors','a'),))),c('b','y',footprint=rhs)]
   self.assertIn('unordered_gameplay_dependency',codes(run(cs,laws=(law(),law('y')))))
 def test_24_write_observation_interference(self):
  cs=[c('a','x',footprint=R.Footprint(writes=(('actors','a','hp'),))),c('b','y',footprint=R.Footprint(observations=(('actors','a','hp'),)))]
  self.assertEqual(run(cs,laws=(law(),law('y'))).tag,'Pending','one-sided observer still depends on written HP')
 def test_25_rng_and_decision_interference(self):
  for path in [('rng','stream'),('decision','choice-1'),('events','child')]:
   cs=[c('a','x',footprint=R.Footprint(observations=(path,))),c('b','y',footprint=R.Footprint(observations=(path,)))]
   self.assertIn('unordered_observation_dependency',codes(run(cs,laws=(law(),law('y')))))
 def test_26_explicit_order_and_commutation_positive(self):
  cs=[c('a','x',footprint=R.Footprint(writes=(('shared',),),observations=(('rng',),))),c('b','y',footprint=R.Footprint(reads=(('shared',),),observations=(('rng',),)))]
  self.ready(run(cs,laws=(law(),law('y')),aspect_orders=(R.AspectOrder('x','y',T,'order'),)))
  self.ready(run(cs,laws=(law(),law('y')),independences=(R.Independence('x','y',T,'commute',True,True),)))
 def test_27_aspect_cycle_pending(self):self.assertIn('cyclic_aspect_order',codes(run([c('a'),c('b','y')],laws=(law(),law('y')),aspect_orders=(R.AspectOrder('x','y',T,'xy'),R.AspectOrder('y','x',T,'yx')))))
 def test_28_open_candidate_closure_pending(self):
  for p in [F,U]:self.assertIn('candidate_closure_incomplete',codes(run([c()],candidate_closure=p)))
 def test_29_source_labels_never_certify(self):
  r=run([c(source_refs=('source-reviewed:true','namespace:approved'))]);self.ready(r)
  with self.assertRaises(ValueError):replace(r,tag='SourceReady')
  with self.assertRaises(ValueError):replace(r,gameplay_certified=True)
 def test_30_receipt_binds_context_and_plan(self):
  q=req([c()]);base=R.resolve(q).request_fingerprint
  for key in ('event_id','event_kind','profile_hash','catalog_hash','context_hash'):
   self.assertNotEqual(R.resolve(replace(q,**{key:'changed'})).request_fingerprint,base)
  for changed in [replace(q,clauses=(c(value=2),)),replace(q,laws=(law(kind='additive'),)),replace(q,clauses=(c(footprint=R.Footprint(reads=(('world',),))),))]:self.assertNotEqual(R.resolve(changed).request_fingerprint,base)
 def test_31_pure_repeat_and_payload_guard(self):
  q=req([c()]);before=R.canonical(q);r=R.resolve(q);self.assertEqual(R.canonical(q),before);self.assertEqual(R.canonical(r),R.canonical(R.resolve(q)));self.assertFalse(R.plan_payload(r)['source_ready'])
  with self.assertRaises(ValueError):R.plan_payload(run([c(scope=U)]))
 def test_32_within_aspect_observation_law(self):
  cs=[c('a',value=1,footprint=R.Footprint(observations=(('rng',),))),c('b',value=2,footprint=R.Footprint(observations=(('decision',),)))]
  self.assertEqual(run(cs,laws=(law(kind='additive'),)).tag,'Pending')
  self.ready(run(cs,laws=(law(kind='additive',observation_policy='ordered',contributor_order=('b','a')),)),3)
 def test_33_explicit_query_does_not_pull_other_aspect_unknown(self):self.ready(run([c('a'),c('b','other',scope=U)],aspects=('x',)),1)
 def test_34_true_and_unknown_cycle_safety(self):self.assertIn('unknown_override_influence',codes(run([c('a'),c('b',value=2)],overrides=(edge('a','b'),edge('b','a',U)))))
 def test_35_predicate_reads_preserved_and_interfere(self):
  pred=R.Predicate(R.Truth.TRUE,reads=(("actors","a","hp"),))
  cs=[c("a","x",footprint=R.Footprint(writes=(("actors","a","hp"),))),c("b","y",scope=pred)]
  self.assertIn("unordered_gameplay_dependency",codes(run(cs,laws=(law(),law("y")))))
  q=req([c("excluded",selected=F,scope=pred)],candidate_closure=R.Predicate(R.Truth.TRUE,reads=(("catalog","closure"),)))
  r=R.resolve(q);self.assertEqual(r.tag,"Excluded");self.assertIn(("actors","a","hp"),r.footprint.reads);self.assertIn(("catalog","closure"),r.footprint.reads)
 def test_36_within_aspect_write_observation_interference(self):
  cs=[c("a",value=1,footprint=R.Footprint(writes=(("actors","a","hp"),))),c("b",value=2,footprint=R.Footprint(observations=(("actors","a","hp"),)))]
  self.assertEqual(run(cs,laws=(law(kind="additive"),)).tag,"Pending","numeric addition does not order one writer and one observer")
  self.ready(run(cs,laws=(law(kind="additive",observation_policy="ordered",contributor_order=("a","b")),)),3)
class Results(unittest.TextTestResult):
 def __init__(self,*a,**kw):super().__init__(*a,**kw);self.records=[]
 def addSuccess(self,t):super().addSuccess(t);self.records.append({'id':'R04-INDEPENDENT-'+t._testMethodName,'status':'pass'})
 def addFailure(self,t,e):super().addFailure(t,e);self.records.append({'id':'R04-INDEPENDENT-'+t._testMethodName,'status':'fail','detail':self._exc_info_to_string(e,t)})
 def addError(self,t,e):super().addError(t,e);self.records.append({'id':'R04-INDEPENDENT-'+t._testMethodName,'status':'error','detail':self._exc_info_to_string(e,t)})
if __name__=='__main__':
 result=unittest.TextTestRunner(verbosity=1,resultclass=Results).run(unittest.defaultTestLoader.loadTestsFromTestCase(Independent))
 paths=['engine/root_resolution.py','tools/test_root_resolution_independent.py','data/verification/topdown-r04-contract.json']
 report={'results':result.records,'input_hashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest()for p in paths},'summary':{'run':result.testsRun,'pass':sum(x['status']=='pass'for x in result.records),'fail':len(result.failures),'error':len(result.errors)},'scope':'Pure typed R04 resolver model. Synthetic witnesses do not prove source semantics or parent admission. Source 20+30 example is a bounded numeric composition oracle only.','whole_source_complete':False}
 (ROOT/'output').mkdir(exist_ok=True);(ROOT/'output/root-resolution-independent-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8');sys.exit(not result.wasSuccessful())
