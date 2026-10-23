"""Selected, parameterized volatile conditions on the native condition family."""
from pathlib import Path
from copy import deepcopy
import csv,hashlib,json
import common_checks as C
import effect_instances as E
import condition_instances as CONDITIONS


import resolution_transaction as _FINGERPRINTS

def _verify_source_record(rules,row):
    source=row.get('source_record')
    if source is None:return
    if (not isinstance(source,dict) or set(source)!={'file','record','sha256'}
            or source['file']!='input/db/moves.csv' or type(source['record']) is not int
            or source['record']<1 or not isinstance(source['sha256'],str)):
        raise ValueError('custom condition source-record authority changed')
    key=(source['file'],source['record'],source['sha256'])
    verified=getattr(rules,'_custom_condition_source_records',set())
    if key in verified:return
    with (Path(rules.root)/source['file']).open(encoding='utf-8-sig',newline='') as stream:
        rows=list(csv.reader(stream))
    if source['record']>len(rows):raise ValueError('custom condition source record missing')
    digest=_FINGERPRINTS.json_fingerprint(rows[source['record']-1], sort_keys=False, compact=True, allow_nan=True)
    if digest!=source['sha256']:raise ValueError('custom condition source record changed')
    verified=set(verified);verified.add(key);rules._custom_condition_source_records=verified


def definition(rules,source):
    if source=='ability/잔인':
        import taskmaster as TASK
        return TASK.cruelty_definition(rules)
    if source=='ability/멸망의바디':
        import perish_body as PERISH_BODY
        return PERISH_BODY.condition_definition(rules)
    policy=getattr(rules,'_custom_condition_policy',None)
    if policy is None:
        policy=json.loads((Path(rules.root)/'data/custom-condition-policy.json').read_text(encoding='utf-8'))
        rules._custom_condition_policy=policy
    row=policy['sources'].get(source)
    if row is not None:
        if source not in rules.moves or rules._selected_rule(source)!=source:raise ValueError('selected custom condition source required')
        actual=[{k:v for k,v in x.items() if not k.startswith('_')} for x in rules.move_mech(source)[0].get('effects_exec',[]) if x.get('type')=='custom_condition']
        if row['raw'] not in actual:raise ValueError('selected custom condition payload changed')
        _verify_source_record(rules,row)
    return row


def records(actor):
    return [r for r in CONDITIONS.records(actor) if r.get('effect',{}).get('kind')=='custom_condition']


def by_name(rules,name):
    """Only reviewed move-defined conditions enter the ordinary condition catalog."""
    if name=='잔인 회복 봉쇄':return definition(rules,'ability/잔인')
    definition(rules,None)
    matches=[definition(rules,source) for source,row in rules._custom_condition_policy['sources'].items()
             if row['payload']['condition']==name]
    if len(matches)>1:raise ValueError('custom condition name requires an unambiguous selected policy')
    return matches[0] if matches else None


def classification(actor,name):
    return next((r['effect']['class'] for r in records(actor) if r['effect']['condition']==name),None)


def prepare(engine,actor,target,effect,source):
    import world_entities as W
    W.require_actors(engine,actor,target)
    if source=='ability/멸망의바디':
        import perish_body as PERISH_BODY
        return PERISH_BODY.prepare_condition(engine,actor,target,effect)
    row=definition(engine.r,source)
    if row is None:raise ValueError('selected custom condition operation policy required')
    import linked_move_conditions as LINKED
    if LINKED.owns(row):return LINKED.prepare(engine,actor,target,effect,source,row)
    import healing_blocks as HEALING
    if HEALING.is_definition(row):return HEALING.prepare(engine,actor,target,effect,source,row)
    if {k:v for k,v in effect.items() if not k.startswith('_')}!=row['raw']:raise ValueError('custom condition extraction changed')
    name=row['payload']['condition']
    old=CONDITIONS.records(target,name)
    if name in target.conditions and not old:raise ValueError('legacy custom condition requires explicit cure before sourced application')
    if old and any(r['source']!=source for r in old):raise ValueError('custom condition source overlap needs an explicit composition policy')
    return row


