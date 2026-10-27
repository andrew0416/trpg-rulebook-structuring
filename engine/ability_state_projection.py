"""Source-owned projections for abilities whose current state changes by form or fact.

The policy fixes every source row and every projected rule identity.  Runtime
records retain the observed fact/choice, own all additive contributions through
``state_grants``, and restore only those contributions at their authored end.
"""
import arithmetic_policy as NUMERIC
from copy import deepcopy
from pathlib import Path
import hashlib,json

import common_checks as C
import state_grants as G

KEY='ability_state_projection'
PENDING='ability_state_projection_pending'
PREFIX='ability-state:'
LEAFY='ability/잎사귀망토'
DESIGNER='ability/디자이너'
LEAFY_HISTORY='leafy_cloak_projection_history'
WEATHER_TYPES={'sunny':'불꽃','rain':'물','hail':'얼음','snow':'얼음','sandstorm':'바위','none':'노말'}


def install(rules):
    data=json.loads((Path(rules.root)/'data/ability-state-projection-policy.json').read_text(encoding='utf-8'))
    if data.get('schema_version')!=1 or len(data.get('sources',{}))!=15:
        raise ValueError('reviewed fifteen-source ability-state projection policy required')
    for file,digest in data['source_files'].items():
        if hashlib.sha256((Path(rules.root)/file).read_bytes()).hexdigest()!=digest:
            raise ValueError('ability-state projection source changed: '+file)
    for source,row in data['sources'].items():
        if row.get('source')!=source or not row.get('row_id') or not row.get('source_row_sha256'):
            raise ValueError('exact ability-state source provenance required')
        if row.get('kind') not in ('choice','weather','turn_choice','hp_form','move_form','creation_slots','season','scene_form','cloak','field','form_grants'):
            raise ValueError('unsupported ability-state projection kind')
        if not isinstance(row.get('choices'),dict) or not row['choices']:
            raise ValueError('reviewed ability-state choices required')
    targets=set(data['sources'])
    leafy=_leafy_policy(rules)
    for row in leafy['definitions'].values():
        for payload in row['choices'].values():targets.update(payload['abilities'])
    for row in data['sources'].values():
        for payload in row['choices'].values():
            targets.update(payload.get('abilities',[]))
            for values in payload.get('ability_pools',{}).values():targets.update(values)
    catalog={row['id']:row for row in json.loads((Path(rules.root)/'output/entities/abilities.json').read_text(encoding='utf-8')) if row['id'] in targets}
    if set(catalog)!=targets:raise ValueError('projected ability identity is missing from the selected catalog')
    rules.ability_state_projection_policy=data
    rules.ability_state_projection_targets=catalog


def definition(rules,source):
    row=getattr(rules,'ability_state_projection_policy',{}).get('sources',{}).get(source)
    if row is not None and rules._selected_rule(source)!=source:
        raise ValueError('ability-state source selection changed')
    return row


def registration(rules,value):
    reg=ability_registration(rules,value)
    return reg['source_id'] if reg and definition(rules,reg['source_id']) is not None else None


def ability_registration(rules,value):
    rows=getattr(rules,'ability_state_projection_targets',{})
    candidates=[uid for uid,row in rows.items() if value==uid or value in (row.get('name'),row.get('eng'))]
    if not candidates:return None
    if value in rows:uid=value
    else:
        from ruleset import ExcludedRuleSelection,UnresolvedRuleSelection
        selected=set()
        for candidate in candidates:
            try:selected.add(rules.selection.resolve(candidate))
            except ExcludedRuleSelection:continue
        # A catalog alias does not claim an excluded or replaced source.
        if not selected:return None
        if len(selected)!=1:raise UnresolvedRuleSelection(value,sorted(selected))
        uid=selected.pop()
        if uid not in rows:return None
    if rules._selected_rule(uid)!=uid:raise ValueError('projected ability target is not selected')
    row=rows[uid]
    return {'name':row['name'],'source_id':uid,'equivalent_source_ids':[uid]}


def _text(value,label):
    if not isinstance(value,str) or not value.strip():raise ValueError(label+' required')
    return value


def _records(actor,create=False):
    rows=actor.spec.get(KEY)
    if rows is None:
        if not create:return {}
        rows={};actor.spec[KEY]=rows
    if not isinstance(rows,dict):raise ValueError('ability-state projection ledger required')
    return rows


def _sid(source):return PREFIX+source


def _owned(actor,source):
    import ability_transitions as A
    return A.active(actor,source)


def handled(rules,value):return registration(rules,value) is not None


def register(engine,actor,value):
    """Registration route: execution waits for an actual fact/choice producer."""
    return handled(engine.r,value)


def choose(engine,actor,source,choice,*,observation=None,reason):
    source=registration(engine.r,source)
    if source is None:raise ValueError('reviewed ability-state source required')
    _text(reason,'ability-state choice reason')
    if source==LEAFY:
        request=_leafy_choice(engine,actor,choice,observation,reason)
        actor.spec.setdefault(PENDING,{})[source]=request
        return deepcopy(request)
    if choice not in definition(engine.r,source)['choices']:raise ValueError('choice is not declared for this ability')
    request={'source':source,'choice':choice,'observation':deepcopy(observation),'reason':reason}
    actor.spec.setdefault(PENDING,{})[source]=request
    return deepcopy(request)


