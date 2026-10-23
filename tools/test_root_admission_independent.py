"""Independent synthetic architecture checks, never source certification."""
import sys,json,hashlib,dataclasses,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tools'))
from engine import root_machine as m,root_resolution as r,root_admission as a
import root_admission_fixture as f
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def setup():
    artifacts={p:sha(ROOT/p) for p in ('tools/root_admission_fixture.py','tools/root_admission_synthetic_evidence.txt','engine/root_machine.py','engine/root_resolution.py','engine/root_admission.py')}
    chain={k:('tools/root_admission_synthetic_evidence.txt',) for k in a.CHAIN};chain['adapter_refinement']=('tools/root_admission_fixture.py',)
    c=a.Certificate('synthetic-only','synthetic',f.PROFILE,f.CATALOG,'hp.change','synthetic_hp',('hp',),('synthetic:hp','synthetic:law'),('synthetic bounded decrement',),'synthetic actor a only','synthetic-adapter',artifacts,chain,('positive-G-change',),('bad-scope',))
    policy=a.TrustedPolicy('operator-test-policy','synthetic',{c.id:c.fingerprint()});reg=a.Registry(ROOT,policy,(a.Adapter('synthetic-adapter',f.support,f.derive,f.build),));h=reg.verify_registration(c)
    g={k:{} for k in m.DOMAINS};g['actors']={'a':{'hp':50,'other':0}}
    machine=m.Machine(m.Snapshot(f.PROFILE,0,g));return c,policy,reg,h,machine,a.Runtime(reg,machine)

def event(machine,id='e',**kw):return m.Event(id,'synthetic_hp',f.PROFILE,machine.state.revision,kw)
def eq(actual,expected):assert actual==expected,(actual,expected)
def finding(x,tag):assert isinstance(x,a.Finding),(type(x),x);eq(x.tag,tag)
def hp(machine):return machine.state.game['actors']['a']['hp']
results=[]
def run(name,fn):
    try:fn();results.append({'id':'ADMISSION-INDEPENDENT-'+name,'status':'passed'})
    except Exception:results.append({'id':'ADMISSION-INDEPENDENT-'+name,'status':'failed','detail':traceback.format_exc()})

def positive():
    c,p,reg,h,mach,rt=setup();t=rt.prepare(h,event(mach));eq(t.tag,'ModelAdmitted');out=rt.submit(t);eq(out.tag,'Completed');eq(out.gameplay_certified,False);eq(hp(mach),47)
run('001-positive-game-transition',positive)

def policy_absent():
    c,p,reg,h,mach,rt=setup();other=a.Registry(ROOT,a.TrustedPolicy('empty','synthetic',{}),(a.Adapter('synthetic-adapter',f.support,f.derive,f.build),));finding(other.verify_registration(c),'PendingEvidence')
run('002-no-trusted-pin',policy_absent)

def registration_negative(kind):
    c,p,reg,h,mach,rt=setup()
    if kind=='dict':finding(reg.verify_registration({'reviewed':True,'source_ready':True}),'PendingEvidence')
    elif kind=='handle':finding(rt.prepare(a.Registration(c.id),event(mach)),'PendingEvidence')
    elif kind=='ticket':finding(rt.submit(dataclasses.replace(rt.prepare(h,event(mach)))),'RejectedIntegrity')
    elif kind=='semantics':finding(reg.verify_registration(dataclasses.replace(c,propositions=('different',))),'PendingEvidence')
    elif kind=='source':finding(reg.verify_registration(dataclasses.replace(c,mode='source')),'RejectedIntegrity')
    elif kind=='chain':
        chain=dict(c.chain);chain.pop('semantics')
        try:dataclasses.replace(c,chain=chain)
        except ValueError:pass
        else:raise AssertionError('missing chain accepted')
    eq(hp(mach),50)
for i,k in enumerate(['dict','handle','ticket','semantics','source','chain'],3):run(f'{i:03}-{k}',lambda k=k:registration_negative(k))

