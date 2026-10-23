from pathlib import Path
import sys,json,hashlib
from dataclasses import replace
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from engine import root_machine as m,root_resolution as r,root_scheduler as s
RESULTS=[]
HP=('actors','a','hp');COST=('resources','a','ap');OTHER=('actors','b','hp')
def eq(a,b):assert a==b,(a,b)
def test(i,fn):
 try:fn();RESULTS.append({'id':f'FRONTIER-INDEPENDENT-{i:03}','status':'pass'})
 except Exception as e:RESULTS.append({'id':f'FRONTIER-INDEPENDENT-{i:03}','status':'fail','error':repr(e)})
def raises(fn):
 try:fn()
 except (TypeError,ValueError):return
 raise AssertionError('must reject')
def fresh(invariants=(),invariant_reads=None):
 g={d:{} for d in m.DOMAINS};g['actors']={'a':{'hp':10},'b':{'hp':20}};g['resources']={'a':{'ap':3}}
 machine=m.Machine(m.Snapshot('p',0,g),invariants);return s.Scheduler(machine,invariant_reads)
def event(sc,uid='A',**kw):return m.Event(uid,'model','p',sc.machine.state.revision,**kw)
def node(uid='n',reads=(HP,),writes=(HP,),wait=False,after=(),bad=False):
 def guard(v,e,inputs):
  if reads:v.get(reads[0])
  return m.Guard(m.Truth.UNKNOWN,m.NeedInput('choose','source_choice','choose once')) if wait and 'choose' not in inputs else m.Guard(m.Truth.TRUE)
 def update(v,e,inputs):return m.Commit(tuple(m.Write(p,99) for p in writes),'done')
 return m.Node(uid,reads,writes,guard,update,after,post=(lambda *a:False) if bad else None)
def sched(nodes=None,footprint=None,deps=()):
 ns=nodes or (node(wait=True),);p=m.Plan('plan','p','model',ns,'model_experiment')
 if footprint is None:footprint=r.Footprint(tuple(p for n in ns for p in n.reads),tuple(p for n in ns for p in n.writes))
 return s.Schedule(p,footprint,deps)
def blocked_pair(fa,fb):
 sc=fresh();a=sched((node(reads=(),writes=(),wait=True),),fa);eq(sc.submit(a,event(sc)).tag,'AwaitingInput');before=sc.machine.state
 b=sched((node(reads=(),writes=()),),fb);eq(sc.submit(b,event(sc,'B')).tag,'BlockedDependency');assert sc.machine.state is before
for i,fa,fb in [(1,r.Footprint(reads=(HP,)),r.Footprint(writes=(HP,))),(2,r.Footprint(writes=(HP,)),r.Footprint(reads=(HP,))),(3,r.Footprint(writes=(('actors','a'),)),r.Footprint(writes=(HP,))),(4,r.Footprint(reads=(HP,)),r.Footprint(writes=(HP,))),(5,r.Footprint(reads=(HP,)),r.Footprint(writes=(HP,))),(7,r.Footprint(observations=(('rng','a'),)),r.Footprint(observations=(('rng','b'),))),(8,r.Footprint(observations=(HP,)),r.Footprint(writes=(HP,)))]:test(i,lambda fa=fa,fb=fb:blocked_pair(fa,fb))
def future():
 sc=fresh();a=sched((node('first',(),(),True),node('later',(HP,),(HP,),after=('first',))));eq(sc.submit(a,event(sc)).tag,'AwaitingInput')
 eq(sc.submit(sched((node(),)),event(sc,'B')).tag,'BlockedDependency')