def _leafy_policy(rules):
    from source_context import verified_source
    value=json.loads((Path(rules.root)/'data/leafy-cloak-source-policy.json').read_text(encoding='utf-8'))
    if value.get('schema_version')!=1 or value.get('source')!=LEAFY:
        raise ValueError('reviewed Leafy Cloak source definitions required')
    verified_source(rules,value['source_reference'],label='Leafy Cloak')
    verified_source(rules,value['english_reference'],label='Leafy Cloak Designer timing',source_root='source-audit')
    return value


def _leafy_document(value):
    return {'schema':1,'id':'native/leafy-cloak-designer','variants':[{
        'rule_id':LEAFY,'source':value['source_reference'],
        'values':{'variant':{'$input':'source_text'},'definitions':value['definitions']},
        'inputs':{'source_text':{'type':'string','authority':'gm','decision_kind':'source_conflict',
            'choices':list(value['definitions']),
            'question':'Leafy Cloak: complete English Overcoat, or Korean Soundproof candidates with English Designer timing clarification?'}}}]}


def leafy_source_choices(actor):
    """The two complete executable definitions; the hybrid label is explicit."""
    import source_policy as POLICY
    value=_leafy_policy(actor.r)
    return dict(POLICY.resolve(actor.r,_leafy_document(value)),
                default=value['default'],definitions=deepcopy(value['definitions']))


def _leafy_choice(engine,actor,choice,observation,reason):
    if actor.kind!='pokemon' or not _owned(actor,LEAFY) or not _owned(actor,DESIGNER):
        raise ValueError('Leafy Cloak requires its actual active user and Designer')
    if observation is not None and (not isinstance(observation,dict) or set(observation)!={'source_choice'}):
        raise ValueError('Leafy Cloak observation accepts only its scoped source choice')
    source_choice=None if observation is None else observation['source_choice']
    import source_policy as POLICY
    value=_leafy_policy(engine.r)
    result=POLICY.resolve(engine.r,_leafy_document(value),
        decisions={} if source_choice is None else {'source_text':source_choice})
    variant=value['default'] if source_choice is None else result['values']['variant']
    if choice not in value['definitions'][variant]['choices']:
        raise ValueError('Leafy Cloak pair is outside the selected complete definition')
    payload=value['definitions'][variant]['choices'][choice];_validate_targets(engine,payload)
    return {'source':LEAFY,'choice':choice,'observation':deepcopy(observation),'reason':reason,
        'leafy_source':{'variant':variant,'choice':deepcopy(source_choice),
            'scope':deepcopy(result['decision_scope']),'binding':deepcopy(result['source_policy_binding'])}}


def prepare_designer(engine,actor):
    """Validate the next real Designer choice before its work/action payment."""
    if not _owned(actor,LEAFY):return None
    request=actor.spec.get(PENDING,{}).get(LEAFY)
    if request is None:raise ValueError('Designer with Leafy Cloak requires a pair choice')
    _text(request.get('reason'),'Leafy Cloak pair reason')
    current=_leafy_choice(engine,actor,request['choice'],request['observation'],request['reason'])
    if current!=request:raise ValueError('Leafy Cloak source choice changed before Designer')
    return current


def complete_designer(engine,actor,receipt):
    request=receipt['details'].get('leafy_cloak')
    old=_records(actor).get(LEAFY)
    if old is not None:
        actor.spec.setdefault(LEAFY_HISTORY,[]).append({'projection':deepcopy(old),
            'replaced_by':receipt['id'],'ended_at':engine.elapsed_seconds})
    if request is None:
        if old is not None:
            _remove(engine,actor,LEAFY)
            G.materialize(actor,'abilities');G.reconcile(engine,actor)
        return
    value=_leafy_policy(engine.r)
    payload=value['definitions'][request['leafy_source']['variant']]['choices'][request['choice']]
    _apply(engine,actor,LEAFY,request['choice'],payload,None,request['reason'],lifetime='until_reactivated')
    _records(actor)[LEAFY]['leafy_producer']={'receipt_id':receipt['id'],
        'garment_source':receipt['details']['grant_source'],'selection':deepcopy(request['leafy_source'])}
    actor.spec.get(PENDING,{}).pop(LEAFY,None)


def _leafy_payload(actor,record,*,current=False):
    """Legacy projections remain legacy; new projections need their actual producer."""
    producer=record.get('leafy_producer')
    if producer is None:
        payload=definition(actor.r,LEAFY)['choices'].get(record.get('choice'))
        if payload is None:raise ValueError('unknown historical Leafy Cloak pair')
        return payload
    import source_selection as SELECTION
    import ability_native_actions as NATIVE
    value=_leafy_policy(actor.r);document=_leafy_document(value);selected=producer['selection']
    SELECTION.policy_values(selected['binding'],document['variants'])
    scope=selected['scope'];choice=selected['choice'];variant=selected['variant']
    if (type(scope)is not dict or scope.get('policy_id')!=document['id']
            or scope.get('definition_hash')!=SELECTION.fingerprint(document)
            or scope.get('selected_id')!=LEAFY or scope.get('selected_version') is not None):
        raise ValueError('Leafy Cloak producing source scope changed')
    if choice is None:
        if variant!=value['default']:raise ValueError('Leafy Cloak authored default changed')
    elif (type(choice)is not dict or set(choice)!={'value','reason','scope'}
            or choice['value']!=variant or choice['scope']!=scope
            or not isinstance(choice['reason'],str) or not choice['reason'].strip()):
        raise ValueError('actual scoped Leafy Cloak source choice required')
    payload=value['definitions'].get(variant,{}).get('choices',{}).get(record.get('choice'))
    matches=[r for r in actor.spec.get(NATIVE.HISTORY,[]) if r.get('id')==producer.get('receipt_id')]
    if len(matches)!=1:raise ValueError('Leafy Cloak lost its actual Designer receipt')
    receipt=matches[0];details=receipt.get('details',{});request=details.get('leafy_cloak',{})
    if (receipt.get('source')!=DESIGNER or receipt.get('operation')!='designer'
            or receipt.get('actor_id')!=actor.entity_id or receipt.get('target_id')!=actor.entity_id
            or details.get('grant_source')!=producer.get('garment_source')
            or request.get('leafy_source')!=selected or request.get('choice')!=record.get('choice')
            or request.get('reason')!=record.get('reason') or receipt.get('at')!=record.get('installed_at')
            or payload is None):
        raise ValueError('Leafy Cloak differs from its completed Designer choice')
    if current:
        creations=[r for r in actor.spec.get(NATIVE.HISTORY,[]) if r.get('source')==DESIGNER and r.get('operation')=='designer']
        if (not creations or creations[-1]['id']!=receipt['id']
                or actor.spec.get(NATIVE.KEY,{}).get(DESIGNER,{}).get('garment')!=details):
            raise ValueError('Leafy Cloak is not bound to the current Designer garment')
    return payload


