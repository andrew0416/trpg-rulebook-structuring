"""Unspent ordinary trainer level rewards, not automatic Edge/Feature ownership.

Only recorded attained levels issue rights. Character creation, special level
bonuses, retroactive providers and qualified choice spending remain separate.
"""
from copy import deepcopy
from source_context import verified_source

SOURCE='ch02-character-creation/캐릭터-발전'
REFERENCE={'file':'input/ch02-character-creation.md','sha256':'44f0412c27e93730445a544096951925273bc98d3c729b65f4030f155d8dc000'}
KEY='trainer_entitlements'
SKILL_REWARDS={2:3,6:4,12:5}


def _source(rules):
    if rules._selected_rule(SOURCE)!=SOURCE:raise ValueError('selected trainer entitlement source needs its own policy')
    if rules.selection.units[SOURCE]['source'].get('file')!=REFERENCE['file'].removeprefix('input/'):
        raise ValueError('trainer entitlement source mismatch')
    for field in ('mech','effects'):
        if getattr(rules.rulings,field,{}).get(SOURCE):raise ValueError('trainer entitlement override requires an explicit policy')
    verified_source(rules,REFERENCE,label='trainer entitlement')


def validate(actor):
    ledger=actor.spec.get(KEY)
    events=actor.spec.get('trainer_progression_events',{})
    if type(events) is not dict:raise ValueError('trainer progression event mapping required')
    for event_id,event in events.items():
        result=event.get('result') if type(event) is dict else None
        if type(result) is not dict or result.get('request_id')!=event_id or result.get('entity_id')!=actor.entity_id:
            raise ValueError('actual trainer progression result required')
        if actor.kind!='trainer' or type(event_id) is not str or not event_id.strip():
            raise ValueError('trainer event identity required')
        if set(event) not in ({'intent','result'},{'intent','request','result'}) or type(event.get('intent')) is not str or not event['intent']:
            raise ValueError('trainer event fingerprint required')
        for field in ('bank_before','bank_after'):
            if type(result.get(field)) is not int or result[field]<0:raise ValueError('nonnegative trainer event bank required')
        if result.get('kind') not in ('experience','milestone') or result.get('source')!='trainer/experience' or type(result.get('reason')) is not str or not result['reason'].strip():
            raise ValueError('explicit trainer event provenance required')
        before=result.get('level_before');after=result.get('level_after')
        if type(before) is not int or type(after) is not int or before<1 or after<before or result.get('attained_levels')!=list(range(before+1,after+1)):
            raise ValueError('progression attained levels disagree with actual transition')
        if result['kind']=='milestone' and (after!=before+1 or result['bank_after']!=result['bank_before']):
            raise ValueError('milestone event must preserve bank and advance exactly one level')
        if 'request' in event:
            import resolution_transaction as TX
            request=event['request']
            if type(request) is not dict or set(request)!={'kind','amount','reason','entity_id','policy'}:
                raise ValueError('exact trainer event request required')
            if TX.request_fingerprint(request)!=event['intent']:
                raise ValueError('trainer event request changed')
            if any(request[key]!=result[key] for key in ('kind','reason','entity_id')):
                raise ValueError('trainer result disagrees with original request')
            policy=request['policy']
            if type(policy) is not dict or type(policy.get('exp_per_level')) is not int or policy['exp_per_level']<1:
                raise ValueError('positive trainer experience threshold required')
            if result['kind']=='experience':
                amount=request['amount']
                if type(amount) is not int or amount<0:raise ValueError('nonnegative original experience amount required')
                levels,bank=divmod(result['bank_before']+amount,policy['exp_per_level'])
                if after!=before+levels or result['bank_after']!=bank:
                    raise ValueError('trainer result disagrees with original experience calculation')
            elif request['amount'] is not None or policy.get('milestone_levels_bypass_bank') is not True:
                raise ValueError('explicit milestone bank policy required')
    skill_levels=set()
    for event in events.values():
        result=event['result']
        if 'skill_reward_levels' not in result:continue
        expected=[level for level in result['attained_levels'] if level in SKILL_REWARDS]
        if result['skill_reward_levels']!=expected or skill_levels.intersection(expected):
            raise ValueError('skill reward thresholds disagree with unique growth events')
        skill_levels.update(expected)
    if ledger is None:
        if any(event['result'].get('entitlement_ids') for event in events.values()):
            raise ValueError('growth event is missing its ordinary entitlement ledger')
        return
    if actor.kind!='trainer' or type(ledger) is not dict or set(ledger)!={'version','awards'} or type(ledger['version']) is not int or ledger['version']!=1 or type(ledger['awards']) is not dict:
        raise ValueError('invalid trainer entitlement ledger')
    events=actor.spec.get('trainer_progression_events',{})
    for identity,row in ledger['awards'].items():
        if type(row) is not dict or set(row)!={'source','event_id','level','kind','status'}:
            raise ValueError('exact ordinary entitlement record required')
        level=row['level']
        if type(level) is not int or level<2 or identity!='ordinary/level/'+str(level):raise ValueError('ordinary entitlement level identity required')
        if row['source']!=SOURCE or row['kind']!=('edge' if level%2==0 else 'feat') or row['status']!='pending_choice':
            raise ValueError('unsupported ordinary entitlement policy or lifecycle')
        if type(row['event_id']) is not str or row['event_id'] not in events:raise ValueError('actual progression event required for entitlement')
        result=events[row['event_id']]['result']
        if level not in result['attained_levels'] or identity not in result.get('entitlement_ids',[]):
            raise ValueError('entitlement disagrees with attained growth event')
    for event in events.values():
        result=event['result']
        if 'entitlement_ids' not in result:continue  # Legacy growth evidence is not invented reward history.
        expected=['ordinary/level/'+str(level) for level in result['attained_levels']]
        if result['entitlement_ids']!=expected:raise ValueError('growth event entitlement list changed')
        if any(identity not in ledger['awards'] or ledger['awards'][identity]['event_id']!=result['request_id'] for identity in expected):
            raise ValueError('growth event is missing its ordinary entitlement')