test(6,future)
def independent(mode):
 sc=fresh();a=sched();ev=event(sc);eq(sc.submit(a,ev).tag,'AwaitingInput');old=sc.machine.state.occurrences['A']
 b=sched((node(reads=(OTHER,),writes=(OTHER,)),));eq(sc.submit(b,event(sc,'B')).tag,'Completed');eq(sc.machine.state.game['actors']['b']['hp'],99)
 if mode==9:return
 eq(sc.resumable('A'),None);eq(sc.resume('A',{'choose':True}).tag,'Completed');eq(sc.machine.state.game['actors']['a']['hp'],99)
 if mode==11:assert sc.machine.state.occurrences['A'].event is ev;eq(ev.expected_revision,0);eq(old.event,ev)
for i in (9,10,11,19):test(i,lambda i=i:independent(i))
def prefix():
 sc=fresh();cost=m.Node('cost',(COST,),(COST,),lambda *a:m.Guard(m.Truth.TRUE),lambda v,*a:m.Commit((m.Write(COST,v.get(COST)-1),)))
 a=sched((cost,node('effect',(HP,),(HP,),True,('cost',))));ev=event(sc);eq(sc.submit(a,ev).committed,('cost',));eq(sc.machine.state.game['resources']['a']['ap'],2)
 eq(sc.submit(sched((node(reads=(OTHER,),writes=(OTHER,)),)),event(sc,'B')).tag,'Completed');out=sc.resume('A',{'choose':True});eq(out.committed,('cost','effect'));eq(sc.machine.state.game['resources']['a']['ap'],2);assert sc.machine.state.occurrences['A'].event is ev
 before=sc.machine.state;eq(sc.submit(a,ev),out);assert sc.machine.state is before
test(12,prefix)
def dependency():
 sc=fresh();eq(sc.submit(sched(),event(sc)).tag,'AwaitingInput')
 eq(sc.submit(sched((node(reads=(OTHER,),writes=(OTHER,)),),deps=('A',)),event(sc,'B')).tag,'BlockedDependency')
 eq(sc.submit(sched((node(reads=(OTHER,),writes=(OTHER,)),),deps=('B',)),event(sc,'C')).tag,'BlockedDependency');eq(set(sc.machine.state.occurrences),{'A'})
test(13,dependency)
def duplicate():
 sc=fresh();a=sched((node(wait=False),));ev=event(sc);out=sc.submit(a,ev);before=sc.machine.state;eq(sc.submit(a,ev),out);assert sc.machine.state is before
 eq(sc.submit(a,replace(ev,payload={'value':1})).tag,'RejectedStaleOrMismatch')
test(14,duplicate)
def reuse():
 sc=fresh();a=sched();ev=event(sc,payload={'v':True});sc.submit(a,ev);before=sc.machine.state
 eq(sc.submit(a,replace(ev,payload={'v':1})).tag,'RejectedStaleOrMismatch');assert sc.machine.state is before
 eq(sc.submit(replace(a),ev).tag,'RejectedStaleOrMismatch')
test(15,reuse);test(16,reuse)
def stale(mode):
 sc=fresh();a=sched();sc.submit(a,event(sc));snap=sc.machine.state
 if mode==17:sc.machine.state=m.Snapshot('other',snap.revision,snap.game,snap.occurrences)
 elif mode==18:
  g=m.thaw(snap.game);g['actors']['a']['hp']=8;sc.machine.state=m.Snapshot('p',snap.revision,g,snap.occurrences)
 else:sc.machine.state=m.Snapshot(snap.profile,snap.revision,snap.game,snap.occurrences)
 before=sc.machine.state;eq(sc.resume('A',{'choose':True}).tag,'RejectedStaleOrMismatch');assert sc.machine.state is before
for i in (17,18,20,21):test(i,lambda i=i:stale(i))
def blocked_input():
 sc=fresh();n=replace(node(),guard=lambda *a:m.Guard(m.Truth.UNKNOWN,m.Block('missing_runtime','no adapter')));eq(sc.submit(sched((n,)),event(sc)).tag,'Blocked');before=sc.machine.state
 eq(sc.resume('A',{'choose':True}).tag,'BlockedDependency');assert sc.machine.state is before
