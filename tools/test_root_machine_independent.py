"""Synthetic independent root-kernel checks; no source or callback-purity proof."""
import sys,json,hashlib,importlib.util
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from engine import root_machine as R
results=[]
def check(c,msg='assertion failed'):
 if not c:raise AssertionError(msg)
def throws(t,fn):
 try:fn()
 except t:return
 raise AssertionError('expected '+t.__name__)
def case(i,fn):
 try:fn();results.append({'id':i,'status':'pass'})
 except Exception as e:results.append({'id':i,'status':'fail','error':type(e).__name__+': '+str(e)})
def game(x=0):
 g={k:{} for k in R.DOMAINS};g['resources']={'x':x,'y':0};return g
def machine(x=0,inv=()):return R.Machine(R.Snapshot('p',0,game(x)),inv)
def true(*a):return R.Guard(R.Truth.TRUE)
def node(i='n',key='x',amount=1,after=(),guard=true,policy='reject',post=None):
 p=('resources',key)
 return R.Node(i,(p,),(p,),guard,lambda v,e,j:R.Commit((R.Write(p,v.get(p)+amount),),{'delta':amount}),after,policy,post)
def plan(*n,origin='model_experiment',refs=()):return R.Plan('plan','p','act',n,origin,refs)
def event(i='e',rev=0,profile='p',payload=None,parent=None):return R.Event(i,'act',profile,rev,payload or {},parent)
def awaiting(prefix=False):
 def guard(v,e,j):return true() if 'choice' in j else R.Guard(R.Truth.UNKNOWN,R.NeedInput('choice','source_choice','model choice'))
 p=plan(node('a'),node('b',after=('a',),guard=guard)) if prefix else plan(node(guard=guard));m=machine();o=m.submit(p,event());check(o.tag=='AwaitingInput');return m,p,o
def immutable():
 g=game();m=R.Machine(R.Snapshot('p',0,g));g['resources']['x']=9;check(m.state.game['resources']['x']==0)
 try:m.state.game['resources']['x']=8
 except TypeError:return
 raise AssertionError('mutable G')
def duplicate(change=None):
 m=machine();p=plan(node());e=event();a=m.submit(p,e)
 b=m.submit(plan(node(amount=8)) if change=='plan' else p,event(payload={'changed':True}) if change=='request' else e)
 check(b.tag==('Rejected' if change else 'Completed') and m.state.game['resources']['x']==1 and m.state.revision==1)
def stale_submit():
 for e in [event(rev=1),event(profile='q')]:
  m=machine();o=m.submit(plan(node()),e);check(o.tag=='Rejected' and not m.state.occurrences and m.state.revision==0)
def bad_dag(kind):
 if kind=='cycle':ns=(node('a',after=('b',)),node('b',after=('a',)))
 elif kind=='missing':ns=(node(after=('missing',)),)
 elif kind=='duplicate':ns=(node(),node())
 else:ns=(node('a'),node('b'))
 m=machine();o=m.submit(plan(*ns),event());check(o.tag=='Blocked' and o.obligation.reason=='conflict' and m.state.revision==0)
def independent():
 for ns in [(node('a','x'),node('b','y')),(node('b','y'),node('a','x'))]:
  m=machine();o=m.submit(plan(*ns),event());check(o.tag=='Completed' and dict(m.state.game['resources'])=={'x':1,'y':1})
def ordered():
 m=machine();o=m.submit(plan(node('a'),node('b',amount=2,after=('a',))),event());check(o.tag=='Completed' and m.state.game['resources']['x']==3)
def false_guard(policy,prefix):
 f=lambda *a:R.Guard(R.Truth.FALSE);n=node('b' if prefix else 'n',after=('a',) if prefix else (),guard=f,policy=policy)
 m=machine();o=m.submit(plan(*((node('a'),n) if prefix else (n,))),event());wanted='Completed' if policy=='exclude' else 'Blocked' if prefix else 'Rejected'
 check(o.tag==wanted and m.state.game['resources']['x']==int(prefix) and len(o.excluded)==int(policy=='exclude'))
def unknown():
 m=machine();o=m.submit(plan(node(guard=lambda *a:R.Guard(R.Truth.UNKNOWN,R.Block('missing_refinement','unimplemented')))),event());check(o.tag=='Blocked' and m.state.revision==0);throws(ValueError,lambda:m.resume('e',{'choice':1}))
def resume(prefix):
 m,p,o=awaiting(prefix);check(m.state.game['resources']['x']==int(prefix));throws(ValueError,lambda:m.resume('e',{'other':1}));throws(ValueError,lambda:m.resume('e',{'choice':1,'extra':2}));o=m.resume('e',{'choice':True});check(o.tag=='Completed' and m.state.game['resources']['x']==1+int(prefix));throws(ValueError,lambda:m.resume('e',{'choice':True}));check(m.submit(p,event())==o)
