"""Durable stage rights with explicit choices; native callers apply their effects."""
from copy import deepcopy

KEY='growth_milestone_choices'


def _options(values):
    if type(values) is not list or any(type(v) is not str or not v for v in values) or len(set(values))!=len(values):
        raise ValueError('distinct explicit milestone options required')


def validate(spec):
    records=spec.get(KEY,{})
    if type(records) is not dict:raise ValueError('milestone records must be a mapping')
    for identity,row in records.items():
        if type(identity) is not str or not identity or type(row) is not dict or set(row)!={'offered','selection'}:
            raise ValueError('identified milestone offer and selection required')
        offered=row['offered']
        if type(offered) is not dict or set(offered)!={'source','stage','options'}:
            raise ValueError('exact milestone offer required')
        if type(offered['source']) is not str or not offered['source'] or type(offered['stage']) is not dict or not offered['stage']:
            raise ValueError('milestone provenance required')
        _options(offered['options'])
        stage=offered['stage']
        if identity.startswith('ability:'):
            level=stage.get('level')
            if offered['source']!='pokemon/level-up' or type(level) is not int or not 1<=level<=spec.get('level',0):
                raise ValueError('actual ability milestone stage required')
            if stage.get('kind') not in ('creation','level') or identity!=('ability:creation' if stage['kind']=='creation' else 'ability:'+str(level)):
                raise ValueError('ability milestone identity differs from stage')
        selection=row['selection']
        if selection is not None:
            if type(selection) is not dict or set(selection)!={'choice','reason','available'}:
                raise ValueError('exact milestone selection required')
            _options(selection['available'])
            if selection['choice'] not in selection['available'] or type(selection['reason']) is not str or not selection['reason'].strip():
                raise ValueError('milestone selection evidence mismatch')


def offer(spec,identity,*,source,stage,options):
    validate(spec)
    if any(type(v) is not str or not v.strip() for v in (identity,source)):
        raise ValueError('milestone identity and source required')
    if type(stage) is not dict or not stage:raise ValueError('explicit milestone stage required')
    _options(options)
    request={'source':source,'stage':deepcopy(stage),'options':list(options)}
    records=spec.get(KEY,{})
    if identity in records:
        if records[identity]['offered']!=request:raise ValueError('milestone identity cannot change its offer')
        return deepcopy(records[identity])
    row={'offered':request,'selection':None}
    spec.setdefault(KEY,{})[identity]=row
    return deepcopy(row)


def select(spec,identity,choice,*,available,reason):
    validate(spec);_options(available)
    if type(reason) is not str or not reason.strip():raise ValueError('explicit milestone choice reason required')
    row=spec.get(KEY,{}).get(identity)
    if row is None:raise ValueError('recorded milestone right required')
    old=row['selection']
    if old is not None:
        if old['choice']!=choice or old['reason']!=reason:raise ValueError('milestone choice already recorded with different input')
        return deepcopy(old),False
    if choice not in available:raise ValueError('choice is not currently available for this milestone')
    result={'choice':choice,'reason':reason,'available':list(available)}
    row['selection']=deepcopy(result)
    return result,True


def natural_abilities(rules,spec,*,pools=('기본 특성','숨겨진 특성','대단한 특성')):
    from builder import species_lookup
    species=species_lookup(rules,spec['species'])
    values=deepcopy(rules.learnsets.get(species['name'],{}).get('abilities') or {})
    import ability_state_projection as PROJECTION
    values.update(PROJECTION.ability_pool_overrides(spec))
    return list(dict.fromkeys(a for pool in pools for a in values.get(pool,[])
        if a not in rules.excluded_abilities))


def ability_options(rules,spec,level):
    from builder import species_lookup
    rule=rules.mech('pokemon/level-up')
    slot={'pool':['기본 특성']} if level=='creation' else next((x for x in rule['ability_slots'] if x['level']==level),None)
    if slot is None:raise ValueError('actual level ability slot required')
    species=species_lookup(rules,spec['species'])
    pools={'choices':natural_abilities(rules,spec,pools=slot['pool'])}
    if level=='creation':
        import example_species as EXAMPLES
        pools['choices']=EXAMPLES.resolved_basic_choices(rules,species,pools['choices'])
    return list(dict.fromkeys(a for a in pools['choices']
        if a not in spec['abilities'] and a not in rules.excluded_abilities))


def choose_ability(engine,actor,level,ability,*,reason):
    import state_grants as G,world_entities as W
    W.require_actors(engine,actor)
    validate(actor.spec)
    if actor.kind!='pokemon' or (level!='creation' and (type(level) is not int or level>actor.level)):
        raise ValueError('actual attained Pokemon ability milestone required')
    identity='ability:'+str(level)
    def apply(e,c):
        row=c.spec.get(KEY,{}).get(identity)
        if row is None:raise ValueError('recorded ability milestone right required')
        e.r._selected_rule(row['offered']['source'])
        options=ability_options(e.r,c.spec,level)
        result,fresh=select(c.spec,identity,ability,available=options,reason=reason)
        if fresh:
            G.set_baseline(c,'abilities',list(c.spec['abilities'])+[ability])
            G.reconcile(e,c)
        return dict(result,replayed=not fresh)
    return G.transition(engine,actor,apply)