test(22,blocked_input)
def evidence_boundary():
 sc=fresh();a=sched();sc.submit(a,event(sc));before=sc.machine.state;eq(sc.resume('A',{'unscoped_yes':True}).tag,'RejectedInput');assert sc.machine.state is before;eq(sc.machine.state.game,before.game);eq(sc.machine.state.occurrences['A'].evidence,{})
test(23,evidence_boundary)
def cycles():
 sc=fresh();eq(sc.submit(sched(deps=('A',)),event(sc)).tag,'BlockedDependency');eq(sc.submit(sched(deps=('missing',)),event(sc)).tag,'BlockedDependency');eq(dict(sc.machine.state.occurrences),{})
test(27,cycles)
def failed():
 sc=fresh();a=sched((node(wait=False,bad=True),));eq(sc.submit(a,event(sc)).tag,'Blocked');eq(sc.machine.state.game['actors']['a']['hp'],10)
 eq(sc.submit(sched((node(reads=(OTHER,),writes=(OTHER,)),),deps=('A',)),event(sc,'B')).tag,'BlockedDependency')
test(28,failed)
def invariants():
 sc=fresh((lambda g:g['actors']['a']['hp']>=0,));sc.submit(sched(),event(sc));eq(sc.submit(sched((node(reads=(OTHER,),writes=(OTHER,)),)),event(sc,'B')).tag,'BlockedDependency')
 sc=fresh((lambda g:g['actors']['a']['hp']>=0,),((HP,),));sc.submit(sched((node(reads=(HP,),writes=(),wait=True),)),event(sc));eq(sc.submit(sched((node(reads=(OTHER,),writes=(OTHER,)),)),event(sc,'B')).tag,'Completed')
test(29,invariants)
def underdeclared():raises(lambda:sched(footprint=r.Footprint()))
test(30,underdeclared)
def unowned():
 sc=fresh();sc.machine.submit(sched().plan,event(sc));other=s.Scheduler(sc.machine);eq(other.submit(sched((node(reads=(OTHER,),writes=(OTHER,)),)),event(other,'B')).tag,'BlockedDependency')
test(31,unowned)
def subtree():
 sc=fresh();a=sched((node(reads=(HP,),writes=(HP,),wait=True),),r.Footprint(reads=(('actors','a'),),writes=(HP,)));ev=event(sc)
 eq(sc.submit(a,ev).tag,'AwaitingInput');eq(sc.submit(sched((node(reads=(OTHER,),writes=(OTHER,)),)),event(sc,'B')).tag,'Completed');eq(sc.resume('A',{'choose':True}).tag,'Completed')
test(32,subtree)
def dryrun():
 sc=fresh();a=sched();ev=event(sc);before=sc.machine.state;eq(sc.check_new(a,ev),None);assert sc.machine.state is before
 sc.submit(a,ev);before=sc.machine.state;eq(sc.check_new(sched((node(),)),event(sc,'B')).tag,'BlockedDependency');assert sc.machine.state is before
 eq(sc.resume('A',{'choose':object()}).tag,'RejectedInput');assert sc.machine.state is before
 eq(sc.resume('A',{'choose':True,'extra':1}).tag,'RejectedInput');assert sc.machine.state is before
 eq(sc.resume('A',{'choose':True}).tag,'Completed')
test(33,dryrun)
report={'scope':'cross-event model frontier only; source footprint completeness, child ownership, durable restore and live Engine are not certified','results':sorted(RESULTS,key=lambda x:x['id']),'input_hashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in ['engine/root_machine.py','engine/root_resolution.py','engine/root_scheduler.py','tools/test_root_frontier_independent.py','data/verification/topdown-root-contract.json']}}
(ROOT/'output/root-frontier-independent-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'passed':sum(t['status']=='pass' for t in RESULTS),'total':len(RESULTS),'failures':[t for t in RESULTS if t['status']=='fail']}))
raise SystemExit(any(t['status']=='fail' for t in RESULTS))
