"""Independent bridge tests: synthetic architecture, no source registration."""
from pathlib import Path
import sys,json,hashlib,dataclasses,traceback
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tools'))
from engine import root_machine as m,root_resolution as r,root_admission as a,root_inputs as i
import root_runtime_io_fixture as f
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
MODULES=('root_machine','root_resolution','root_admission','root_inputs','root_scheduler')
FILES=[f'engine/{x}.py' for x in MODULES]+['tools/root_runtime_io_fixture.py','tools/root_runtime_io_synthetic_evidence.txt','tools/test_root_runtime_io_independent.py']
def setup(factory=f.input_request):
 artifacts={p:sha(ROOT/p) for p in FILES};chain={k:('tools/root_runtime_io_synthetic_evidence.txt',) for k in a.CHAIN};chain['adapter_refinement']=('tools/root_runtime_io_fixture.py',)
 cert=a.Certificate('io','synthetic',f.PROFILE,f.CATALOG,'synthetic.input','synthetic_io',('prefix','consume'),f.REFS,('synthetic input consumption',),'synthetic two actors','io-adapter',artifacts,chain,('positive',),('negative',))
 reg=a.Registry(ROOT,a.TrustedPolicy('synthetic policy','synthetic',{cert.id:cert.fingerprint()}),(a.Adapter('io-adapter',f.support,f.derive,f.build,factory),));handle=reg.verify_registration(cert)
 game={k:{} for k in m.DOMAINS};game['actors']={x:{'hp':50,'cost':10} for x in ('a','b')};mach=m.Machine(m.Snapshot(f.PROFILE,0,game));gm=i.Principal('gm');player=i.Principal('player');rt=a.Runtime(reg,mach,principals=(gm,player));return reg,handle,mach,rt,gm,player

def eq(x,y):assert x==y,(x,y)
def hp(mach,x='a'):return mach.state.game['actors'][x]['hp']
def event(mach,id='e',**p):return m.Event(id,'synthetic_io',f.PROFILE,mach.state.revision,p)
def pending(mode='choice',**p):
 reg,h,mach,rt,gm,player=setup();e=event(mach,mode=mode,**p);ticket=rt.prepare(h,e);assert type(ticket) is a.Ticket,ticket;eq(rt.submit(ticket).tag,'AwaitingInput');value=rt.get_input(ticket);return reg,h,mach,rt,gm,player,ticket,value
results=[]
def run(id,fn):
 try:fn();results.append({'id':'ROOT-IO-INDEPENDENT-'+id,'status':'passed'})
 except Exception:results.append({'id':'ROOT-IO-INDEPENDENT-'+id,'status':'failed','detail':traceback.format_exc()})
def positive(mode,value,expected):
 reg,h,mach,rt,gm,pl,t,p=pending(mode);assert type(p) is a.PendingInput,p
 eq(hp(mach),50);eq(mach.state.game['actors']['a']['cost'],9);eq(rt.answer(p,gm,value).tag,'Completed');eq(hp(mach),expected)
 rec=mach.state.occurrences['e'];eq(i.canonical(rec.evidence['faces' if mode=='dice' else 'decision']),i.canonical(value));eq(rec.committed,('prefix','consume'))
run('001-choice-real-G-consumption',lambda:positive('choice',2,52));run('002-exact-dice-consumption',lambda:positive('dice',[1,6],57))
def unchanged(kind):
 reg,h,mach,rt,gm,pl,t,p=pending('dice' if kind=='faces' else 'choice');before=mach.state
 if kind=='unauthorized':out=rt.answer(p,pl,2)
 elif kind=='forged-principal':out=rt.answer(p,i.Principal('gm'),2)
 elif kind=='fake-input':out=rt.answer(dataclasses.replace(p),gm,2)
 elif kind=='faces':out=rt.answer(p,gm,[True,6])
 else:out=rt.answer(p,gm,True)
 assert type(out) is a.Finding,out;assert mach.state is before,(kind,out)
for n,k in enumerate(('unauthorized','forged-principal','fake-input','faces','domain'),3):run(f'{n:03}-{k}-no-GK',lambda k=k:unchanged(k))
def stale():
 reg,h,mach,rt,gm,pl,t,p=pending();mach.state=dataclasses.replace(mach.state,revision=999);before=mach.state;out=rt.answer(p,gm,2);assert type(out) is a.Finding;assert mach.state is before;eq(hp(mach),50)
run('008-external-stale-state',stale)
def replay():
 reg,h,mach,rt,gm,pl,t,p=pending();out=rt.answer(p,gm,2);before=mach.state;eq(rt.answer(p,gm,2),out);assert mach.state is before;eq(rt.answer(p,gm,4).tag,'ConflictingReplay');assert mach.state is before