def issue(rules,actor,event_id,levels):
    """Called only inside the native progression transaction before its commit."""
    _source(rules);validate(actor)
    if type(levels) is not list or any(type(level) is not int or level<2 for level in levels) or len(set(levels))!=len(levels):
        raise ValueError('distinct attained trainer levels required')
    if not levels:return []
    ledger=actor.spec.setdefault(KEY,{'version':1,'awards':{}})
    ids=[]
    for level in levels:
        identity='ordinary/level/'+str(level)
        row={'source':SOURCE,'event_id':event_id,'level':level,'kind':'edge' if level%2==0 else 'feat','status':'pending_choice'}
        if identity in ledger['awards'] and ledger['awards'][identity]!=row:
            raise ValueError('trainer level entitlement already issued by another event')
        ledger['awards'][identity]=row;ids.append(identity)
    return ids


def pending(engine,actor):
    import world_entities as W
    if W.actor_index(engine).get(actor.entity_id) is not actor or actor.r is not engine.r or actor.kind!='trainer':
        raise ValueError('actual registered trainer required')
    _source(engine.r);validate(actor)
    return [dict(deepcopy(row),entitlement_id=identity) for identity,row in actor.spec.get(KEY,{}).get('awards',{}).items()]


def skill_rewards(engine,actor):
    """Read observed restricted rewards; absence never fabricates past awards.

    max_rank is the highest rank this specific free reward may produce, not
    the actor's general rank cap or certification of a candidate Skill Edge.
    """
    import world_entities as W
    if W.actor_index(engine).get(actor.entity_id) is not actor or actor.r is not engine.r or actor.kind!='trainer':
        raise ValueError('actual registered trainer required')
    _source(engine.r);validate(actor)
    return [{'entitlement_id':'skill/level/'+str(level),'event_id':event_id,
             'source':SOURCE,'level':level,'kind':'skill_edge','count':1,
             'max_rank':SKILL_REWARDS[level],'excluded_rank':SKILL_REWARDS[level]+1,
             'status':'pending_qualified_choice'}
            for event_id,event in actor.spec.get('trainer_progression_events',{}).items()
            for level in event['result'].get('skill_reward_levels',[])]
