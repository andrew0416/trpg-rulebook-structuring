"""Temporary AP funding over the ordinary account and existing count lifetime.

The caller selects funding priority and the GM's binding-expiry policy; neither
is asserted as a rule printed by the temporary-AP source.
"""
from copy import deepcopy
from contextvars import ContextVar
_FUNDING_END=ContextVar("temporary_ap_funding_end",default=None)
import common_checks as C
import combat_timing as T
import effect_instances as E

KIND='temporary_ap'

def live(actor):
    return [r for r in T.records(actor) if r.get(E.KEY,{}).get('kind')==KIND]

def all_records(actor):
    return live(actor)+[r for r in actor.spec.get('effect_instance_history',[]) if r.get(E.KEY,{}).get('kind')==KIND]

def policy(value):
    if type(value) is not dict or set(value)!={'priority','binding_expiry','reason'}:
        raise ValueError('explicit temporary AP funding priority, binding expiry and GM reason required')
    if value['priority'] not in ('temporary_first','ordinary_first') or value['binding_expiry'] not in ('end_effect','require_decision'):
        raise ValueError('unsupported explicit temporary AP funding policy')
    E.text(value['reason'],'GM temporary AP funding reason')
    return deepcopy(value)

def remaining(row):
    return row['effect']['amount']-sum(x['amount'] for x in row['payments'] if x['state'] not in ('released','refunded'))

def validate_record(actor,row,*,terminal=False):
    E.validate(row,actor=actor,terminal=terminal)
    if row[E.KEY]['kind']!=KIND or row['effect'].get('kind')!=KIND:
        raise ValueError('temporary AP family changed')
    C.integer(row['effect'].get('amount'),'temporary AP grant',1)
    policy(row['effect'].get('funding'))
    life=row[E.KEY]['lifetime'];born=C.integer(row.get('issued_round'),'temporary AP issuing round',0)
    if life['boundary']=='initiative_count':
        if born<1 or life!={'boundary':'initiative_count','round':born+1,'count':row.get('issued_count')} or row.get('count_deadline')!=[born+1,row['issued_count']] or row.get('encounter_end') is not True:
            raise ValueError('temporary AP must expire at the same count one round later')
    elif life['boundary']=='elapsed_time':
        plan=row.get('elapsed_lifetime',{})
        if plan.get('declaration')!={'duration':{'seconds':10}} or plan.get('started_at')!=row['at'] or plan.get('end_at')!=row['at']+10 or life!={'boundary':'elapsed_time','end_at':plan['end_at']} or 'count_deadline' in row:
            raise ValueError('outside-combat one-round AP must use its actual ten-second duration')
    else:raise ValueError('unsupported temporary AP lifetime')
    if row[E.KEY]['capacity']!={'bucket':'independent','source':row['source']} or row.get('manual_end') is not False:
        raise ValueError('temporary AP capacity or scene ending changed')
    if type(row.get('payments')) is not list:raise ValueError('temporary AP payment history required')
    for p in row['payments']:
        if type(p) is not dict or set(p)!={'mode','amount','instance_id','state','binding_owner'} or p['mode'] not in ('spend','drain','bind'):
            raise ValueError('exact temporary AP payment required')
        C.integer(p['amount'],'temporary AP payment',1)
        if p['mode']=='bind':
            E.text(p['instance_id'],'temporary AP actual binding')
            if p['binding_owner'] not in ('bound_ap','class_passive_combat','combat_precision_features','commander_orders','rune_master','arcanist'):raise ValueError('temporary AP actual binding owner changed')
            if p['state'] not in ('bound','released'):raise ValueError('temporary binding state changed')
        elif p['instance_id'] is not None or p['state'] not in (('spent','refunded') if p['mode']=='spend' else ('spent',)) or p['binding_owner'] is not None:raise ValueError('temporary Drain cannot be recovered')
    if remaining(row)<0:raise ValueError('temporary AP overspent')
    if terminal and any(p['state']=='bound' for p in row['payments']):raise ValueError('temporary funding ended with a live binding')
    # Each native producer supplies its authenticated issuance link.
    if row['source']=='feat/포획-추진력':
        import captured_momentum as CM
        CM.validate_effect_origin(actor,row)
    elif row['source']=='feat/행동의-순간':
        import moment_of_action as MOMENT
        MOMENT.validate_effect_origin(actor,row)
    else:raise ValueError('temporary AP requires a registered actual source adapter')
    return True

