"""Synthetic protocol fixture; no rulebook authority or real gameplay implementation."""
from engine import root_admission as a,root_machine as m,root_resolution as r,root_children as c,root_inputs as i
PROFILE='1'*64;CATALOG='2'*64
PATHS={'parent':('resources','a','ap'),'child':('actors','a','hp'),'grand':('actors','b','hp')}
ASPECTS={'parent':'p','child':'c','grand':'g'}
def support(snapshot,event):
 return r.FALSE if event.payload.get('target')=='unauthorized' else r.TRUE
def derive(snapshot,event):
 aspect=ASPECTS.get(event.kind,'c');path=PATHS.get(event.kind,PATHS['child'])
 refs=(event.payload.get('derive_source','synthetic:shared'),)
 return r.ResolutionRequest(event.id,event.kind,PROFILE,event.payload.get('catalog',CATALOG),a.context_fingerprint(snapshot,event),(r.Clause('clause:'+aspect,aspect,1,footprint=r.Footprint(reads=(path,),writes=(path,)),source_refs=refs),),laws=(r.CompositionLaw(aspect,'exclusive','synthetic:shared'),),candidate_closure=r.TRUE,aspects=(aspect,))
def build(aspect,snapshot,event):
 path=PATHS.get(event.kind,PATHS['child']);data=event.payload
 def guard(v,e,ev):
  if data.get('wait') and 'pick' not in ev:return m.Guard(m.Truth.UNKNOWN,m.NeedInput('pick','source_choice','choose local child option'))
  return m.Guard(m.Truth.TRUE)
 def update(v,e,ev):
  children=()
  if e.kind=='parent' or data.get('nested'):
   kind=data.get('emit_kind','child' if e.kind=='parent' else 'grand')
   cfg=dict(data.get('child_config',{}))
   children=(c.ChildSpec('spawn',kind,cfg,data.get('barrier','before_parent_complete'),'model:owner','model:scope',(data.get('emission_source','synthetic:shared'),),data.get('timing','after_emission')),)
  return m.Commit((m.Write(path,v.get(path)+1),),{'kind':e.kind},children)
 return m.Node(aspect.aspect,aspect.footprint.reads,aspect.footprint.writes,guard,update)
def select_child(row,snapshot,event):return event.payload.get('select_certificate','cert:'+row.spec.event_kind)
def select_invalid(row,snapshot,event):return {'label':'cert:child'}
def input_request(binding,pending,snapshot,event):
 domain=(True,False) if event.payload.get('domain_child_count',len(snapshot.children))==len(snapshot.children) else (False,)
 return i.ChoiceRequest('pick:'+event.id,binding,'synthetic child input',('synthetic:shared',),'synthetic',('gm',),domain)