def _fact(value,label):
    if not isinstance(value,dict) or set(value)!={'source','reason'}:raise ValueError(label+' needs an observed source and reason')
    _text(value['source'],label+' source');_text(value['reason'],label+' reason')
    return deepcopy(value)


def _weather_choice(engine,choice,observation,actor):
    effective=__import__('effects').effective_weather(engine,actor)
    mapping=WEATHER_TYPES
    if observation is None:
        candidates=['none' if effective is None else effective]
        evidence=[{'weather':candidates[0],'source':'engine/weather-state','reason':'actual active canonical weather'}]
        import weather_state as WEATHER
        if 'nicolette' in getattr(engine,WEATHER.KEY,{}):
            candidates=list(WEATHER.effective_weathers(engine,actor)) or ['none']
            evidence=[{'weather':w,'source':'engine/weather-state','reason':'actual active sourced sample weather'} for w in candidates]
    else:
        if not isinstance(observation,dict) or set(observation)-{'weather_effects','weather_candidates','canonical_weather','canonical_weather_index'} or 'weather_effects' not in observation or not isinstance(observation['weather_effects'],list) or not observation['weather_effects']:
            raise ValueError('Forecast requires actual weather-effect observations')
        evidence=[];candidates=[]
        for fact in observation['weather_effects']:
            if not isinstance(fact,dict) or set(fact)!={'weather','source','reason'} or fact['weather'] not in mapping:
                raise ValueError('reviewed Forecast weather fact required')
            _text(fact['source'],'weather fact source');_text(fact['reason'],'weather fact reason')
            candidates.append(fact['weather']);evidence.append(deepcopy(fact))
        current='none' if effective is None else effective
        if current not in candidates:raise ValueError('weather observations omit the actual canonical weather')
        if observation.get('canonical_weather',current)!=current:raise ValueError('stored Forecast canonical weather changed')
    allowed={mapping[x] for x in candidates}
    if choice not in allowed:raise ValueError('Forecast type must come from an actual active weather')
    current='none' if effective is None else effective
    primary_index=candidates.index(current) if observation is None else observation.get('canonical_weather_index',candidates.index(current))
    if type(primary_index) is not int or not 0<=primary_index<len(candidates) or candidates[primary_index]!=current:
        raise ValueError('Forecast canonical weather fact must match the actual primary weather')
    result={'weather_effects':evidence,'weather_candidates':candidates,
            'canonical_weather':current,'canonical_weather_index':primary_index}
    if observation is not None and observation.get('weather_candidates',candidates)!=candidates:raise ValueError('stored Forecast candidates changed')
    return result


FIELD_TYPES={
 '해변':('땅','물'),'동굴':('바위','악'),'사막':('땅','바위'),'숲':('풀',),'민물':('물',),'바다':('물',),
 '초원':('노말','풀'),'습지':('물','독'),'산':('바위','땅'),'열대 우림':('풀','독'),'타이가':('얼음','풀'),
 '툰드라':('얼음',),'도시':('노말','강철'),'sunny':('불꽃',),'rain':('물',),'hail':('얼음',),'snow':('얼음',),'sandstorm':('바위',)}


def _field_choice(engine,choice,observation,actor):
    if not isinstance(observation,dict) or set(observation)-{'environment','fact','gm_options','candidates'} or not {'environment','fact'}<=set(observation):
        raise ValueError('Mimicry requires an observed environment fact')
    _fact(observation['fact'],'environment fact');environment=observation['environment'];_text(environment,'environment')
    candidates=set(FIELD_TYPES.get(environment,()))
    weather=__import__('effects').effective_weather(engine,actor)
    if weather in FIELD_TYPES:candidates.update(FIELD_TYPES[weather])
    extra=observation.get('gm_options',[])
    if extra:
        if not isinstance(extra,list):raise ValueError('GM type options must be a list')
        import type_state as TYPES
        TYPES.validate_types(engine.r,extra,label='Mimicry GM type options');candidates.update(extra)
    if choice not in candidates:raise ValueError('Mimicry type is not available from the actual field/weather')
    expected=sorted(candidates)
    if 'candidates' in observation and observation['candidates']!=expected:raise ValueError('stored Mimicry candidates changed')
    result={k:deepcopy(v) for k,v in observation.items() if k!='candidates'};result['candidates']=expected;return result


