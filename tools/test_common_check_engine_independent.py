"""Independent native-host bridge probes; synthetic registration is not source certification."""
from pathlib import Path
import sys,importlib.util,copy,json,hashlib,traceback,os
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import common_check_fixture as f
spec=importlib.util.spec_from_file_location('independent_native_host',ROOT/'engine/engine.py')
n=importlib.util.module_from_spec(spec);spec.loader.exec_module(n)
DATA_ROOT=Path(os.environ['PTK_NATIVE_RULE_ROOT']) if os.environ.get('PTK_NATIVE_RULE_ROOT') else ROOT if (ROOT/'data/core-rules.json').is_file() else (_ for _ in ()).throw(ValueError('set PTK_NATIVE_RULE_ROOT or install native data/core-rules.json'))
BASE_RULES=n.Rules(str(DATA_ROOT),ruleset='core')
RESULTS=[]
def check(number,title,fn):
 try:fn();RESULTS.append(dict(id='COMMON-ENGINE-INDEPENDENT-'+str(number).zfill(3),status='pass',title=title))
 except Exception as exc:RESULTS.append(dict(id='COMMON-ENGINE-INDEPENDENT-'+str(number).zfill(3),status='fail',title=title,error=str(exc),trace=traceback.format_exc()))
def assert_rejected(x):
 assert isinstance(x,f.a.Finding),(type(x).__name__,repr(x))
 assert x.tag.startswith('Rejected') or x.tag in ('InvalidFaces','OutsideDomain','ConflictingReplay'),x
 return x
def raises(fn):
 try:fn()
 except (ValueError,TypeError):return
 raise AssertionError('expected explicit rejection')
def setup(decision=None,edit=None,actor_edit=None):
 e=n.Engine(copy.deepcopy(BASE_RULES),seed=7)
 actors={}
 for key,rank in [('a','미숙'),('b','초보'),('helper','초보')]:
  actors[key]=n.Combatant(e.r,{'name':'same displayed name','kind':'trainer','level':1,'stats':{'hp':10,'atk':5,'def':5,'spa':5,'spd':5,'spe':5},'skills':{'athletics':rank}})
 if actor_edit:actor_edit(e,actors)
 session,principals,config=f.setup(decision=decision)
 if edit:edit(config)
 e.gm.everyone=list(actors.values())
 b=e.open_common_checks(session.runtime.registry,session.registration,actors,config,tuple(principals.values()))
 return e,actors,b,principals,config
def start(b):
 t=b.begin('event','check');assert isinstance(t,f.a.Ticket),t
 assert b.submit(t).tag=='AwaitingInput'
 return t
def choose(b,t,p,c):return b.answer(b.pending(t),p['gm'],c['requests']['check']['decisions'][0])
def complete(x,faces=(4,4)):
 e,actors,b,p,c=x;t=start(b);out=choose(b,t,p,c)
 if c['requests']['check']['decisions'][0]['mode']!='no_roll':out=b.answer(b.pending(t),p['a'],faces)
 assert out.tag=='AwaitingInput',out
 out=b.answer(b.pending(t),p['gm'],c['requests']['check']['outcomes'][0]);assert out.tag=='Completed',out
 return t,out

def positive():
 x=setup();_,out=complete(x);e,actors,b,p,c=x
 assert b.result('event')['raw']['total']==8
 assert len(e._root_common_receipts)==1 and not out.gameplay_certified
check(1,'native actors/rules positive arithmetic with synthetic Registry',positive)
def no_roll():
 x=setup({'mode':'no_roll','reason':'trivial'});e,actors,b,p,c=x
 old=(e.rng.getstate(),e.elapsed_seconds,actors['a'].hp,copy.deepcopy(actors['a'].spec))
 complete(x)
 assert old==(e.rng.getstate(),e.elapsed_seconds,actors['a'].hp,actors['a'].spec)
 assert not b.result('event')['rolls']
check(2,'no-roll leaves RNG HP spec time unchanged',no_roll)
def names():
 x=setup({'mode':'opposed','skill':'athletics'}) if False else setup()
 e,actors,b,p,c=x
 assert actors['a'].name==actors['b'].name and actors['a'] is not actors['b']
 assert b.runtime.machine.state.game['actors']['a']['skills']['athletics']==2
 assert b.runtime.machine.state.game['actors']['b']['skills']['athletics']==3
check(3,'same displayed name remains two explicit identities',names)
def dup():
 raises(lambda:setup(actor_edit=lambda e,a:a.update(b=a['a'])))
