"""Actual shared Tutor Point payments for source-owned grants.

The host supplies already-adjudicated acquisition and optional refund allocation.
This common primitive does not grant class eligibility or infer missing Edge rules.
Version 2 receipts preserve the acquisition request to validate live provenance.
Legacy version 1 receipts remain readable with their original grant-only evidence;
missing historical provenance is never retroactively asserted or fabricated.
"""
from copy import deepcopy
import resolution_transaction as TX

class RefundAllocationPending(ValueError):
    """Actual partial refund needs an explicit allocation of the original debit."""
    pass


def _text(value):
    if type(value) is not str or not value.strip():raise ValueError('nonempty payment identity/reason required')
    return value


def _points(value):
    if type(value) is not int or value<0:raise ValueError('nonnegative whole Tutor Points required')
    return value


def _allocation(value,children,paid):
    # A zero payment has exactly one nonnegative allocation; no ruling is inferred.
    if value is None:return {child:0 for child in children} if paid==0 else None
    if type(value) is not dict or set(value)!=set(children):raise ValueError('allocation must cover exactly every payment child')
    if sum(_points(x) for x in value.values())!=paid:raise ValueError('allocation must sum to actual group payment')
    return deepcopy(value)


def _actor(engine,actor):
    import world_entities as W
    if actor.r is not engine.r or W.actor_index(engine).get(actor.entity_id) is not actor:
        raise ValueError('actual registered payment recipient required')
    if actor.kind!='pokemon':raise ValueError('Tutor Point grant recipient must be a Pokemon')


