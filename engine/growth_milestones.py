"""Durable stage rights with explicit choices; native callers apply their effects."""
from copy import deepcopy

KEY='growth_milestone_choices'
INHERITANCE_SOURCE='ch05-pokemon/포켓몬-교배'


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
        if identity.startswith('inheritance:'):
            level=stage.get('level')
            if offered['source']!=INHERITANCE_SOURCE or stage.get('kind')!='inheritance' or type(level) is not int or level<20 or level%10 or level>spec.get('level',0) or identity!='inheritance:'+str(level):
                raise ValueError('actual inheritance milestone stage required')
        selection=row['selection']
        if selection is not None:
            if type(selection) is not dict or set(selection)!={'choice','reason','available'}:
                raise ValueError('exact milestone selection required')
            _options(selection['available'])
            if selection['choice'] not in selection['available'] or type(selection['reason']) is not str or not selection['reason'].strip():
                raise ValueError('milestone selection evidence mismatch')
            if identity.startswith('inheritance:') and (selection['choice'] not in offered['options'] or any(x not in offered['options'] for x in selection['available'])):
                raise ValueError('inheritance choice differs from the offered list')


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


def offer_inheritance(rules,spec):
    """Keep future candidates; offer each actual level slot with its own admission."""
    policy=spec.get('inheritance_tutoring_policy')
    if policy is None:
        level=spec['level'];options=spec.get('inheritance_moves',[])
        if not options or level<20 or level%10:return
        if rules._selected_rule(INHERITANCE_SOURCE)!=INHERITANCE_SOURCE:raise ValueError('selected inheritance source required')
        _options(options)
        if any(rules.move_id(mid)!=mid for mid in options):raise ValueError('canonical inherited Move list required')
        identity='inheritance:'+str(level)
        if identity in spec.get(KEY,{}):return
        return offer(spec,identity,source=INHERITANCE_SOURCE,
            stage={'kind':'inheritance','level':level,'species':spec['species']},options=list(options))
    import pokemon_teaching as T,move_state as M
    if policy not in ('core','official_sep2015','kr_errata'):raise ValueError('selected inheritance tutoring policy required')
    source='ch05-pokemon/포켓몬-교배';rules._selected_rule(source)
    candidates=[rules.move_id(x) for x in spec.get('inheritance_moves',[])]
    if any(x is None or x in rules.excluded_moves for x in candidates) or len(set(candidates))!=len(candidates):
        raise ValueError('actual distinct inheritance candidates required')
    for level in range(20,spec['level']+1,10):
        identity='inheritance:'+str(level)
        if identity in spec.get(KEY,{}):continue
        eligible=[];admissions={};blocked={}
        unlearned=[mid for mid in candidates if mid not in M.known(rules,spec)]
        for mid in unlearned:
            try:admissions[mid]=T.tutor_admission(rules,mid,level,policy=policy)
            except ValueError as exc:
                if not str(exc).startswith('tutoring restriction'):raise
                blocked[mid]=str(exc)
            else:eligible.append(mid)
        offer(spec,identity,source=source,stage={'kind':'inheritance','level':level,'policy':policy,
              'candidates':list(unlearned),'admissions':admissions,'blocked':blocked},options=eligible)


