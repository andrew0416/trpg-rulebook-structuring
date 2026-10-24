"""Source-owned parameterized conditions, shared by Trainers and Pokemon.

The existing condition set is a presence projection. Move parameters, actual
actor references and deadlines live on one common effect record. Unresolved
legacy flags are preserved but cannot silently provide parameterized effects.
"""
import common_checks as C
import effect_instances as E
import combat_timing as CLOCK

KEY='condition_instances'
KIND='condition'
SUPPORTED=('사슬묶기','헤롱헤롱','억압','풀죽음')
REVIEWED_DEFINITIONS={'사슬묶기': 'b3a023b3d65b2bcb00570a040b3e95634d59859fe81112433a6b6d4673257954', '헤롱헤롱': '90a0faa870a14a3c3365b5e312984df002e2f2b940565b459e0ddfca38b34129', '억압': '772cfd2f2820dad822facc521035f4b1584477147eaa7814d15b89204a963e36'}

REVIEWED_DEFINITIONS['풀죽음']='de51fdd98ee786516e07d1062fa2bbce9bd2d3ba34b658c7b9ab6ca01b1d7925'

REVIEWED_DEFINITIONS['독']='3cc0d8a73ac312e176cdefff80e1388576710ba6c0b7aafe989f246c6a296daa'

import resolution_transaction as _FINGERPRINTS

def selected_definition(rules,condition):
    import json,hashlib
    definition=rules.units['condition/'+condition]['mech']['data']
    signature=_FINGERPRINTS.json_fingerprint(definition, sort_keys=True, compact=True, allow_nan=True)
    if signature!=REVIEWED_DEFINITIONS[condition]:raise ValueError('selected parameterized condition needs a reviewed source adapter')



def records(actor,condition=None):
    rows=actor.custom_conditions.get(KEY,[])
    if not isinstance(rows,list):raise ValueError('parameterized conditions must be a list')
    return [r for r in rows if condition is None or r.get('effect',{}).get('condition')==condition]


def legacy_sources(actor,condition):
    return [r for r in CLOCK.records(actor) if condition in r.get('statuses',[]) and
            (condition!='헤롱헤롱' or r.get('infatuation_source') is not None)]


def prepare(engine,actor,condition,*,parameters=None,applied_by=None):
    if condition not in SUPPORTED:raise ValueError('parameterized condition required')
    selected_definition(engine.r,condition)
    import world_entities as W
    if W.actor_index(engine).get(actor.entity_id) is not actor:raise ValueError('actual condition recipient required')
    params={} if parameters is None else dict(parameters)
    payload={'kind':KIND,'condition':condition}
    life={'boundary':'condition_cure_or_volatile_end'}
    if condition=='사슬묶기':
        if set(params)!={'move_id'} or not isinstance(params['move_id'],str):raise ValueError('Disabled requires one explicit Move identity')
        move=engine.r.move(params['move_id']);payload['move_id']=move['id']
    elif condition=='헤롱헤롱':
        if params:raise ValueError('Infatuation uses an actual applying actor, not a name parameter')
        import world_entities as W
        if applied_by is None or applied_by is actor or W.actor_index(engine).get(applied_by.entity_id) is not applied_by:raise ValueError('Infatuation requires its actual distinct beloved actor')
        payload['beloved_id']=applied_by.entity_id
        existing=beloved(actor)
        if existing and any(c is not applied_by for c in existing):raise ValueError('multiple different Infatuation sources require a composition ruling')
    elif condition=='풀죽음':
        if params:raise ValueError('ordinary Flinch has no custom magnitude or duration')
        CLOCK.current(engine)
        if engine.round_start_seconds is None:raise ValueError('Flinch requires an actual combat initiative boundary')
        if condition in actor.conditions and not records(actor,condition):raise ValueError('unresolved legacy Flinch needs an explicit cure before sourced replacement')
    else:
        if params:raise ValueError('ordinary Suppressed has no custom duration parameter')
        count=CLOCK.current(engine)
        if engine.round_start_seconds is None:raise ValueError('Suppressed requires an actual combat initiative boundary')
        life={'boundary':'initiative_count','round':engine.round_no+1,'count':count}
    return payload,life


