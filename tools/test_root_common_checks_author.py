"""Author tests of actual Runtime/Broker ordinary-check adapter; synthetic registry."""
from pathlib import Path
import sys,json,hashlib,traceback,copy
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tools'))
import common_check_fixture as f
from engine import root_common_checks as c,root_admission as a,root_inputs as i,root_machine as m
results=[]
def run(id,fn):
    try:fn();results.append({'id':'COMMON-ROOT-AUTHOR-'+id,'status':'passed'})
    except Exception:results.append({'id':'COMMON-ROOT-AUTHOR-'+id,'status':'failed','detail':traceback.format_exc()})
def eq(x,y):assert x==y,(x,y)
def req(decision,ids=('a',)):
    return {'intent':'Attempt the declared ordinary task.','actors':list(ids),'decisions':[decision],'outcomes':[{'outcome':x,'description':x} for x in ('success','failure','other')]+[{'outcome':'success_with_cost','description':'partial','cost':'GM specified cost','failure_margin_accepted':True}], 'modifier_policy':'none','context_obligations':[]}
def begin(decision,actors=None,ids=('a',)):
    s,p,cfg=f.setup(actors=actors,requests={'check':req(decision,ids)});t=f.start(s);out=f.answer(s,t,p['gm'],decision);return s,p,t,out
def finish(s,p,t,outcome='success'):
    return f.answer(s,t,p['gm'],{'outcome':outcome,'description':outcome})
def dc(totalface,dc=7):
    s,p,t,out=begin({'mode':'dc','skill':'athletics','dc':dc});eq(out.tag,'AwaitingInput');f.answer(s,t,p['a'],totalface)
    result=s.result('e')['raw'];eq(result['total'],sum(totalface));eq(result['passed'],sum(totalface)>=dc);eq(result['margin'],sum(totalface)-dc)
    eq(finish(s,p,t,'success' if result['passed'] else 'failure').tag,'Completed')
run('001-DC-equality',lambda:dc([3,4]));run('002-DC-failure',lambda:dc([1,1]));run('003-DC-success',lambda:dc([6,6]))
def no_roll():
    s,p,t,out=begin({'mode':'no_roll','reason':'trivial'});eq(out.tag,'AwaitingInput');eq(s.result('e')['rolls'],());eq(type(s.pending(t).request),i.ChoiceRequest);eq(finish(s,p,t).tag,'Completed');eq(s.runtime.machine.state.game['clock'],{})
run('004-no-roll-no-dice',no_roll)
def ranked():
    for rank in range(1,7):
        s,p,t,out=begin({'mode':'dc','skill':'athletics','dc':rank},actors={'a':f.actor(rank)})
        eq(s.pending(t).request.count,rank);f.answer(s,t,p['a'],[1]*rank);eq(s.result('e')['raw']['passed'],True)
run('005-ordinary-rank-one-through-six',ranked)
def default2():
    x=f.actor();x['skills']={};s,p,t,out=begin({'mode':'dc','skill':'survival','dc':2},actors={'a':x});eq(s.pending(t).request.count,2)
run('006-known-initial-default2',default2)
def unknown():
    x=f.actor(None);s,p,t,out=begin({'mode':'dc','skill':'athletics','dc':2},actors={'a':x});eq(out.tag,'Blocked');assert s.result('e') is None
run('007-unknown-rank-not-default',unknown)
def helper(rank,expected):
    s,p,t,out=begin({'mode':'dc','skill':'athletics','dc':3,'helper_id':'helper'},actors={'a':f.actor(1),'helper':f.actor(rank)})
    if rank<3:eq(out.tag,'Blocked');return
    f.answer(s,t,p['a'],[1]);eq(s.result('e')['raw']['total'],expected)
run('008-helper-rank3-floor',lambda:helper(3,2));run('009-helper-rank5-floor',lambda:helper(5,3));run('010-helper-rank2-denied',lambda:helper(2,None))
def penalty():
    s,p,t,out=begin({'mode':'dc','skill':'athletics','dc':1,'penalty_count':2},actors={'a':f.actor(1)});f.answer(s,t,p['a'],[1]);eq(s.pending(t).request.count,2);f.answer(s,t,p['a'],[5,6]);eq(s.result('e')['raw']['total'],-10);eq(s.result('e')['rolls'][0]['faces'],(1,));eq(s.result('e')['rolls'][0]['penalties'],(5,6))
run('011-separate-penalty-negative-total',penalty)
def opposed():
    s,p,t,out=begin({'mode':'opposed','skill':'athletics'},actors={'a':f.actor(1),'b':f.actor(1)},ids=('a','b'));f.answer(s,t,p['a'],[4]);f.answer(s,t,p['b'],[4]);eq(s.result('e')['raw']['winner'],'defender')