def grant(engine,actor,*,source,amount,origin,funding,issuer=None):
    combat=engine.encounter_active
    if combat and engine.round_start_seconds is None:raise ValueError('combat temporary AP requires an actual open round')
    count=T.current(engine) if combat else None;funding=policy(funding)
    if any(r['effect']['funding']!=funding for r in live(actor)):
        raise ValueError('overlapping temporary AP grants need the same explicit funding policy')
    import effect_lifetime_policy as LIFE
    duration=LIFE.prepare(engine,actor,actor,{'duration':{'seconds':10}},source)[LIFE.KEY] if not combat else None
    lifetime={'boundary':'initiative_count','round':engine.round_no+1,'count':count} if combat else {'boundary':'elapsed_time','end_at':duration['end_at']}
    row=E.create(engine,actor,kind=KIND,source=source,payload={'kind':KIND,'amount':amount,'funding':funding},
        capacity={'bucket':'independent','source':source},lifetime=lifetime,applied_by=actor if issuer is None else issuer)
    row.update(issued_round=engine.round_no,manual_end=False,payments=[],origin=deepcopy(origin))
    if issuer is not None:row['issuer_actor']=issuer
    if combat:row.update(issued_count=count,count_deadline=[engine.round_no+1,count],encounter_end=True)
    else:row['elapsed_lifetime']=duration
    T.install(engine,actor,row)
    return row

def available(actor):
    for row in live(actor):validate_record(actor,row)
    return sum(remaining(row) for row in live(actor))

def bound_amount(actor,instance_id=None):
    return sum(p['amount'] for row in live(actor) for p in row['payments'] if p['state']=='bound' and (instance_id is None or p['instance_id']==instance_id))

def charge(actor,amount,*,ordinary_available,mode,instance_id,binding_owner=None):
    rows=live(actor)
    if not rows:return amount
    capacity=available(actor)
    if any(row['effect']['funding']!=rows[0]['effect']['funding'] for row in rows):raise ValueError('temporary AP funding policies disagree')
    funding=rows[0]['effect']['funding']
    used=min(amount,capacity) if funding['priority']=='temporary_first' else max(0,amount-ordinary_available)
    if used>capacity:raise ValueError('insufficient temporary funding')
    if used and mode=='bind' and binding_owner not in ('bound_ap','class_passive_combat','combat_precision_features','commander_orders','rune_master','arcanist'):
        raise ValueError('temporary AP funding requires a supported actual bound-effect owner before payment')
    if used and mode=='bind' and funding['binding_expiry']=='require_decision':
        raise ValueError('temporary AP binding requires an explicit funding-loss ending policy before activation')
    left=used
    for row in rows:
        take=min(left,remaining(row))
        if take:row['payments'].append({'mode':mode,'amount':take,'instance_id':instance_id,'state':'bound' if mode=='bind' else 'spent','binding_owner':binding_owner if mode=='bind' else None})
        left-=take
    return amount-used

def refund_spend(actor, references, *, expected):
    if type(references)is not list or type(expected)is not int or expected<0:raise ValueError('actual temporary spend receipt required')
    rows={r['id']:r for r in live(actor)};payments=[];seen=set()
    for ref in references:
        if type(ref)is not dict or set(ref)!={'grant_id','index','amount'} or type(ref['index'])is not int or ref['index']<0:
            raise ValueError('exact temporary AP spend reference required')
        row=rows.get(ref['grant_id']);key=(ref['grant_id'],ref['index'])
        if row is None or ref['index']>=len(row['payments']) or key in seen:raise ValueError('live distinct temporary funding receipt required')
        validate_record(actor,row);payment=row['payments'][ref['index']]
        if payment['mode']!='spend' or payment['state']!='spent' or payment['amount']!=ref['amount']:
            raise ValueError('one actual unrefunded temporary AP spend required')
        payments.append(payment);seen.add(key)
    if sum(p['amount'] for p in payments)!=expected:raise ValueError('temporary AP refund amount differs from actual spend')
    for payment in payments:payment['state']='refunded'