check(4,'duplicate alias of one actor rejected',dup)
check(5,'unknown participating actor rejected',lambda:raises(lambda:setup(edit=lambda c:c['requests']['check'].update(actors=['missing']))))
check(6,'actor from another native Rules context rejected',lambda:raises(lambda:setup(actor_edit=lambda e,a:setattr(a['a'],'r',copy.deepcopy(e.r)))))
check(7,'misspelled skill outside registered catalog rejected',lambda:raises(lambda:setup(edit=lambda c:c['requests']['check']['decisions'][0].update(skill='athletcis'))))
def defaults():
 raises(lambda:setup(actor_edit=lambda e,a:a['a'].spec['skills'].update(athletics=None)))
 x=setup(edit=lambda c:c.update(ordinary_default_actor_ids=['a']),actor_edit=lambda e,a:a['a'].spec['skills'].clear())
 complete(x);assert x[2].result('event')['rolls'][0]['rank']==2
 x=setup(actor_edit=lambda e,a:a['a'].spec['skills'].clear());t=start(x[2]);out=choose(x[2],t,x[3],x[4]);assert out.tag=='Blocked',out
check(8,'unknown rank distinct from explicit complete-sheet default',defaults)
def stale(mutate,at_pending=False):
 e,actors,b,p,c=setup()
 t=start(b) if at_pending else None
 mutate(e,actors)
 assert_rejected(b.pending(t) if t else b.begin('event','check'))
 assert not e._root_common_receipts
check(9,'rank edit before begin stale',lambda:stale(lambda e,a:a['a'].spec['skills'].update(athletics='초보')))
check(10,'rank edit while awaiting input stale',lambda:stale(lambda e,a:a['a'].spec['skills'].update(athletics='초보'),True))
check(11,'HP life edit stale',lambda:stale(lambda e,a:setattr(a['a'],'hp',a['a'].hp-1),True))
check(12,'gear/modifier change stale',lambda:stale(lambda e,a:a['a'].modifiers.append({'type':'skill_mod','value':2}),True))
check(13,'selected native profile mutation stale',lambda:stale(lambda e,a:setattr(e.r.ruleset,'name','changed'),True))
check(14,'GM formula override stale',lambda:stale(lambda e,a:e.rulings.set_formula('tick','2','independent probe'),True))
def old_answers():
 x=setup();e,a,b,p,c=x;t=start(b)
 assert isinstance(b.pending(t).request,f.i.ChoiceRequest)
 e.rulings.answers.append({'key':'common:event:decision','answer':c['requests']['check']['decisions'][0]})
 assert_rejected(b.pending(t));assert not e._root_common_receipts
check(15,'legacy stored GM answer cannot fulfill scoped input',old_answers)
check(16,'clock edit stale',lambda:stale(lambda e,a:setattr(e,'elapsed_seconds',1),True))
def principal():
 e,a,b,p,c=setup();t=start(b);pending=b.pending(t)
 old=b.runtime.machine.state
 assert_rejected(b.answer(pending,f.i.Principal('gm'),c['requests']['check']['decisions'][0]))
 assert b.runtime.machine.state is old
check(17,'same principal text is not capability identity',principal)
def invalid_faces():
 e,a,b,p,c=setup();t=start(b);choose(b,t,p,c);pending=b.pending(t);old=b.runtime.machine.state
 for faces in ([0,6],[7,1],[True,2],[4],[]):assert_rejected(b.answer(pending,p['a'],faces));assert b.runtime.machine.state is old
check(18,'invalid dice reject with no state progress',invalid_faces)
def repeated_answer():
 e,a,b,p,c=setup();t=start(b);pending=b.pending(t);choice=c['requests']['check']['decisions'][0]
 first=b.answer(pending,p['gm'],choice);old=b.runtime.machine.state
 second=b.answer(pending,p['gm'],choice)
 assert b.runtime.machine.state is old,(first,second)
 assert_rejected(b.answer(pending,p['gm'],{'mode':'no_roll','reason':'trivial'}))
check(19,'answered request cannot duplicate prefix or change answer',repeated_answer)
def begin_replay():
 e,a,b,p,c=setup();t=b.begin('event','check');t2=b.begin('event','check');assert t==t2
 assert_rejected(b.begin('event','missing'))
check(20,'prepare-only repeated request and changed key',begin_replay)
def frozen_config():
 e,a,b,p,c=setup();c['requests']['check']['decisions'][0]['dc']=999;c['ordinary_default_actor_ids']=['b']
 t=start(b);pending=b.pending(t)
 assert pending.request.domain[0]['dc']==7
check(21,'caller configuration mutation cannot edit installed snapshot',frozen_config)
def receipt_copy():
 x=setup();complete(x);e,a,b,p,c=x;json.dumps(e._root_common_receipts)
 e._root_common_receipts[0]['results'][0][1]['total']=999
 assert b.result('event')['raw']['total']==8
