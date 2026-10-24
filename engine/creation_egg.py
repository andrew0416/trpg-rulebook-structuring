"""Declared parent qualification, inherited knowledge and native egg birth."""
from copy import deepcopy
import re
import common_checks as C,crafting_recipes as Q,world_entities as W,resolution_transaction as TX
from builder import species_lookup

BINDING='parentage_evidence'
CONTRACT='egg_creation_contract'
RECORDS='egg_creation_records'


def moves(engine,values):
    if type(values) is not list:raise ValueError('explicit inherited/known move list required')
    result=[engine.r.move_id(value) for value in values]
    if any(uid is None or uid in engine.r.excluded_moves for uid in result) or len(set(result))!=len(result):
        raise ValueError('distinct selected available move identities required')
    return result


def _indices(values,count):
    if type(values) is not list or not values or len(set(map(str,values)))!=len(values):raise ValueError('distinct actual parent indices required')
    for index in values:C.integer(index,'selected parent index',0,count-1)


def _condition(value,depth=0):
    if depth>12:raise ValueError('bounded egg qualification required')
    kind=value.get('kind') if type(value) is dict else None
    if kind in ('all','any'):
        Q._fields(value,('kind','conditions'))
        if type(value['conditions']) is not list or not value['conditions']:raise ValueError('explicit parent qualification alternatives required')
        for child in value['conditions']:_condition(child,depth+1)
    elif kind=='fact':
        Q._fields(value,('kind','field','operator','value'))
        if value['field'] not in ('gender','species','level','egg_group'):raise ValueError('supported actual parent fact required')
        if value['operator']=='minimum' and value['field']=='level':C.integer(value['value'],'required parent level',1,100)
        elif value['operator']=='equals':Q._text(value['value'])
        else:raise ValueError('explicit parent fact comparison required')
    else:Q._condition(value)


def _observe(engine,actor,value):
    kind=value['kind']
    if kind in ('all','any'):
        observed=[_observe(engine,actor,child) for child in value['conditions']]
        return all(observed) if kind=='all' else any(observed)
    if kind!='fact':return Q._observe(engine,actor,value,set())
    actual=actor.level if value['field']=='level' else actor.spec.get(value['field'])
    if actual is None:return False
    if value['operator']=='minimum':return C.integer(actual,'actual qualifying parent level',1,100)>=value['value']
    if value['field']=='species':return species_lookup(engine.r,actual)['id']==species_lookup(engine.r,value['value'])['id']
    return actual==value['value']


def declaration(value):
    Q._fields(value,('id','source','parent_count','owned_parents','requirements','species','inheritance','work_seconds','hatch'))
    Q._text(value['id']);Q._text(value['source']);C.integer(value['parent_count'],'actual parent count',1)
    C.integer(value['work_seconds'],'egg production seconds',0)
    if type(value['owned_parents']) is not bool or type(value['requirements']) is not list:raise ValueError('explicit parent ownership and qualification policy required')
    identities=set()
    for row in value['requirements']:
        Q._fields(row,('id','source','subject','condition','reason'))
        for key in ('id','source','reason'):Q._text(row[key])
        if row['id'] in identities:raise ValueError('distinct egg qualification identities required')
        identities.add(row['id']);subject=row['subject']
        if subject not in ('provider','parents'):C.integer(subject,'qualified parent index',0,value['parent_count']-1)
        _condition(row['condition'])
    Q._fields(value['species'],('parents','allowed'))
    if value['species']['parents']:_indices(value['species']['parents'],value['parent_count'])
    elif type(value['species']['parents']) is not list:raise ValueError('explicit species parent indices required')
    if type(value['species']['allowed']) is not list:raise ValueError('explicit declared species list required')
    for uid in value['species']['allowed']:Q._text(uid)
    inheritance=value['inheritance'];Q._fields(inheritance,('kind','moves','parents','knowledge'))
    if inheritance['kind'] not in ('species_egg','parent_known_egg_and_tm','declared') or inheritance['knowledge'] not in ('any','all'):raise ValueError('explicit inheritance list and parental knowledge policy required')
    _indices(inheritance['parents'],value['parent_count'])
    if type(inheritance['moves']) is not list:raise ValueError('declared inheritance list required')
    if inheritance['kind'] in ('species_egg','parent_known_egg_and_tm') and inheritance['moves']:raise ValueError('species inheritance lists cannot merge an unrelated declared move list')
    for uid in inheritance['moves']:Q._text(uid)
    hatch=value['hatch'];Q._fields(hatch,('level','seconds','tutor_points','known_moves'))
    C.integer(hatch['level'],'declared birth level',1,100);C.integer(hatch['tutor_points'],'actual newborn Tutor Points',0)
    if hatch['seconds'] is not None:C.integer(hatch['seconds'],'declared hatch waiting seconds',0)
    if hatch['known_moves'] not in ('natural_and_inherited','observed'):raise ValueError('explicit birth move authority required')
    return deepcopy(value)