def release(actor,instance_id):
    for row in live(actor):
        for payment in row['payments']:
            if payment['state']=='bound' and payment['instance_id']==instance_id:payment['state']='released'

def before_expire(engine,actor,row):
    """End the actual funded effect through its owner before removing funding."""
    import bound_ap as B
    validate_record(actor,row)
    ids={p['instance_id'] for p in row['payments'] if p['state']=='bound'}
    for uid in ids:
        if row['effect']['funding']['binding_expiry']!='end_effect':raise ValueError('explicit temporary binding-loss policy required')
        owner=next(p['binding_owner'] for p in row['payments'] if p['instance_id']==uid and p['state']=='bound')
        binding,target,rule=native_binding(engine,actor,uid,owner)
        if owner=='arcanist':
            __import__('arcanist').end_binding(engine,actor,binding)
            continue
        if owner=='rune_master':
            __import__('rune_master').end_binding(engine,actor,binding)
            continue
        if owner=='commander_orders':
            __import__('commander_orders').end_binding(engine,actor,binding)
            continue
        if owner=='class_passive_combat':
            import class_passive_combat as CP
            CP._unbind(engine,target,rule,actor,binding)
            continue
        if owner=='combat_precision_features':
            import combat_precision_features as CP
            CP._unbind(engine,target,binding)
            continue
        event={'kind':'temporary_ap_expired','source':row['source'],'grant_id':row['id'],'round':engine.round_no}
        if binding['adapter']=='native_effect_bundle_v1':
            B._live_bundle(engine,actor,uid,binding)
            token=_FUNDING_END.set((actor.entity_id,uid,row['id']))
            try:
                for part in list(binding['components']):T.expire(engine,part['holder'],part['record'],ending='ended',event=event)
            finally:_FUNDING_END.reset(token)
        elif binding['adapter']=='single_damage_roll_modifier_v1':
            mod=binding['modifier']
            if mod!=binding['expected_modifier'] or sum(m is mod for m in actor.modifiers)!=1:raise ValueError('temporary AP bound modifier changed')
            actor.modifiers[:]=[m for m in actor.modifiers if m is not mod]
            actor.ap_account.release_binding(uid,expected_amount=binding['amount'])
            binding.update(state='ended',end_event=event)
        else:raise ValueError('unsupported temporary AP bound effect owner')

def validate_world(engine,index):
    import moment_of_action as MOMENT
    MOMENT.validate_world(engine,index)
    for actor in index.values():
        for row in all_records(actor):
            active=row in live(actor);validate_record(actor,row,terminal=not active)
            if active and row[E.KEY]['lifetime']['boundary']=='initiative_count' and (not engine.encounter_active or engine.round_no>row['issued_round']+1):raise ValueError('temporary AP lifetime passed without expiry')
            if active and row[E.KEY]['lifetime']['boundary']=='elapsed_time' and row['elapsed_lifetime']['end_at']<=engine.elapsed_seconds:raise ValueError('temporary AP duration passed without expiry')
            for payment_index,p in enumerate(row['payments']):
                if p['state']=='bound':
                    if actor.spec.get('ap_bound',{}).get(p['instance_id'],0)<bound_amount(actor,p['instance_id']):raise ValueError('temporary AP binding has no actual account reservation')
                    native_binding(engine,actor,p['instance_id'],p['binding_owner'])
                elif p['state']=='refunded':
                    __import__('arcanist').validate_temporary_refund(engine,actor,row,payment_index)


def boundary(engine,event):
    if event!='time_advanced':return
    for actor in list(getattr(engine,'_time_actors',())):
        for row in list(live(actor)):
            if row.get('elapsed_lifetime',{}).get('end_at',float('inf'))<=engine.elapsed_seconds:
                T.expire(engine,actor,row,event={'kind':'duration_elapsed','at':engine.elapsed_seconds})

