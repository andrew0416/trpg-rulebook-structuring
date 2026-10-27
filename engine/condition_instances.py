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
FLINCH_TEXT={'file':'input/ch07-combat.md','sha256':'57abb79c4f70c64246cd7927bffe2377e951bdc32dfa4c9a5c14b4ad97618c18'}

REVIEWED_DEFINITIONS['독']='3cc0d8a73ac312e176cdefff80e1388576710ba6c0b7aafe989f246c6a296daa'
REVIEWED_DEFINITIONS['마비']='fac3ee002d5cd74477a195a75a3813f26e2e96b0c2849a996d288435cacc2495'
CSV_VERSION='csv-core-1.05'
CSV_REVIEWED={'마비':'2f38fa2d46648e52f7db15f71e18f107b748c471a2155d9436c19beb8f6b57b0', '풀죽음':'d5bae86ea96de599398030ceae79861d0351b24b1446247ddb609f04b7c5cadf', '헤롱헤롱':'8421ee5cae23d2e83b8014c1b922266e5d19e177f643aae75b13e86f5fca3a07', '억압':'e20ea16374ee288007bd759b86a033ca28d2c3cd40a3ed55eb8edbae362b1b5f'}

import resolution_transaction as _FINGERPRINTS

def selected_definition(rules,condition):
    import json,hashlib
    definition=dict(rules.units['condition/'+condition]['mech']['data'])
    if CSV_VERSION in definition:
        edition=definition.pop(CSV_VERSION)
        if _FINGERPRINTS.json_fingerprint(edition,sort_keys=True,compact=True,allow_nan=True)!=CSV_REVIEWED.get(condition):raise ValueError('unreviewed CSV condition edition')
    signature=_FINGERPRINTS.json_fingerprint(definition, sort_keys=True, compact=True, allow_nan=True)
    if signature!=REVIEWED_DEFINITIONS[condition]:raise ValueError('selected parameterized condition needs a reviewed source adapter')



def csv_edition(rules,condition):
    if condition not in CSV_REVIEWED or rules.mech('condition/'+condition).get('_version')!=CSV_VERSION:return False
    selected_definition(rules,condition)
    edition=rules.units['condition/'+condition]['mech']['data'][CSV_VERSION]
    if rules.condition_effects(condition)!=edition['effects']:raise ValueError('selected CSV condition effects changed')
    from source_context import verified_source
    verified_source(rules,edition['authority'],label='CSV Core 1.05 '+condition)
    return True


def _noncombat_flinch_source(rules):
    # This is the reviewed Feb2016 immediate -5 stack, not Core247's old
    # next-turn-that-round rule. One round is ten actual seconds (ch07:25).
    selected_definition(rules,'풀죽음')
    from source_context import verified_source
    verified_source(rules,FLINCH_TEXT,label='noncombat February2016 Flinch')


