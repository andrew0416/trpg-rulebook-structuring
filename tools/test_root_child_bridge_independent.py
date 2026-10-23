from pathlib import Path
from dataclasses import replace
import sys,json,hashlib
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tools'))
from engine import root_admission as a,root_machine as m,root_resolution as r,root_children as c,root_inputs as i
import child_bridge_fixture as f
RESULTS=[]
def eq(x,y):assert x==y,(x,y)
def test(n,fn):
 try:fn();RESULTS.append({'id':f'CHILD-BRIDGE-INDEPENDENT-{n:03}','status':'pass'})
 except Exception as e:RESULTS.append({'id':f'CHILD-BRIDGE-INDEPENDENT-{n:03}','status':'fail','error':repr(e)})
def certificate(kind,route=True,**kw):
 fixture='tools/child_bridge_fixture.py';sha=hashlib.sha256((ROOT/fixture).read_bytes()).hexdigest()
 meta='tools/certificate-'+kind+'.json';(ROOT/meta).write_text('{"synthetic":true}',encoding='utf-8');metasha=hashlib.sha256((ROOT/meta).read_bytes()).hexdigest()
 routes=()
 if route:
  ck='child' if kind=='parent' else 'grand';aspect=f.ASPECTS[kind]
  routes=tuple(a.ChildRoute(aspect,'spawn','cert:'+ck,ck,b,t) for b,t in [('before_parent_complete','after_emission'),('independent_lifetime','after_parent_complete'),('independent_lifetime','after_emission')])
 args=dict(id='cert:'+kind,mode='synthetic',profile_hash=f.PROFILE,catalog_hash=f.CATALOG,interface='model:child-boundary',event_kind=kind,aspects=(f.ASPECTS[kind],),source_refs=('synthetic:shared',),propositions=('model:child-contract',),support_domain='synthetic protocol only',adapter_id='adapter:'+kind,artifacts={fixture:sha,meta:metasha},chain={role:(fixture,) if role=='adapter_refinement' else (meta,) for role in a.CHAIN},positive_cases=('model:positive',),negative_cases=('model:negative',),child_routes=routes)
 args.update(kw);return a.Certificate(**args)
def setup(payload=None,parent_changes=None,child_changes=None,register_child=True,register_grand=True,selector=f.select_child):
 pc=certificate('parent',**(parent_changes or {}));cc=certificate('child',**(child_changes or {}));gc=certificate('grand',route=True)
 certs=[pc,cc,gc];policy=a.TrustedPolicy('synthetic-test','synthetic',{v.id:v.fingerprint() for v in certs})
 adapters=[a.Adapter('adapter:'+kind,f.support,f.derive,f.build,f.input_request,selector if kind=='parent' else f.select_child) for kind in ('parent','child','grand')]
 registry=a.Registry(ROOT,policy,adapters);ph=registry.verify_registration(pc)
 if register_child:registry.verify_registration(cc)
 if register_grand:registry.verify_registration(gc)
 g={d:{} for d in m.DOMAINS};g['actors']={'a':{'hp':10},'b':{'hp':20}};g['resources']={'a':{'ap':0}}
 principal=i.Principal('gm');rt=a.Runtime(registry,m.Machine(m.Snapshot(f.PROFILE,0,g)),(principal,))
 ev=m.Event('P','parent',f.PROFILE,0,payload or {});ticket=rt.prepare(ph,ev);assert isinstance(ticket,a.Ticket),ticket
 return rt,ticket,principal

def emit(**kwargs):
 rt,t,p=setup(**kwargs);out=rt.submit(t);rows=rt.get_children(t);assert type(rows) is tuple and len(rows)==1,(out,rows);return rt,t,p,rows[0]
def positive():
 rt,t,p,row=emit();eq(rt.machine.state.occurrences['P'].outcome.tag,'AwaitingChildren');eq(rt.machine.state.game['resources']['a']['ap'],1)
 child=rt.prepare_child(t,row.id);assert isinstance(child,a.Ticket),child;eq(child.tag,'ModelAdmitted');eq(rt.submit(child).tag,'Completed');eq(rt.resume_children(t).tag,'Completed');eq(rt.machine.state.game['actors']['a']['hp'],11);eq(rt.machine.state.game['resources']['a']['ap'],1)
 before=rt.machine.state;eq(rt.submit(child).tag,'Completed');assert rt.machine.state is before;eq(rt.prepare_child(t,row.id),child);eq(rt.submit(t).tag,'Completed');assert rt.machine.state is before

