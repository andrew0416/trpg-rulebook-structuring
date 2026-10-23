"""Dynamic child kernel author checks; synthetic only, source registration absent."""
from pathlib import Path
import sys,json,hashlib,traceback,dataclasses
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from engine import root_machine as m,root_children as c,root_scheduler as s,root_resolution as r
P='synthetic-profile';REF='synthetic:child';HP=('actors','a','hp');COST=('actors','a','cost')
def eq(a,b):assert a==b,(a,b)
def world():
 g={k:{} for k in m.DOMAINS};g['actors']={'a':{'hp':100,'cost':10}}
 mach=m.Machine(m.Snapshot(P,0,g));return mach,s.Scheduler(mach)
def spec(key='x',barrier='before_parent_complete',timing='after_emission',**kw):return c.ChildSpec(key,'child',{'amount':5},barrier,'actor:a','synthetic-action-completion',(REF,),timing,**kw)
def emitting(specs,extra=(),false=False):
 n=m.Node('emit',(COST,),(COST,),lambda v,e,d:m.Guard(m.Truth.FALSE if false else m.Truth.TRUE),lambda v,e,d:m.Commit((m.Write(COST,v.get(COST)-1),),'emit',tuple(specs)),false_policy='exclude' if false else 'reject')
 return m.Plan('parent',P,'parent',(n,)+tuple(extra),'model_experiment',(REF,))
def schedule(plan):return s.Schedule(plan,r.Footprint(tuple(p for n in plan.nodes for p in n.reads),tuple(p for n in plan.nodes for p in n.writes)))
def child_plan(wait=False,reject=False,grand=()):
 def guard(v,e,d):
  if reject:return m.Guard(m.Truth.FALSE)
  if wait and 'yes' not in d:return m.Guard(m.Truth.UNKNOWN,m.NeedInput('yes','source_choice','synthetic'))
  return m.Guard(m.Truth.TRUE)
 n=m.Node('apply',(HP,),(HP,),guard,lambda v,e,d:m.Commit((m.Write(HP,v.get(HP)-e.payload['amount']),),'child',tuple(grand)))
 return m.Plan('child-plan',P,'child',(n,),'model_experiment',(REF,))
def begin(specs,extra=(),false=False):
 mach,sch=world();plan=emitting(specs,extra,false);sc=schedule(plan);ev=m.Event('parent','parent',P,0);out=sch.submit(sc,ev);return mach,sch,sc,ev,out
def emitid(mach,key='x',parent='parent',node='emit'):return c.child_id(parent,node,key)
def dispatch(mach,sch,id,plan=None):
 ev=mach.child_event(id);assert isinstance(ev,m.Event),ev
 sc=schedule(plan or child_plan());return sch.submit(sc,ev),sc,ev
rows=[]
def run(id,fn):
 try:fn();rows.append({'id':'ROOT-CHILD-AUTHOR-'+id,'status':'passed'})
 except Exception:rows.append({'id':'ROOT-CHILD-AUTHOR-'+id,'status':'failed','detail':traceback.format_exc()})
def required():
 mach,sch,sc,ev,out=begin([spec()]);eq(out.tag,'AwaitingChildren');eq(mach.state.game['actors']['a']['cost'],9);id=emitid(mach);eq(mach.state.children[id].status,'outstanding');eq(dispatch(mach,sch,id)[0].tag,'Completed');eq(mach.state.children[id].status,'completed');eq(sch.resume_children('parent').tag,'Completed');eq(mach.state.game['actors']['a']['hp'],95)
run('001-required-dynamic-child',required)
def duplicate():
 mach,sch,sc,ev,out=begin([spec()]);eq(sch.submit(sc,ev),out);eq(len(mach.state.children),1);eq(mach.state.game['actors']['a']['cost'],9)
 co,cs,ce=dispatch(mach,sch,emitid(mach));eq(sch.submit(cs,ce),co);eq(mach.state.game['actors']['a']['hp'],95)
