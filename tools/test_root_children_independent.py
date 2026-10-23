"""Independent synthetic child lifecycle model tests, not source Engine proof."""
import sys,json,hashlib,unittest
from pathlib import Path
from dataclasses import replace
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from engine import root_machine as M,root_scheduler as S,root_children as C,root_resolution as R
REF=('model-explicit-order',)
def spec(key='child',**kw):
 d=dict(key=key,event_kind='child',payload={},barrier='before_parent_complete',completion_owner='parent',scope='test-event-scope',source_refs=REF,timing='after_emission');d.update(kw);return C.ChildSpec(**d)
def node(id='n',key='x',value=1,*,after=(),children=(),guard=None,increment=False,**kw):
 path=('world',key)
 def update(v,e,j):return M.Commit((M.Write(path,v.get(path)+value if increment else value),),value,children)
 return M.Node(id,(path,) if increment else (), (path,),guard or (lambda v,e,j:M.Guard(M.Truth.TRUE)),update,after=after,**kw)
def schedule(nodes,kind='parent',deps=()):
 p=M.Plan('plan-'+kind,'p',kind,tuple(nodes),'model_experiment',REF)
 return S.Schedule(p,R.Footprint(tuple(q for n in nodes for q in n.reads),tuple(q for n in nodes for q in n.writes)),deps)
def env():
 g={k:{}for k in M.DOMAINS};g['world']={'x':0,'y':0,'z':0,'prefix':0,'childprefix':0,'result':0,'final':0}
 m=M.Machine(M.Snapshot('p',0,g));return m,S.Scheduler(m)
def event(m,id='parent',kind='parent'):return M.Event(id,kind,'p',m.state.revision)
def wait_guard(v,e,j):return M.Guard(M.Truth.TRUE) if j.get('answer')==7 else M.Guard(M.Truth.UNKNOWN,M.NeedInput('answer','source_choice','synthetic exact decision'))
def submit_child(m,s,parent='parent',emitter='emit',key='child',nodes=None,deps=()):
 id=C.child_id(parent,emitter,key);e=m.child_event(id);sc=schedule(nodes or [node('effect','result',7)],'child',deps);return s.submit(sc,e),id,sc,e