run('012-opposed-equality-defender',opposed)
def team():
    d={'mode':'team','skill':'athletics','dc':4,'required_people':3,'equal_contribution':True,'no_main_actor':True}
    s,p,t,out=begin(d,actors={'a':f.actor(1),'b':f.actor(1)},ids=('a','b'));f.answer(s,t,p['a'],[6]);f.answer(s,t,p['b'],[6]);raw=s.result('e')['raw'];eq(raw['dc'],12);eq(raw['passed'],True)
run('013-team-needed-count-and-equality',team)
def ext(interval='one',rank=4,limited=True):return {'mode':'extended','skill':'athletics','dc':6,'complexity':2,'limited':limited,'task_id':'task','interval_id':interval,'interval':{'amount':10,'unit':'minutes'}}
def extended():
    d=ext();d2=ext('two');s,p,cfg=f.setup(actors={'a':f.actor(4)},requests={'one':req(d),'two':req(d2),'three':req(ext('three'))})
    t=f.start(s,'one');f.answer(s,t,p['gm'],d);f.answer(s,t,p['a'],[1,1,1,1]);eq(s.result('e')['raw']['status'],'in_progress');finish(s,p,t,'other')
    t=f.start(s,'two','e2');f.answer(s,t,p['gm'],d2);f.answer(s,t,p['a'],[2,2,2,2]);raw=s.result('e2')['raw'];eq(raw['status'],'complete');eq(raw['total'],12);eq(raw['attempts_used'],2);finish(s,p,t)
    t=f.start(s,'three','e3');eq(f.answer(s,t,p['gm'],ext('three')).tag,'Blocked');eq(s.runtime.machine.state.game['clock'],{});eq(len(s.runtime.machine.state.game['domains']['common_checks']['tasks']['task']['interval_obligations']),2)
run('014-extended-final-equality-and-terminal',extended)
def zero_cap():
    s,p,t,out=begin(ext(),actors={'a':f.actor(1)});eq(s.result('e')['raw']['attempt_limit'],0);eq(s.result('e')['raw']['status'],'exhausted');eq(type(s.pending(t).request),i.ChoiceRequest);eq(s.result('e')['owed_intervals'],())
run('015-extended-rank1-zero-cap',zero_cap)
def unlimited_negative():
    d=ext(limited=False);d['penalty_count']=1;s,p,t,out=begin(d,actors={'a':f.actor(1)});f.answer(s,t,p['a'],[1]);f.answer(s,t,p['a'],[6]);eq(s.result('e')['raw']['total'],-5);eq(s.result('e')['raw']['status'],'in_progress');eq(s.result('e')['raw']['attempt_limit'],None)
run('016-unlimited-negative-not-clamped',unlimited_negative)
def authority():
    s,p,cfg=f.setup();t=f.start(s);pending=s.pending(t);before=s.runtime.machine.state
    out=s.answer(pending,p['a'],cfg['requests']['check']['decisions'][0]);eq(type(out),a.Finding);assert s.runtime.machine.state is before
    out=s.answer(pending,i.Principal('gm'),cfg['requests']['check']['decisions'][0]);eq(type(out),a.Finding);assert s.runtime.machine.state is before
run('017-principal-not-role-string',authority)
def invalid_dice():
    s,p,t,out=begin({'mode':'dc','skill':'athletics','dc':7});pending=s.pending(t);before=s.runtime.machine.state
    for faces in ([True,6],[0,6],[7,1],[6]):eq(type(s.answer(pending,p['a'],faces)),a.Finding);assert s.runtime.machine.state is before
run('018-invalid-no-fallback',invalid_dice)
def narrative_prefix():
    s,p,t,out=begin({'mode':'dc','skill':'athletics','dc':7});pending=s.pending(t);f.answer(s,t,p['a'],[3,4]);raw=s.result('e')['raw'];before=s.runtime.machine.state
    eq(type(s.answer(s.pending(t),p['a'],{'outcome':'success','description':'success'})),a.Finding);assert s.runtime.machine.state is before;eq(s.result('e')['raw'],raw)
    out=finish(s,p,t);eq(out.tag,'Completed');after=s.runtime.machine.state;s.answer(pending,p['a'],[3,4]);assert s.runtime.machine.state is after
run('019-raw-prefix-no-reroll',narrative_prefix)
def unknown_scope():
    q=req({'mode':'no_roll','reason':'trivial'});q['context_obligations']=['target feasibility not established'];s,p,cfg=f.setup(requests={'check':q});out=s.begin('e','check');eq(out.tag,'PendingContext');eq(s.runtime.machine.state.revision,0)
run('020-unknown-not-GM-option',unknown_scope)
def cost_record():
    s,p,t,out=begin({'mode':'dc','skill':'athletics','dc':8});f.answer(s,t,p['a'],[3,4]);out=f.answer(s,t,p['gm'],{'outcome':'success_with_cost','description':'partial','cost':'GM specified cost','failure_margin_accepted':True});eq(out.tag,'Completed');eq(s.result('e')['raw']['passed'],False);eq(s.result('e')['costs_applied'],False);eq(s.runtime.machine.state.game['resources'],{})