def grant(engine,actor,condition,*,source=None,parameters=None,applied_by=None,force=False):
    payload,life=prepare(engine,actor,condition,parameters=parameters,applied_by=applied_by)
    source=source or 'condition/'+condition
    if not force and engine.immune_to(actor,condition):return False
    old=records(actor,condition)
    if condition not in ('억압','풀죽음') and any(r['effect']==payload for r in old):return False
    # A bare historical flag has no origin, target parameter or exact clock.
    if condition in actor.conditions and not old and not legacy_sources(actor,condition):
        raise ValueError('unresolved legacy condition must be explicitly cured before sourced replacement')
    import enduring_resilience as RESILIENCE
    if not force and RESILIENCE.prevent(engine,actor,condition=condition,source=source,attacker=applied_by):return False
    row=E.create(engine,actor,kind=KIND,source=source,payload=payload,
        capacity={'bucket':'condition:'+condition,'source':'condition/'+condition},lifetime=life,applied_by=applied_by)
    if condition=='헤롱헤롱':row['beloved']=applied_by
    if condition in ('억압','풀죽음'):row['applied_round']=engine.round_no;row['applied_count']=CLOCK.current(engine)
    CLOCK.on_status_apply(actor,condition)
    actor.custom_conditions.setdefault(KEY,[]).append(row)
    engine.time_actors([actor,*([applied_by] if applied_by is not None else [])])
    actor.conditions.add(condition)
    if condition=='풀죽음':
        # PTU February 2016 packet p2: subtract FIVE, not set initiative TO five.
        # One round of vulnerability has a different lifetime from the stack.
        CLOCK.install(engine,actor,{'source':source,'flinch_parent_id':row['id'],
            'statuses':['취약'],'count_deadline':(engine.round_no+1,CLOCK.current(engine))})
    engine.log('    '+actor.name+': '+condition+' sourced state '+row['id'],source)
    if not force and applied_by is not None and applied_by is not actor:
        import effects as FX
        FX.fire_event(engine,applied_by,{'event':'on_inflict_status','status':condition},actor)
    return True


def validate_record(actor,row,*,terminal=False):
    import eldritch_magic as ELDRITCH
    if ELDRITCH.owns(row):return ELDRITCH.validate_record(actor,row,terminal=terminal)
    import condition_variants as VARIANTS
    if VARIANTS.owns(row):return VARIANTS.validate_record(actor,row,terminal=terminal)
    if row.get('effect',{}).get('kind')=='custom_condition':
        import custom_condition_effects as CUSTOM
        return CUSTOM.validate_record(actor,row,terminal=terminal)
    E.validate(row,actor=actor,terminal=terminal)
    if row[E.KEY]['kind']!=KIND:raise ValueError('condition effect family mismatch')
    effect=row['effect'];condition=effect.get('condition')
    if condition not in (*SUPPORTED,'독') or effect.get('kind')!=KIND:raise ValueError('supported condition payload required')
    selected_definition(actor.r,condition)
    expected={'kind','condition'}|({'move_id'} if condition=='사슬묶기' else {'beloved_id'} if condition=='헤롱헤롱' else {'variant'} if condition=='독' else set())
    if set(effect)!=expected:raise ValueError('unexpected condition parameter')
    if row[E.KEY]['capacity']!={'bucket':'condition:'+condition,'source':'condition/'+condition}:raise ValueError('condition capacity authority mismatch')
    if condition=='사슬묶기':
        if actor.r.move(effect['move_id'])['id']!=effect['move_id']:raise ValueError('canonical disabled Move required')
    if condition=='헤롱헤롱':
        person=row.get('beloved')
        if person is None or getattr(person,'entity_id',None)!=effect['beloved_id'] or person is actor:raise ValueError('Infatuation reference and identity disagree')
        if row[E.KEY].get('applied_by_actor_id')!=effect['beloved_id']:raise ValueError('Infatuation creator and beloved disagree')
    life=row[E.KEY]['lifetime']
    if condition=='풀죽음':
        C.integer(row.get('applied_round'),'Flinch application round',1)
        C.integer(row.get('applied_count'),'Flinch application count')
    if condition=='억압':
        if set(life)!={'boundary','round','count'} or life['boundary']!='initiative_count':raise ValueError('ordinary Suppressed requires its exact count deadline')
        born=C.integer(row.get('applied_round'),'Suppressed application round',1)
        count=C.integer(row.get('applied_count'),'Suppressed application count')
        if life['round']!=born+1 or type(life['round']) is not int or life['count']!=count or type(life['count']) is not int:raise ValueError('Suppressed must end exactly one round after its own application')
    elif condition=='독':
        if effect.get('variant')!='맹독' or life!={'boundary':'persistent_condition_cure'}:raise ValueError('Badly Poisoned variant lifetime mismatch')
        n=C.integer(row.get('completed_rounds'),'poison completed rounds',0)
        history=row.get('round_history')
        if not isinstance(history,list) or len(history)!=n:raise ValueError('poison round count must match its actual round history')
        previous=0
        for number in history:previous=C.integer(number,'poison actual completed round',previous+1)
        if row.get('last_completed_round')!=(history[-1] if history else None):raise ValueError('poison last round and history disagree')
    elif life!={'boundary':'condition_cure_or_volatile_end'}:raise ValueError('condition lifetime mismatch')
    if not terminal:
        if condition not in actor.conditions:raise ValueError('live condition instance requires its presence projection')
        peers=records(actor,condition)
        if condition=='사슬묶기' and sum(x['effect']==effect for x in peers)!=1:raise ValueError('Disabled instances must specify distinct Moves')
        if condition in ('헤롱헤롱','독') and len(peers)!=1:raise ValueError('multiple Infatuation sources need a composition ruling')
    if terminal and row[E.KEY]['end_event'].get('kind') not in ('condition_cure','initiative_count','round_end'):raise ValueError('condition ending event required')
    return True


