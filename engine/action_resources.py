"""Shared next-action losses, preserving native source-owned storage.

A loss is not an action taken: paying it creates no activation or heavy-injury
trigger. Overlapping native debts need an explicit conjunction policy.
"""
KINDS=('standard','shift','swift')
TURN_LOCK='_next_turn_action_lock'


def turn_lock(actor, engine=None):
    row=actor.spec.get(TURN_LOCK)
    if row is None:return None
    if (type(row) is not dict or set(row)!={'source','instance_ids','scheduled_round','phase','active_round'}
            or row['source']!='ch09-equipment/manual-handoff' or actor.kind!='pokemon'
            or row['phase'] not in ('pending','active')
            or type(row['scheduled_round']) is not int or row['scheduled_round']<0
            or type(row['instance_ids']) is not list or not row['instance_ids']
            or any(not isinstance(x,str) or not x for x in row['instance_ids'])
            or len(set(row['instance_ids']))!=len(row['instance_ids'])):
        raise ValueError('invalid next-turn handoff action lock')
    active=row['active_round']
    if ((row['phase']=='pending' and active is not None) or
            (row['phase']=='active' and (type(active) is not int or active<row['scheduled_round']))):
        raise ValueError('invalid next-turn action lock boundary')
    if engine is not None:
        if row['scheduled_round']>engine.round_no or (active is not None and active>engine.round_no):
            raise ValueError('next-turn action lock is from the future')
        if any(x not in engine._physical_objects for x in row['instance_ids']):
            raise ValueError('next-turn action lock needs its actual handoff objects')
        if active is not None and (engine._active_turn_actor is not actor or active!=engine.round_no):
            raise ValueError('active action lock has no matching open owner turn')
    return row


def schedule_turn_lock(engine, actor, instance_id):
    row=turn_lock(actor,engine)
    if row is not None and row['phase']=='active':
        raise ValueError('handoff during the already locked turn needs a separate next-turn occurrence')
    if row is None:
        row=dict(source='ch09-equipment/manual-handoff',instance_ids=[],scheduled_round=engine.round_no,phase='pending',active_round=None)
        actor.spec[TURN_LOCK]=row
    if instance_id not in row['instance_ids']:row['instance_ids'].append(instance_id)
    turn_lock(actor,engine)


def begin_turn_lock(engine, actor):
    row=turn_lock(actor,engine)
    if row is not None:
        row.update(phase='active',active_round=engine.round_no)


def close_turn_lock(engine, actor):
    row=turn_lock(actor,engine)
    if row is not None and row['phase']=='active':actor.spec.pop(TURN_LOCK)


def action_locked(actor):
    row=turn_lock(actor)
    return row is not None and row['phase']=='active'


def loss(value):
    if type(value) is not dict or not value or any(k not in KINDS or type(v) is not int or v<=0 for k,v in value.items()):
        raise ValueError('action loss requires positive whole known action amounts')
    return dict(value)


def subtract(budget,owed):
    if type(budget) is not dict or any(type(budget.get(k)) is not int or budget[k]<0 for k in KINDS):
        raise ValueError('actual nonnegative action budget required')
    planned=dict(budget)
    if owed:
        for kind,amount in loss(owed).items():planned[kind]=max(0,planned[kind]-amount)
    return planned


def pending(actor):
    import exhaust_moves as EXHAUST
    EXHAUST.validate(actor)
    recipient=getattr(actor,'pending_action_loss',None)
    result={} if recipient is None else loss(recipient)
    burrow=actor.spec.get('_burrow',{}).get('standard_debt',False)
    if type(burrow) is not bool:raise ValueError('Burrow debt must be boolean')
    if burrow:
        if result.get('standard'):raise ValueError('Burrow upkeep debt and another next-Standard loss require an explicit conjunction ruling')
        result['standard']=1
    return result


def plan_debt(actor,owed):
    """Check a recipient loss before its producer spends or applies effects."""
    owed=loss(owed)
    existing=getattr(actor,'pending_action_loss',None)
    if existing is not None and loss(existing)!=owed:
        raise ValueError('different pending action losses require a conjunction policy')
    if owed.get('standard') and actor.spec.get('_burrow',{}).get('standard_debt'):
        raise ValueError('Burrow and recipient action losses require a conjunction policy')
    return owed


def schedule(actor,owed):
    """Declare next-turn recipient loss; repeated identical losses coalesce."""
    actor.pending_action_loss=plan_debt(actor,owed)


def reset(engine,actor,budget):
    """Validate every loss before installing a fresh budget and settling once."""
    owed=pending(actor)
    planned=subtract(budget,owed)
    actor.budget=planned
    actor.pending_action_loss=None
    import exhaust_moves as EXHAUST
    EXHAUST.settle(engine,actor,owed)
    import priority_limited as PRIORITY
    PRIORITY.settle(engine,actor,owed)
    import initiative_interrupts as INTERRUPTS
    INTERRUPTS.settle_action_losses(engine,actor,owed)
    state=actor.spec.get('_burrow',{})
    if state.get('standard_debt'):
        state['standard_debt']=False;state['debt_paid_round']=engine.round_no
    if owed:engine.log(actor.name+': next-action losses '+str(owed),'combat/action-economy')


def plan_cost(budget,components):
    """Reserve declared costs against one shared budget, without mutating it.

    Reserve Standard first, then downgrade remaining Standard tokens to lower
    actions. Permissions (including movement exceptions) belong to callers.
    """
    if not isinstance(components,(tuple,list)) or not components or any(k not in KINDS for k in components):
        raise ValueError('explicit ordinary action cost components required')
    planned=subtract(budget,{})
    for kind in sorted(components,key=lambda k:k!='standard'):
        token=kind if planned[kind]>0 else 'standard' if kind in ('shift','swift') and planned['standard']>0 else None
        if token is None:return None
        planned[token]-=1
    return planned