def next_interval(engine,end_at):
    deadlines=[row['elapsed_lifetime']['end_at'] for actor in getattr(engine,'_time_actors',()) for row in live(actor)
               if 'elapsed_lifetime' in row and engine.elapsed_seconds<row['elapsed_lifetime']['end_at']<end_at]
    return min([end_at,*deadlines])-engine.elapsed_seconds


def funding_ending(actor,instance_id,event):
    identity=event.get('grant_id')
    if event.get('kind')!='temporary_ap_expired' or _FUNDING_END.get()!=(actor.entity_id,instance_id,identity):return False
    rows=[row for row in live(actor) if row['id']==identity]
    if len(rows)!=1:return False
    row=rows[0];validate_record(actor,row)
    return row['effect']['funding']['binding_expiry']=='end_effect' and event.get('source')==row['source'] and any(
        p['mode']=='bind' and p['state']=='bound' and p['instance_id']==instance_id and p['binding_owner']=='bound_ap' for p in row['payments'])

def preflight_binding(actor,amount,binding_owner):
    rows=live(actor)
    if not rows:return
    capacity=available(actor);ordinary=actor.ap_account.available()-capacity
    funding=rows[0]['effect']['funding']
    used=min(amount,capacity) if funding['priority']=='temporary_first' else max(0,amount-ordinary)
    if used and (binding_owner not in ('bound_ap','class_passive_combat','combat_precision_features','commander_orders','rune_master','arcanist') or funding['binding_expiry']!='end_effect'):
        raise ValueError('temporary AP binding requires supported actual owner and explicit funding-loss policy before action cost')


def native_binding(engine,actor,uid,owner):
    """Resolve the same actual native owner for restore and funding-loss expiry."""
    if owner=='arcanist':return __import__('arcanist').binding(engine,actor,uid),actor,None
    if owner=='rune_master':return __import__('rune_master').binding(engine,actor,uid),actor,None
    if owner=='bound_ap':
        import bound_ap as B
        binding=getattr(actor,'_ap_bound_effects',{}).get(uid)
        if binding is None or binding.get('state')!='active' or binding.get('owner') is not actor or actor.spec.get('ap_bound',{}).get(uid)!=binding.get('amount'):
            raise ValueError('temporary AP binding owner does not match its actual native producer')
        if binding['adapter']=='native_effect_bundle_v1':B._live_bundle(engine,actor,uid,binding)
        elif binding['adapter']=='single_damage_roll_modifier_v1':
            if binding['modifier']!=binding['expected_modifier'] or sum(m is binding['modifier'] for m in actor.modifiers)!=1:raise ValueError('temporary AP bound modifier producer changed')
        else:raise ValueError('unsupported actual bound AP producer')
        return binding,None,None
    import world_entities as W
    found=[]
    for target in W.actor_index(engine).values():
        if owner=='class_passive_combat':
            import class_passive_combat as CP
            state=CP._state(target)
            for rule,row in (state or {}).get('sustains',{}).items():
                if row.get('instance')==uid:
                    actual=CP._active(engine,target,rule)
                    if actual is not None and actual[0] is actor:found.append((actual[1],target,rule))
        elif owner=='combat_precision_features':
            import combat_precision_features as CP
            if target.custom_conditions.get(CP.KEY,{}).get('instance')==uid:
                actual=CP.binding(engine,target)
                if actual is not None and actual['owner'] is actor:found.append((actual,target,None))
        elif owner=='commander_orders':
            import commander_orders as CP
            for row in CP.live(engine,target,CP.BRACE):
                if row['id']==uid and row['issuer_id']==actor.entity_id:found.append((row,target,CP.BRACE))
        else:raise ValueError('unknown temporary AP binding owner')
    if len(found)!=1:raise ValueError('temporary AP binding owner does not match its actual native producer')
    return found[0]

def has_duration(engine):
    return any('elapsed_lifetime' in row for actor in getattr(engine,'_time_actors',()) for row in live(actor))
