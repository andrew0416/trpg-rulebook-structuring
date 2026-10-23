from engine import root_machine as m, root_resolution as r, root_admission as a
PROFILE='a'*64
CATALOG='b'*64
PATH=('actors','a','hp')
def support(snapshot,event):
    mode=event.payload.get('support','true')
    if mode=='false':return r.FALSE
    if mode=='unknown':return r.Predicate(r.Truth.UNKNOWN,'unresolved support')
    return r.TRUE

def derive(snapshot,event):
    p=event.payload;aspect='alien' if p.get('outside_aspect') else 'hp'
    source='outside' if p.get('outside_source') else 'synthetic:hp'
    closure=r.Predicate(r.Truth.UNKNOWN,'unknown closure') if p.get('closure_unknown') else r.TRUE
    selected=r.FALSE if p.get('excluded') else r.TRUE
    premise=r.Predicate(r.Truth.UNKNOWN,'unknown premise') if p.get('premise_unknown') else r.TRUE
    cs=[r.Clause('base',aspect,p.get('amount',3),selected=selected,premises=premise,footprint=r.Footprint((PATH,),(PATH,)),source_refs=(source,))]
    if p.get('conflict'):cs.append(r.Clause('peer',aspect,99,footprint=r.Footprint((PATH,),(PATH,)),source_refs=(source,)))
    return r.ResolutionRequest(event.id,event.kind,event.profile,'c'*64 if p.get('wrong_catalog') else CATALOG,'wrong' if p.get('wrong_context') else a.context_fingerprint(snapshot,event),tuple(cs),laws=(r.CompositionLaw(aspect,'exclusive','foreign:law' if p.get('foreign_law') else 'synthetic:law'),),candidate_closure=closure,aspects=(aspect,))

def build(aspect,snapshot,event):
    def guard(view,ev,evidence):
        if ev.payload.get('await_input') and 'answer' not in evidence:return m.Guard(m.Truth.UNKNOWN,m.NeedInput('answer','source_choice','synthetic decision'))
        return m.Guard(m.Truth.TRUE)
    def update(view,ev,evidence):
        path=('actors','a','other') if ev.payload.get('hidden_write') else PATH
        return m.Commit((m.Write(path,view.get(PATH)-aspect.value),),{'delta':aspect.value})
    writes=(('actors','a','other'),) if event.payload.get('wrong_footprint') else (PATH,)
    after=('missing',) if event.payload.get('wrong_order') else ()
    return m.Node(aspect.aspect,(PATH,),writes,guard,update,after=after)