def stale_revision():
 m,p,o=awaiting();m.submit(plan(node('other','y')),event('other'));o=m.resume('e',{'choice':1});check(o.tag=='Blocked' and o.obligation.reason=='stale_evidence' and m.state.game['resources']['x']==0)
def incompatible_snapshot(kind):
 old,p,o=awaiting();s=old.state;m=R.Machine(R.Snapshot('q' if kind=='profile' else s.profile,s.revision,game(80) if kind=='state' else s.game,s.occurrences));o=m.resume('e',{'choice':True})
 check(o.tag in ('Blocked','Rejected') and m.state.game['resources']['x']==(80 if kind=='state' else 0),'stale '+kind+' resumed: '+o.tag)
def duplicate_other_profile():
 m=machine();p=plan(node());e=event();m.submit(p,e);s=m.state;m=R.Machine(R.Snapshot('q',s.revision,s.game,s.occurrences));o=m.submit(p,e);check(o.tag in ('Blocked','Rejected'),'old profile Completed returned')
def frame(kind):
 if kind=='read':n=R.Node('n',(),(),lambda v,e,j:true() if v.get(('resources','x'))==0 else true(),lambda *a:R.Commit())
 else:n=R.Node('n',(),(),true,lambda *a:R.Commit((R.Write(('resources','x'),9),)))
 m=machine();o=m.submit(plan(n),event());check(o.tag=='Blocked' and o.obligation.reason=='frame_violation' and m.state.revision==0)
def failed_check(kind,prefix):
 n=node('b' if prefix else 'n',after=('a',) if prefix else (),post=(lambda *a:False) if kind=='post' else None)
 m=machine(inv=((lambda g:g['resources']['x']<=int(prefix)),) if kind=='invariant' else ());o=m.submit(plan(*((node('a'),n) if prefix else (n,))),event());check(o.tag=='Blocked' and o.obligation.reason=='invalid_state' and m.state.game['resources']['x']==int(prefix) and len(o.committed)==int(prefix))
def exception_prefix():
 def bad(*a):raise RuntimeError('missing implementation')
 m=machine();o=m.submit(plan(node('a'),R.Node('b',(),(),true,bad,('a',))),event());check(o.tag=='Blocked' and o.committed==('a',) and m.state.game['resources']['x']==1)
def snapshot_replay():
 m,p,o=awaiting(True);s=m.state;m.resume('e',{'choice':'left'});m=R.Machine(s);o=m.resume('e',{'choice':'right'});check(o.tag=='Completed' and m.state.game['resources']['x']==2 and s.game['resources']['x']==1)
def mutable_K():
 record={'forged':0}
 try:s=R.Snapshot('p',0,game(),{'e':record})
 except (TypeError,ValueError):return
 record['forged']=1;check(s.occurrences['e']['forged']==0,'untyped mutable occurrence retained in frozen K')
def label():
 m=machine();o=m.submit(plan(node(),origin='source_refinement_candidate',refs=('not-verified',)),event());check(o.tag=='Completed' and o.gameplay_certified is False)
def parent():
 m=machine();o=m.submit(plan(node()),event(parent='absent'));check(o.tag=='Rejected' and not m.state.occurrences)
case('RMI-001-immutable-G',immutable)
for c in [None,'request','plan']:case('RMI-002-duplicate-'+str(c),lambda c=c:duplicate(c))
case('RMI-003-stale-submit',stale_submit)
for k in ['cycle','missing','duplicate','hazard']:case('RMI-004-'+k,lambda k=k:bad_dag(k))
case('RMI-005-independent',independent);case('RMI-006-ordered',ordered)
for p in ['exclude','reject']:
 for pre in [False,True]:case('RMI-007-'+p+'-'+str(pre),lambda p=p,pre=pre:false_guard(p,pre))
case('RMI-008-unknown',unknown)
for pre in [False,True]:case('RMI-009-resume-'+str(pre),lambda pre=pre:resume(pre))
case('RMI-010-stale-revision',stale_revision)
for k in ['profile','state']:case('RMI-F01-stale-'+k,lambda k=k:incompatible_snapshot(k))
case('RMI-F02-duplicate-profile',duplicate_other_profile)
for k in ['read','write']:case('RMI-011-frame-'+k,lambda k=k:frame(k))
for k in ['post','invariant']:
 for pre in [False,True]:case('RMI-012-'+k+'-'+str(pre),lambda k=k,pre=pre:failed_check(k,pre))
