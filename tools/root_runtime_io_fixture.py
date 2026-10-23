"""Independent synthetic input-consuming adapter, no source registrations."""
import dataclasses
from engine import root_machine as m,root_resolution as r,root_admission as a,root_inputs as i
PROFILE='a'*64
CATALOG='b'*64
REFS=('synthetic:io','synthetic:law','synthetic:order')
def support(snapshot,event):return r.TRUE
def derive(snapshot,event):
 actor=event.payload.get('actor','a');cost=('actors',actor,'cost');hp=('actors',actor,'hp')
 clauses=(r.Clause('p','prefix',0,footprint=r.Footprint((cost,),(cost,)),source_refs=(REFS[0],)),r.Clause('c','consume',0,footprint=r.Footprint((hp,),(hp,)),source_refs=(REFS[0],)))
 return r.ResolutionRequest(event.id,event.kind,event.profile,CATALOG,a.context_fingerprint(snapshot,event),clauses,laws=tuple(r.CompositionLaw(x,'exclusive',REFS[1]) for x in ('prefix','consume')),candidate_closure=r.TRUE,aspects=('prefix','consume'),aspect_orders=(r.AspectOrder('prefix','consume',r.TRUE,REFS[2]),))
def build(aspect,snapshot,event):
 actor=event.payload.get('actor','a');cost=('actors',actor,'cost');hp=('actors',actor,'hp');mode=event.payload.get('mode','choice')
 def guard(view,ev,evidence):
  if aspect.aspect=='prefix':return m.Guard(m.Truth.TRUE)
  if mode in ('choice','double') and 'decision' not in evidence:return m.Guard(m.Truth.UNKNOWN,m.NeedInput('decision','source_choice','synthetic explicit choice'))
  if mode in ('dice','double') and 'faces' not in evidence:return m.Guard(m.Truth.UNKNOWN,m.NeedInput('faces','randomness','synthetic exact dice'))
  return m.Guard(m.Truth.TRUE)
 def update(view,ev,evidence):
  if aspect.aspect=='prefix':return m.Commit((m.Write(cost,view.get(cost)-1),),'paid-prefix')
  amount=7 if mode=='automatic' else evidence['decision'] if mode=='choice' else sum(evidence['faces']) if mode=='dice' else evidence['decision']*sum(evidence['faces'])
  return m.Commit((m.Write(hp,view.get(hp)+amount),),{'used_value':amount,'evidence':dict(evidence)})
 path=cost if aspect.aspect=='prefix' else hp
 return m.Node(aspect.aspect,(path,),(path,),guard,update,after=() if aspect.aspect=='prefix' else ('prefix',))
def input_request(binding,pending,snapshot,event):
 fault=event.payload.get('input_fault')
 if fault=='binding':binding=dataclasses.replace(binding,event_id='foreign')
 mode='source' if fault=='mode' else 'synthetic'
 refs=('foreign:source',) if fault=='source' else (REFS[0],)
 base=dict(id=event.id+':'+pending.key+':'+binding.context_hash,binding=binding,purpose=pending.reason,source_refs=refs,mode=mode)
 if pending.kind=='source_choice' and fault!='kind':return i.ChoiceRequest(**base,chooser_ids=('gm',),domain=(2,4))
 return i.RollRequest(**base,supplier_ids=('gm',),count=2,sides=6,distribution='independent_uniform_faces')
