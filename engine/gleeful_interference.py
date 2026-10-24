"""Book Gleeful Interference consumes native recipient hits and the shared clock."""
from copy import deepcopy
import cheerleader as CHEER
import trainer_feature_acquisition as TFA
import moment_of_action as M
import world_entities as WORLD
import combat_timing as CLOCK
import effect_lifetimes as LIFE

FEATURE='feat/신나게-방해'
KEY='gleeful_interference'


def interested(engine,pokemon,move):
    return move.get('class') in ('물리','특수') and CHEER.owned_friend_guard(engine,pokemon,FEATURE) is not None


def snapshot(engine,pokemon,target,move):
    if move.get('class') not in ('물리','특수') or pokemon is target:return None
    if getattr(pokemon,'side',None) is None or getattr(target,'side',None) is None or pokemon.side==target.side:return None
    if target.kind not in ('trainer','pokemon'):return None
    facts=CHEER.owned_friend_guard(engine,pokemon,FEATURE)
    if facts is None:return None
    facts.update(target_id=target.entity_id,pokemon_side=pokemon.side,target_side=target.side,
                 move_id=move['id'],round=engine.round_no,count=CLOCK.current(engine))
    return facts


def observe_hit(engine,pokemon,target,move,event_id):
    """Capture before on-hit effects such as Mummy can replace Friend Guard."""
    if event_id is None:return
    event=engine._passive_events[event_id]
    if event['actor'] is not pokemon or event['target'] is not target or event['move_id']!=move['id']:
        raise ValueError('actual native Gleeful recipient required')
    if KEY in event:return
    facts=snapshot(engine,pokemon,target,move)
    if facts is not None:event[KEY]=facts


def _seal(row):return TFA._digest('gleeful-interference/hit/v1',{k:v for k,v in row.items() if k!='integrity'})


def issue(engine,facts,origin):
    """The existing native Move or grapple transaction owns this activation."""
    import action_points as AP,action_lifecycle as ACTION,body_modes as BODY
    index=WORLD.actor_index(engine);owner=index[facts['owner_id']];target=index[facts['target_id']]
    choice=engine.rulings.decide({'type':KEY,'unit':FEATURE,'actor':owner.name,
        'text':'Spend 1 AP and a triggered Free Action for -2 Accuracy for one full Round?',
        'pokemon_id':facts['pokemon_id'],'target_id':target.entity_id,'trigger':deepcopy(origin)})
    if choice is not None and type(choice) is not bool:raise ValueError('explicit Gleeful use or decline required')
    row={'snapshot':deepcopy(facts),'origin':deepcopy(origin),'used':choice is True}
    if choice is True:
        if CHEER.acquired(owner,FEATURE) is None:raise ValueError('current acquired Gleeful Interference required')
        if AP.available(owner)<1:raise ValueError('Gleeful Interference needs one AP')
        if not BODY.permits(owner,'free'):raise ValueError('actual triggered Free action body permission required')
        effect=LIFE.prepare(engine,owner,target,{'type':'accuracy_mod','value':-2,'duration':'1라운드'},FEATURE)
        # Completion may follow held suffixes; the printed round starts at the hit.
        effect['count_deadline']=(facts['round']+1,facts['count'])
        ACTION.triggered_free_action(engine,owner,FEATURE)
        owner.ap_account.charge(1,mode='spend')
        effect['gleeful_origin']=deepcopy(origin)
        CLOCK.install(engine,target,effect)
    row['integrity']=_seal(row)
    return row


def after_move(engine,completion):
    import move_completion as COMPLETE
    if completion['phase']!='complete':return
    for event_id in completion.get('native_returns',{}):
        event=engine._passive_events[event_id];facts=event.get(KEY)
        if facts is None or KEY in event.get('outcomes',{}):continue
        target=event['target'];result=COMPLETE.recipient_result(completion,target)
        if (result is None or not result['hit'] or result.get('cancelled') or
                completion['native_returns'][event_id]['facts']['hit_prevented']):continue
        COMPLETE.require_hit_return(engine,event_id,target)
        origin={'kind':'move','completion_id':completion['id'],'event_id':event_id}
        result=issue(engine,facts,origin)
        event.setdefault('outcomes',{})[KEY]={'status':'applied' if result['used'] else 'inapplicable','gleeful':result}


def _validate(engine,index,row):
    if set(row)!={'snapshot','origin','used','integrity'} or row['integrity']!=_seal(row) or type(row['used']) is not bool:
        raise ValueError('Gleeful native activation evidence changed')
    facts=row['snapshot'];owner=index.get(facts['owner_id']);pokemon=index.get(facts['pokemon_id']);target=index.get(facts['target_id'])
    if (owner is None or owner.kind!='trainer' or pokemon is None or pokemon.kind!='pokemon' or target is None or
            target.kind not in ('trainer','pokemon') or pokemon is target or facts['friend_guard']!='ability/프렌드가드' or
            facts['pokemon_side'] is None or facts['target_side'] is None or facts['pokemon_side']==facts['target_side']):
        raise ValueError('actual owned Friend Guard and foe observation required')
    if facts['source']!=TFA._static_source(engine.r,FEATURE) or len([
            r for r in M.receipts(owner,FEATURE) if r['request_id']==facts['acquisition_request_id']])!=1:
        raise ValueError('historical Gleeful acquisition source required')


def validate_world(engine,index):
    import move_completion as COMPLETE,grapple_state as GRAPPLE
    records=[]
    for event in getattr(engine,'_passive_events',{}).values():
        facts=event.get(KEY)
        if facts is None:continue
        if (facts['pokemon_id']!=event['actor'].entity_id or facts['target_id']!=event['target'].entity_id or
                facts['move_id']!=event['move_id'] or facts['round']!=event['round']):
            raise ValueError('Gleeful snapshot must belong to its actual recipient hit')
        row=event.get('outcomes',{}).get(KEY,{}).get('gleeful')
        if row is None:continue
        _validate(engine,index,row)
        if row['snapshot']!=facts or row['origin']!={'kind':'move','completion_id':event['completion_id'],'event_id':event['id']}:
            raise ValueError('Gleeful Move origin changed')
        COMPLETE.require_hit_return(engine,event['id'],event['target']);records.append(row)
    for relation in GRAPPLE._state(engine)['relations'].values():
        for number,entry in enumerate(relation['history']):
            row=entry.get('gleeful')
            if row is None:continue
            _validate(engine,index,row)
            if (entry['action']!='attack' or entry['actor']!=row['snapshot']['pokemon_id'] or
                    row['snapshot']['target_id'] not in relation['participants'] or
                    row['origin']!={'kind':'grapple','relation_id':relation['id'],'history_index':number}):
                raise ValueError('Gleeful grapple origin changed')
            records.append(row)
    for target in index.values():
        for effect in CLOCK.records(target):
            if effect.get('source')!=FEATURE:continue
            matches=[r for r in records if r['used'] and r['origin']==effect.get('gleeful_origin')]
            if len(matches)!=1:raise ValueError('Gleeful timed penalty requires one actual paid trigger')
            facts=matches[0]['snapshot']
            if (target.entity_id!=facts['target_id'] or effect.get('accuracy_modifier')!=-2 or
                    tuple(effect.get('count_deadline',()))!=(facts['round']+1,facts['count'])):
                raise ValueError('Gleeful recipient, Accuracy or full-round expiry changed')
    return True