def _material_choice(choice,observation):
    expected={'초목도롱이':{'나뭇잎','잔가지'},'모래땅도롱이':{'모래','돌'},'슈레도롱이':{'쓰레기','파편'}}
    if not isinstance(observation,dict) or set(observation)!={'materials','fact'} or not isinstance(observation['materials'],list):
        raise ValueError('Quick Cloak requires observed nearby materials')
    _fact(observation['fact'],'material fact')
    if not expected[choice].intersection(observation['materials']):raise ValueError('nearby materials do not produce that cloak')
    return deepcopy(observation)


def _selection(engine,actor,source,choice,observation):
    row=definition(engine.r,source);kind=row['kind']
    if choice not in row['choices']:raise ValueError('choice is not declared for this ability')
    payload=deepcopy(row['choices'][choice])
    if kind=='weather':
        observation=_weather_choice(engine,choice,observation,actor)
        import weather_state as WEATHER
        sample_types=WEATHER.rudolf_types(engine,actor)
        if sample_types is not None:payload['types']=sample_types
    elif kind=='field':observation=_field_choice(engine,choice,observation,actor)
    elif kind=='cloak':
        observation=_material_choice(choice,observation)
        secondary=payload.pop('secondary_type')
        base=list(actor.spec.get('types',[]))
        if not base:raise ValueError('Quick Cloak requires the actual permanent primary type')
        payload['types']=list(dict.fromkeys([*base,secondary]))
    elif kind=='season':
        if not isinstance(observation,dict) or set(observation)!={'season','fact'} or observation['season']!=choice:raise ValueError('Seasonal requires the actual current season')
        _fact(observation['fact'],'season fact')
    elif kind=='choice' and source=='ability/기막힌손질':
        if not isinstance(observation,dict) or observation.get('location')!='미용실' or set(observation)!={'location','fact'}:raise ValueError('Fabulous Trim requires an actual salon')
        _fact(observation['fact'],'salon fact')
    elif kind=='form_grants':
        if actor.form!=choice and not (source=='ability/폴터가이스트-playtest' and actor.form=='로토무' and choice=='보통 로토무'):
            raise ValueError('form-derived grants require the actual current form')
        observation={'form':actor.form}
        if actor.level<40:payload.pop('moves',None)
    elif kind in ('creation_slots','turn_choice','move_form','hp_form','scene_form','choice') and observation is not None:
        if not isinstance(observation,dict):raise ValueError('ability-state observation must be structured')
    return payload,deepcopy(observation)


def _validate_targets(engine,payload):
    import type_state as TYPES,ability_transitions as A
    if payload.get('types') is not None:TYPES.validate_types(engine.r,payload['types'],label='projected ability types')
    for uid in payload.get('abilities',[]):
        if A.ability_id(engine.r,uid)!=uid or engine.r._selected_rule(uid)!=uid:raise ValueError('projected ability identity is not selected')
    for uid in payload.get('moves',[]):
        if engine.r.move_id(uid)!=uid or engine.r._selected_rule(uid)!=uid:raise ValueError('projected move identity is not selected')
    effects=payload.get('effects',[])
    if not isinstance(effects,list) or any(not isinstance(x,dict) for x in effects):raise ValueError('typed projected effects required')


def _switch_form_direct(engine,actor,form):
    import living_weapon as LIVING
    if LIVING.locked_form(engine,actor,form):form='블레이드폼'
    import form_allocations as FORMS
    if FORMS.KEY not in actor.spec:
        actor.form=form;return
    projected=FORMS.project(actor)
    if form not in projected:raise ValueError('declared form allocation required for ability transition')
    actor.spec['stats']=deepcopy(projected[form]['base']);actor.stats=deepcopy(projected[form]['effective'])
    actor.spec[FORMS.KEY]['active']=form;actor.form=form;G.commit_stat_baseline(actor)


def _battle_forms(actor):
    import form_allocations as FORMS
    if FORMS.KEY in actor.spec:return
    base=deepcopy(actor.spec['stats'])
    blade=dict(base,atk=base['def'],def_=base['atk'],spa=base['spd'],spd=base['spa']);blade['def']=blade.pop('def_')
    record={'source':'ability/배틀스위치','active':'실드폼','forms':{'실드폼':base,'블레이드폼':blade}}
    FORMS.validate(actor,record);actor.spec[FORMS.KEY]=record;actor.form='실드폼'


def _require_forms(actor,source,choice):
    import form_allocations as FORMS
    required={
      'ability/리밋실드':{'유성','코어'},
      'ability/스웜체인지':{choice,'퍼펙트폼'},
      'ability/어군':{'군집의모습','단독의모습'},
    }.get(source)
    if required is None:return
    record=FORMS.validate(actor)
    if not required.issubset(record['forms']):raise ValueError('ability transition requires every authored form allocation')
    if source=='ability/스웜체인지':
        if record['source']!=source or choice not in ('10%폼','50%폼'):
            raise ValueError('Power Construct requires its actual original form source')
        if 'form_growth_allocations' not in actor.spec:
            raise ValueError('Power Construct requires each form\'s checked BST investment')
        import growth_stats as GROWTH
        from builder import species_lookup
        GROWTH.form_projection(actor.r,actor.spec)
        for name,plan in actor.spec['form_growth_allocations']['plans'].items():
            species='지가르데 '+name
            if plan['species_base']!=species_lookup(actor.r,species)['base_stats']:
                raise ValueError('Power Construct requires the actual species base for each form')