run('009-replay-conflict',replay)
def independent():
 reg,h,mach,rt,gm,pl,t,p=pending();old_revision=mach.state.revision;other=rt.prepare(h,event(mach,'other',actor='b',mode='automatic'));assert type(other) is a.Ticket,other;eq(rt.submit(other).tag,'Completed');eq(hp(mach,'b'),57);assert mach.state.revision>old_revision
 eq(rt.get_input(t) is p,True);eq(rt.answer(p,gm,4).tag,'Completed');eq(hp(mach),54);eq(hp(mach,'b'),57)
run('010-independent-event-then-input',independent)
def prefix():
 reg,h,mach,rt,gm,pl,t,p=pending();before=mach.state;eq(mach.state.game['actors']['a']['cost'],9);eq(rt.answer(p,gm,3).tag,'OutsideDomain');assert mach.state is before;eq(rt.answer(p,gm,2).tag,'Completed');eq(mach.state.game['actors']['a']['cost'],9)
run('011-committed-prefix-preserved',prefix)
def two_requests():
 reg,h,mach,rt,gm,pl,t,p=pending('double');out=rt.answer(p,gm,2);eq(out.tag,'AwaitingInput');q=rt.get_input(t);assert q is not p;assert q.request.id!=p.request.id;assert q.request.binding.context_hash!=p.request.binding.context_hash;assert type(q.request) is i.RollRequest
 before=mach.state;eq(rt.answer(p,gm,2),out);assert mach.state is before;eq(rt.answer(q,gm,[1,6]).tag,'Completed');eq(hp(mach),64);eq(mach.state.game['actors']['a']['cost'],9)
run('012-dynamic-second-request',two_requests)
def factory_scope(fault):
 reg,h,mach,rt,gm,pl,t,p=pending(input_fault=fault);assert type(p) is a.Finding,p;eq(p.tag,'RejectedIntegrity');eq(hp(mach),50);eq(mach.state.game['actors']['a']['cost'],9)
for n,k in enumerate(('binding','mode','source','kind'),13):run(f'{n:03}-factory-{k}',lambda k=k:factory_scope(k))
def unreviewed_factory(binding,pending,snapshot,event):return f.input_request(binding,pending,snapshot,event)
def unreviewed():
 reg,h,mach,rt,gm,pl=setup(unreviewed_factory);assert type(h) is a.Finding;eq(h.tag,'RejectedIntegrity');eq(mach.state.revision,0)
run('017-unreviewed-input-factory',unreviewed)
def before_submit():
 reg,h,mach,rt,gm,pl=setup();t=rt.prepare(h,event(mach));before=mach.state;eq(rt.get_input(t).tag,'RejectedIntegrity');assert mach.state is before
run('018-input-before-actual-pending',before_submit)
def no_factory():
 reg,h,mach,rt,gm,pl=setup(None);t=rt.prepare(h,event(mach));rt.submit(t);before=mach.state;eq(rt.get_input(t).tag,'PendingRefinement');assert mach.state is before
run('019-missing-factory-not-GM-choice',no_factory)
def overlap():
 reg,h,mach,rt,gm,pl,t,p=pending();before=mach.state;eq(rt.prepare(h,event(mach,'overlap',actor='a',mode='automatic')).tag,'PendingContext');assert mach.state is before
run('020-overlap-frontier',overlap)
def old_input_after_another():
 reg,h,mach,rt,gm,pl,t,p=pending();out=rt.answer(p,gm,2);other=rt.prepare(h,event(mach,'second',actor='a',mode='automatic'));rt.submit(other);before=mach.state;eq(rt.answer(p,gm,2),out);assert mach.state is before;eq(hp(mach),59)
run('021-historical-answer-after-new-event',old_input_after_another)
def missing_principal():
 reg,h,mach,rt,gm,pl=setup();rt=a.Runtime(reg,mach);t=rt.prepare(h,event(mach));rt.submit(t);before=mach.state;eq(rt.get_input(t).tag,'PendingAuthority');assert mach.state is before
run('022-uninstalled-request-principal',missing_principal)
report={'kind':'synthetic_runtime_input_bridge_independent_tests','source_admitted_registrations':0,'real_source_semantics_certified':False,'results':results,'input_hashes':{p:sha(ROOT/p) for p in FILES}}
(ROOT/'output/root-runtime-io-independent-tests.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps({'passed':sum(x['status']=='passed' for x in results),'total':len(results),'failures':[x for x in results if x['status']!='passed']},indent=2));raise SystemExit(any(x['status']!='passed' for x in results))
