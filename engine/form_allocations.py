"""Explicit per-form base allocations, projected through shared stat sources."""
from copy import deepcopy
import state_grants as G
import state_fields as S
KEY='form_allocations'

def validate_hp(record):
    """Keep the authored HP exception consistent across form growth paths."""
    forms=record['forms']
    if record['source']=='ability/스웜체인지':
        if '퍼펙트폼' not in forms or not set(forms)&{'10%폼','50%폼'} or set(forms)-{'10%폼','50%폼','퍼펙트폼'}:
            raise ValueError('Power Construct requires its original and Perfect form allocations')
    elif len({stats['hp'] for stats in forms.values()})!=1:raise ValueError('forms require shared HP base')


def validate(actor,record=None):
    record=actor.spec.get(KEY) if record is None else record
    if type(record) is not dict or set(record)!={'source','active','forms'}:raise ValueError('exact form allocation record required')
    forms=record['forms']
    if type(forms) is not dict or not forms or record['active'] not in forms:raise ValueError('actual active form allocation required')
    if type(record['source']) is not str or not record['source']:raise ValueError('form allocation source required')
    for name,stats in forms.items():
        if type(name) is not str or not name or type(stats) is not dict or set(stats)!=set(S.STATS):raise ValueError('named form with complete base statistics required')
        if any(type(v) is not int or v<S.stat_minimum(actor.spec,k) for k,v in stats.items()):raise ValueError('legal whole-number form base required')
    validate_hp(record)
    return record

def configure(engine,actor,forms,*,active,source):
    import world_entities as W
    W.require_actors(engine,actor,actor)
    return G.transition(engine,actor,lambda e,c:_configure_staged(e,c,forms,active=active,source=source))


def _configure_staged(engine,actor,forms,*,active,source):
    """Validate and install base forms in the caller's staged actor graph."""
    import world_entities as W
    W.require_actors(engine,actor,actor)
    if engine.r._selected_rule(source)!=source:raise ValueError('selected form source required')
    record={'source':source,'active':active,'forms':deepcopy(forms)};validate(actor,record)
    if actor.spec['stats']!=forms[active]:raise ValueError('active allocation must match actual base statistics')
    if KEY in actor.spec and actor.spec[KEY]!=record:raise ValueError('recorded form allocations cannot be replaced')
    for stats in forms.values():G.prepare_stat_baseline(actor,stats)
    actor.spec[KEY]=deepcopy(record);actor.form=active
    return deepcopy(record)

def project(actor):
    record=validate(actor)
    if 'form_growth_allocations' in actor.spec:
        import growth_stats as GROWTH
        GROWTH.form_projection(actor.r,actor.spec)
    if actor.r._selected_rule(record['source'])!=record['source']:raise ValueError('form source selection changed')
    if actor.spec['stats']!=record['forms'][record['active']] or actor.form!=record['active']:
        raise ValueError('untracked active form base change')
    return {name:{'base':deepcopy(stats),'effective':G.prepare_stat_baseline(actor,stats)} for name,stats in record['forms'].items()}

def switch(engine,actor,form):
    import living_weapon as LIVING
    if LIVING.locked_form(engine,actor,form):raise ValueError('equipped Aegislash is fixed in Blade Form')
    if KEY not in actor.spec:
        def apply(e,c):
            c.form=form
            import ability_state_projection as PROJECTION
            PROJECTION.form_changed(e,c)
            return form
        return G.transition(engine,actor,apply)
    def apply(e,c):
        projected=project(c)
        if form not in projected:raise ValueError('declared form allocation required')
        record=c.spec[KEY];c.spec['stats']=deepcopy(projected[form]['base']);c.stats=deepcopy(projected[form]['effective'])
        record['active']=form;c.form=form;G.commit_stat_baseline(c)
        import ability_state_projection as PROJECTION
        PROJECTION.form_changed(e,c)
        return form
    return G.transition(engine,actor,apply)