def _remove(engine,actor,source,*,restore_form=False):
    record=_records(actor).get(source)
    if record is None:return False
    sid=record['grant_source'];G.revoke(actor,sid,engine=engine)
    if restore_form and record.get('prior_form') is not None:_switch_form_direct(engine,actor,record['prior_form'])
    _records(actor).pop(source,None)
    return True


def _apply(engine,actor,source,choice,payload,observation,reason,*,lifetime,prior_form=None):
    import living_weapon as LIVING
    if source=='ability/배틀스위치' and LIVING.locked_form(engine,actor,payload.get('form')):
        choice='블레이드폼';payload=deepcopy(definition(engine.r,source)['choices'][choice])
    sid=_sid(source);_validate_targets(engine,payload)
    old=_records(actor).get(source)
    if old is not None:
        G.revoke(actor,old['grant_source'],engine=engine);_records(actor).pop(source,None)
    form=payload.get('form')
    if source=='ability/배틀스위치':_battle_forms(actor)
    _require_forms(actor,source,prior_form)
    import form_allocations as FORMS
    if form is not None and FORMS.KEY in actor.spec:_switch_form_direct(engine,actor,form)
    G._source(actor,sid,'ability_state_projection',owner_id=actor.entity_id,rule_id=source,lifetime=lifetime,tutor_points=0,
      **({'move_mode':'permission'} if payload.get('moves') else {}))
    def contributions():
        if payload.get('types') is not None:G.type_operation(actor,'set',payload['types'],sid)
        for uid in payload.get('abilities',[]):G.grant(actor,'abilities',uid,sid,'ability_state_projection',owner_id=actor.entity_id,lifetime=lifetime,rule_id=source)
        if payload.get('moves'):G.grant_moves(actor,payload['moves'],sid,'ability_state_projection',owner_id=actor.entity_id,lifetime=lifetime,rule_id=source,mode='permission')
        if form is not None and FORMS.KEY not in actor.spec:G.scalar(actor,'form',form,sid)
        if payload.get('effects'):
            import effects as FX
            FX.apply_passives(engine,actor,[dict(x,_ability=source,_rule_id=source) for x in payload['effects']])
    G.apply_owned(engine,actor,sid,contributions,effects=payload.get('effects',[]))
    if payload.get('temp_hp'):
        import temporary_hp as TEMP
        # The projected Perfect allocation supplies this one grant. The source
        # record installed below makes all subsequent real-HP consumers use the
        # original form through hp_stat(), without copying a second HP balance.
        TEMP.grant(engine,actor,engine.tick(actor)*payload['temp_hp'] if payload.get('temp_hp_unit')=='tick' else NUMERIC.ratio(actor.base_max_hp*payload['temp_hp'],2))
    record={'source':source,'row_id':definition(engine.r,source)['row_id'],'choice':choice,'observation':deepcopy(observation),'reason':reason,
      'grant_source':sid,'lifetime':lifetime,'payload':deepcopy(payload),'prior_form':prior_form,'installed_at':engine.elapsed_seconds,
      'blocks_temp_hp':bool(payload.get('blocks_temp_hp'))}
    _records(actor,True)[source]=record
    G.materialize(actor,'abilities');G.materialize(actor,'moves');G.reconcile(engine,actor)
    return deepcopy(record)


def _cost(engine,actor,source,row,seconds,*,triggered=False):
    action='full' if source=='ability/배틀스위치' and not triggered else row.get('action');frequency=row.get('frequency')
    if action=='extended':
        if engine.encounter_active:raise ValueError('extended ability-state choice requires a noncombat interval')
        C.integer(seconds,'extended ability-state seconds',1);engine.preflight_advance_time(seconds,[actor])
    elif action in ('free','swift','standard','full') and engine.encounter_active:
        import turn as TURN
        if not TURN.spend(engine,actor,action,source):raise ValueError('ability-state action unavailable')
    if frequency in ('Scene','Daily'):
        import frequency as F
        quota={'kind':frequency.lower(),'uses':1}
        if not F.activation_allowed(actor,source,quota,engine=engine,action_actor=actor if action is not None else None):raise ValueError('ability-state frequency exhausted')
        F.consume_activation(actor,source,quota,engine=engine,action_actor=actor if action is not None else None)
    if action=='extended':engine.advance_time(seconds,[actor])


def activate(engine,actor,source,*,choice=None,observation=None,reason,seconds=None,_triggered=False):
    source=registration(engine.r,source)
    if source is None:raise ValueError('reviewed ability-state source required')
    _text(reason,'ability-state activation reason')
    if actor.kind!='pokemon' or not _owned(actor,source):raise ValueError('actual active Pokemon ability required')
    if source==LEAFY:raise ValueError('Leafy Cloak is chosen only by actual Designer creation')
    row=definition(engine.r,source)
    if row['kind']=='creation_slots':raise ValueError('creation pattern requires one native initialization')
    if choice is None:
        pending=actor.spec.get(PENDING,{}).get(source)
        if pending is None:raise ValueError('ability-state choice required')
        choice,observation,reason=pending['choice'],pending['observation'],pending['reason']
    payload,observation=_selection(engine,actor,source,choice,observation)
    if source=='ability/스웜체인지' and actor.hp*2>=actor.base_max_hp:raise ValueError('form activation requires HP below half')
    if source=='ability/리밋실드':
        expected='코어' if actor.hp*2<actor.base_max_hp else ('유성' if not engine.encounter_active else None)
        if choice!=expected:raise ValueError('Shields Down form must follow the actual HP/combat boundary')
    prior=actor.form
    def commit(e,c):
        _cost(e,c,source,row,seconds,triggered=_triggered)
        out=_apply(e,c,source,choice,payload,observation,reason,lifetime=row['lifetime'],prior_form=prior)
        c.spec.get(PENDING,{}).pop(source,None)
        return out
    return G.transition(engine,actor,commit,include_rulings=True)