class Independent(unittest.TestCase):
 def parent(self,specs=None,follow=False):
  m,s=env();specs=tuple(specs or [spec(before_nodes=('finish',)if follow else ())]);ns=[node('emit','prefix',1,increment=True,children=specs)]
  if follow:
   ns.append(M.Node('finish',(('world','result'),),(('world','final'),),lambda v,e,j:M.Guard(M.Truth.TRUE),lambda v,e,j:M.Commit((M.Write(('world','final'),v.get(('world','result'))),)),after=('emit',)))
  sc=schedule(ns);e=event(m);o=s.submit(sc,e);return m,s,sc,e,o
 def test_01_required_child_then_parent_reads_result(self):
  m,s,sc,e,o=self.parent(follow=True);self.assertEqual(o.tag,'AwaitingChildren');self.assertEqual(m.state.game['world']['final'],0)
  out,id,_,_=submit_child(m,s);self.assertEqual(out.tag,'Completed');self.assertEqual(s.resume_children(e.id).tag,'Completed');self.assertEqual(m.state.game['world']['final'],7);self.assertEqual(m.state.game['world']['prefix'],1)
 def test_02_required_child_input_pending_propagates(self):
  m,s,_,e,_=self.parent(follow=True);out,id,_,_=submit_child(m,s,nodes=[node('effect','result',7,guard=wait_guard)]);self.assertEqual(out.tag,'AwaitingInput');self.assertIn(s.resume_children(e.id).tag,('AwaitingChildren','BlockedDependency'));self.assertEqual(m.state.game['world']['final'],0);self.assertEqual(s.resume(id,{'answer':7}).tag,'Completed');self.assertEqual(s.resume_children(e.id).tag,'Completed')
 def test_03_required_child_blocked_propagates(self):
  m,s,_,e,_=self.parent();guard=lambda v,e,j:M.Guard(M.Truth.UNKNOWN,M.Block('missing_refinement','child effect missing'));out,id,_,_=submit_child(m,s,nodes=[node(guard=guard)]);self.assertEqual(out.tag,'Blocked');self.assertEqual(s.resume_children(e.id).tag,'AwaitingChildren');self.assertEqual(m.state.children[id].status,'blocked')
 def test_04_grandchild_wait_and_completion(self):
  m,s,_,e,_=self.parent();out,id,_,_=submit_child(m,s,nodes=[node('emit','childprefix',1,children=(spec('grand'),))]);self.assertEqual(out.tag,'AwaitingChildren');self.assertEqual(s.resume_children(e.id).tag,'AwaitingChildren')
  gout,gid,_,_=submit_child(m,s,parent=id,key='grand',nodes=[node('grand','result',7)]);self.assertEqual(gout.tag,'Completed');self.assertEqual(s.resume_children(id).tag,'Completed');self.assertEqual(s.resume_children(e.id).tag,'Completed');self.assertEqual(m.state.children[gid].status,'completed')
 def test_05_grandchild_blocked_stays_transitive(self):
  m,s,_,e,_=self.parent();_,id,_,_=submit_child(m,s,nodes=[node('emit','childprefix',1,children=(spec('grand'),))]);bad=lambda v,e,j:M.Guard(M.Truth.UNKNOWN,M.Block('missing_runtime','grandchild unavailable'));out,_,_,_=submit_child(m,s,parent=id,key='grand',nodes=[node(guard=bad)]);self.assertEqual(out.tag,'Blocked');self.assertEqual(s.resume_children(id).tag,'AwaitingChildren');self.assertEqual(s.resume_children(e.id).tag,'AwaitingChildren')
 def test_06_independent_lifetime_parent_completes_responsibility_remains(self):
  m,s,_,e,o=self.parent([spec(barrier='independent_lifetime',completion_owner='effect-instance:1',scope='until-source-boundary',timing='after_parent_complete')]);self.assertEqual(o.tag,'Completed');id=C.child_id(e.id,'emit','child');row=m.state.children[id];self.assertEqual(row.status,'outstanding');self.assertEqual(row.spec.completion_owner,'effect-instance:1');self.assertEqual(row.spec.scope,'until-source-boundary');out,_,_,_=submit_child(m,s);self.assertEqual(out.tag,'Completed');self.assertIn(id,m.state.children);self.assertEqual(m.state.children[id].status,'completed')
 def test_07_owner_and_scope_required(self):
  for kw in [{'completion_owner':''},{'scope':''}]:
   with self.assertRaises(ValueError):spec(barrier='independent_lifetime',**kw)
 def test_08_unknown_barrier_preserves_prefix_not_complete(self):
  m,s,_,e,o=self.parent([spec(barrier='unknown')]);self.assertEqual(o.tag,'AwaitingChildren');self.assertEqual(m.state.game['world']['prefix'],1);self.assertIsInstance(m.child_event(C.child_id(e.id,'emit','child')),M.Block);self.assertEqual(s.resume_children(e.id).tag,'AwaitingChildren');self.assertEqual(m.state.game['world']['prefix'],1)
 def test_09_unknown_timing_preserved(self):
  m,s,_,e,o=self.parent([spec(timing='unknown')]);self.assertEqual(o.tag,'AwaitingChildren');self.assertEqual(s.resume_children(e.id).tag,'AwaitingChildren')
 def test_10_causal_parent_not_completion_dependency(self):
  m,s,_,e,o=self.parent();self.assertEqual(o.tag,'AwaitingChildren');out,_,_,_=submit_child(m,s);self.assertEqual(out.tag,'Completed')
 def test_11_exact_parent_replay_no_reemission(self):
  m,s,sc,e,o=self.parent();self.assertEqual(s.submit(sc,e),o);self.assertEqual(m.state.game['world']['prefix'],1);self.assertEqual(len(m.state.children),1)
 def test_12_child_replay_no_effect_repeat(self):
  m,s,_,_,_=self.parent();out,id,sc,e=submit_child(m,s,nodes=[node('effect','result',1,increment=True)]);self.assertEqual(out.tag,'Completed');self.assertEqual(s.submit(sc,e).tag,'Completed');self.assertEqual(m.state.game['world']['result'],1)
 def test_13_duplicate_child_key_rejected_before_patch(self):
  m,s=env();sc=schedule([node('emit','prefix',1,children=(spec(),spec(payload={'different':True})))]);o=s.submit(sc,event(m));self.assertEqual(o.tag,'Blocked');self.assertEqual(m.state.game['world']['prefix'],0);self.assertEqual(len(m.state.children),0)
 def test_14_changed_child_payload_and_parent_rejected(self):
  m,s,_,_,_=self.parent();id=C.child_id('parent','emit','child');e=m.child_event(id);sc=schedule([node()],kind='child')
  for altered in [replace(e,payload={'different':True}),replace(e,parent='unrelated')]:self.assertEqual(s.submit(sc,altered).tag,'RejectedStaleOrMismatch')
  self.assertNotIn(id,m.state.occurrences)
 def test_15_dynamic_false_no_children(self):
  m,s=env();false=lambda v,e,j:M.Guard(M.Truth.FALSE);sc=schedule([node('emit','prefix',1,children=(spec(),),guard=false,false_policy='exclude')]);o=s.submit(sc,event(m));self.assertEqual(o.tag,'Completed');self.assertEqual(len(m.state.children),0);self.assertEqual(m.state.game['world']['prefix'],0)
 def test_16_false_dynamic_required_consumer_is_unresolved(self):
  m,s=env();false=lambda v,e,j:M.Guard(M.Truth.FALSE);n0=node('emit','prefix',1,children=(spec(before_nodes=('finish',)),),guard=false,false_policy='exclude');n1=node('finish','final',1,after=('emit',),after_children=(('emit','child'),));o=s.submit(schedule([n0,n1]),event(m));self.assertEqual(o.tag,'AwaitingChildren');self.assertEqual(m.state.game['world']['final'],0)
 def test_17_child_prefix_resumes_once(self):
  m,s,_,e,_=self.parent();ns=[node('pre','childprefix',1,increment=True),node('finish','result',7,after=('pre',),guard=wait_guard)];o,id,_,_=submit_child(m,s,nodes=ns);self.assertEqual(o.tag,'AwaitingInput');self.assertEqual(m.state.game['world']['childprefix'],1);self.assertEqual(s.resume(id,{'answer':7}).tag,'Completed');self.assertEqual(s.resume_children(e.id).tag,'Completed');self.assertEqual(m.state.game['world']['childprefix'],1);self.assertEqual(m.state.game['world']['prefix'],1)
 def test_18_independent_siblings_all_settle(self):
  a=spec('a',independent_siblings=('b',));b=spec('b',independent_siblings=('a',));m,s,_,e,_=self.parent([a,b]);oa,_,_,_=submit_child(m,s,key='a',nodes=[node('a','x',1)]);self.assertEqual(oa.tag,'Completed');self.assertEqual(s.resume_children(e.id).tag,'AwaitingChildren');ob,_,_,_=submit_child(m,s,key='b',nodes=[node('b','y',2)]);self.assertEqual(ob.tag,'Completed');self.assertEqual(s.resume_children(e.id).tag,'Completed')
 def test_19_explicit_sibling_dependency_positive_and_reverse_wait(self):
  a=spec('a');b=spec('b',after_siblings=('a',));m,s,_,e,_=self.parent([a,b]);ob,_,_,_=submit_child(m,s,key='b',nodes=[node('b','x',1,increment=True)]);self.assertEqual(ob.tag,'BlockedDependency');oa,_,_,_=submit_child(m,s,key='a',nodes=[node('a','x',1)]);self.assertEqual(oa.tag,'Completed');ob,_,_,_=submit_child(m,s,key='b',nodes=[node('b','x',1,increment=True)]);self.assertEqual(ob.tag,'Completed');self.assertEqual(m.state.game['world']['x'],2);self.assertEqual(s.resume_children(e.id).tag,'Completed')
 def test_20_unordered_siblings_cannot_invent_submit_order(self):
  m,s,_,_,_=self.parent([spec('a'),spec('b')]);out,_,_,_=submit_child(m,s,key='a',nodes=[node('a','x',1)]);self.assertEqual(out.tag,'BlockedDependency');self.assertEqual(m.state.game['world']['x'],0)
 def test_21_independent_sibling_can_run_while_other_waits(self):
  m,s,_,e,_=self.parent([spec('a',independent_siblings=('b',)),spec('b',independent_siblings=('a',))]);a,aid,_,_=submit_child(m,s,key='a',nodes=[node('a','x',1,guard=wait_guard)]);self.assertEqual(a.tag,'AwaitingInput');b,_,_,_=submit_child(m,s,key='b',nodes=[node('b','y',1)]);self.assertEqual(b.tag,'Completed');self.assertEqual(s.resume(aid,{'answer':7}).tag,'Completed');self.assertEqual(s.resume_children(e.id).tag,'Completed')
 def test_22_sibling_cycle_rejected_before_prefix(self):
  m,s,_,_,o=self.parent([spec('a',after_siblings=('b',)),spec('b',after_siblings=('a',))]);self.assertEqual(o.tag,'Blocked');self.assertEqual(m.state.game['world']['prefix'],0);self.assertEqual(len(m.state.children),0)
 def test_23_source_false_child_not_successful_settlement(self):
  m,s,_,e,_=self.parent();false=lambda v,e,j:M.Guard(M.Truth.FALSE);o,id,_,_=submit_child(m,s,nodes=[node(guard=false)]);self.assertEqual(o.tag,'Rejected');self.assertEqual(m.state.children[id].status,'rejected');self.assertEqual(s.resume_children(e.id).tag,'AwaitingChildren')
 def test_24_childless_backward_compatible(self):
  m,s=env();sc=schedule([node()]);e=event(m);o=s.submit(sc,e);self.assertEqual(o.tag,'Completed');self.assertEqual(m.state.game['world']['x'],1);self.assertEqual(len(m.state.children),0)
 def test_25_new_parent_occurrence_generates_distinct_child(self):
  m,s,sc,e,_=self.parent();submit_child(m,s);s.resume_children(e.id);e2=event(m,'parent-2');o=s.submit(sc,e2);self.assertEqual(o.tag,'AwaitingChildren');self.assertEqual(len(m.state.children),2);self.assertNotEqual(C.child_id(e.id,'emit','child'),C.child_id(e2.id,'emit','child'));self.assertEqual(m.state.game['world']['prefix'],2)
 def test_26_external_machine_change_blocks_resume(self):
  m,s,_,e,_=self.parent();m.state=M.Snapshot(m.state.profile,m.state.revision,m.state.game,m.state.occurrences,m.state.children);self.assertEqual(s.resume_children(e.id).tag,'RejectedStaleOrMismatch');self.assertEqual(m.state.game['world']['prefix'],1)
 def test_27_unknown_parent_node_order_stays_unresolved(self):
  m,s,_,e,o=self.parent([spec()],follow=True);self.assertEqual(o.tag,'AwaitingChildren');submit_child(m,s);self.assertEqual(s.resume_children(e.id).tag,'AwaitingChildren');self.assertEqual(m.state.game['world']['final'],0)
 def test_28_after_parent_timing_cannot_execute_early(self):
  late=spec('late',barrier='independent_lifetime',timing='after_parent_complete',independent_nodes=('wait',));m,s=env();sc=schedule([node('emit','prefix',1,children=(late,)),node('wait','x',1,after=('emit',),guard=wait_guard)]);e=event(m);o=s.submit(sc,e);self.assertEqual(o.tag,'AwaitingInput');self.assertIsInstance(m.child_event(C.child_id(e.id,'emit','late')),M.Block)
 def test_29_emission_payload_immutable(self):
  value={'nested':[1]};child=spec(payload=value);value['nested'][0]=9;self.assertEqual(C.plain(child.payload),{'nested':[1]})
 def test_30_independent_unplanned_lifetime_blocks_unproven_future_event(self):
  m,s,_,_,o=self.parent([spec(barrier='independent_lifetime',timing='after_parent_complete')]);self.assertEqual(o.tag,'Completed');other=s.submit(schedule([node('other','z',1)],'other'),event(m,'other','other'));self.assertEqual(other.tag,'BlockedDependency');self.assertEqual(m.state.game['world']['z'],0)
 def test_31_existing_waiter_cannot_resume_across_unknown_child(self):
  m,s=env();prior=schedule([node("waiting","z",1,guard=wait_guard)],"prior");e0=event(m,"prior","prior");self.assertEqual(s.submit(prior,e0).tag,"AwaitingInput")
  parent=schedule([node("emit","prefix",1,children=(spec(),))]);self.assertEqual(s.submit(parent,event(m)).tag,"AwaitingChildren")
  outcome=s.resume(e0.id,{"answer":7});self.assertEqual(outcome.tag,"BlockedDependency","resume must honor same unknown descendant frontier as a new submit");self.assertEqual(m.state.game["world"]["z"],0)
 def test_32_parent_resume_observes_new_unplanned_child_frontier(self):
  m,s,_,e,_=self.parent(follow=True);self.assertEqual(submit_child(m,s)[0].tag,"Completed")
  other=schedule([node("emit","y",1,children=(spec(),))],"other");self.assertEqual(s.submit(other,event(m,"other","other")).tag,"AwaitingChildren")
  out=s.resume_children(e.id);self.assertEqual(out.tag,"BlockedDependency");self.assertEqual(m.state.game["world"]["final"],0)
 def test_33_parent_resume_cannot_overlap_pending_independent_child(self):
  a=spec("a",barrier="independent_lifetime",independent_nodes=("finish",),independent_siblings=("b",))
  b=spec("b",before_nodes=("finish",),independent_siblings=("a",))
  m,s,_,e,_=self.parent([a,b],follow=True)
  out,aid,_,_=submit_child(m,s,key="a",nodes=[node("a","final",9,guard=wait_guard)]);self.assertEqual(out.tag,"AwaitingInput")
  out,_,_,_=submit_child(m,s,key="b",nodes=[node("b","result",7)]);self.assertEqual(out.tag,"Completed")
  out=s.resume_children(e.id);self.assertEqual(out.tag,"BlockedDependency","independent_nodes label does not defeat actual pending write conflict");self.assertEqual(m.state.game["world"]["final"],0)
 def test_34_terminal_parent_ignores_only_past_write_overlap(self):
  a=spec("a",barrier="independent_lifetime",independent_siblings=("b",));b=spec("b",independent_siblings=("a",))
  m,s,_,e,_=self.parent([a,b]);out,aid,_,_=submit_child(m,s,key="a",nodes=[node("a","prefix",9,guard=wait_guard)]);self.assertEqual(out.tag,"AwaitingInput")
  self.assertEqual(submit_child(m,s,key="b")[0].tag,"Completed");self.assertEqual(s.resume_children(e.id).tag,"Completed");self.assertEqual(m.state.game["world"]["prefix"],1);self.assertEqual(m.state.children[aid].status,"awaiting_input")
 def test_35_waiter_resumes_after_unknown_frontier_settles(self):
  m,s=env();prior=schedule([node("waiting","z",1,guard=wait_guard)],"prior");e0=event(m,"prior","prior");self.assertEqual(s.submit(prior,e0).tag,"AwaitingInput")
  parent=schedule([node("emit","prefix",1,children=(spec(),))]);e=event(m);self.assertEqual(s.submit(parent,e).tag,"AwaitingChildren");self.assertEqual(s.resume(e0.id,{"answer":7}).tag,"BlockedDependency")
  self.assertEqual(submit_child(m,s)[0].tag,"Completed");self.assertEqual(s.resume_children(e.id).tag,"Completed");self.assertEqual(s.resume(e0.id,{"answer":7}).tag,"Completed");self.assertEqual(m.state.game["world"]["z"],1);self.assertEqual(m.state.game["world"]["prefix"],1)
 def test_36_continuation_preserves_declared_context_reads(self):
  a=spec("a",barrier="independent_lifetime",independent_nodes=("finish",),independent_siblings=("b",));b=spec("b",before_nodes=("finish",),independent_siblings=("a",))
  m,s,_,e,_=self.parent([a,b],follow=True);aid=C.child_id(e.id,"emit","a");base=schedule([node("a","z",9,guard=wait_guard)],"child")
  scoped=S.Schedule(base.plan,R.Footprint(reads=(("world","final"),),writes=base.footprint.writes));self.assertEqual(s.submit(scoped,m.child_event(aid)).tag,"AwaitingInput")
  self.assertEqual(submit_child(m,s,key="b")[0].tag,"Completed")
  self.assertEqual(s.resume_children(e.id).tag,"BlockedDependency","declared scope/predicate reads survive continuation footprint reduction");self.assertEqual(m.state.game["world"]["final"],0)