def _tm_moves(engine,learnset):
    """Resolve the child's sourced TM/HM list without treating machine codes as Move names."""
    result=[]
    for raw in learnset.get('tm',[]):
        match=re.fullmatch(r'\s*[A-Za-z]?[0-9]+\s+(.+?)\s*',str(raw))
        if match is None:raise ValueError('child TM learnset row has no supported machine-code identity')
        mid=engine.r.move_id(match.group(1))
        if mid is None or mid in engine.r.excluded_moves:raise ValueError('child TM learnset contains an unavailable Move')
        if mid not in result:result.append(mid)
    return result


def inheritance_pool(engine,species,policy,knowledge):
    """Return candidates plus their exact Egg-list/TM source partition."""
    learnset=engine.r.learnsets.get(species_lookup(engine.r,species)['name'],{})
    qualifies=any if policy['knowledge']=='any' else all
    if policy['kind']=='declared':
        listed=moves(engine,policy['moves']);pool=[mid for mid in listed if qualifies(mid in known for known in knowledge)]
        return pool,{'kind':'declared','egg_moves':[],'tm_moves':[],'declared_moves':listed}
    egg=moves(engine,list(learnset.get('egg',[])))
    egg_pool=[mid for mid in egg if qualifies(mid in known for known in knowledge)]
    if policy['kind']=='species_egg':
        return egg_pool,{'kind':'species_egg','egg_moves':egg_pool,'tm_moves':[],'declared_moves':[]}
    tm=_tm_moves(engine,learnset);tm_pool=[mid for mid in tm if qualifies(mid in known for known in knowledge)]
    pool=list(dict.fromkeys([*egg_pool,*tm_pool]))
    return pool,{'kind':'parent_known_egg_and_tm','egg_moves':egg_pool,'tm_moves':tm_pool,'declared_moves':[]}


def parent_snapshot(engine,parents):
    import pokemon_activities as A,move_state as M
    index=W.actor_index(engine);result=[]
    if len({id(parent) for parent in parents})!=len(parents):raise ValueError('distinct actual parents required')
    for parent in parents:
        if index.get(getattr(parent,'entity_id',None)) is not parent:raise ValueError('actual registered parent required')
        A._pokemon(parent)
        known=None if 'moves' not in parent.spec else M.known(engine.r,parent.spec)
        if known is not None and moves(engine,[mid for mid in parent.moves if mid!='struggle'])!=known:raise ValueError('actual parent known-move state disagrees with its sheet')
        result.append({'entity_id':parent.entity_id,'species':None if parent.spec.get('species') is None else species_lookup(engine.r,parent.spec['species'])['id'],
                       'gender':parent.spec.get('gender'),'level':parent.level,'known_moves':known})
    return result


def bind_parents(engine,owner,row):
    """Snapshot actual parents without inventing missing individual facts."""
    if not row.get('parents') or BINDING in row:return
    index=W.actor_index(engine)
    parents=[index.get(uid) for uid in row['parents']]
    if any(parent is None for parent in parents):raise ValueError('egg parent must resolve to an actual individual')
    facts={'source':row['source'],'created_by':owner.entity_id,'parents':parent_snapshot(engine,parents)}
    row[BINDING]={'facts':facts,'sha256':TX.request_fingerprint(facts)}