def grant(engine,actor,target,effect,source):
    row=prepare(engine,actor,target,effect,source)
    import enduring_resilience as RESILIENCE
    if (not CONDITIONS.records(target,row['payload']['condition'])
            and not engine.immune_to(target,row['payload']['condition'])
            and RESILIENCE.prevent(engine,target,condition=row['payload']['condition'],source=source,
                attacker=actor,classification=row['payload']['class'])):return False
    import linked_move_conditions as LINKED
    if LINKED.owns(row):return LINKED.grant(engine,actor,target,effect,source,row)
    import healing_blocks as HEALING
    if HEALING.is_definition(row):return HEALING.grant(engine,actor,target,effect,source,row)
    name=row['payload']['condition']
    if CONDITIONS.records(target,name) or engine.immune_to(target,name):return False
    record=E.create(engine,target,kind='condition',source=source,payload=row['payload'],
        capacity={'bucket':'condition:'+name,'source':source},
        lifetime={'boundary':'condition_cure_or_volatile_end'},applied_by=actor)
    record.update(issued_turn=target.custom_conditions.get('combat_turn_serial',0),applications=[])
    target.custom_conditions.setdefault(CONDITIONS.KEY,[]).append(record)
    target.conditions.add(name);engine.time_actors([actor,target]);validate_record(target,record)
    return True


def validate_record(actor,record,*,terminal=False):
    E.validate(record,actor=actor,terminal=terminal)
    row=definition(actor.r,record['source']);meta=record[E.KEY]
    if row is None or record['effect']!=row['payload'] or meta['kind']!='condition':raise ValueError('selected custom condition state required')
    import linked_move_conditions as LINKED
    if LINKED.owns(row):
        result=LINKED.validate_record(actor,record,row=row,terminal=terminal)
        if record['source']=='ability/멸망의바디':
            import perish_body as PERISH_BODY
            PERISH_BODY.validate_record(actor,record)
        return result
    import healing_blocks as HEALING
    if HEALING.is_definition(row):return HEALING.validate_record(actor,record,row=row,terminal=terminal)
    name=row['payload']['condition']
    if meta['capacity']!={'bucket':'condition:'+name,'source':record['source']} or meta['lifetime']!={'boundary':'condition_cure_or_volatile_end'}:raise ValueError('custom condition authority mismatch')
    if not terminal and name not in actor.conditions:raise ValueError('custom condition presence projection missing')
    turn=C.integer(record.get('issued_turn'),'custom condition issue turn',0)
    at=record['at']
    for event in record.get('applications',[]):
        turn=C.integer(event['turn'],'custom condition actual turn',turn+1,actor.custom_conditions.get('combat_turn_serial',0))
        at=C.integer(event['at'],'custom condition actual time',at)
        if event['kind']!='holder_turn_tick' or event['holder_id']!=actor.entity_id:raise ValueError('actual holder turn tick required')
        ticks=max([row['payload']['ticks']]+[n for t,n in row['payload']['typed_ticks'].items() if t in event['types']])
        if event['ticks']!=ticks or event['requested']!=event['tick']*ticks:raise ValueError('custom condition tick policy mismatch')
        C.integer(event['tick'],'actual tick HP',1)
    if terminal and meta['end_event'].get('kind')!='condition_cure':raise ValueError('actual custom condition cure required')
    return True


def turn_start(engine,actor):
    turn=actor.custom_conditions.get('combat_turn_serial',0)
    for record in list(records(actor)):
        validate_record(actor,record)
        import linked_move_conditions as LINKED
        if LINKED.owns(record):
            LINKED.turn_start(engine,actor,record)
            continue
        import healing_blocks as HEALING
        if HEALING.is_record(record):continue
        last=record['applications'][-1]['turn'] if record['applications'] else record['issued_turn']
        if turn<=last:continue
        payload=record['effect'];types=list(actor.types)
        ticks=max([payload['ticks']]+[n for t,n in payload['typed_ticks'].items() if t in types])
        tick=engine.tick(actor)
        event={'kind':'holder_turn_tick','holder_id':actor.entity_id,'turn':turn,
               'at':engine.elapsed_seconds,'types':types,'ticks':ticks,'tick':tick,'requested':tick*ticks}
        # Record the actual start before HP loss can faint and cure the holder.
        record['applications'].append(event)
        engine.lose_tick_hp(actor,ticks,source=record['source'])