class Results(unittest.TextTestResult):
 def __init__(self,*a,**kw):super().__init__(*a,**kw);self.records=[]
 def addSuccess(self,t):super().addSuccess(t);self.records.append({'id':'ROOTCHILD-INDEPENDENT-'+t._testMethodName,'status':'pass'})
 def addFailure(self,t,e):super().addFailure(t,e);self.records.append({'id':'ROOTCHILD-INDEPENDENT-'+t._testMethodName,'status':'fail','detail':self._exc_info_to_string(e,t)})
 def addError(self,t,e):super().addError(t,e);self.records.append({'id':'ROOTCHILD-INDEPENDENT-'+t._testMethodName,'status':'error','detail':self._exc_info_to_string(e,t)})
if __name__=='__main__':
 result=unittest.TextTestRunner(verbosity=1,resultclass=Results).run(unittest.defaultTestLoader.loadTestsFromTestCase(Independent));files=['engine/root_machine.py','engine/root_scheduler.py','engine/root_children.py','engine/root_resolution.py','tools/test_root_children_independent.py','data/verification/topdown-root-contract.json'];report={'results':result.records,'input_hashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest()for p in files},'summary':{'run':result.testsRun,'pass':sum(r['status']=='pass'for r in result.records),'fail':len(result.failures),'error':len(result.errors)},'scope':'Synthetic root Machine/Scheduler child emission and lifecycle. Trusted source ordering declarations are not source certificates. No live Engine, source admission, general Bound AP lifespan or durable snapshot completion.','whole_source_complete':False,'actual_engine_connection':False};(ROOT/'output/root-child-independent-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8');sys.exit(not result.wasSuccessful())