def prepare(engine,owner,parents,value,*,compatible,species,inheritance_moves,reason):
    import pokemon_activities as A
    value=declaration(value);Q._selected(engine,value['source']);Q._text(reason)
    W.require_actors(engine,owner,*parents);A._trainer(owner);A._outside(engine)
    if len(parents)!=value['parent_count']:raise ValueError('actual parent count does not match the declaration')
    if type(compatible) is not bool or not compatible:raise ValueError('explicit observed compatible parents required; unknown is not true')
    facts=parent_snapshot(engine,parents)
    if value['owned_parents']:
        for parent in parents:A._owner(owner,parent)
    for row in value['requirements']:
        Q._selected(engine,row['source']);subject=row['subject']
        actors=[owner] if subject=='provider' else parents if subject=='parents' else [parents[subject]]
        if not all(_observe(engine,actor,row['condition']) for actor in actors):raise ValueError(row['reason'])
    candidates=[]
    for n in value['species']['parents']:
        if facts[n]['species'] is None:raise ValueError('actual parent species is unknown')
        candidates.append(facts[n]['species'])
    candidates+= [species_lookup(engine.r,uid)['id'] for uid in value['species']['allowed']]
    candidates=list(dict.fromkeys(candidates));selected=species_lookup(engine.r,species)['id']
    if selected not in candidates:raise ValueError('selected egg species is outside the declared actual candidates')
    policy=value['inheritance']
    knowledge=[facts[n]['known_moves'] for n in policy['parents']]
    if any(known is None for known in knowledge):raise ValueError('required parental known moves are unknown')
    pool,candidate_sources=inheritance_pool(engine,selected,policy,knowledge)
    inherited=moves(engine,inheritance_moves)
    if any(mid not in pool for mid in inherited):raise ValueError('inherited move is not on the selected list and known by the required actual parents')
    if policy['kind']=='parent_known_egg_and_tm' and inherited!=pool:
        raise ValueError('the standard inheritance list must record every parent-known Egg-list and child-compatible TM Move')
    return {'declaration':value,'provider_id':owner.entity_id,'parent_facts':facts,'compatible':True,'reason':reason,
            'species_candidates':candidates,'species':selected,'inheritance_candidates':pool,
            'inheritance_candidate_sources':candidate_sources,'inheritance_moves':inherited}


def create(engine,owner,parents,value,*,request_id,compatible=None,species=None,inheritance_moves=None,reason):
    import state_grants as G,pokemon_entities as P,activity_jobs as J
    value=declaration(value);Q._text(request_id);Q._text(reason)
    W.require_actors(engine,owner,*parents)
    request={'request_id':request_id,'declaration':value,'provider_id':owner.entity_id,'parent_ids':[parent.entity_id for parent in parents],
             'compatible':compatible,'species':species,'inheritance_moves':deepcopy(inheritance_moves),'reason':reason}
    def apply(e,a,*ps):
        prior=TX.replay_result(a.spec.get(RECORDS,{}),request_id,request,fingerprint_field='intent')
        if prior is not None:
            actual=P.egg_index(e).get(prior['egg_entity_id'])
            if actual is None:raise ValueError('created egg lost its actual lifetime identity')
            return deepcopy(actual[1])
        plan=prepare(e,a,ps,value,compatible=compatible,species=species,inheritance_moves=inheritance_moves,reason=reason)
        if any(row.get('id')==request_id for row in a.spec.get('eggs',[])):raise ValueError('egg producer request key already used')
        job=None
        if value['work_seconds']:
            job=J.run_fixed(e,a,ps,seconds=value['work_seconds'],source=value['source'],job_id='egg-creation:'+a.entity_id+':'+request_id,context={'reason':reason})
        if parent_snapshot(e,ps)!=plan['parent_facts']:raise ValueError('actual parental evidence changed during egg production')
        row=P.prepare_egg(e,a,{'id':request_id,'parents':[p.entity_id for p in ps],'produced_at':e.elapsed_seconds,
            'hatched':False,'source':value['source'],'species':plan['species'],'hatch_level':value['hatch']['level'],'inheritance_moves':plan['inheritance_moves']})
        row[CONTRACT]={'request':deepcopy(request),'intent':TX.request_fingerprint(request),'plan':plan,'plan_sha256':TX.request_fingerprint(plan),
                       'job_id':None if job is None else job['job_id']}
        a.spec.setdefault(RECORDS,{})[request_id]={'intent':TX.request_fingerprint(request),'egg_entity_id':row['entity_id']}
        P.validate_egg(e,a,row);a.spec.setdefault('eggs',[]).append(row)
        return deepcopy(row)
    return G.transition(engine,owner,apply,participants=parents)