def choose_inheritance(engine,actor,level,move,*,reason,replace=None):
    import state_grants as G,world_entities as W,learning_grant as L,move_state as M,pokemon_teaching as T
    W.require_actors(engine,actor)
    if actor.kind!='pokemon' or type(level)is not int or level>actor.level:raise ValueError('actual attained Pokemon inheritance slot required')
    mid=engine.r.move_id(move)
    def apply(e,p):
        offer_inheritance(e.r,p.spec);identity='inheritance:'+str(level)
        row=p.spec.get(KEY,{}).get(identity)
        if row is None:raise ValueError('recorded inheritance slot required')
        stage=row['offered']['stage'];admission=None
        if 'policy' in stage:
            admission=T.tutor_admission(e.r,mid,level,policy=stage['policy'])
            if stage['admissions'].get(mid)!=admission:raise ValueError('inheritance move outside original eligible slot candidates')
        elif e.r._selected_rule(INHERITANCE_SOURCE)!=INHERITANCE_SOURCE:raise ValueError('selected inheritance source required')
        if mid not in p.spec.get('inheritance_moves',[]):raise ValueError('move no longer belongs to individual inheritance list')
        available=[x for x in row['offered']['options'] if x not in M.known(e.r,p.spec) and x not in e.r.excluded_moves]
        selected,fresh=select(p.spec,identity,mid,available=available,reason=reason)
        if fresh:
            old=None if replace is None else e.r.move_id(replace)
            if replace is not None:
                if old not in M.known(e.r,p.spec):raise ValueError('actual forgotten permanent move required')
                __import__('move_type_sync').forget_spec(e.r,p.spec,old,at=e.elapsed_seconds,reason=reason)
                __import__('ace_trainer').forget_spec(e.r,p.spec,old,at=e.elapsed_seconds,reason=reason)
                G.set_baseline(p,'moves',[x for x in M.known(e.r,p.spec) if x!=old])
            if admission is None:
                L.learn_moves(e.r,p.spec,candidates=available,selected=[mid],method='level_up',source='pokemon/level-up',
                    reason=reason,details={'inheritance_milestone':identity},replaced=old)
            else:
                L.learn_moves(e.r,p.spec,candidates=row['offered']['options'],selected=[mid],method='inheritance',
                    source=row['offered']['source'],reason=reason,details={'inheritance_slot':level,'inheritance_admission':admission},replaced=old)
            G.set_baseline(p,'moves',p.spec['moves']);G.reconcile(e,p)
        return dict(selected,replayed=not fresh)
    return G.transition(engine,actor,apply)


def validate_inheritance(rules,spec):
    import pokemon_teaching as T
    validate(spec)
    for identity,row in spec.get(KEY,{}).items():
        if not identity.startswith('inheritance:'):continue
        stage=row['offered']['stage']
        if 'policy' not in stage:continue
        if stage['policy']!=spec.get('inheritance_tutoring_policy'):raise ValueError('inheritance tutoring policy changed')
        for mid,admission in stage['admissions'].items():
            if admission!=T.tutor_admission(rules,mid,stage['level'],policy=stage['policy']):raise ValueError('historical inheritance admission changed')
        if set(row['offered']['options'])!=set(stage['admissions']) or set(stage['candidates'])!=set(stage['admissions'])|set(stage['blocked']):
            raise ValueError('inheritance slot candidate partition changed')
    for mid,row in spec.get('move_learning',{}).items():
        if row.get('method')!='inheritance':continue
        slot=row.get('inheritance_slot');receipt=spec.get(KEY,{}).get('inheritance:'+str(slot))
        if receipt is None or receipt['selection'] is None or receipt['selection']['choice']!=mid or row.get('inheritance_admission')!=receipt['offered']['stage']['admissions'].get(mid):
            raise ValueError('learned inheritance move lost its actual slot selection')
    seen=set()
    for row in spec.get('move_learning_log',[]):
        if not isinstance(row,dict) or 'inheritance_milestone' not in row:continue
        identity=row['inheritance_milestone']
        if not isinstance(identity,str) or not identity.startswith('inheritance:') or identity in seen:
            raise ValueError('one learning receipt per inherited growth choice required')
        seen.add(identity);right=spec.get(KEY,{}).get(identity)
        if right is None or right['selection'] is None:
            raise ValueError('inherited Move requires its completed growth choice')
        if row.get('method')!='level_up' or row.get('source')!='pokemon/level-up' or row.get('paid_tp')!=0 or row.get('move_id')!=right['selection']['choice'] or type(row.get('learned_at_level')) is not int or row['learned_at_level']<right['offered']['stage']['level']:
            raise ValueError('inherited Move learning disagrees with its growth choice')
        if rules._selected_rule(INHERITANCE_SOURCE)!=INHERITANCE_SOURCE:raise ValueError('selected inheritance source required')


def inheritance_natural_moves(rules,spec):
    validate_inheritance(rules,spec)
    return ({mid for mid,row in spec.get('move_learning',{}).items() if row.get('method')=='inheritance'}
            | {row['move_id'] for row in spec.get('move_learning_log',[]) if 'inheritance_milestone' in row})
