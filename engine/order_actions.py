"""Native Order payment and delivery composition.

Each source adapter retains acquisition, targets, costs, frequency and lifetime.
Orders reuse the actual communication producer and ordinary or Priority payment.
"""
from contextlib import contextmanager
import acquired_features as A
import action_lifecycle as ACTION


def priority(engine, actor, source):
    return (engine.encounter_active and engine._active_turn_actor is not actor
            and current(engine, actor, source) is None)


def preflight(engine, actor, source, *, action='standard'):
    """Keep ordinary turns ordinary; reserve only an actual between-turn right."""
    if not priority(engine, actor, source):return
    import priority_limited as P,turn as TURN,body_modes as BODY
    import effect_lifetimes as LIFE,initiative_interrupts as INTERRUPTS
    import passive_events as PASSIVE,heavy_injury_adapter as HEAVY
    import effect_contracts as EFFECTS,maneuver_grants as GRANTS
    from action_metadata import ActionCost
    P.preflight(engine, actor, action=action, source=source)
    INTERRUPTS.require_clear(engine)
    if getattr(engine,'_initiative_schedule',None) is not None:
        INTERRUPTS.between_trigger(engine)
        _,_,due=INTERRUPTS._loan_location(engine,actor)
        if due!=engine.round_no:raise ValueError('Priority Order requires its unacted current schedule slot')
    else:
        # Manual play has a fresh round, explicit count, or real turn closure.
        cursor=getattr(engine,'_initiative_cursor',None)
        observed=bool(cursor and cursor['round']==engine.round_no and cursor['available_for_turn'])
        fresh=not any(round_no==engine.round_no for round_no in engine._ordinary_turn_rounds.values())
        closures=engine._turn_closures
        closed=bool(closures and closures[-1]['round']==engine.round_no
                    and engine._ordinary_turn_rounds.get(closures[-1]['actor'])==engine.round_no)
        if not (fresh or observed or closed):
            raise ValueError('Priority Order requires a fresh manual round, observed count or actual turn closure')
    ACTION.ensure_resolutions_clear(engine)
    PASSIVE.ensure_clear(engine);HEAVY.ensure_clear(engine)
    EFFECTS.ensure_clear(engine);GRANTS.ensure_clear(engine)
    components=action.components if type(action) is ActionCost else (action,)
    import combat_maneuvers as MANEUVERS
    if (not TURN.can_act(engine, actor) or not ACTION.status_permission(engine, actor, action)
            or any(not BODY.permits(actor, kind) or not MANEUVERS.standard_allowed(actor,kind,None) for kind in components)
            or LIFE.forbids(actor, 'priority')):
        raise ValueError('actual printed Priority action permission required')


def spend(engine, actor, source, *, subject, communication, action='standard'):
    """Pay a source-admitted Order through its native budget or debt owner."""
    import priority_limited as P,turn as TURN
    from action_metadata import ActionCost
    if type(communication) is not dict or communication.get('status')!='delivered':
        raise ValueError('actual delivered Order communication required')
    preflight(engine, actor, source, action=action)
    if priority(engine, actor, source):
        return P.reserve(engine, actor, action=action, source=source,
                         subject=subject, communication=communication)
    if not TURN.spend(engine, actor, action, source):
        raise ValueError('Order printed action is unavailable')
    free=payment(engine, actor, source)
    if free is not None:return free
    return {'kind':'ordinary', 'action':list(action.components) if type(action) is ActionCost else action,
            'turn':actor.custom_conditions.get('combat_turn_serial',0),
            'history_index':len(actor._action_history)-1}


def delivery(engine, actor, target, source, *, communication=None):
    """Use the existing contemporaneous communication producer for an Order."""
    import moment_of_action as M,perception_communicate as COMM
    serial=len(getattr(engine,COMM.KEY,{}).get('attempts',[]))+1
    _,result=M._communication(engine,actor,target,'order:'+actor.entity_id+':'+str(serial),
                              communication,source=source,label='Order')
    return result


def current(engine,actor,source=None):
    row=getattr(engine,'_free_order_scope',None)
    if row is None or row['actor'] is not actor:return None
    unit=engine.r.selection.units[row['feature']]
    if source is not None and source not in (row['feature'],unit['title'],unit.get('eng')):return None
    return row