def _flinch_vulnerability():return {'type':'apply_status','status':'취약','duration':{'seconds':10}}


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
        if csv_edition(engine.r,condition) and engine.round_start_seconds is None:raise ValueError('CSV Flinch requires its actual application round')
        if engine.encounter_active or engine.round_start_seconds is not None:
            CLOCK.current(engine)
            if engine.round_start_seconds is None:raise ValueError('Flinch requires an actual combat initiative boundary')
        else:_noncombat_flinch_source(engine.r)
        if condition in actor.conditions and not records(actor,condition):raise ValueError('unresolved legacy Flinch needs an explicit cure before sourced replacement')
    else:
        if params:raise ValueError('ordinary Suppressed has no custom duration parameter')
        if not csv_edition(engine.r,condition):
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
    outside_flinch=condition=='풀죽음' and not engine.encounter_active and engine.round_start_seconds is None
    if (condition=='풀죽음' or condition=='억압' and not csv_edition(engine.r,condition)) and not outside_flinch:row['applied_round']=engine.round_no;row['applied_count']=CLOCK.current(engine)
    CLOCK.on_status_apply(actor,condition)
    actor.custom_conditions.setdefault(KEY,[]).append(row)
    engine.time_actors([actor,*([applied_by] if applied_by is not None else [])])
    actor.conditions.add(condition)
    if condition=='풀죽음' and not csv_edition(engine.r,condition):
        # PTU February 2016 packet p2: subtract FIVE, not set initiative TO five.
        # One round of vulnerability has a different lifetime from the stack.
        if outside_flinch:
            import effect_contracts as CONTRACTS,effect_lifetimes as LIFE,frequency as F
            effect=_flinch_vulnerability()
            occurrence,receipt=CONTRACTS.issue_receipt(engine,source,actor,actor,effect,0)
            row['noncombat_flinch']={'definition_sha256':REVIEWED_DEFINITIONS['풀죽음'],
                'text':dict(FLINCH_TEXT),'at':engine.elapsed_seconds,'scene':F.state(actor)['scene'],
                'vulnerability_occurrence':occurrence}
            LIFE.install(engine,actor,actor,effect,source,receipt,occurrence)
            derivative=next(r for r in CLOCK.records(actor) if r.get('effect_occurrence')==occurrence)
            derivative['flinch_parent_id']=row['id']
            CONTRACTS.finish(engine,receipt,'completed',True)
        else:
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
        saved=row.get('csv_start_save')
        if saved is not None:
            if not csv_edition(actor.r,condition) or set(saved)!={'turn','check','value','closed','automatic_failure'} or type(saved['closed'])is not bool or type(saved['automatic_failure'])is not bool:raise ValueError('actual CSV Infatuation start save required')
            C.integer(saved['turn'],'Infatuation actual turn',1)
            check=saved['check']
            if saved['automatic_failure']:
                if check is not None or saved['value']!=0:raise ValueError('automatic Infatuation failure cannot invent a save roll')
            elif saved['value']!=C.integer(check['natural'],'Infatuation save face',1,20)+19-C.integer(check['dc'],'Infatuation save DC'):raise ValueError('Infatuation band and actual save disagree')
    life=row[E.KEY]['lifetime']
    if condition=='풀죽음':
        if 'noncombat_flinch' in row:
            _noncombat_flinch_source(actor.r);meta=row['noncombat_flinch']
            if set(meta)!={'definition_sha256','text','at','scene','vulnerability_occurrence'} or meta['definition_sha256']!=REVIEWED_DEFINITIONS['풀죽음'] or meta['text']!=FLINCH_TEXT:raise ValueError('exact selected noncombat Flinch source required')
            if 'applied_round' in row or 'applied_count' in row or C.integer(meta['at'],'noncombat Flinch actual time',0)!=row['at']:raise ValueError('noncombat Flinch cannot invent a round or count')
            C.integer(meta['scene'],'noncombat Flinch actual scene',0);E.text(meta['vulnerability_occurrence'],'native Flinch derivative occurrence')
        else:
            C.integer(row.get('applied_round'),'Flinch application round',1)
            C.integer(row.get('applied_count'),'Flinch application count')
            if 'csv_blocked_turn' in row:
                if not csv_edition(actor.r,condition):raise ValueError('ordinary Flinch cannot acquire CSV action loss')
                C.integer(row['csv_blocked_turn'],'Flinch actual blocked turn',1)
                if type(row.get('csv_blocked_turn_closed',False))is not bool:raise ValueError('Flinch actual turn closure required')
    if condition=='억압':
        if csv_edition(actor.r,condition):
            if life!={'boundary':'condition_cure_or_volatile_end'} or 'applied_round' in row or 'applied_count' in row:raise ValueError('CSV Suppressed has ordinary volatile lifetime, not a fixed round')
        else:
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
    __import__('defense_curl').validate_world(engine,index)
    import eldritch_magic as ELDRITCH
    ELDRITCH.validate_world(engine,index)
    import condition_variants as VARIANTS
    VARIANTS.validate_world(engine,index)
    cursor=getattr(engine,'_initiative_cursor',None)
    def validate_flinch_application(row):
        if 'noncombat_flinch' in row:
            import frequency as F
            meta=row['noncombat_flinch'];holder=index[row[E.KEY]['holder_id']]
            if meta['at']>engine.elapsed_seconds or meta['scene']>F.state(holder)['scene']:raise ValueError('noncombat Flinch application cannot be in the future')
            producers=[p for p in getattr(engine,'_effect_dispatch_receipts',{}).values() if p['occurrence']==meta['vulnerability_occurrence']]
            if len(producers)!=1:raise ValueError('actual noncombat Flinch derivative producer required')
            producer=producers[0]
            if producer['actor'] is not holder or producer['target'] is not holder or producer['source_id']!=row['source'] or producer['effect']!=_flinch_vulnerability() or producer['status']!='completed':raise ValueError('noncombat Flinch derivative target or source changed')
            contract=producer.get('lifetime_contracts',{}).get(holder.entity_id,{})
            policy=contract.get('policy',{})
            if policy.get('started_at')!=meta['at'] or policy.get('end_at')!=meta['at']+10 or policy.get('declaration')!={'duration':{'seconds':10}} or contract.get('contribution')!={'statuses':['취약']}:raise ValueError('noncombat Flinch requires its immediate exact ten-second derivative')
            return None
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
                if phase!='terminal' or 'noncombat_flinch' in row:validate_flinch_application(row)
        for timed in CLOCK.records(actor):
            if 'flinch_parent_id' not in timed:continue
            parent_id=E.text(timed['flinch_parent_id'],'Flinch parent identity')
            entry=flinches.get(parent_id)
            if entry is None:raise ValueError('Flinch derivative requires its canonical source instance')
            parent,_=entry
            if 'noncombat_flinch' in parent:
                import effect_lifetime_policy as LIFE
                validate_flinch_application(parent)
                expected={'source','flinch_parent_id','statuses','owned_statuses','installing','effect_contract','timing_text',LIFE.KEY,'lifetime_actor','lifetime_target','lifetime_deliveries','effect_occurrence','effect_receipt'}
                if set(timed)!=expected or timed['effect_occurrence']!=parent['noncombat_flinch']['vulnerability_occurrence'] or timed['source']!=parent['source'] or timed['statuses']!=['취약'] or timed['lifetime_actor'] is not actor or timed['lifetime_target'] is not actor:raise ValueError('noncombat Flinch derivative lost its exact native parent and target')
                if timed['installing'] is not False or type(timed['owned_statuses'])is not set or not timed['owned_statuses']<={'취약'} or not timed['owned_statuses']<=actor.conditions:raise ValueError('noncombat Flinch owns only its present Vulnerable status')
                if engine.elapsed_seconds>=parent['at']+10:raise ValueError('expired noncombat Flinch derivative remains active')
                continue
            # Only CLOCK.install's native envelope is authoritative here. Extra
            # owner-turn, scene, or payload fields could override the full round.
            if set(timed)!={'source','flinch_parent_id','statuses','count_deadline','owned_statuses','installing'}:
                raise ValueError('unexpected Flinch derivative timing or effect field')
            owned=timed['owned_statuses']
            if type(owned) is not set or not owned<={'취약'} or not owned<=actor.conditions:
                raise ValueError('Flinch derivative owns only its present Vulnerable status')
            if timed['installing'] is not False:
                raise ValueError('Flinch derivative installation must be complete')
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
        if round_end and csv_edition(engine.r,'풀죽음'):
            for row in list(records(actor,'풀죽음')):end(engine,actor,row,{'kind':'round_end','round':engine.round_no})
        for row in list(records(actor,'억압')):
            if csv_edition(engine.r,'억압'):continue
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
    if '억압' in conditions and not getattr(actor,'_duelist_ignoring',False) and not csv_edition(engine.r,'억압'):
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
    require_target(actor,target)
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
    if csv_edition(actor.r,'풀죽음'):return 0
    return -5*len(rows)