def initialize(engine,actor,source,*,choice=None,parent_choices=(),reason):
    source=registration(engine.r,source);row=definition(engine.r,source) if source else None
    if row is None or row['kind']!='creation_slots':raise ValueError('reviewed creation-state source required')
    _text(reason,'creation-state reason')
    if actor.kind!='pokemon' or not _owned(actor,source):raise ValueError('actual active Pokemon ability required')
    if source in _records(actor):raise ValueError('creation pattern is already initialized')
    if source=='ability/뱀무늬-playtest':
        parents=list(parent_choices)
        if parents:
            if any(x not in row['choices'] for x in parents) or len(parents)>2:raise ValueError('actual parent patterns required')
            choice=parents[0] if len(set(parents))==1 else parents[engine.rng.randrange(2)]
        else:
            if choice is not None:raise ValueError('Serpent\'s Mark without parents requires the authored 1d6 producer')
            choice=list(row['choices'])[engine.rng.randrange(6)]
    elif choice is None:raise ValueError('creation color choice required')
    payload,observation=_selection(engine,actor,source,choice,{'creation':True})
    def commit(e,c):return _apply(e,c,source,choice,payload,observation,reason,lifetime='permanent')
    return G.transition(engine,actor,commit,include_rulings=True)


def start_turn(engine,actor):
    source='ability/꼬르륵스위치'
    if _owned(actor,source):activate(engine,actor,source,reason='turn-start form choice')


def hp_change_interested(actor):
    """Whether a native HP boundary may execute an existing form projection."""
    return _owned(actor,'ability/리밋실드') or 'ability/어군' in _records(actor)


def native_move_interested(engine,actor,target):
    """Use the existing world transaction when a Move can reach these hooks."""
    import world_entities as WORLD
    return _owned(actor,'ability/배틀스위치') or any(
        hp_change_interested(c) or bool(_records(c))
        for c in WORLD.actor_index(engine,extra=(actor,target)).values())


def after_hp_change(engine,actor):
    shield='ability/리밋실드'
    if _owned(actor,shield):
        desired='코어' if actor.hp*2<actor.base_max_hp else ('유성' if not engine.encounter_active else None)
        if desired is not None and (_records(actor).get(shield,{}).get('choice')!=desired):
            activate(engine,actor,shield,choice=desired,reason='actual HP/form boundary')
    school='ability/어군';record=_records(actor).get(school)
    if record and record['choice']=='군집의모습' and actor.hp*2<actor.base_max_hp and actor.temp_hp==0:
        def commit(e,c):
            current=_records(c)[school]
            payload,obs=_selection(e,c,school,'단독의모습',None)
            return _apply(e,c,school,'단독의모습',payload,obs,'Schooling HP/temp-HP boundary',lifetime='persistent',prior_form=current.get('prior_form'))
        G.transition(engine,actor,commit,include_rulings=True)


def after_move(engine,actor,move_id,move,mech):
    source='ability/배틀스위치'
    if not _owned(actor,source):return
    choice=None
    if move.get('class') in ('물리','특수'):choice='블레이드폼'
    else:
        named=move_id in ('move/킹실드','move/방어') or '축복' in move.get('keywords',[])
        stage_effects=mech.get('effects_exec',[])
        raised=any(x.get('target') in (None,'self') and x.get('stat')=='def' and x.get('delta',0)>0 for x in stage_effects)
        if named or raised:choice='실드폼'
    if choice and _records(actor).get(source,{}).get('choice')!=choice:
        activate(engine,actor,source,choice=choice,reason='actual used move form trigger',_triggered=True)


def after_hit(engine,actor,*,multiplier,dealt):
    source='ability/신속도롱이';record=_records(actor).get(source)
    if record and multiplier>1 and dealt>0:G.transition(engine,actor,lambda e,c:_remove(e,c,source),include_rulings=True)


def weather_changed(engine):
    for actor in list(getattr(engine,'everyone',[])):
        reconcile_weather(engine,actor,weather_changed=True)