def reject_prepare(expected,**kwargs):
 rt,t,p,row=emit(**kwargs);before=rt.machine.state;out=rt.prepare_child(t,row.id);eq(out.tag,expected);assert rt.machine.state is before;eq(rt.machine.state.game['actors']['a']['hp'],10)
test(1,positive)
test(2,lambda:reject_prepare('PendingEvidence',register_child=False))
test(3,lambda:reject_prepare('RejectedIntegrity',parent_changes={'route':False}))
test(4,lambda:reject_prepare('RejectedIntegrity',selector=f.select_invalid))
test(5,lambda:reject_prepare('RejectedIntegrity',payload={'select_certificate':'cert:grand'}))
def foreign_emission():
 rt,t,p=setup(payload={'emission_source':'unreviewed:source'});before=rt.machine.state.game;eq(rt.submit(t).tag,'Blocked');eq(rt.get_children(t),());eq(rt.machine.state.game,before)
test(6,foreign_emission)
test(7,lambda:reject_prepare('RejectedIntegrity',child_changes={'source_refs':('other:source',)}))
test(8,lambda:reject_prepare('RejectedIntegrity',child_changes={'profile_hash':'3'*64}))
test(9,lambda:reject_prepare('RejectedIntegrity',payload={'emit_kind':'other'}))
test(10,lambda:reject_prepare('OutsideSupportedDomain',payload={'child_config':{'target':'unauthorized'}}))
test(11,lambda:reject_prepare('RejectedIntegrity',payload={'child_config':{'derive_source':'unreviewed:source'}}))
def input_child():
 rt,t,p,row=emit(payload={'child_config':{'wait':True}});child=rt.prepare_child(t,row.id);assert isinstance(child,a.Ticket),child;eq(rt.submit(child).tag,'AwaitingInput');before=rt.machine.state;eq(rt.resume_children(t).tag,'AwaitingChildren')
 pending=rt.get_input(child);assert isinstance(pending,a.PendingInput),pending;bad=rt.answer(pending,i.Principal('gm'),True);assert isinstance(bad,a.Finding),bad;eq(rt.machine.state.game['actors']['a']['hp'],10)
 eq(rt.answer(pending,p,True).tag,'Completed');eq(rt.resume_children(t).tag,'Completed');before=rt.machine.state;eq(rt.answer(pending,p,True).tag,'Completed');assert rt.machine.state is before;eq(rt.machine.state.game['resources']['a']['ap'],1)
test(12,input_child)
def reaction():
 rt,t,p,row=emit(payload={'barrier':'independent_lifetime','timing':'after_parent_complete'});eq(rt.machine.state.occurrences['P'].outcome.tag,'Completed');eq(row.status,'outstanding');ct=rt.prepare_child(t,row.id);assert isinstance(ct,a.Ticket),ct;eq(rt.submit(ct).tag,'Completed');eq(rt.machine.state.game['resources']['a']['ap'],1)
test(13,reaction)
def nested():
 rt,t,p,row=emit(payload={'child_config':{'nested':True}});ct=rt.prepare_child(t,row.id);eq(rt.submit(ct).tag,'AwaitingChildren');g=rt.get_children(ct)[0];gt=rt.prepare_child(ct,g.id);assert isinstance(gt,a.Ticket),gt;eq(rt.submit(gt).tag,'Completed');eq(rt.resume_children(ct).tag,'Completed');eq(rt.resume_children(t).tag,'Completed');eq(rt.machine.state.game['actors']['b']['hp'],21);eq(rt.machine.state.game['actors']['a']['hp'],11);eq(rt.machine.state.game['resources']['a']['ap'],1)
test(14,nested)
def before_submit():
 rt,t,p=setup();before=rt.machine.state;eq(rt.get_children(t).tag,'RejectedIntegrity');eq(rt.prepare_child(t,'x').tag,'RejectedIntegrity');assert rt.machine.state is before