check(22,'plain receipt has no mutable alias into immutable result',receipt_copy)
def no_world_commit():
 x=setup();e,a,b,p,c=x;before=(a['a'].hp,e.elapsed_seconds,copy.deepcopy(a['a'].spec))
 t=start(b);choose(b,t,p,c);out=b.answer(b.pending(t),p['a'],(1,1));assert out.tag=='AwaitingInput'
 out=b.answer(b.pending(t),p['gm'],c['requests']['check']['outcomes'][2]);assert out.tag=='Completed'
 assert before==(a['a'].hp,e.elapsed_seconds,a['a'].spec)
 assert not b.result('event')['world_effects_applied'] and not b.result('event')['costs_applied']
check(23,'GM success-with-cost is receipt not automatic HP/time consequence',no_world_commit)
def restore_identical():
 e,a,b,p,c=setup();t=start(b);pending=b.pending(t);e.gm.snapshot('same');e.gm.restore('same')
 assert_rejected(b.answer(pending,p['gm'],c['requests']['check']['decisions'][0]));assert_rejected(b.result('event'))
check(24,'same-value restore invalidates old authenticated input',restore_identical)
def restore_receipts():
 x=setup();complete(x);e,a,b,p,c=x;e.gm.snapshot('done');e._root_common_receipts.clear();e.gm.restore('done')
 assert len(e._root_common_receipts)==1 and e._root_common_receipts[0]['event_id']=='event'
 assert_rejected(b.result('event'))
check(25,'completed receipt restores without reviving binding',restore_receipts)
def pending_restore():
 e,a,b,p,c=setup();t=start(b);e.gm.snapshot('pending');e.gm.restore('pending')
 assert not e._root_common_receipts;assert_rejected(b.submit(t));assert_rejected(b.pending(t))
check(26,'pending runtime not silently restored',pending_restore)
def twice_restore():
 e,a,b,p,c=setup();e.gm.snapshot('s');e.gm.restore('s');e.gm.restore('s')
 assert e._root_common_epoch==2;assert_rejected(b.begin('event','check'))
check(27,'repeated restore advances monotonic host epoch',twice_restore)
def fresh_after_restore():
 e,a,b,p,c=setup();e.gm.snapshot('s');e.gm.restore('s')
 newer=e.open_common_checks(b.runtime.registry,b.session.registration,a,c,tuple(p.values()))
 complete((e,a,newer,p,c));assert e._root_common_receipts[0]['host_epoch']==1
check(28,'new binding after restore succeeds in new epoch',fresh_after_restore)
check(29,'synthetic certificate cannot become source by configuration label',lambda:raises(lambda:setup(edit=lambda c:c.update(mode='source'))))
def artifact_stale():
 e,a,b,p,c=setup();t=start(b);pending=b.pending(t);path=ROOT/'tools/common_check_synthetic_evidence.txt';saved=path.read_bytes()
 try:
  path.write_bytes(saved+b'changed')
  assert_rejected(b.answer(pending,p['gm'],c['requests']['check']['decisions'][0]))
 finally:path.write_bytes(saved)
check(30,'changed admission artifact rejects pending input',artifact_stale)
def two_bindings():
 e,a,b,p,c=setup()
 raises(lambda:e.open_common_checks(b.runtime.registry,b.session.registration,a,c,tuple(p.values())))
check(31,'second concurrent binding per Engine epoch rejected',two_bindings)
def harmless_log():
 x=setup();e,a,b,p,c=x;e.log('independent diagnostic','test/diagnostic');e.rulings.record('note','not a rule change',None,None,'probe','once')
 complete(x)
check(32,'diagnostic logging does not invalidate gameplay context',harmless_log)
# Structural source-mode branch probes use deliberately synthetic evidence files.
# Their success is NOT a source registration/certification claim.
def source_mode(case):
 from dataclasses import replace
 import root_common_engine as bridge
 e,actors,b,principals,config=setup()
 cert,_=b.runtime.registry.checked(b.session.registration)
 e._root_common_binding=None
 config=copy.deepcopy(config);config['mode']='source'
 rel='tools/native-profile-test-'+case+'.json'
 context=bridge.host_context(e,actors)
 native=bridge._digest({k:context[k] for k in ('profile','rank_rule','ordinary_rule')})
 evidence={'kind':'common-check-native-profile-v1','profile_hash':cert.profile_hash,'catalog_hash':cert.catalog_hash,'native_profile_hash':native}
 if case=='mismatch':evidence['native_profile_hash']='c'*64
 path=ROOT/rel;path.write_text(json.dumps(evidence,sort_keys=True),encoding='utf-8')
 artifacts=dict(cert.artifacts);chain={k:tuple(v) for k,v in cert.chain.items()}
 if case!='missing':config['native_binding_artifact']=rel
 if case not in ('missing','unpinned'):artifacts[rel]=hashlib.sha256(path.read_bytes()).hexdigest()
 if case not in ('missing','unpinned','wrong_role'):chain['adapter_refinement']+= (rel,)
 new=replace(cert,id='synthetic-structural-source-branch-'+case,mode='source',artifacts=artifacts,chain=chain)
 registry=f.a.Registry(ROOT,f.a.TrustedPolicy('synthetic structural source-mode probe','source',{new.id:new.fingerprint()}),(f.c.adapter(),))
 registration=registry.verify_registration(new);assert isinstance(registration,f.a.Registration),registration
 return e,actors,registry,registration,config,principals,path