def validate_binding(engine,row):
    import csv_item_capability_contracts as CAP
    CAP.egg_heat_seconds(engine,row)
    import physical_incubator as INCUBATOR
    INCUBATOR.validate_egg(engine,row)
    if BINDING in row:
        binding=row[BINDING]
        if type(binding) is not dict or type(binding.get('facts')) is not dict:raise ValueError('actual egg parentage record required')
        facts=binding['facts']
        if binding.get('sha256')!=TX.request_fingerprint(facts) or facts.get('source')!=row['source']:
            raise ValueError('egg parentage evidence changed')
        index=W.actor_index(engine);parents=facts.get('parents')
        if type(parents) is not list or [p.get('entity_id') for p in parents]!=list(row.get('parents',[])) or facts.get('created_by') not in index:
            raise ValueError('egg actual parent/provider identities changed')
        for parent in parents:
            actual=index.get(parent['entity_id'])
            if actual is None or actual.kind!='pokemon':raise ValueError('egg parent no longer resolves to an actual individual')
            C.integer(parent['level'],'historical parent level',1,100)
            if parent['species'] is not None:species_lookup(engine.r,parent['species'])
            if parent['known_moves'] is not None:moves(engine,parent['known_moves'])
    if CONTRACT not in row:return
    if BINDING not in row or type(row[CONTRACT]) is not dict:raise ValueError('actual declared egg parentage required')
    record=row[CONTRACT];request=record['request'];plan=record['plan'];value=declaration(request['declaration'])
    Q._selected(engine,value['source'])
    if record['intent']!=TX.request_fingerprint(request) or record['plan_sha256']!=TX.request_fingerprint(plan):raise ValueError('declared egg creation evidence changed')
    if row['source']!=value['source'] or plan['declaration']!=value or plan['provider_id']!=request['provider_id'] or plan['provider_id']!=row[BINDING]['facts']['created_by'] or request['parent_ids']!=list(row['parents']) or plan['parent_facts']!=row[BINDING]['facts']['parents'] or plan['compatible'] is not True:
        raise ValueError('egg provider/admission evidence changed')
    if row['species']!=plan['species'] or row['hatch_level']!=value['hatch']['level'] or row.get('inheritance_moves')!=plan['inheritance_moves']:
        raise ValueError('egg selected species, birth level or inheritance changed')
    provider=W.actor_index(engine).get(plan['provider_id'])
    if provider is None or provider.kind!='trainer':raise ValueError('actual original egg producer required')
    receipts=provider.spec.get(RECORDS)
    receipt=receipts.get(request['request_id']) if type(receipts) is dict else None
    if type(receipt) is not dict or receipt.get('intent')!=record['intent'] or receipt.get('egg_entity_id')!=row['entity_id']:raise ValueError('egg producer replay receipt changed or missing')
    if record['job_id'] is not None:
        import activity_jobs as J
        job=J._row(engine,record['job_id'])
        if job['status']!='complete' or job['owner'].entity_id!=plan['provider_id'] or [p.entity_id for p in job['participants']]!=request['parent_ids'] or job['progress_seconds']!=value['work_seconds'] or job['end_seconds']!=row['produced_at']:
            raise ValueError('egg lost its actual completed production work')


def details(engine,value):
    fields=('gender','nature','abilities','moves','special_appearance','inheritance_moves')
    Q._fields(value,fields+('baby_template',) if type(value) is dict and 'baby_template' in value else fields)
    if 'baby_template' in value:
        import baby_templates as BABY
        BABY.native_physical_choice(value['baby_template'])
    Q._text(value['gender']);import nature_state as NATURE
    if NATURE.describe(engine.r,value['nature']) is None:raise ValueError('known selected nature required')
    if type(value['special_appearance']) is not bool:raise ValueError('explicit special-appearance choice required')
    result=deepcopy(value);result['moves']=moves(engine,value['moves']);result['inheritance_moves']=moves(engine,value['inheritance_moves'])
    if len(result['moves'])>6 or type(value['abilities']) is not list or len(set(value['abilities']))!=len(value['abilities']):raise ValueError('distinct explicit birth abilities and supported move capacity required')
    for ability in value['abilities']:
        selected=engine.r.selection.resolve_name(ability,('ability/',));engine.r.selection.require_supported_version(selected)
    return result


