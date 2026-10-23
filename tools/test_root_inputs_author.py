"""Author checks of input-boundary engineering; synthetic, not source certification."""
from pathlib import Path
import sys,json,hashlib,dataclasses,traceback
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from engine import root_inputs as i
results=[]
def run(name,fn):
 try:fn();results.append({'id':'ROOT-INPUT-AUTHOR-'+name,'status':'passed'})
 except Exception:results.append({'id':'ROOT-INPUT-AUTHOR-'+name,'status':'failed','detail':traceback.format_exc()})
def eq(a,b):assert a==b,(a,b)
def binding():return i.Binding('event','a'*64,'b'*64,0,'c'*64)
def setup(roll=False,domain=(1,True,{'x':[True]},None)):
 b=binding();p=i.Principal('gm');other=i.Principal('player')
 kw=dict(id='input',binding=b,purpose='synthetic decision',source_refs=('synthetic:input',),mode='synthetic')
 req=i.RollRequest(**kw,supplier_ids=('gm',),count=2,sides=6,distribution='independent_uniform_faces') if roll else i.ChoiceRequest(**kw,chooser_ids=('gm',),domain=domain)
 broker=i.Broker(i.TrustedPolicy('test','synthetic',{req.id:i.request_fingerprint(req)}),(p,other));h=broker.register(req)
 return b,p,other,req,broker,h

def positive(roll=False):
 b,p,o,q,br,h=setup(roll);v=[1,6] if roll else {'x':[True]};r=br.accept(h,p,v,b)
 assert type(r) is i.AcceptedReceipt;eq(i.canonical(br.validate_receipt(h,r,b)),i.canonical(v))
 eq(br.accept(h,p,v,b) is r,True)
run('001-choice',positive);run('002-roll',lambda:positive(True))
def denied(which):
 b,p,o,q,br,h=setup();r=br.accept(h,p,1,b)
 inputs={'principal':lambda:br.accept(h,i.Principal('gm'),1,b),'role':lambda:br.accept(h,o,1,b),'handle':lambda:br.accept(i.Handle(q.id),p,1,b),'receipt':lambda:br.validate_receipt(h,dataclasses.replace(r),b),'conflict':lambda:br.accept(h,p,True,b),'domain':lambda:br.accept(h,p,{'x':[1]},b)}
 assert type(inputs[which]()) is i.Finding
 eq(br.validate_receipt(h,r,b),1)
for n,k in enumerate(('principal','role','handle','receipt','conflict','domain'),3):run(f'{n:03}-{k}',lambda k=k:denied(k))
def stale(field,value):
 b,p,o,q,br,h=setup();r=br.accept(h,p,1,b);new=dataclasses.replace(b,**{field:value})
 eq(br.accept(h,p,1,new).code,'StaleOrMismatchedContext');eq(br.validate_receipt(h,r,new).code,'StaleOrMismatchedContext')
for n,(f,v) in enumerate((('event_id','other'),('event_hash','d'*64),('profile_hash','d'*64),('revision',1),('context_hash','d'*64)),9):run(f'{n:03}-{f}',lambda f=f,v=v:stale(f,v))
def bad_faces():
 b,p,o,q,br,h=setup(True)
 for v in ([True,2],[0,2],[7,2],[1],(1,2.0),None):eq(br.accept(h,p,v,b).code,'InvalidFaces')
 eq(br.accept(h,p,[2,3],b).value,(2,3))
run('014-invalid-faces-no-fallback',bad_faces)
def immutable():
 original={'x':[True]};b,p,o,q,br,h=setup(domain=(original,));original['x'][0]=False
 v={'x':[True]};r=br.accept(h,p,v,b);v['x'][0]=False;eq(i.canonical(r.value),'{"x":[true]}')
 try:r.value['x']=()
 except TypeError:pass
 else:raise AssertionError('mutable receipt')
run('015-immutable',immutable)
def unpinned():
 b,p,o,q,br,h=setup();empty=i.Broker(i.TrustedPolicy('empty','synthetic',{}),(p,));eq(empty.register(q).code,'PendingAuthority')
 eq(br.register(dataclasses.replace(q,mode='source')).code,'PendingAuthority')
 eq(br.register({'reviewed':True}).code,'RejectedRequest')
run('016-unpinned-metadata-mode',unpinned)
def constructor_boundaries():
 b,p,o,q,br,h=setup(True)
 for kw in ({'count':True},{'count':0},{'sides':True},{'sides':1},{'distribution':'unknown'},{'purpose':''}):
  try:dataclasses.replace(q,**kw)
  except (TypeError,ValueError):pass
  else:raise AssertionError(kw)
run('017-constructor-boundaries',constructor_boundaries)
def JSON_types():
 b,p,o,q,br,h=setup(domain=(1,));eq(br.accept(h,p,True,b).code,'OutsideDomain');eq(br.accept(h,p,1.0,b).code,'OutsideDomain')
 for bad in (float('nan'),float('inf'),{1:'x'},object()):assert type(br.accept(h,p,bad,b)) is i.Finding
run('018-json-exact-types',JSON_types)
def foreign_broker():
 b,p,o,q,br,h=setup();b2,p2,o2,q2,br2,h2=setup();eq(br2.accept(h,p,1,b).code,'RejectedHandle')
 r=br.accept(h,p,1,b);eq(br2.validate_receipt(h2,r,b).code,'RejectedReceipt')
run('019-foreign-broker',foreign_broker)
def distinct_requests():
 b,p,o,q,br,h=setup();q2=dataclasses.replace(q,id='second');br=i.Broker(i.TrustedPolicy('two','synthetic',{x.id:i.request_fingerprint(x) for x in (q,q2)}),(p,))
 h=br.register(q);h2=br.register(q2);assert br.register(q) is h
 r=br.accept(h,p,1,b);r2=br.accept(h2,p,True,b);assert r is not r2;eq(type(r.value),int);eq(type(r2.value),bool)
run('020-distinct-request',distinct_requests)
def kernel_json_grammar():
 for value in (1.5, {'':1}, {'x':[0.5]}, {'x':{'':True}}):
  try:setup(domain=(value,))
  except (TypeError,ValueError):pass
  else:raise AssertionError('kernel-incompatible domain accepted')
run('021-kernel-json-grammar',kernel_json_grammar)
files=('engine/root_inputs.py','tools/test_root_inputs_author.py')
report={'kind':'synthetic_input_boundary_author_checks','source_admitted_registrations':0,'kernel_connected':False,'results':results,'input_hashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files}}
(ROOT/'output').mkdir(exist_ok=True);(ROOT/'output/root-inputs-author-tests.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'total':len(results),'passed':sum(r['status']=='passed' for r in results),'failed':[r for r in results if r['status']!='passed']},indent=2));raise SystemExit(any(r['status']!='passed' for r in results))
