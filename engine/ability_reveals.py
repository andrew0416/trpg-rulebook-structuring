"""Native Swift-action information projections for two reviewed abilities.

Anticipation owns its per-target encounter history.  Frisk reads only current
actor fields and actual held-slot names; neither source grants generic sensing
rights or exposes information absent from its original clause.
"""
import common_checks as C
import state_grants as G
import world_entities as W

HISTORY='ability_reveal_history'
SOURCES={
    'ability/위험예지':{
        'name':'위험예지','effect':[{'type':'reveal','info':'whether target knows a super-effective move'}],
        'target':'다수의 포켓몬 또는 트레이너','mode':'anticipation'},
    'ability/통찰-playtest':{
        'name':'통찰 [Playtest]','effect':[{'type':'reveal','info':'types, ability, nature, level, held item'}],
        'target':'인접한 단일 포켓몬','mode':'frisk'},
}


def _source(rules,identity):
    matches=[source for source,row in SOURCES.items() if identity in (source,row['name'])]
    if len(matches)!=1:raise ValueError('reviewed reveal ability source required')
    source=matches[0];row=SOURCES[source]
    if rules._selected_rule(source)!=source:raise ValueError('reveal ability source is not selected')
    if rules.ability_effects.get(row['name'])!=row['effect']:raise ValueError('reveal ability declaration changed; review required')
    return source,row


def registration(rules,identity):
    if not any(identity in (source,row['name']) for source,row in SOURCES.items()):return None
    source,row=_source(rules,identity)
    return {'source_id':source,'name':row['name'],'mode':row['mode']}


def deferred_registration(rules,effect):
    identity=effect.get('_rule_id') or effect.get('_ability')
    row=registration(rules,identity)
    if row is None:return False
    actual=[{key:value for key,value in effect.items() if not key.startswith('_')}]
    return actual==SOURCES[row['source_id']]['effect']


def _owns(actor,source,row):
    return (row['mode']!='anticipation' or actor.kind=='pokemon') and not actor.abilities_suppressed and any(
        name in (source,row['name']) for name in actor.abilities)


def _history(actor,*,create=True):
    value=actor.spec.get(HISTORY)
    if value is None:
        if not create:return {}
        value={};actor.spec[HISTORY]=value
    if type(value) is not dict:raise ValueError('ability reveal history must be a mapping')
    return value


def _anticipation(engine,user,target):
    """Return only the sourced Boolean; never leak the qualifying Move identity."""
    if target.kind not in ('pokemon','trainer'):raise ValueError('Anticipation targets Pokemon or Trainers')
    knows=False
    for move_id in target.moves:
        move=engine.r.move(move_id)
        if move.get('class') in ('물리','특수') and engine.type_multiplier(move.get('type'),user)[0]>1:
            knows=True;break
    return {'target_id':target.entity_id,'knows_super_effective_move':knows}


def _frisk(target):
    if target.kind!='pokemon':raise ValueError('Frisk requires one Pokemon target')
    import held_equipment as HELD
    HELD.validate(target)
    nature=target.spec.get('nature')
    if not isinstance(nature,str) or not nature.strip():raise ValueError('Frisk target needs its actual Nature')
    return {'target_id':target.entity_id,'types':list(target.types),'abilities':list(target.abilities),
        'nature':nature,'level':target.level,'held_item_names':[entry['name'] for entry in HELD.entries(target)]}


def activate(engine,user,ability,targets):
    source,row=_source(engine.r,ability);targets=list(targets)
    if not targets or len({id(target) for target in targets})!=len(targets):raise ValueError('distinct reveal targets required')
    W.require_actors(engine,user,*targets)
    if not _owns(user,source,row):raise ValueError('actual active reveal ability required')
    if row['mode']=='frisk':
        if len(targets)!=1:raise ValueError('Frisk requires exactly one target')
        import body_state as BODY
        if not BODY.adjacent(user,targets[0]):raise ValueError('Frisk target must be adjacent')
        _frisk(targets[0])
    else:
        if not engine.encounter_active:raise ValueError('Anticipation target history requires an active encounter')
        history=_history(user,create=False).get(source)
        used=set(history['target_ids']) if history and history.get('encounter_epoch')==engine._party_encounter_epoch else set()
        if used.intersection(target.entity_id for target in targets):raise ValueError('Anticipation already revealed this target in the encounter')
        for target in targets:_anticipation(engine,user,target)
    import frequency as FREQUENCY,turn as TURN
    def apply(staged,actor,*subjects):
        staged_source,staged_row=_source(staged.r,source)
        if not _owns(actor,staged_source,staged_row):raise ValueError('actual active reveal ability required')
        key='ability:'+staged_row['name']
        if not FREQUENCY.activation_allowed(actor,key,'임의',engine=staged):raise ValueError('reveal ability frequency unavailable')
        if not TURN.spend(staged,actor,'swift',staged_row['name']):raise ValueError('reveal ability Swift action unavailable')
        FREQUENCY.consume_activation(actor,key,'임의',engine=staged)
        if staged_row['mode']=='frisk':
            result={'source':staged_source,'actor_id':actor.entity_id,'reveal':_frisk(subjects[0])}
        else:
            epoch=staged._party_encounter_epoch;history=_history(actor);record=history.get(staged_source)
            prior=[] if record is None or record.get('encounter_epoch')!=epoch else list(record['target_ids'])
            additions=[target.entity_id for target in subjects]
            if set(prior).intersection(additions):raise ValueError('Anticipation already revealed this target in the encounter')
            history[staged_source]={'encounter_epoch':epoch,'target_ids':prior+additions}
            result={'source':staged_source,'actor_id':actor.entity_id,'encounter_epoch':epoch,
                'reveals':[_anticipation(staged,actor,target) for target in subjects]}
        staged.log(f"    {actor.name}: {staged_row['name']} 정보 공개",staged_source)
        return result
    return G.transition(engine,user,apply,participants=tuple(targets))


def validate_world(engine,index):
    epoch=getattr(engine,'_party_encounter_epoch',0);C.integer(epoch,'encounter epoch',0)
    for actor in index.values():
        history=actor.spec.get(HISTORY,{})
        if type(history) is not dict:raise ValueError('ability reveal history must be a mapping')
        for source,record in history.items():
            row=SOURCES.get(source)
            if row is None or row['mode']!='anticipation':raise ValueError('unknown ability reveal history source')
            _source(engine.r,source)
            if type(record) is not dict or set(record)!= {'encounter_epoch','target_ids'}:raise ValueError('invalid Anticipation history record')
            C.integer(record['encounter_epoch'],'Anticipation encounter epoch',1,epoch);ids=record['target_ids']
            if type(ids) is not list or len(ids)!=len(set(ids)) or any(not isinstance(uid,str) or not uid for uid in ids):raise ValueError('Anticipation history needs distinct target identities')
            if record['encounter_epoch']==epoch and engine.encounter_active and any(uid not in index for uid in ids):raise ValueError('current Anticipation target no longer resolves')