def birth_abilities(engine,species,abilities):
    """Ordinary hatch grants one Basic Ability; a birth level is not a level-up event."""
    import growth_milestones as MILESTONES
    if type(abilities) is not list or len(abilities)!=1:
        raise ValueError('birth needs one species Basic Ability')
    selected=engine.r.selection.resolve_name(abilities[0],('ability/',))
    options=MILESTONES.ability_options(engine.r,{'species':species,'abilities':[]},'creation')
    for option in options:
        try:identity=engine.r.selection.resolve_name(option,('ability/',))
        except ValueError:continue
        if selected==identity:return
    raise ValueError('birth Ability is outside the child species Basic Ability candidates')


def birth_gender(engine,species,gender):
    from builder import species_lookup
    import species_metadata as METADATA
    if not isinstance(gender,str):raise ValueError('known birth gender required')
    canonical={'male':'male','female':'female','genderless':'genderless','수컷':'male','암컷':'female','무성':'genderless'}.get(gender)
    if canonical is None:raise ValueError('known birth gender required')
    distribution=METADATA.project(engine.r,species_lookup(engine.r,species))['sex_distribution']
    if distribution['status']=='genderless':
        if canonical!='genderless':raise ValueError('birth gender disagrees with the genderless species')
    elif distribution['status']=='known':
        if canonical=='genderless' or distribution[canonical]<=0:raise ValueError('birth gender is impossible for the species')
    return gender


def construct(engine,owner,egg,*,name,birth_level,tutor_points,selected,extra=None,inheritance_candidates=None):
    """Shared fresh stat/progression allocation and selected learning consumer."""
    import physical_incubator as INCUBATOR
    INCUBATOR.require_access(engine,owner,egg)
    from builder import build_pokemon
    from engine import Combatant
    import pokemon_progression as P,move_state as M
    Q._text(name);selected=details(engine,selected)
    birth_gender(engine,egg['species'],selected['gender'])
    inherited=selected['inheritance_moves']
    natural=M.current_natural_evidence(engine.r,{'species':egg['species'],'level':birth_level})
    if inheritance_candidates is not None and any(mid in inherited and not any(row['kind']=='level_up' for row in natural.get(mid,[])) for mid in selected['moves']):
        raise ValueError('inheritance list does not grant a birth Move; wait for its growth milestone')
    spec=build_pokemon(engine.r,egg['species'],birth_level,name=name,nature=selected['nature'],moves=selected['moves'],
        abilities=list(selected['abilities']),extra={'gender':selected['gender'],'trainer_id':owner.entity_id,'special_appearance':selected['special_appearance'],
        'inheritance_moves':inherited,'egg_entity_id':egg['entity_id'],'tutor_points':tutor_points,**deepcopy(extra or {})})
    spec[P.LEVEL_STATE].update(origin='hatch',egg_entity_id=egg['entity_id'])
    import growth_milestones as MILESTONES
    MILESTONES.offer_inheritance(engine.r,spec)
    import marsupial_state as MARSUPIAL
    if spec.get('species')!=MARSUPIAL.SPECIES and 'baby_template' in selected:
        raise ValueError('native Baby Template birth choice requires actual Kangaskhan')
    MARSUPIAL.prepare_birth(engine,egg,spec,physical_choice=selected.get('baby_template'))
    spec.pop('pos',None);spec['location']=deepcopy(owner.location)
    pokemon=Combatant(engine.r,spec)
    import baby_templates as BABY
    BABY.finish_native_body(pokemon)
    W.actor_index(engine,extra=[pokemon])
    return pokemon,selected


def commit_birth(engine,owner,egg,pokemon,selected,*,reason,placement):
    import pokemon_party as PARTY
    import physical_incubator as INCUBATOR
    INCUBATOR.finish_egg(engine,egg,actor_id=owner.entity_id,reason=reason)
    egg.update(hatched=True,pokemon_id=pokemon.entity_id,gm_hatch_details=deepcopy(selected),hatch_reason=reason,
               hatch_timing={'status':'hatched','reason':reason})
    __import__('researcher_fields').birth_quality(engine,egg,pokemon)
    PARTY.finish_hatch(engine,owner,pokemon,placement,egg)
    engine.gm.everyone.append(pokemon)
    if engine.everyone is not engine.gm.everyone:engine.everyone.append(pokemon)
    PARTY.project_current_owner(engine,pokemon)
    import marsupial_state as MARSUPIAL
    MARSUPIAL.finish_birth_placement(engine)
    lineage(engine,pokemon)
    import advanced_connection as CONNECTION
    CONNECTION.birth(engine,pokemon,egg,reason=reason)