def reconcile_weather(engine,actor,*,weather_changed=False):
    """Keep Forecast's existing weather contribution tied to its live ability.

    Generic grant reconciliation must not refresh an independent weather fact:
    only the actual weather producer updates an already active projection.
    """
    source='ability/기분파';current=_records(actor).get(source)
    import ability_transitions as A
    if current is None and source not in A.known(actor):return False
    if not _owned(actor,source):return _remove(engine,actor,source)
    if current is not None and not weather_changed:return False
    effective=__import__('effects').effective_weather(engine,actor)
    weather='none' if effective is None else effective
    choice=WEATHER_TYPES.get(weather)
    observation=None
    import weather_state as WEATHER
    if 'nicolette' in getattr(engine,WEATHER.KEY,{}):
        prior=(current or {}).get('observation') or {}
        primary_index=prior.get('canonical_weather_index',0)
        independent=[deepcopy(fact) for i,fact in enumerate(prior.get('weather_effects',[]))
            if i!=primary_index and fact['source']!='engine/weather-state']
        actual=list(WEATHER.effective_weathers(engine,actor)) or ['none']
        facts=independent+[{'weather':w,'source':'engine/weather-state','reason':'actual active sourced sample weather'} for w in actual]
        if current and current['choice'] in {WEATHER_TYPES[fact['weather']] for fact in facts}:choice=current['choice']
        observation={'weather_effects':facts,'canonical_weather_index':len(independent)+actual.index(weather)}
        return activate(engine,actor,source,choice=choice,observation=observation,reason='actual adopted weather occurrence changed')
    if current:
        prior=current.get('observation') or {}
        effects=prior.get('weather_effects',[])
        # The primary battlefield weather can end or refresh without
        # ending a separately observed weather selected by Forecast.
        previous=prior.get('canonical_weather')
        if previous is None:
            history=getattr(engine,'_weather_state',{}).get('history',[])
            previous=history[-1]['weather'] if history else weather
        # Remove just the fact bound to the battlefield weather. Two
        # distinct active sources can expose the same weather type.
        primary_index=prior.get('canonical_weather_index')
        if primary_index is None:
            primary_index=next((i for i,fact in enumerate(effects) if fact['weather']==previous),None)
        independent=[deepcopy(fact) for i,fact in enumerate(effects) if i!=primary_index]
        still_active={WEATHER_TYPES[fact['weather']] for fact in independent}
        if current['choice'] in still_active:choice=current['choice']
        if independent:
            observation={'weather_effects':[*independent,{'weather':weather,'source':'engine/weather-state','reason':'actual active canonical weather'}],
                         'canonical_weather_index':len(independent)}
    if choice and (current is None or current.get('choice')!=choice or observation is not None):
        return activate(engine,actor,source,choice=choice,observation=observation,reason='actual canonical weather changed' if weather_changed else 'actual Forecast ownership changed')
    return False


def form_changed(engine,actor):
    if getattr(actor,'_ability_projection_switching',False):return
    source='ability/폴터가이스트-playtest'
    # Most form switches have no relationship to the optional Playtest source.
    # Avoid resolving an excluded variant in rulesets where it cannot be owned.
    import ability_transitions as A
    if source not in A.known(actor):return
    if _owned(actor,source):
        choice='보통 로토무' if actor.form=='로토무' else actor.form
        if choice in definition(engine.r,source)['choices']:
            activate(engine,actor,source,choice=choice,reason='actual Rotom form changed')
        else:_remove(engine,actor,source)


def level_changed(engine,actor,old_level):
    source='ability/폴터가이스트-playtest'
    record=_records(actor).get(source)
    if record is None or not old_level<40<=actor.level:return False
    payload,_=_selection(engine,actor,source,record['choice'],record['observation'])
    _validate_targets(engine,payload)
    if payload.get('moves'):
        G._source(actor,record['grant_source'],'ability_state_projection',move_mode='permission')
        G.grant_moves(actor,payload['moves'],record['grant_source'],'ability_state_projection',
          owner_id=actor.entity_id,lifetime=record['lifetime'],rule_id=source,mode='permission')
    record['payload']=payload
    return True


def end_scene(engine,actors):
    for actor in actors:
        for source,record in list(_records(actor).items()):
            if record['lifetime']=='scene':_remove(engine,actor,source,restore_form=True)


def temp_hp_blocked(actor):return any(row.get('blocks_temp_hp') for row in _records(actor).values())


def hp_stat(actor):
    """Power Construct retains its original form's real-HP stat authority."""
    source='ability/스웜체인지';record=_records(actor).get(source)
    if record is None:return actor.stats['hp']
    import form_allocations as FORMS
    forms=FORMS.validate(actor);prior=record.get('prior_form')
    if forms['source']!=source or prior not in ('10%폼','50%폼') or prior not in forms['forms']:
        raise ValueError('Power Construct requires its original HP allocation')
    return G.prepare_stat_baseline(actor,forms['forms'][prior])['hp']


def ability_pool_overrides(spec):
    result={}
    for source,row in (spec.get(KEY) or {}).items():
        payload=row.get('payload',{})
        for pool,values in payload.get('ability_pools',{}).items():result[pool]=list(values)
    return result


_CLOAK_EVOLUTIONS={
  '초목도롱이':'도롱마담 초목도롱',
  '모래땅도롱이':'도롱마담 모래땅도롱',
  '슈레도롱이':'도롱마담 슈레도롱',
}


def preflight_evolution(rules,spec,target_species):
    """Bind an active cloak to the corresponding actual Wormadam branch."""
    record=(spec.get(KEY) or {}).get('ability/신속도롱이')
    if record is None:return
    from builder import species_lookup
    old=species_lookup(rules,spec['species']);new=species_lookup(rules,target_species)
    if old['name']!='도롱충이':raise ValueError('Quick Cloak permanence requires an actual Burmy evolution')
    if new['name']!=_CLOAK_EVOLUTIONS.get(record['choice']):
        raise ValueError('Wormadam evolution form must match the actual active cloak')


def evolution_option(rules,spec,target_species,options):
    """Resolve the source database's generic Wormadam edge to one exact form."""
    from builder import species_lookup
    new=species_lookup(rules,target_species)
    if new['name'] not in _CLOAK_EVOLUTIONS.values():return new['name']
    preflight_evolution(rules,spec,target_species)
    if '도롱마담' not in options:raise ValueError('Burmy evolution table lacks its Wormadam branch')
    return '도롱마담'