run('021-raw-failure-cost-adjudication-not-debit',cost_record)
def unknown_skill():
    try:f.setup(decision={'mode':'dc','skill':'typo','dc':3})
    except ValueError:return
    raise AssertionError('unknown skill defaulted')
run('022-skill-catalog-rejects-typo',unknown_skill)
def effects_scope():
    x=f.actor();x['modifier_sources']=['held_item'];s,p,cfg=f.setup(actors={'a':x});eq(s.begin('e','check').tag,'PendingContext')
run('023-modifier-evidence-not-none-by-assertion',effects_scope)
def bool_dc():
    try:f.setup(decision={'mode':'dc','skill':'athletics','dc':True})
    except ValueError:return
    raise AssertionError('bool DC')
run('024-exact-int-dc',bool_dc)
def delivery():
    s,p,cfg=f.setup();t=f.start(s);eq(s.begin('e','check') is t,True)
    f.answer(s,t,p['gm'],cfg['requests']['check']['decisions'][0]);f.answer(s,t,p['a'],[3,4]);f.answer(s,t,p['gm'],{'outcome':'success','description':'Succeeded.'})
    before=s.runtime.machine.state;eq(s.begin('e','check') is t,True);eq(s.submit(t).tag,'Completed');assert s.runtime.machine.state is before
    eq(s.begin('e','changed').tag,'ConflictingReplay')
run('025-event-redelivery-preserves-original-revision',delivery)
def conflicting_narrative(mode):
    if mode=='opposed':
        s,p,t,out=begin({'mode':mode,'skill':'athletics'},actors={'a':f.actor(1),'b':f.actor(1)},ids=('a','b'));f.answer(s,t,p['a'],[1]);f.answer(s,t,p['b'],[6])
    elif mode=='exhausted':s,p,t,out=begin(ext(),actors={'a':f.actor(1)})
    else:
        s,p,t,out=begin(ext(),actors={'a':f.actor(4)});f.answer(s,t,p['a'],[1,1,1,1])
    eq(finish(s,p,t).tag,'Blocked');eq(s.result('e')['narrative'],None)
for num,mode in enumerate(('opposed','exhausted','in_progress'),26):run(f'{num:03}-no-unsupported-success-{mode}',lambda mode=mode:conflicting_narrative(mode))
def intent():
    s,p,t,out=begin({'mode':'no_roll','reason':'trivial'});eq(s.result('e')['intent'],'Attempt the declared ordinary task.')
run('029-declaration-intent-preserved',intent)
def invalid_intent():
    for value in (None,'','   ',True):
        q=req({'mode':'no_roll','reason':'trivial'});q['intent']=value
        try:f.setup(requests={'check':q})
        except ValueError:continue
        raise AssertionError('invalid intent accepted')
run('030-declaration-intent-required',invalid_intent)
def opposed_different_skills():
    one=f.actor(1);two=f.actor(6);two['skills']['survival']=2
    d={'mode':'opposed','skills':{'a':'athletics','b':'survival'}}
    s,p,t,out=begin(d,actors={'a':one,'b':two},ids=('a','b'))
    eq(s.pending(t).request.count,1);f.answer(s,t,p['a'],[6]);eq(s.pending(t).request.count,2);f.answer(s,t,p['b'],[3,3]);eq(s.result('e')['raw']['winner'],'defender')
run('031-opposed-different-participant-skills',opposed_different_skills)
def opposed_missing_skill():
    for skills in ({'a':'athletics'},{'a':'athletics','b':'survival','foreign':'athletics'}):
        try:f.setup(requests={'check':req({'mode':'opposed','skills':skills},('a','b'))})
        except ValueError:continue
        raise AssertionError('inexact participant skill map')
run('032-opposed-requires-exact-participant-skill-map',opposed_missing_skill)
def opposed_ambiguous_skill():
    try:f.setup(requests={'check':req({'mode':'opposed','skill':'athletics','skills':{'a':'athletics','b':'survival'}},('a','b'))})
    except ValueError:return
    raise AssertionError('ambiguous shorthand plus map')
run('033-opposed-map-shorthand-ambiguity',opposed_ambiguous_skill)
files=[str(p.relative_to(ROOT)).replace('\\','/') for p in (ROOT/'engine').glob('*.py')]+['tools/common_check_fixture.py','tools/common_check_synthetic_evidence.txt','tools/test_root_common_checks_author.py']
report={'kind':'bounded_common_check_Runtime_adapter_author_tests','source_admitted_registrations':0,'whole_source_complete':False,'results':results,'input_hashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files}}
(ROOT/'output/root-common-check-author-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'passed':sum(x['status']=='passed' for x in results),'total':len(results),'failures':[x for x in results if x['status']!='passed']},ensure_ascii=False,indent=2))
raise SystemExit(any(x['status']!='passed' for x in results))
