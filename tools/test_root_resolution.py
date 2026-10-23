"""Finite model tests, not source fidelity/admission certification."""
from pathlib import Path
import sys, json, hashlib
from dataclasses import replace
from itertools import permutations, product
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'engine'))
from root_resolution import *
RESULTS=[]
def check(uid,fn):
    try: fn(); RESULTS.append({'id':uid,'status':'pass'})
    except Exception as e: RESULTS.append({'id':uid,'status':'fail','error':repr(e)})
def eq(a,b): assert a==b,(a,b)
def req(cs,**kw):
    aspects=sorted({c.aspect for c in cs})
    base=dict(event_id='event:1',event_kind='model',profile_hash='profile',catalog_hash='catalog',context_hash='context',clauses=cs,laws=tuple(CompositionLaw(a,'exclusive','model:law') for a in aspects),candidate_closure=TRUE)
    base.update(kw);return ResolutionRequest(**base)
def code(r,c): assert c in {o.code for o in r.obligations}, plain(r)
def raises(fn):
    try: fn()
    except (ValueError,TypeError):return
    raise AssertionError('must reject')
a=Clause('a','x',1);b=Clause('b','x',2);c=Clause('c','x',3)
U=Predicate(Truth.UNKNOWN,'source input needed')
edge=lambda x,y,g=TRUE:Override(x,y,'x',g,'model:'+x+y)
law=lambda kind,**kw:CompositionLaw('x',kind,'model:law',**kw)
check('R04-AUTHOR-001',lambda:eq(resolve(req((a,))).tag,'ModelReady'))
check('R04-AUTHOR-002',lambda:eq(resolve(req((replace(a,selected=FALSE,premises=U),))).tag,'Excluded'))
check('R04-AUTHOR-003',lambda:code(resolve(req((replace(a,premises=U),))),'unknown_applicability'))
check('R04-AUTHOR-004',lambda:code(resolve(req((a,),candidate_closure=U)),'candidate_closure_incomplete'))
check('R04-AUTHOR-005',lambda:eq(resolve(req((a,b),overrides=(edge('a','b'),))).aspects[0].value,2))
check('R04-AUTHOR-006',lambda:eq(resolve(req((a,b,c),overrides=(edge('a','b'),edge('b','c')))).aspects[0].value,3))
check('R04-AUTHOR-007',lambda:code(resolve(req((a,replace(b,selected=FALSE),c),overrides=(edge('a','b'),edge('b','c')))),'composition_unresolved'))
check('R04-AUTHOR-008',lambda:eq(resolve(req((a,replace(b,premises=FALSE),c),overrides=(edge('a','c'),))).aspects[0].value,3))
check('R04-AUTHOR-009',lambda:code(resolve(req((a,b),overrides=(edge('a','b',FALSE),))),'composition_unresolved'))
check('R04-AUTHOR-010',lambda:code(resolve(req((a,b),overrides=(edge('a','b',U),))),'unknown_override_influence'))
check('R04-AUTHOR-011',lambda:eq(resolve(req((a,b,c),overrides=(edge('a','c'),edge('b','c'),edge('a','b',U)))).tag,'ModelReady'))
check('R04-AUTHOR-012',lambda:code(resolve(req((a,b),overrides=(edge('a','b'),edge('b','a')))),'cyclic_override_relation'))
check('R04-AUTHOR-013',lambda:code(resolve(req((a,b),overrides=(edge('a','b'),edge('b','a',U)))),'unknown_override_influence'))
check('R04-AUTHOR-014',lambda:code(resolve(req((a,),laws=())),'missing_composition_law'))
check('R04-AUTHOR-015',lambda:eq(resolve(req((a,replace(b,value=1)),laws=(law('exclusive',idempotent=True),))).tag,'ModelReady'))
check('R04-AUTHOR-016',lambda:code(resolve(req((a,replace(b,value=True)),laws=(law('exclusive',idempotent=True),))),'composition_unresolved'))
check('R04-AUTHOR-017',lambda:code(resolve(req((a,replace(b,value=1)))),'composition_unresolved'))
check('R04-AUTHOR-018',lambda:eq(resolve(req((a,b),laws=(law('additive'),))).aspects[0].value,3))
check('R04-AUTHOR-019',lambda:eq(resolve(req((replace(a,value={'numerator':1,'denominator':3}),replace(b,value={'numerator':2,'denominator':3})),laws=(law('additive'),))).aspects[0].value,1))
check('R04-AUTHOR-020',lambda:eq(resolve(req((a,b),laws=(law('sequence',contributor_order=('b','a')),))).aspects[0].value,(2,1)))
check('R04-AUTHOR-021',lambda:code(resolve(req((a,b),laws=(law('sequence'),))),'composition_unresolved'))
x=replace(a,footprint=Footprint(writes=(('actor','hp'),)))
y=Clause('y','y',1,footprint=Footprint(reads=(('actor','hp'),)))
check('R04-AUTHOR-022',lambda:code(resolve(req((x,y))),'unordered_gameplay_dependency'))
check('R04-AUTHOR-023',lambda:eq(resolve(req((x,y),aspect_orders=(AspectOrder('x','y',TRUE,'model:order'),))).tag,'ModelReady'))
check('R04-AUTHOR-024',lambda:eq(resolve(req((x,replace(y,footprint=Footprint(writes=(('other','hp'),)))))).tag,'ModelReady'))
oy=replace(y,footprint=Footprint(observations=(('actor','hp'),)))
check('R04-AUTHOR-025',lambda:code(resolve(req((x,oy))),'unordered_observation_dependency'))
check('R04-AUTHOR-026',lambda:code(resolve(req((replace(x,footprint=Footprint(observations=(('rng','a'),))),replace(y,footprint=Footprint(observations=(('rng','b'),)))))),'unordered_observation_dependency'))
check('R04-AUTHOR-027',lambda:eq(resolve(req((x,y),independences=(Independence('x','y',TRUE,'model:commutation',gameplay_commutes=True),))).tag,'ModelReady'))
check('R04-AUTHOR-028',lambda:code(resolve(req((replace(a,footprint=Footprint(observations=(('event','a'),))),replace(b,footprint=Footprint(observations=(('event','b'),)))),laws=(law('additive'),))),'within_aspect_observation_order_missing'))
check('R04-AUTHOR-029',lambda:eq(resolve(req((replace(a,footprint=Footprint(observations=(('event','a'),))),replace(b,footprint=Footprint(observations=(('event','b'),)))),laws=(law('additive',observation_policy='commutative'),))).tag,'ModelReady'))
check('R04-AUTHOR-030',lambda:raises(lambda:plan_payload(resolve(req((a,b))))))
check('R04-AUTHOR-031',lambda:eq(resolve(req((replace(a,premises=Predicate(Truth.TRUE,reads=(('actor','status'),))),))).footprint.reads,(('actor','status'),)))
check('R04-AUTHOR-032',lambda:code(resolve(req((x,replace(y,premises=Predicate(Truth.TRUE,reads=(('actor','hp'),)),footprint=Footprint())))),'unordered_gameplay_dependency'))
check('R04-AUTHOR-033',lambda:raises(lambda:req((a,a))))
check('R04-AUTHOR-034',lambda:raises(lambda:Clause('a','x',1.1)))
check('R04-AUTHOR-035',lambda:eq(len({resolve(req(cs,laws=(law('additive'),))).receipt['plan_fingerprint'] for cs in permutations((a,b,c))}),1))
# MappingProxy has no __setitem__; use ordinary assignment to expose TypeError.
def immutable():
    value={'nested':[1]};q=req((replace(a,value=value),));value['nested'].append(2);r=resolve(q)
    eq(r.aspects[0].value['nested'],(1,))
    try:r.receipt['source_ready']=True
    except TypeError:pass
    else:raise AssertionError('mutable receipt')