def _commit_cloak_evolution(engine,actor,record,reason):
    source='ability/신속도롱이';types=record['payload'].get('types',[])
    if len(types)!=2:raise ValueError('cloak type projection required')
    G.revoke(actor,record['grant_source'],engine=engine);_records(actor).pop(source,None)
    new=list(dict.fromkeys([*actor.spec.get('types',[]),types[-1]]));actor.spec['types']=new;actor._types=new
    actor.spec.setdefault('ability_state_permanent_history',[]).append({'source':source,'types':new,'reason':reason})
    return deepcopy(new)


def after_evolution(engine,actor):
    """Consume the cloak only after the native evolution committed its species."""
    source='ability/신속도롱이';record=_records(actor).get(source)
    if record is None:return False
    from builder import species_lookup
    species=species_lookup(engine.r,actor.spec['species'])
    if species['name']!=_CLOAK_EVOLUTIONS.get(record['choice']):return False
    _commit_cloak_evolution(engine,actor,record,'native Burmy to Wormadam evolution')
    return True


def evolve_cloak(engine,actor,*,reason):
    source='ability/신속도롱이';record=_records(actor).get(source);_text(reason,'cloak evolution reason')
    if record is None:raise ValueError('actual active cloak required')
    from builder import species_lookup
    species=species_lookup(engine.r,actor.spec['species'])
    if species['name']!=_CLOAK_EVOLUTIONS.get(record['choice']):raise ValueError('actual matching Wormadam evolution required')
    migrations=actor.spec.get('allocation_migrations',[])
    if not migrations or migrations[-1].get('kind')!='evolution' or migrations[-1].get('previous_species')!='pokemon/도롱충이':
        raise ValueError('native Burmy evolution receipt required')
    def commit(e,c):
        return _commit_cloak_evolution(e,c,_records(c)[source],reason)
    return G.transition(engine,actor,commit,include_rulings=True)


def validate_world(engine,index):
    import form_allocations as FORMS,ability_transitions as A,type_state as TYPES
    for actor in index.values():
        rows=_records(actor)
        if len(rows)!=len(set(rows)):raise ValueError('duplicate ability-state projection source')
        for ended in actor.spec.get(LEAFY_HISTORY,[]):
            previous=ended['projection']
            if previous.get('source')!=LEAFY or previous.get('payload')!=_leafy_payload(actor,previous):
                raise ValueError('historical Leafy Cloak projection changed')
            import ability_native_actions as NATIVE
            replacement=[r for r in actor.spec.get(NATIVE.HISTORY,[]) if r.get('id')==ended.get('replaced_by')]
            if (len(replacement)!=1 or replacement[0].get('source')!=DESIGNER
                    or replacement[0].get('operation')!='designer'
                    or replacement[0].get('at')!=ended.get('ended_at')
                    or previous.get('installed_at',0)>ended['ended_at']):
                raise ValueError('Leafy Cloak replacement lost its actual Designer boundary')
            prior=previous.get('leafy_producer')
            if prior is not None:
                before=next(r for r in actor.spec[NATIVE.HISTORY] if r['id']==prior['receipt_id'])
                if before['sequence']>=replacement[0]['sequence']:
                    raise ValueError('Leafy Cloak replacement must follow its producing Designer')
        for source,record in rows.items():
            row=definition(engine.r,source)
            if source not in A.known(actor):raise ValueError('ability-state projection outlived its source ability')
            if row is None or record.get('source')!=source or record.get('row_id')!=row['row_id'] or (source!=LEAFY and record.get('choice') not in row['choices']):
                raise ValueError('ability-state projection differs from reviewed source')
            if record.get('grant_source')!=_sid(source) or record.get('lifetime')!=row['lifetime']:
                raise ValueError('ability-state projection ownership/lifetime changed')
            payload=record.get('payload');_validate_targets(engine,payload)
            if source==LEAFY:expected=_leafy_payload(actor,record,current=True)
            else:expected,_=_selection(engine,actor,source,record['choice'],record.get('observation'))
            if payload!=expected:raise ValueError('ability-state payload differs from the reviewed projection')
            owner=actor.spec.get(G.KEY,{}).get('sources',{}).get(record['grant_source'])
            if owner is None or owner.get('rule_id')!=source or owner.get('lifetime')!=row['lifetime']:
                raise ValueError('ability-state projection lacks its owned producer')
            if payload.get('types') is not None and actor.spec[G.KEY].get('type_sources',{}).get('sources',{}).get(record['grant_source'],{}).get('values')!=payload['types']:
                raise ValueError('projected types differ from the owned type consumer')
            if payload.get('form') is not None:
                if FORMS.KEY in actor.spec and actor.spec[FORMS.KEY]['active']!=payload['form']:raise ValueError('projected form allocation is not active')
                if actor.form!=payload['form']:raise ValueError('projected visible form changed')
                if source=='ability/기분파' and FORMS.KEY not in actor.spec:
                    scalar=actor.spec[G.KEY].get('scalar_sources',{}).get('form',{})
                    if scalar.get('sources',{}).get(record['grant_source'])!=payload['form'] or scalar.get('visible')!=actor.form:
                        raise ValueError('Forecast appearance differs from its owned form consumer')
            if record.get('blocks_temp_hp')!=bool(payload.get('blocks_temp_hp')):raise ValueError('temporary-HP lock changed')
            if source=='ability/스웜체인지':_require_forms(actor,source,record.get('prior_form'))
            for uid in payload.get('abilities',[]):
                if uid not in A.known(actor):raise ValueError('projected ability is not consumed by effective abilities')
            for uid in payload.get('moves',[]):
                if uid not in actor.moves:raise ValueError('projected move permission is not effective')
            TYPES.validate_actor(actor)
    return True