run('002-idempotent-no-duplicate-emission',duplicate)
def independent(timing):
 mach,sch,sc,ev,out=begin([spec(barrier='independent_lifetime',timing=timing)]);eq(out.tag,'Completed');row=mach.state.children[emitid(mach)];eq(row.status,'outstanding');eq(row.spec.completion_owner,'actor:a');eq(dispatch(mach,sch,row.id)[0].tag,'Completed');eq(mach.state.occurrences['parent'].outcome.tag,'Completed')
run('003-independent-responsibility',lambda:independent('after_emission'));run('004-post-parent-dispatch',lambda:independent('after_parent_complete'))
def unknown(field):
 kw={field:'unknown'};mach,sch,sc,ev,out=begin([spec(**kw)]);eq(out.tag,'AwaitingChildren');eq(mach.state.game['actors']['a']['cost'],9);eq(type(mach.child_event(emitid(mach))),m.Block);eq(sch.resume_children('parent').tag,'AwaitingChildren')
run('005-unknown-barrier',lambda:unknown('barrier'));run('006-unknown-timing',lambda:unknown('timing'))
def cycle():
 for kw in ({'timing':'after_parent_complete'},{'barrier':'independent_lifetime','timing':'after_parent_complete','before_nodes':('after',)}):
  try:spec(**kw)
  except ValueError:pass
  else:raise AssertionError('cycle accepted')
run('007-completion-timing-cycles',cycle)
def child_state(which):
 mach,sch,sc,ev,out=begin([spec()]);id=emitid(mach);co,cs,ce=dispatch(mach,sch,id,child_plan(wait=which=='wait',reject=which=='reject'));eq(co.tag,'AwaitingInput' if which=='wait' else 'Rejected');eq(sch.resume_children('parent').tag,'AwaitingChildren')
 if which=='wait':eq(sch.resume(id,{'yes':True}).tag,'Completed');eq(sch.resume_children('parent').tag,'Completed')
run('008-child-awaits-input',lambda:child_state('wait'));run('009-child-rejected-not-settled',lambda:child_state('reject'))
def grandchild():
 mach,sch,sc,ev,out=begin([spec()]);id=emitid(mach);co,cs,ce=dispatch(mach,sch,id,child_plan(grand=(spec(key='g'),)));eq(co.tag,'AwaitingChildren');eq(sch.resume_children('parent').tag,'AwaitingChildren');gid=c.child_id(id,'apply','g');eq(dispatch(mach,sch,gid)[0].tag,'Completed');eq(sch.resume_children(id).tag,'Completed');eq(sch.resume_children('parent').tag,'Completed');eq(mach.state.game['actors']['a']['hp'],90)
run('010-grandchild-transitive-completion',grandchild)
def later_node(after_children=()):return m.Node('after',(HP,),(HP,),lambda v,e,d:m.Guard(m.Truth.TRUE),lambda v,e,d:m.Commit((m.Write(HP,v.get(HP)*2),),'reads-child-result'),after=('emit',),after_children=after_children)
def child_before_parent():
 mach,sch,sc,ev,out=begin([spec(before_nodes=('after',))],(later_node((('emit','x'),)),));eq(out.tag,'AwaitingChildren');eq(mach.state.game['actors']['a']['hp'],100);dispatch(mach,sch,emitid(mach));eq(sch.resume_children('parent').tag,'Completed');eq(mach.state.game['actors']['a']['hp'],190);eq(mach.state.game['actors']['a']['cost'],9)
run('011-child-result-parent-consumer',child_before_parent)
def independent_parent_node():
 n=m.Node('after',(COST,),(COST,),lambda v,e,d:m.Guard(m.Truth.TRUE),lambda v,e,d:m.Commit((m.Write(COST,v.get(COST)-1),)),after=('emit',))
 mach,sch,sc,ev,out=begin([spec(independent_nodes=('after',))],(n,));eq(out.tag,'AwaitingChildren');eq(out.committed,('emit','after'));eq(mach.state.game['actors']['a']['cost'],8)