def validate(actor):
    state=actor.spec.get('state_grants')
    if state is None:return
    if type(state) is not dict or type(state.get('sources',{})) is not dict:raise ValueError('source grant ledger must be a mapping')
    payments=state.get('payments',{})
    if not isinstance(payments,dict):raise ValueError('payment ledger must be a mapping')
    seen=set()
    for identity,row in payments.items():
        _text(identity)
        if type(row) is not dict or type(row.get('version')) is not int or row['version'] not in (1,2):
            raise ValueError('unsupported grant payment')
        fields={'version','intent','paid','children','allocation','refunds','acquisition','grant_snapshot'}
        if row['version']==2:fields.add('request')
        if set(row)!=fields:raise ValueError('unsupported grant payment fields')
        request=row.get('request')
        if row['version']==2:
            if type(request) is not dict or set(request)!={'group_id','grants','points','rule_id','reason','allocation','owner_id','lifetime'}:
                raise ValueError('complete acquisition request required')
            if TX.request_fingerprint(request)!=row['intent']:
                raise ValueError('acquisition request changed')
            if request['group_id']!=identity or type(request['points']) is not int or request['points']!=row['paid']:
                raise ValueError('request disagrees with actual group payment')
            if type(request['grants']) is not list or any(type(g) is not dict for g in request['grants']):
                raise ValueError('acquisition grant declarations required')
            if [g.get('source_id') for g in request['grants']]!=row['children']:
                raise ValueError('request disagrees with payment children')
        _text(row['intent'])
        if type(row['refunds']) is not list:raise ValueError('refund history must be a list')
        paid=_points(row['paid']);children=row['children']
        if type(children) is not list or not children or any(type(x) is not str or not x for x in children) or len(set(children))!=len(children):raise ValueError('distinct payment children required')
        for child in children:_text(child)
        if seen.intersection(children):raise ValueError('grant child belongs to multiple payments')
        receipt=row['acquisition']
        if type(receipt) is not dict or set(receipt)!={'group_id','sources','paid','rule_id'} or receipt['group_id']!=identity or receipt['sources']!=children or type(receipt['paid']) is not int or receipt['paid']!=paid:raise ValueError('acquisition receipt disagrees with actual payment')
        _text(receipt['rule_id'])
        if request is not None and request['rule_id']!=receipt['rule_id']:
            raise ValueError('request disagrees with acquisition rule')
        if type(row['grant_snapshot']) is not dict or set(row['grant_snapshot'])!=set(children):raise ValueError('payment requires exact acquired grant snapshots')
        seen.update(children);allocation=_allocation(row['allocation'],children,paid)
        if request is not None and request['allocation'] is not None and allocation!=request['allocation']:
            raise ValueError('original explicit payment allocation changed')
        ended=set();refunded=0
        for receipt in row['refunds']:
            if type(receipt) is not dict or set(receipt) not in ({'sources','amount','reason'},{'sources','amount','reason','refund_mode'}):raise ValueError('invalid payment refund receipt')
            ids=receipt['sources'];amount=_points(receipt['amount']);_text(receipt['reason'])
            if type(ids) is not list or not ids or any(type(x) is not str or not x for x in ids) or len(set(ids))!=len(ids) or not set(ids)<=set(children) or ended.intersection(ids):
                raise ValueError('invalid or duplicate payment refund children')
            expected=paid if allocation is None and set(ids)==set(children) else sum(allocation[x] for x in ids) if allocation is not None else None
            if 'refund_mode' in receipt:
                if receipt['refund_mode']!='none':raise ValueError('unknown refund mode')
                expected=0
            if expected is None or amount!=expected:raise ValueError('refund lacks actual payment allocation')
            ended.update(ids);refunded+=amount
        if refunded>paid:raise ValueError('refund exceeds actual payment')
        for child in children:
            source=state.get('sources',{}).get(child)
            if source is not None and request is not None:
                declared=next(g for g in request['grants'] if g['source_id']==child)
                expected={'kind':'feature','owner_id':request['owner_id'],
                          'lifetime':request['lifetime'],'rule_id':request['rule_id'],
                          'tutor_points':0,'learning_route':declared.get('learning_route')}
                if any(type(source.get(key)) is not type(value) or source.get(key)!=value for key,value in expected.items()):
                    raise ValueError('paid grant provenance changed without a new acquisition')
            if request is not None:
                declared=next(g for g in request['grants'] if g['source_id']==child)
                if declared['field']=='stats':
                    contributions={field:entry['sources'][child] for field,entry in state.get('stat_sources',{}).items() if child in entry['sources']}
                    expected={} if child in ended else {declared['stat']:{'0':{'delta':declared['delta'],'minimum':declared['minimum']}}}
                    if contributions!=expected:raise ValueError('paid stat contribution changed without a new acquisition')
            if child in ended:
                if source is not None:raise ValueError('refunded child still has active grant')
            elif source is None or source.get('payment_id')!=identity or source.get('tutor_points')!=0:
                raise ValueError('active payment child disagrees with actual grant')
            elif source.get('grants')!=row['grant_snapshot'][child]:
                raise ValueError('paid grant changed without a new acquisition')
            elif source.get('grants',{}).get('moves') and (source.get('learning_route') not in ('taught','granted') or (source.get('learning_route')=='taught' and paid==0)):
                raise ValueError('grouped move requires its explicit learning route')
    for child,source in state.get('sources',{}).items():
        if 'payment_id' in source and (source['payment_id'] not in payments or child not in payments[source['payment_id']]['children']):
            raise ValueError('grant has no matching actual payment')
    receipts=state.get('payment_refunds',{})
    if type(receipts) is not dict:raise ValueError('refund request ledger must be a mapping')
    for request,receipt in receipts.items():
        _text(request)
        if type(receipt) is not dict or set(receipt)!={'intent','result'}:raise ValueError('invalid refund request receipt')
        _text(receipt['intent']);result=receipt['result']
        if type(result) is not dict or set(result)!={'sources','tutor_points_refunded','reason'}:raise ValueError('invalid refund request result')
        ids=result['sources'];_text(result['reason']);amount=_points(result['tutor_points_refunded'])
        if type(ids) is not list or not ids or any(type(x) is not str for x in ids) or len(set(ids))!=len(ids):raise ValueError('invalid refunded request sources')
        relevant=[event for group in payments.values() for event in group['refunds'] if set(event['sources']).intersection(ids)]
        if {child for event in relevant for child in event['sources']}!=set(ids) or sum(event['amount'] for event in relevant)!=amount or any(event['reason']!=result['reason'] for event in relevant):
            raise ValueError('refund request disagrees with actual settlements')
    if payments:_points(actor.spec.get('tutor_points'))