def lineage(engine,pokemon):
    """Common view over the actual egg, also used by fossil births."""
    import pokemon_entities as P,materialization_origins as ORIGIN
    identity=pokemon.spec.get('egg_entity_id')
    entry=P.egg_index(engine).get(identity)
    if entry is None:raise ValueError('actual birth egg origin required')
    owner,egg=entry
    if not egg['hatched'] or egg.get('pokemon_id')!=pokemon.entity_id:
        raise ValueError('birth origin and actual Pokemon disagree')
    inputs=[egg['entity_id']]
    if pokemon.spec.get('fossil_entity_id'):
        fossil=P.egg_fossil(engine,egg)
        if fossil['entity_id']!=pokemon.spec['fossil_entity_id']:raise ValueError('actual fossil origin mismatch')
        inputs.insert(0,fossil['entity_id'])
    return ORIGIN.describe(kind='hatch',source=egg['source'],owner_id=owner.entity_id,
        inputs=inputs,outputs=[pokemon.entity_id],retained=[],
        native_ref={'kind':'egg','owner_id':owner.entity_id,'entity_id':egg['entity_id']})


def hatch_remaining(engine,egg,seconds=None):
    """Original declared wait minus real elapsed time and this egg's warmth.

    Unknown GM timing stays unknown. A legacy/display remaining field is never
    the authority for a declared egg's actual birth.
    """
    import csv_item_capability_contracts as CAP
    heat=CAP.egg_heat_seconds(engine,egg)
    import physical_incubator as INCUBATOR
    heat+=INCUBATOR.extra_seconds(engine,egg)
    if seconds is None:
        if CONTRACT in egg:seconds=egg[CONTRACT]['plan']['declaration']['hatch']['seconds']
        elif 'fossil_birth_policy' in egg:seconds=egg['fossil_birth_policy']['seconds']
    if seconds is None:return None
    C.integer(seconds,'declared hatch waiting time',0)
    produced=C.integer(egg.get('produced_at'),'actual egg production time',0,engine.elapsed_seconds)
    return max(0,seconds-(engine.elapsed_seconds-produced)-heat)


def hatch(engine,owner,egg_entity_id,*,name,ready=None,reason,choices):
    import state_grants as G,pokemon_entities as P,pokemon_party as PARTY,move_state as M
    W.require_actors(engine,owner);Q._text(reason)
    def apply(e,a):
        import pokemon_activities as A
        A._trainer(a);A._outside(e)
        entry=P.egg_index(e).get(egg_entity_id)
        if entry is None or entry[0] is not a or entry[1]['hatched'] or CONTRACT not in entry[1]:raise ValueError('actual unhatched declared egg owned by this trainer required')
        egg=entry[1];plan=egg[CONTRACT]['plan'];policy=plan['declaration']['hatch'];selected=details(e,choices)
        if policy['seconds'] is None:
            if type(ready) is not bool or not ready:raise ValueError('explicit observed hatch readiness required')
        elif hatch_remaining(e,egg,policy['seconds']):raise ValueError('declared hatch waiting time has not elapsed')
        if selected['inheritance_moves']!=plan['inheritance_moves']:raise ValueError('birth inheritance differs from actual egg selection')
        if policy['known_moves']=='natural_and_inherited':
            evidence=M.current_natural_evidence(e.r,{'species':egg['species'],'level':policy['level']})
            allowed={mid for mid,rows in evidence.items() if any(row['kind']=='level_up' for row in rows)}
            if any(mid not in allowed for mid in selected['moves']):raise ValueError('birth known move is outside natural level-up candidates')
        birth_abilities(e,egg['species'],selected['abilities'])
        pokemon,selected=construct(e,a,egg,name=name,birth_level=policy['level'],tutor_points=policy['tutor_points'],selected=selected,inheritance_candidates=plan['inheritance_candidates'])
        placement=PARTY.preflight_hatch(e,a,pokemon,egg)
        commit_birth(e,a,egg,pokemon,selected,reason=reason,placement=placement)
        return {'activity':'hatch_egg','egg_entity_id':egg['entity_id'],'pokemon':pokemon}
    return G.transition(engine,owner,apply)