def artifact_change():
    c,p,reg,h,mach,rt=setup();fp=ROOT/'tools/root_admission_synthetic_evidence.txt';old=fp.read_bytes()
    try:fp.write_bytes(old+b'changed');finding(rt.prepare(h,event(mach)),'RejectedIntegrity');eq(hp(mach),50)
    finally:fp.write_bytes(old)
run('009-stale-artifact',artifact_change)
negative=[('support-false',{'support':'false'},'OutsideSupportedDomain'),('support-unknown',{'support':'unknown'},'PendingContext'),('wrong-catalog',{'wrong_catalog':True},'RejectedStaleOrMismatch'),('wrong-context',{'wrong_context':True},'RejectedStaleOrMismatch'),('outside-aspect',{'outside_aspect':True},'RejectedIntegrity'),('outside-source',{'outside_source':True},'RejectedIntegrity'),('closure-unknown',{'closure_unknown':True},'PendingResolution'),('premise-unknown',{'premise_unknown':True},'PendingResolution'),('conflict',{'conflict':True},'PendingResolution'),('excluded',{'excluded':True},'ExcludedBySelectedSource'),('footprint',{'wrong_footprint':True},'RejectedIntegrity'),('order',{'wrong_order':True},'RejectedIntegrity')]
def neg(payload,tag):
    c,p,reg,h,mach,rt=setup();finding(rt.prepare(h,event(mach,**payload)),tag);eq(hp(mach),50)
for i,(name,pay,tag) in enumerate(negative,10):run(f'{i:03}-{name}',lambda pay=pay,tag=tag:neg(pay,tag))

def stale(field,value):
    c,p,reg,h,mach,rt=setup();e=dataclasses.replace(event(mach),**{field:value});finding(rt.prepare(h,e),'RejectedStaleOrMismatch');eq(hp(mach),50)
for i,(field,value) in enumerate([('profile','d'*64),('expected_revision',9),('kind','alien')],22):run(f'{i:03}-{field}',lambda field=field,value=value:stale(field,value))

def hidden():
    c,p,reg,h,mach,rt=setup();out=rt.submit(rt.prepare(h,event(mach,hidden_write=True)));eq(out.tag,'Blocked');eq(out.obligation.reason,'frame_violation');eq(hp(mach),50)
run('025-hidden-write',hidden)

def repeated():
    c,p,reg,h,mach,rt=setup();t=rt.prepare(h,event(mach));out=rt.submit(t);eq(rt.submit(t),out);eq(hp(mach),47)
run('026-same-ticket-idempotent',repeated)

def distinct():
    c,p,reg,h,mach,rt=setup();rt.submit(rt.prepare(h,event(mach,'first')));rt.submit(rt.prepare(h,event(mach,'second')));eq(hp(mach),44)
run('027-distinct-events',distinct)

def changed(ledger=False):
    c,p,reg,h,mach,rt=setup();t=rt.prepare(h,event(mach,'old'));rt.submit(rt.prepare(h,event(mach,'new',await_input=ledger)));finding(rt.submit(t),'RejectedStaleOrMismatch');eq(hp(mach),50 if ledger else 47)
run('028-changed-game-state',changed);run('029-changed-ledger-same-revision',lambda:changed(True))

def pending_repeat():
    c,p,reg,h,mach,rt=setup();e=event(mach,await_input=True);t=rt.prepare(h,e);eq(rt.submit(t).tag,'AwaitingInput');again=rt.prepare(h,e);assert isinstance(again,a.Ticket),again;eq(rt.submit(again).tag,'AwaitingInput');eq(hp(mach),50)
run('030-pending-event-reprepare',pending_repeat)

def frontier():
    c,p,reg,h,mach,rt=setup();eq(rt.submit(rt.prepare(h,event(mach,'pending',await_input=True))).tag,'AwaitingInput');later=rt.prepare(h,event(mach,'later'));assert isinstance(later,a.Finding),'overlapping pending frontier yielded '+repr(later);assert later.tag in ('PendingContext','PendingRefinement','PendingResolution');eq(hp(mach),50)