def quote(actor,sources,allocations=None,*,refund_mode='actual'):
    """Pure refund plan. Partial unknown allocations stay unresolved."""
    if refund_mode not in ('actual','none'):raise ValueError('explicit actual or no-refund policy required')
    validate(actor);state=actor.spec.get('state_grants',{});allocations={} if allocations is None else allocations
    if type(allocations) is not dict:raise ValueError('explicit group allocation mapping required')
    groups={}
    for source in sources:
        identity=state.get('sources',{}).get(source,{}).get('payment_id')
        if identity is not None:groups.setdefault(identity,[]).append(source)
    if set(allocations)-set(groups):raise ValueError('allocation belongs to an unselected payment')
    plans=[]
    for identity,ids in groups.items():
        row=state['payments'][identity];allocation=row['allocation']
        if identity in allocations:
            proposed=_allocation(allocations[identity],row['children'],row['paid'])
            if allocation is not None and proposed!=allocation:raise ValueError('recorded refund allocation cannot change')
            allocation=proposed
        if refund_mode=='none':amount=0
        elif allocation is None:
            if set(ids)!=set(row['children']):raise RefundAllocationPending('explicit allocation required for a partial group refund')
            amount=row['paid']
        else:amount=sum(allocation[x] for x in ids)
        plans.append({'group_id':identity,'sources':sorted(ids),'amount':amount,'allocation':deepcopy(allocation)})
        if refund_mode=='none':plans[-1]['refund_mode']='none'
    return plans


def commit(actor,plans,reason):
    from acquisition_ledger import AcquisitionLedger
    AcquisitionLedger(actor).commit_refunds(plans,reason)


def settle_sources(engine,actor,sources,plans,reason,*,legacy_refund=0):
    """Settle admitted withdrawals inside the caller's staged transition.

    Callers own cause policy, allocation, pending decisions and replay receipts.
    Legacy owner-bound sources may add their separately evidenced fixed refund.
    This primitive opens no nested transaction and creates no second ledger.
    """
    import state_grants as G
    _points(legacy_refund)
    G._revoke_sources(actor,sources,engine,
        _settled_payment_ids=tuple(plan['group_id'] for plan in plans))
    commit(actor,plans,reason)
    amount=legacy_refund+sum(plan['amount'] for plan in plans)
    if amount:actor.spec['tutor_points']=actor.spec.get('tutor_points',0)+amount
    validate(actor)
    return amount