test(15,before_submit)
def foreign_id():
 rt,t,p,row=emit();before=rt.machine.state;eq(rt.prepare_child(t,'child:unissued').tag,'RejectedIntegrity');assert rt.machine.state is before
 rt2,t2,p2,row2=emit();eq(rt2.prepare_child(t,row2.id).tag,'RejectedIntegrity')
test(16,foreign_id)
def stale():
 rt,t,p,row=emit();s=rt.machine.state;rt.machine.state=m.Snapshot(s.profile,s.revision,s.game,s.occurrences,s.children);before=rt.machine.state;eq(rt.prepare_child(t,row.id).tag,'RejectedStaleOrMismatch');assert rt.machine.state is before
test(17,stale)
def nofactory():
 rt,t,p=setup(selector=None);out=rt.submit(t);row=rt.get_children(t)[0];eq(rt.prepare_child(t,row.id).tag,'PendingRefinement')
test(18,nofactory)
def input_no_inherit():
 rt,t,p,row=emit(payload={'child_config':{'wait':True}});ct=rt.prepare_child(t,row.id);rt.submit(ct);before=rt.machine.state;out=rt.get_input(t);assert isinstance(out,a.Finding);assert rt.machine.state is before;eq(rt.machine.state.game['actors']['a']['hp'],10)
test(19,input_no_inherit)
def cache_stale():
 rt,t,p,row=emit();ct=rt.prepare_child(t,row.id);assert isinstance(ct,a.Ticket);s=rt.machine.state;g=m.thaw(s.game);g['actors']['a']['hp']=77;rt.machine.state=m.Snapshot(s.profile,s.revision,g,s.occurrences,s.children);before=rt.machine.state;eq(rt.submit(ct).tag,'RejectedStaleOrMismatch');assert rt.machine.state is before
test(20,cache_stale)
def cycle():
 try:c.ChildSpec('x','child',{},'before_parent_complete','o','s',('synthetic:shared',),'after_parent_complete')
 except ValueError:return
 raise AssertionError('cyclic timing accepted')
test(21,cycle)
def invalid_route_timing():reject_prepare('RejectedIntegrity',payload={'barrier':'independent_lifetime','timing':'unknown'})
test(22,invalid_route_timing)
def catalog():reject_prepare('RejectedIntegrity',child_changes={'catalog_hash':'4'*64},payload={'child_config':{'catalog':'4'*64}})
test(23,catalog)
def child_handle(rt,kind='child'):
 return next(h for h,(cert,adapter) in rt.registry._registrations.items() if cert.id=='cert:'+kind)
def direct(mode):
 rt,t,p,row=emit(parent_changes={'route':False} if mode==26 else None);ev=rt.machine.child_event(row.id);before=rt.machine.state
 handle=child_handle(rt,'grand' if mode==25 else 'child');result=rt.prepare(handle,ev)
 if mode==24:
  assert isinstance(result,a.Ticket),result;eq(rt.prepare_child(t,row.id),result);eq(rt.submit(result).tag,'Completed')
 else:eq(result.tag,'RejectedIntegrity');assert rt.machine.state is before
for num in (24,25,26):test(num,lambda num=num:direct(num))
def stale_parent(which):
 rt,t,p,row=emit(payload={'child_config':{'wait':True}} if which in (28,29) else None);ct=rt.prepare_child(t,row.id);assert isinstance(ct,a.Ticket)
 if which in (28,29):eq(rt.submit(ct).tag,'AwaitingInput')
 if which==29:pending=rt.get_input(ct)
 path=ROOT/'tools/certificate-parent.json';saved=path.read_bytes();path.write_text('{"tampered":true}',encoding='utf-8');before=rt.machine.state
 try:
  out=rt.submit(ct) if which==27 else rt.get_input(ct) if which==28 else rt.answer(pending,p,True)
  eq(out.tag,'RejectedIntegrity');assert rt.machine.state is before
 finally:path.write_bytes(saved)