run('031-pending-frontier',frontier)

def alien_runtime():
    c,p,reg,h,mach,rt=setup();t=rt.prepare(h,event(mach));other=setup()[-1];finding(other.submit(t),'RejectedIntegrity');eq(hp(mach),50)
run('032-foreign-runtime-ticket',alien_runtime)
def completed_reprepare():
    c,p,reg,h,mach,rt=setup();e=event(mach);t=rt.prepare(h,e);eq(rt.submit(t).tag,'Completed')
    again=rt.prepare(h,e);assert isinstance(again,a.Ticket),again;eq(rt.submit(again).tag,'Completed');eq(hp(mach),47)
run('033-completed-event-reprepare',completed_reprepare)

def pre_submit_reprepare():
    c,p,reg,h,mach,rt=setup();e=event(mach);t1=rt.prepare(h,e);t2=rt.prepare(h,e);eq(rt.submit(t1).tag,'Completed');eq(rt.submit(t2).tag,'Completed');eq(hp(mach),47)
run('034-reprepare-before-first-submit',pre_submit_reprepare)

def invalid_public_types():
    c,p,reg,h,mach,rt=setup()
    for fn in (lambda:rt.prepare([],event(mach)),lambda:rt.prepare(h,None),lambda:rt.submit({})):
        try:out=fn()
        except (TypeError,ValueError):pass
        else:assert isinstance(out,a.Finding),out
        eq(hp(mach),50)
run('035-invalid-public-types-fail-closed',invalid_public_types)

def historical_after_other_completed():
    c,p,reg,h,mach,rt=setup();t=rt.prepare(h,event(mach,'first'));out=rt.submit(t);rt.submit(rt.prepare(h,event(mach,'second')))
    eq(rt.submit(t),out);eq(hp(mach),44)
run('036-historical-delivery-no-new-change',historical_after_other_completed)

def restore_before_delivery():
    c,p,reg,h,mach,rt=setup();before=mach.state;e=event(mach);t=rt.prepare(h,e);rt.submit(t);mach.state=before
    finding(rt.submit(t),'RejectedStaleOrMismatch');finding(rt.prepare(h,e),'RejectedStaleOrMismatch');eq(hp(mach),50)
run('037-restore-does-not-reexecute-old-ticket',restore_before_delivery)

def changed_profile_after_delivery():
    c,p,reg,h,mach,rt=setup();e=event(mach);t=rt.prepare(h,e);rt.submit(t);mach.state=dataclasses.replace(mach.state,profile='d'*64)
    eq(rt.submit(t).tag,'Rejected');finding(rt.prepare(h,e),'RejectedStaleOrMismatch');eq(hp(mach),47)
run('038-profile-change-rejects-old-delivery',changed_profile_after_delivery)

def changed_same_id_request():
    c,p,reg,h,mach,rt=setup();e=event(mach);rt.prepare(h,e)
    finding(rt.prepare(h,dataclasses.replace(e,payload={'amount':4})),'RejectedStaleOrMismatch');eq(hp(mach),50)
run('039-same-event-changed-payload',changed_same_id_request)

run('040-foreign-composition-witness',lambda:neg({'foreign_law':True},'RejectedIntegrity'))

files=['engine/root_machine.py','engine/root_resolution.py','engine/root_admission.py','tools/root_admission_fixture.py','tools/test_root_admission_independent.py','tools/root_admission_synthetic_evidence.txt']
report={'kind':'synthetic_architecture_independent_tests','source_admitted_registrations':0,'actual_game_source_certified':False,'results':results,'input_hashes':{p:sha(ROOT/p) for p in files}}
(ROOT/'output').mkdir(exist_ok=True)
(ROOT/'output/admission-independent-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'passed':sum(x['status']=='passed' for x in results),'total':len(results),'failures':[x for x in results if x['status']!='passed']},ensure_ascii=False,indent=2));raise SystemExit(any(x['status']!='passed' for x in results))