def pay(engine,actor,source,kind):
    kind=__import__('commander').pay(engine,actor,source,kind)
    row=current(engine,actor,source)
    if row is None:return kind
    if row['spent']:raise ValueError('one source-proved Free Order payment only')
    row['spent']=True
    return 'free'


def payment(engine,actor,source):
    row=current(engine,actor,source)
    if row is None:return None
    if not row['spent']:raise ValueError('actual Free Order action must precede its receipt')
    return {'kind':'free_order','source':row['source'],'parent':row['parent'],
        'feature':row['feature'],'target_id':row['target'].entity_id}


def validate(engine,actor,target,feature,proof):
    if (type(proof) is not dict or set(proof)!={'kind','source','parent','feature','target_id'}
            or proof['kind']!='free_order' or proof['source']!='feat/채찍질'
            or proof['feature']!=feature or proof['target_id']!=target.entity_id):
        raise ValueError('exact source-proved targeted Free Order payment required')
    parent=getattr(engine,'_native_action_resolutions',{}).get(proof['parent'])
    if (parent is None or parent['actor'] is not actor or parent['source']!='feat/압박'
            or parent['kind']!='feature' or parent['phase']!='producer_returned'):
        raise ValueError('Free Order requires its completed native Press producer')
    facts=[] if parent is None else [fact for trigger in parent['triggers'] if trigger['actor'] is actor
        and trigger['source']=='feat/압박' and trigger['status']=='completed' for fact in trigger['observations']]
    import training_features as TRAINING
    if not any(fact.get('press_target')==target.entity_id and
               (fact.get('whip_order')==feature or TRAINING.identity(fact.get('whip_order'))==feature)
               for fact in facts):
        raise ValueError('Free Order requires its actual Press and Whip occurrence')
    return True


@contextmanager
def granted(engine,actor,target,feature,*,source,parent):
    if getattr(engine,'_free_order_scope',None) is not None:raise ValueError('nested Free Order grant is not the same Order')
    row={'actor':actor,'target':target,'feature':feature,'source':source,'parent':parent,'spent':False}
    engine._free_order_scope=row
    try:
        yield
        if not row['spent']:raise ValueError('selected Order did not execute its native action payment')
    finally:engine._free_order_scope=None


def execute(engine,actor,target,choice,*,source,parent):
    import training_features as TRAINING,moment_of_action as MOMENT
    if isinstance(choice,str):feature=choice;options={}
    elif type(choice) is dict and set(choice)=={'feature','options'} and type(choice['options']) is dict:
        feature=choice['feature'];options=choice['options']
    else:raise ValueError('explicit known targeted Order and native options required')
    if not isinstance(feature,str):raise ValueError('exact selected Order identity required')
    if feature not in engine.r.selection.units:feature=engine.r.selection.resolve_name(feature,('feat/',))
    unit=engine.r.selection.units[feature]
    training=TRAINING.identity(feature)
    owned=training or feature
    if not A.owned_rule_count(actor,owned):raise ValueError('actual known Order required')
    if TRAINING.identity(feature) is None and not any('지시' in tag or tag=='Orders' for tag in unit.get('tags',[])):
        raise ValueError('known targeted [Orders] Feature required')
    with granted(engine,actor,target,owned,source=source,parent=parent):
        if training is not None:
            if options:raise ValueError('Training Order has no native adjustment choices')
            return TRAINING.orders(engine,actor,feature,target)
        import ace_trainer as ACE
        if feature==ACE.CRITICAL:
            if options:raise ValueError('Critical Moment has only its actual targeted recipient')
            return ACE.critical_moment(engine,actor,[target])
        if feature==MOMENT.FEATURE:
            return MOMENT.use(engine,actor,[target],**options)
        import directive_features as DIRECTIVE
        if feature==DIRECTIVE.FEATURE:
            if set(options)-{'adjustment'}:raise ValueError('native directive adjustment only')
            return engine.manual_feat(actor,feature,target,adjustment=options.get('adjustment'))
        return engine.manual_feat(actor,feature,target,adjustment=options or None)