for num,case in [(33,'missing'),(34,'unpinned'),(35,'mismatch'),(36,'wrong_role')]:
 def run(case=case):
  e,actors,registry,registration,config,principals,path=source_mode(case)
  raises(lambda:e.open_common_checks(registry,registration,actors,config,tuple(principals.values())))
 check(num,'source-mode native-profile relation rejects '+case,run)
def source_positive():
 e,actors,registry,registration,config,principals,path=source_mode('positive')
 b=e.open_common_checks(registry,registration,actors,config,tuple(principals.values()))
 assert isinstance(b.begin('positive','check'),f.a.Ticket)
 assert not e._root_common_receipts
check(37,'pinned exact native-profile relation structurally admits (synthetic evidence only)',source_positive)
def source_post_change():
 e,actors,registry,registration,config,principals,path=source_mode('changed')
 b=e.open_common_checks(registry,registration,actors,config,tuple(principals.values()))
 t=b.begin('event','check');b.submit(t);pending=b.pending(t);path.write_text('{}',encoding='utf-8')
 assert_rejected(b.answer(pending,principals['gm'],config['requests']['check']['decisions'][0]))
check(38,'native-profile pinned artifact freshness persists during input',source_post_change)

def source_external_context():
 mutations={
 'formulas':lambda e:e.rulings.formulas.update(tick={'expr':'2','scope':'campaign','reason':'test'}),
 'mech':lambda e:e.rulings.mech.update(unused={'path':{'value':1,'scope':'campaign'}}),
 'effects':lambda e:e.rulings.effects.update(unused=[{'op':'add'}]),
 'situational':lambda e:e.rulings.situational.append({'modifier':'skill','value':2}),
 'answers':lambda e:e.rulings.answers.append({'key':'choice','answer':1}),
 'hooks':lambda e:e.rulings.hooks['before_effect'].append(lambda *a:None),
 'provider':lambda e:setattr(e.rulings,'provider',lambda *a:None)}
 for name,mutate in mutations.items():
  e,actors,registry,registration,config,principals,path=source_mode('context-'+name)
  mutate(e)
  raises(lambda:e.open_common_checks(registry,registration,actors,config,tuple(principals.values())))
check(39,'source mode blocks seven unresolved external ruling families at installation',source_external_context)
def initial_modifier_block():
 e,actors,b,p,c=setup(actor_edit=lambda e,a:a['a'].modifiers.append({'type':'skill_mod','value':2}))
 result=b.begin('event','check')
 assert isinstance(result,f.a.Finding) and result.tag in ('PendingContext',),result
 assert not e._root_common_receipts
check(40,'initial native potential modifier cannot be silently ignored',initial_modifier_block)

files=list((ROOT/'engine').glob('root_*.py'))+[ROOT/'engine/engine.py',ROOT/'engine/gm_state.py',ROOT/'engine/common_checks.py',Path(__file__),ROOT/'tools/common_check_fixture.py',ROOT/'tools/common_check_synthetic_evidence.txt']+list((ROOT/'tools').glob('native-profile-test-*.json'))
report={'scope':'native host bridge with explicitly synthetic Registry; no source certifications','source_gameplay_certifications':0,'native_data_root':str(DATA_ROOT.resolve()),'native_data_hashes':{str(p.relative_to(DATA_ROOT)).replace(chr(92),'/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in (DATA_ROOT/'data').glob('*.json')},'native_selected_context_hash':__import__('root_common_engine')._digest({'profile':vars(BASE_RULES.ruleset),'rank_rule':BASE_RULES.mech('gameplay/skill-rank-dice'),'ordinary_rule':BASE_RULES.mech('gameplay/skill-check')}),'input_hashes':{str(p.relative_to(ROOT)).replace(chr(92),'/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},'results':RESULTS,'passed':sum(x['status']=='pass' for x in RESULTS),'failed':sum(x['status']=='fail' for x in RESULTS)}
(ROOT/'output').mkdir(exist_ok=True)
(ROOT/'output/common-check-engine-independent-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'passed':report['passed'],'failed':report['failed'],'failures':[x for x in RESULTS if x['status']=='fail']},ensure_ascii=False,indent=2))
raise SystemExit(bool(report['failed']))