for num in (27,28,29):test(num,lambda num=num:stale_parent(num))
def stale_ancestor():
 rt,t,p,row=emit(payload={'child_config':{'nested':True}});ct=rt.prepare_child(t,row.id);rt.submit(ct);gr=rt.get_children(ct)[0];gt=rt.prepare_child(ct,gr.id);assert isinstance(gt,a.Ticket),gt
 path=ROOT/'tools/certificate-parent.json';saved=path.read_bytes();path.write_text('{"tampered":true}',encoding='utf-8');before=rt.machine.state
 try:eq(rt.submit(gt).tag,'RejectedIntegrity');assert rt.machine.state is before
 finally:path.write_bytes(saved)
test(30,stale_ancestor)
def child_ledger_input():
 rt,t,p,row=emit(payload={'child_config':{'wait':True,'domain_child_count':1}});ct=rt.prepare_child(t,row.id);eq(rt.submit(ct).tag,'AwaitingInput');pending=rt.get_input(ct);assert isinstance(pending,a.PendingInput),pending
 gh=child_handle(rt,'grand');ev=m.Event('independent-G','grand',f.PROFILE,rt.machine.state.revision,{'nested':True,'emit_kind':'grand','barrier':'independent_lifetime','timing':'after_parent_complete'})
 gt=rt.prepare(gh,ev);assert isinstance(gt,a.Ticket),gt;eq(rt.submit(gt).tag,'Completed');gr=rt.get_children(gt)[0];gct=rt.prepare_child(gt,gr.id);assert isinstance(gct,a.Ticket),gct;eq(rt.submit(gct).tag,'Completed');before=rt.machine.state
 out=rt.answer(pending,p,True);assert isinstance(out,a.Finding),out;assert rt.machine.state is before
 renewed=rt.get_input(ct);assert isinstance(renewed,a.PendingInput),renewed;assert renewed is not pending;eq(renewed.request.domain,(False,));eq(rt.answer(renewed,p,False).tag,'Completed');eq(rt.resume_children(t).tag,'Completed')
test(31,child_ledger_input)
def unchanged_child_input():
 rt,t,p,row=emit(payload={'child_config':{'wait':True}});ct=rt.prepare_child(t,row.id);rt.submit(ct);pending=rt.get_input(ct)
 ev=m.Event('unrelated-G','grand',f.PROFILE,rt.machine.state.revision,{});gt=rt.prepare(child_handle(rt,'grand'),ev);assert isinstance(gt,a.Ticket),gt;eq(rt.submit(gt).tag,'Completed')
 eq(rt.answer(pending,p,True).tag,'Completed');eq(rt.resume_children(t).tag,'Completed')
test(32,unchanged_child_input)
test(33,lambda:reject_prepare('RejectedIntegrity',child_changes={'aspects':('other-aspect',)}))
def outstanding_frontier():
 rt,t,p,row=emit(payload={'child_config':{'wait':True}});ct=rt.prepare_child(t,row.id);rt.submit(ct);pending=rt.get_input(ct)
 ev=m.Event('emitter-G','grand',f.PROFILE,rt.machine.state.revision,{'nested':True,'emit_kind':'grand','barrier':'independent_lifetime','timing':'after_parent_complete'})
 gt=rt.prepare(child_handle(rt,'grand'),ev);assert isinstance(gt,a.Ticket),gt;rt.submit(gt);before=rt.machine.state
 out=rt.answer(pending,p,True);assert isinstance(out,a.Finding),out;assert rt.machine.state is before;eq(rt.machine.state.game['actors']['a']['hp'],10)
test(34,outstanding_frontier)
report={'scope':'synthetic independent child-admission bridge tests; zero source certification','results':RESULTS,'input_hashes':{str(p.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in list((ROOT/'engine').glob('*.py'))+[ROOT/'tools/child_bridge_fixture.py',Path(__file__)]+list((ROOT/'tools').glob('certificate-*.json'))}}
(ROOT/'output/root-child-bridge-independent-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'passed':sum(x['status']=='pass' for x in RESULTS),'total':len(RESULTS),'failed':[x for x in RESULTS if x['status']=='fail']}))
raise SystemExit(any(x['status']=='fail' for x in RESULTS))