check('R04-AUTHOR-036',immutable)
check('R04-AUTHOR-037',lambda:eq(resolve(req((replace(a,source_refs=('fake:source',)),))).gameplay_certified,False))
check('R04-AUTHOR-038',lambda:code(resolve(req((a,),laws=(law('arbitrary_callback'),))),'composition_unresolved'))
def finite():
    count=0
    for flags in product((TRUE,FALSE,U),repeat=3):
        cs=tuple(replace(q,selected=f) for q,f in zip((a,b,c),flags))
        hashes={resolve(req(order,laws=(law('additive'),))).receipt['plan_fingerprint'] for order in permutations(cs)}
        eq(len(hashes),1); count+=6
    return count
check('R04-AUTHOR-039',finite)
check('R04-AUTHOR-040',lambda:code(resolve(req((x,replace(b,footprint=Footprint(observations=(('actor','hp'),)))),laws=(law('additive'),))),'within_aspect_observation_order_missing'))
check('R04-AUTHOR-041',lambda:eq(resolve(req((x,replace(b,footprint=Footprint(observations=(('actor','hp'),)))),laws=(law('additive',observation_policy='ordered',contributor_order=('a','b')),))).tag,'ModelReady'))
paths=['engine/root_resolution.py','tools/test_root_resolution.py','data/verification/topdown-r04-contract.json']
report={'scope':'finite model behavior only; no source refinement or live Engine integration proof','finite_permutation_cases':162,'input_hashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths},'results':RESULTS}
(ROOT/'output').mkdir(exist_ok=True)
(ROOT/'output/root-resolution-tests.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
print(json.dumps({'passed':sum(r['status']=='pass' for r in RESULTS),'total':len(RESULTS),'failed':[r for r in RESULTS if r['status']!='pass']},ensure_ascii=False))
raise SystemExit(any(r['status']!='pass' for r in RESULTS))