def acquire(engine,actor,group_id,grants,points,*,rule_id,reason,allocation=None,owner_id=None,lifetime=None):
    """Debit once and commit an application-adjudicated native grant group."""
    import state_grants as G
    _actor(engine,actor);_text(group_id);_text(rule_id);_text(reason);_points(points)
    if type(grants) is not list or not grants:raise ValueError('nonempty declared grant group required')
    children=[]
    for row in grants:
        if type(row) is not dict or row.get('field') not in (*G.LIST_FIELDS,'stats','skill_modifier','native_poke_edge'):raise ValueError('supported source-owned list grant required')
        fields={'source_id','field','skill','delta'} if row['field']=='skill_modifier' else {'source_id','field','stat','delta','minimum'} if row['field']=='stats' else {'source_id','field','value','learning_route'} if row['field']=='moves' else {'source_id','field','value'}
        if set(row)!=fields:raise ValueError('exact group grant fields and explicit move learning route required')
        if row['field']=='moves' and (row['learning_route'] not in ('taught','granted') or (row['learning_route']=='taught' and points==0)):
            raise ValueError('explicit paid taught route or granted route required')
        children.append(_text(row['source_id']))
        if row['field']=='skill_modifier':
            import skill_modifiers as SKILL
            SKILL.skill_id(engine.r.skill_policy,row['skill'],required=True)
            if type(row['delta']) is not int:raise ValueError('whole-number skill modifier required')
        elif row['field']=='stats':
            if row['stat'] not in actor.stats or type(row['delta']) is not int or (row['minimum'] is not None and type(row['minimum']) is not int):
                raise ValueError('explicit known stat, integer delta and optional integer minimum required')
        else:_text(row['value'])
    if len(set(children))!=len(children):raise ValueError('distinct payment children required')
    allocation=_allocation(allocation,children,points)
    intent={'group_id':group_id,'grants':grants,'points':points,'rule_id':rule_id,'reason':reason,
            'allocation':allocation,'owner_id':owner_id,'lifetime':lifetime}
    records=actor.spec.get(G.KEY,{}).get('payments',{})
    validate(actor)
    replay=TX.replay_result(records,group_id,intent,fingerprint_field='intent')
    if replay is not None:return deepcopy(replay['acquisition'])
    if engine.r._selected_rule(rule_id)!=rule_id:raise ValueError('selected acquisition rule requires its own grant group')
    if lifetime not in (None,'owner_bound','your_pokemon'):raise ValueError('unsupported grouped grant lifetime')
    if owner_id is not None:
        import world_entities as W
        owner=W.actor_index(engine).get(owner_id)
        if owner is None or owner.kind!='trainer' or owner.r is not engine.r:raise ValueError('actual source owner required')
    if lifetime is not None and (owner_id is None or actor.spec.get('trainer_id')!=owner_id):raise ValueError('owner-bound group requires actual Pokemon ownership')
    reserved={child for row in records.values() for child in row['children']}
    if any(child in actor.spec.get(G.KEY,{}).get('sources',{}) or child in reserved for child in children):raise ValueError('grant child identity already used')
    balance=_points(actor.spec.get('tutor_points'))
    if balance<points:raise ValueError('insufficient Tutor Points')
    def apply(e,c):
        for row in grants:
            if row['field']=='native_poke_edge':
                if row['value']!=row['source_id'] or len([edge for edge in c.spec.get('learned_poke_edges',[]) if edge.get('mentor_source_id')==row['value'] and edge.get('status')=='active'])!=1:
                    raise ValueError('one actual active native Poke Edge contribution required')
                G._source(c,row['source_id'],'feature',rule_id=rule_id,owner_id=owner_id,lifetime=lifetime,tutor_points=0)
            elif row['field']=='skill_modifier':
                G.skill_modifier(c,row['skill'],row['delta'],row['source_id'],'feature',rule_id=rule_id,owner_id=owner_id,lifetime=lifetime)
            elif row['field']=='stats':
                G._source(c,row['source_id'],'feature',rule_id=rule_id,owner_id=owner_id,lifetime=lifetime,tutor_points=0)
                G.stat(c,row['stat'],row['delta'],row['source_id'],minimum=row['minimum'])
            else:
                value=row['value']
                if row['field']=='abilities' and value.startswith('ability/'):
                    selected=e.r.select_source_definition(value)
                    if selected['selected_id']!=value:raise ValueError('ability replacement requires its own grant choice')
                    name=e.r.selection.units[value]['title']
                    if e.r.selection.resolve_name(name,('ability/',))!=value:
                        raise ValueError('exact ability grant needs an unambiguous native registration')
                    value=name
                G.grant(c,row['field'],value,row['source_id'],'feature',rule_id=rule_id,owner_id=owner_id,lifetime=lifetime,tutor_points=0)
                if row['field']=='abilities':G.ensure_ability(e,c,value)
        c.spec['tutor_points']-=points
        receipt={'group_id':group_id,'sources':children,'paid':points,'rule_id':rule_id}
        c.acquisitions.record_payment(group_id, {'version':2,'intent':TX.request_fingerprint(intent),'request':deepcopy(intent),
            'paid':points,'children':children,'allocation':allocation,'refunds':[],'acquisition':deepcopy(receipt),
            'grant_snapshot':{child:deepcopy(G.state(c)['sources'][child]['grants']) for child in children}})
        for row in grants:
            source=G.state(c)['sources'][row['source_id']]
            source['payment_id']=group_id
            if row['field']=='moves':source['learning_route']=row['learning_route']
        import move_state as MOVES
        MOVES.validate_spec(e.r,c.spec)
        validate(c)
        return deepcopy(receipt)
    return G.transition(engine,actor,apply)


def refund(engine,actor,sources,*,request_id,reason,allocations=None,refund_mode='actual'):
    import state_grants as G
    _actor(engine,actor);_text(request_id);_text(reason)
    if type(sources) is not list or not sources or any(type(x) is not str or not x for x in sources) or len(set(sources))!=len(sources):raise ValueError('distinct source identities required')
    sources=sorted(sources)
    intent={'sources':sources,'reason':reason,'allocations':allocations}
    if refund_mode not in ('actual','none'):raise ValueError('unknown refund mode')
    if refund_mode!='actual':intent['refund_mode']=refund_mode
    validate(actor)
    replay=TX.replay_result(actor.spec.get(G.KEY,{}).get('payment_refunds',{}),request_id,intent,fingerprint_field='intent')
    if replay is not None:return replay['result']
    if any(x not in actor.spec.get(G.KEY,{}).get('sources',{}) for x in sources):raise ValueError('actual active grant sources required')
    plans=quote(actor,sources,allocations,refund_mode=refund_mode)
    if set(sources)!={x for plan in plans for x in plan['sources']}:raise ValueError('group refund requires payment-backed sources')
    amount=sum(plan['amount'] for plan in plans)
    def apply(e,c):
        settle_sources(e,c,sources,plans,reason)
        result={'sources':sources,'tutor_points_refunded':amount,'reason':reason}
        c.acquisitions.record_refund(request_id, {'intent':TX.request_fingerprint(intent),'result':deepcopy(result)})
        validate(c)
        return result
    return G.transition(engine,actor,apply)