def validate_world(engine,index):
    import eldritch_magic as ELDRITCH
    ELDRITCH.validate_world(engine,index)
    import condition_variants as VARIANTS
    VARIANTS.validate_world(engine,index)
    cursor=getattr(engine,'_initiative_cursor',None)
    def validate_flinch_application(row):
        born=C.integer(row.get('applied_round'),'Flinch application round',1)
        count=C.integer(row.get('applied_count'),'Flinch application count')
        # Initiative counts descend: a lower count in this round has not occurred.
        if born>engine.round_no or (born==engine.round_no and cursor and
            cursor['round']==born and count<cursor['count']):
            raise ValueError('Flinch application cannot be in the future')
        return born,count
    for actor in index.values():
        # Derivative Vulnerable records outlive their initiative source. Resolve
        # provenance through the common authoritative live/history enumeration.
        canonical=list(E.records(actor))
        flinches={}
        for row,phase in canonical:
            if row[E.KEY]['kind']!=KIND:continue
            validate_record(actor,row,terminal=phase=='terminal')
            if row['effect']['condition']=='풀죽음':
                flinches[row['id']]=(row,phase)
                if phase!='terminal':validate_flinch_application(row)
        for timed in CLOCK.records(actor):
            if 'flinch_parent_id' not in timed:continue
            # Only CLOCK.install's native envelope is authoritative here. Extra
            # owner-turn, scene, or payload fields could override the full round.
            if set(timed)!={'source','flinch_parent_id','statuses','count_deadline','owned_statuses','installing'}:
                raise ValueError('unexpected Flinch derivative timing or effect field')
            owned=timed['owned_statuses']
            if type(owned) is not set or not owned<={'취약'} or not owned<=actor.conditions:
                raise ValueError('Flinch derivative owns only its present Vulnerable status')
            if timed['installing'] is not False:
                raise ValueError('Flinch derivative installation must be complete')
            parent_id=E.text(timed['flinch_parent_id'],'Flinch parent identity')
            entry=flinches.get(parent_id)
            if entry is None:raise ValueError('Flinch derivative requires its canonical source instance')
            parent,_=entry
            born,count=validate_flinch_application(parent)
            deadline=(born+1,count)
            actual=timed.get('count_deadline')
            if (not isinstance(actual,(tuple,list)) or len(actual)!=2 or
                type(actual[0]) is not int or type(actual[1]) is not int or
                tuple(actual)!=deadline or timed.get('source')!=parent['source'] or
                timed.get('statuses')!=['취약']):
                raise ValueError('Flinch derivative deadline or source changed')
            if engine.round_no>deadline[0] or (engine.round_no==deadline[0] and
                ((cursor and cursor['round']==engine.round_no and cursor['count']<=deadline[1]) or
                 (engine.encounter_active and engine.round_start_seconds is None))):
                raise ValueError('expired Flinch Vulnerable child remains active')
        for row,phase in canonical:
            if row[E.KEY]['kind']!=KIND:continue
            terminal=phase=='terminal'
            if 'beloved' in row and index.get(row['effect']['beloved_id']) is not row['beloved']:raise ValueError('Infatuation must reference the actual world actor')
            if row['effect']['condition']=='독' and row.get('last_completed_round') is not None and row['last_completed_round']>engine.round_no:raise ValueError('poison round counter is in the future')
            life=row[E.KEY]['lifetime']
            if life['boundary']=='initiative_count':
                if row['applied_round']>engine.round_no:raise ValueError('condition application cannot be in a future round')
                cursor=getattr(engine,'_initiative_cursor',None)
                if not terminal and (not engine.encounter_active or life['round']<engine.round_no or (cursor and cursor['round']==life['round'] and cursor['count']<=life['count'])):raise ValueError('expired Suppressed instance remains active')
                if terminal:
                    event=row[E.KEY]['end_event'];kind=event['kind']
                    if kind in ('initiative_count','round_end'):
                        ended=C.integer(event.get('round'),'condition ending round',life['round'])
                        if kind=='initiative_count' and ended==life['round'] and C.integer(event.get('count'),'condition ending count')>life['count']:raise ValueError('condition expired before its count deadline')
    return True