case('RMI-013-exception-prefix',exception_prefix);case('RMI-014-snapshot-replay',snapshot_replay);case('RMI-F03-mutable-K',mutable_K);case('RMI-015-label-not-certificate',label);case('RMI-016-parent',parent)
case('RMI-017-overlapping-writes',lambda:throws(ValueError,lambda:R.Commit((R.Write(('resources',),{}),R.Write(('resources','x'),1)))))
def update_input():
 def update(v,e,j):
  return R.NeedInput('roll','randomness','external die') if 'roll' not in j else R.Commit((R.Write(('resources','y'),j['roll']),))
 n=R.Node('b',(),(('resources','y'),),true,update,('a',));m=machine();p=plan(node('a'),n);o=m.submit(p,event());check(o.tag=='AwaitingInput' and o.committed==('a',));o=m.resume('e',{'roll':6});check(o.tag=='Completed' and dict(m.state.game['resources'])=={'x':1,'y':6})
def ancestor_hazard():
 a=R.Node('a',(),(('resources','branch'),),true,lambda *x:R.Commit())
 b=R.Node('b',(('resources','branch','leaf'),),(),true,lambda *x:R.Commit());check(R.validate_plan(plan(a,b)).reason=='conflict')
def failure_local_atomic():
 n=R.Node('n',(),(('resources',),),true,lambda *a:R.Commit((R.Write(('resources','x'),9),R.Write(('resources','missing'),delete=True))))
 m=machine();o=m.submit(plan(n),event());check(o.tag=='Blocked' and m.state.game['resources']['x']==0 and m.state.revision==0)
def immutable_evidence():
 m,p,o=awaiting();answer={'nested':[1]};m.resume('e',{'choice':answer});answer['nested'].append(2);check(tuple(m.state.occurrences['e'].evidence['choice']['nested'])==(1,))
case('RMI-018-update-source-input',update_input)
case('RMI-019-ancestor-hazard',ancestor_hazard)
case('RMI-020-local-write-failure',failure_local_atomic)
case('RMI-021-evidence-frozen',immutable_evidence)
case('RMI-022-initial-invariant',lambda:throws(ValueError,lambda:machine(inv=(lambda g:False,))))
case('RMI-023-untyped-guard',lambda:throws(ValueError,lambda:R.Guard(True)))
def bool_int_request():
 for a,b in [(True,1),(False,0),({'nested':[True]},{'nested':[1]})]:
  m=machine();p=plan(node());m.submit(p,event(payload={'value':a}));o=m.submit(p,event(payload={'value':b}));check(o.tag=='Rejected' and m.state.game['resources']['x']==1)
def snapshot_key_mismatch():
 m,p,o=awaiting();s=m.state;throws(ValueError,lambda:R.Snapshot(s.profile,s.revision,s.game,{'other':s.occurrences['e']}))
case('RMI-024-bool-int-distinct-request',bool_int_request)
case('RMI-025-snapshot-key-mismatch',snapshot_key_mismatch)
def source_refs_frozen():
 ref={'document':'original'}
 try:p=plan(node(),origin='source_refinement_candidate',refs=(ref,))
 except (TypeError,ValueError):return
 m=machine();m.submit(p,event());ref['document']='changed';check(m.state.occurrences['e'].plan.source_refs[0]['document']=='original','submitted source evidence aliases caller dictionary')
case('RMI-F04-source-ref-alias',source_refs_frozen)
def nested_receipt():
 d={'nested':[1]};o=R.Outcome('Completed','e',results=(('n',d),));d['nested'].append(2);check(tuple(o.results[0][1]['nested'])==(1,))
 d={'nested':[1]};p=plan(node());e=event();rec=R.Occurrence(e,p,0,results=(('n',d),));d['nested'].append(2);check(tuple(rec.results[0][1]['nested'])==(1,))
def no_self_certification():
 throws(ValueError,lambda:R.Outcome('Completed','e',gameplay_certified=True))
def typed_obligation():
 throws((ValueError,TypeError),lambda:R.Outcome('Blocked','e',obligation={'mutable':[]}))
case('RMI-026-nested-receipt-frozen',nested_receipt)
case('RMI-027-certificate-cannot-be-set',no_self_certification)
case('RMI-028-typed-obligation',typed_obligation)
report={'results':results,'input_hashes':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'engine/root_machine.py',Path(__file__)]},'source_refinement_proved':False,'callback_purity_proved':False,'scope':'Synthetic kernel tests; no live Engine integration or source certification'}
(ROOT/'output/root-machine-independent-tests.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps({'passed':sum(x['status']=='pass' for x in results),'failed':[x for x in results if x['status']=='fail']}));raise SystemExit(any(x['status']=='fail' for x in results))