run('012-completion-barrier-not-global-pause',independent_parent_node)
def missing_order():
 mach,sch,sc,ev,out=begin([spec()],(later_node(),));eq(out.tag,'AwaitingChildren');eq(out.committed,('emit',));eq(mach.state.game['actors']['a']['hp'],100);dispatch(mach,sch,emitid(mach));eq(sch.resume_children('parent').tag,'AwaitingChildren')
run('013-unknown-child-parent-order',missing_order)
def false_emission(dependent=False):
 mach,sch,sc,ev,out=begin([spec()],(later_node((('emit','x'),)),) if dependent else (),True);eq(len(mach.state.children),0);eq(mach.state.game['actors']['a']['cost'],10);eq(out.tag,'AwaitingChildren' if dependent else 'Completed')
run('014-conditional-no-emission',false_emission);run('015-absent-dynamic-dependency-unresolved',lambda:false_emission(True))
def forged_child():
 mach,sch,sc,ev,out=begin([spec()]);id=emitid(mach);ce=mach.child_event(id);before=mach.state;bad=dataclasses.replace(ce,payload={'amount':100});o=sch.submit(schedule(child_plan()),bad);eq(o.tag,'RejectedStaleOrMismatch');assert mach.state is before
run('016-exact-child-event-binding',forged_child)
def unplanned():
 mach,sch,sc,ev,out=begin([spec(barrier='independent_lifetime')]);before=mach.state;o=sch.submit(schedule(child_plan()),m.Event('unrelated','child',P,mach.state.revision,{'amount':1}));eq(o.tag,'BlockedDependency');assert mach.state is before
run('017-unplanned-responsibility-not-forgotten',unplanned)
def siblings(ordered):
 specs=(spec(key='x'),spec(key='y',after_siblings=('x',))) if ordered else (spec(key='x'),spec(key='y'))
 mach,sch,sc,ev,out=begin(specs)
 if not ordered:eq(dispatch(mach,sch,emitid(mach))[0].tag,'BlockedDependency');eq(mach.state.game['actors']['a']['hp'],100);return
 eq(dispatch(mach,sch,emitid(mach,'y'))[0].tag,'BlockedDependency');eq(dispatch(mach,sch,emitid(mach))[0].tag,'Completed');eq(dispatch(mach,sch,emitid(mach,'y'))[0].tag,'Completed');eq(sch.resume_children('parent').tag,'Completed')
run('018-ordered-siblings',lambda:siblings(True));run('019-unknown-sibling-order',lambda:siblings(False))
def bad_batch(kind):
 specs=(spec(),spec()) if kind=='duplicate' else (spec('x',after_siblings=('y',)),spec('y',after_siblings=('x',))) if kind=='cycle' else (dataclasses.replace(spec(),source_refs=('outside',)),)
 mach,sch,sc,ev,out=begin(specs);eq(out.tag,'Blocked');eq(mach.state.game['actors']['a']['cost'],10);eq(len(mach.state.children),0)
for n,k in enumerate(('duplicate','cycle','source'),20):run(f'{n:03}-invalid-batch-{k}',lambda k=k:bad_batch(k))
def immutable_snapshot():
 payload={'amount':5};sp=dataclasses.replace(spec(),payload=payload);mach,sch,sc,ev,out=begin([sp]);old=mach.state;payload['amount']=99;eq(old.children[emitid(mach)].spec.payload['amount'],5);dispatch(mach,sch,emitid(mach));eq(old.children[emitid(mach)].status,'outstanding');eq(mach.state.children[emitid(mach)].status,'completed')
run('023-inprocess-snapshot-immutability',immutable_snapshot)
files=['engine/root_children.py','engine/root_machine.py','engine/root_scheduler.py','engine/root_resolution.py','tools/test_root_children_author.py'];report={'scope':'synthetic dynamic child structural tests, source registrations0','results':rows,'input_hashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files}}
(ROOT/'output/root-children-author-tests.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps({'total':len(rows),'passed':sum(x['status']=='passed' for x in rows),'failures':[x for x in rows if x['status']!='passed']},indent=2));raise SystemExit(any(x['status']!='passed' for x in rows))