def end(engine,actor,row,event,*,project=True):
    live=actor.custom_conditions.get(KEY,[])
    if row not in live:return
    import eldritch_magic as ELDRITCH
    import condition_variants as VARIANTS
    if ELDRITCH.owns(row):ELDRITCH.archive(engine,actor,row,event)
    elif VARIANTS.owns(row):VARIANTS.archive(engine,actor,row,event)
    else:E.archive(engine,actor,row,state='expired',event=event)
    live.remove(row)
    if not live:actor.custom_conditions.pop(KEY,None)
    condition=row['effect']['condition']
    if project and not records(actor,condition) and not legacy_sources(actor,condition):engine.cure_status(actor,condition)


def cure(engine,actor,condition):
    for row in list(records(actor,condition)):end(engine,actor,row,{'kind':'condition_cure','condition':condition},project=False)


def boundary(engine,*,count=None,round_end=False):
    for actor in getattr(engine,'_time_actors',[]):
        for row in list(records(actor,'억압')):
            life=row[E.KEY]['lifetime']
            if engine.round_no>life['round'] or engine.round_no==life['round'] and (round_end or count is not None and count<=life['count']):
                end(engine,actor,row,{'kind':'round_end' if round_end else 'initiative_count','round':engine.round_no,'count':count})


def beloved(actor):
    people=[r['beloved'] for r in records(actor,'헤롱헤롱')]
    people.extend(r['infatuation_source'] for r in legacy_sources(actor,'헤롱헤롱'))
    return people


def move_allowed(engine,actor,move):
    conditions=__import__('blessing_effects').effective_conditions(actor)
    if '사슬묶기' in conditions:
        locks=records(actor,'사슬묶기')
        if not locks:return False,'사슬묶기의 대상 기술 확인 필요'
        if any(r['effect']['move_id']==move['id'] for r in locks):return False,'사슬묶기된 기술'
    if '억압' in conditions and not getattr(actor,'_duelist_ignoring',False):
        import frequency as F
        if not records(actor,'억압'):
            import gmax_moves as GMAX
            if GMAX.encounter_suppressed(actor):return GMAX.move_allowed(engine,actor,move)
            import fashionista as FASHIONISTA
            if FASHIONISTA.encounter_suppressed(actor):return FASHIONISTA.move_allowed(engine,actor,move)
            return False,'억압의 출처와 종료 시점 확인 필요'
        if F.move_frequency(engine,move['id'],actor)[0]!='at_will':return False,'억압 중 임의 빈도 기술만 사용 가능'
    return True,''


def native_parameters(engine,actor,target,condition):
    if condition=='사슬묶기':return {'move_id':target.last_move}
    return None


def preflight_move(engine,actor,target,mm):
    if '헤롱헤롱' in __import__('blessing_effects').effective_conditions(actor) and not getattr(actor,'_duelist_ignoring',False) and not beloved(actor):raise ValueError('Infatuation needs its actual beloved before action cost or rolls')
    def contains_flinch(value):
        if isinstance(value,list):return any(contains_flinch(x) for x in value)
        if not isinstance(value,dict):return False
        return (value.get('type')=='apply_status' and value.get('status')=='풀죽음') or any(contains_flinch(v) for v in value.values())
    if contains_flinch(mm.get('effects_exec',[])):
        prepare(engine,target,'풀죽음',applied_by=actor)
    condition=mm.get('apply_status')
    if condition in SUPPORTED:
        prepare(engine,target,condition,parameters=native_parameters(engine,actor,target,condition),applied_by=actor)


def grant_bad_poison(engine,actor,*,source=None,applied_by=None):
    selected_definition(engine.r,'독')
    if '독' not in actor.conditions:raise ValueError('Badly Poisoned requires the actual poison condition')
    if records(actor,'독'):raise ValueError('one poison variant instance required')
    row=E.create(engine,actor,kind=KIND,source=source or 'condition/독',
        payload={'kind':KIND,'condition':'독','variant':'맹독'},
        capacity={'bucket':'condition:독','source':'condition/독'},
        lifetime={'boundary':'persistent_condition_cure'},applied_by=applied_by)
    row.update(completed_rounds=0,last_completed_round=None,round_history=[])
    actor.custom_conditions.setdefault(KEY,[]).append(row)
    engine.time_actors([actor,*([applied_by] if applied_by is not None else [])])
    validate_record(actor,row)
    return row


def flinch_penalty(actor):
    """Source-owned additive stacks, never inferred from an untracked old flag."""
    rows=records(actor,'풀죽음')
    for row in rows:validate_record(actor,row)
    return -5*len(rows)