def start_turn(engine,actor):
    serial=actor.custom_conditions['combat_turn_serial']
    import boss_transitions as BOSS
    if csv_edition(engine.r,'풀죽음') and BOSS.condition_applies_this_turn(actor,'풀죽음'):
        for row in records(actor,'풀죽음'):
            if row['applied_round']==engine.round_no:row.setdefault('csv_blocked_turn',serial)
    if not csv_edition(engine.r,'헤롱헤롱') or '잠듦' in actor.conditions or getattr(actor,'_duelist_ignoring',False) or not BOSS.condition_applies_this_turn(actor,'헤롱헤롱'):return
    import condition_recovery as RECOVERY,combat_maneuvers as MANEUVERS
    for row in list(records(actor,'헤롱헤롱')):
        disposition=MANEUVERS.save_disposition(actor,'헤롱헤롱')
        if disposition=='forbidden':continue
        check=None if disposition=='automatic_failure' else RECOVERY.saving_check(engine,actor,'헤롱헤롱',19)
        value=0 if disposition=='automatic_failure' else check['natural']+19-check['dc']
        row['csv_start_save']={'turn':serial,'check':check,'value':value,'closed':False,'automatic_failure':disposition=='automatic_failure'}
        if value>=19:engine.cure_status(actor,'헤롱헤롱')


def flinch_blocks(actor):
    return '풀죽음' in __import__('blessing_effects').effective_conditions(actor) and not getattr(actor,'_duelist_ignoring',False) and csv_edition(actor.r,'풀죽음') and any(not row.get('csv_blocked_turn_closed',False) and row.get('csv_blocked_turn')==actor.custom_conditions.get('combat_turn_serial',0) for row in records(actor,'풀죽음'))


def close_turn(actor):
    limit=getattr(actor,'_turn_action_limit',None)
    if limit and limit.get('source')=='condition/마비' and csv_edition(actor.r,'마비'):
        owned=next(effect for effect in actor.r.condition_effects('마비') if effect.get('type')=='action_limit')
        if limit==owned:actor._turn_action_limit=None
    for row in records(actor,'풀죽음'):
        if 'csv_blocked_turn' in row:row['csv_blocked_turn_closed']=True
    for row in records(actor,'헤롱헤롱'):
        if 'csv_start_save' in row:row['csv_start_save']['closed']=True


def require_target(actor,target):
    if getattr(actor,'_duelist_ignoring',False) or '헤롱헤롱' not in __import__('blessing_effects').effective_conditions(actor) or not csv_edition(actor.r,'헤롱헤롱'):return
    for row in records(actor,'헤롱헤롱'):
        validate_record(actor,row)
        saved=row.get('csv_start_save')
        if saved and not saved['closed'] and saved['turn']==actor.custom_conditions.get('combat_turn_serial',0) and saved['value']<=10 and row['beloved'] is target:
            raise ValueError('CSV Infatuation forbids targeting the actual beloved with a Move or attack')


def csv_suppressed(actor):
    return actor is not None and not getattr(actor,'_duelist_ignoring',False) and '억압' in __import__('blessing_effects').effective_conditions(actor) and csv_edition(actor.r,'억압')

