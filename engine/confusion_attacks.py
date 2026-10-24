"""One Confusion draw per admitted Move, consumed after all actual effects.

The existing Move completion owns the observation and retry state. This adapter
does not fabricate an attack from a damage label or an arbitrary HP change.
"""
from copy import deepcopy
import arithmetic_policy as M
import common_checks as C
import root_resolution as R
import state_grants as G
import combat_damage as DAMAGE
import roll_pools as POOLS

FIELD='confusion'
SOURCE='condition/혼란'
ACTION_KINDS={'capture','maneuver','item_attack','net_capsule','threaded','ability_attack'}
EXPECTED=[{'type':'no_attack_of_opportunity'},
          {'type':'on_attack_roll','die':'1d2','fail_on':1},
          {'type':'self_hp_loss','by_move_class':{'물리':'atk/2','특수':'spa/2','변화':'2 ticks'},'after':'attack_resolves'},
          {'type':'save','dc':16,'timing':'end_of_turn','on_success':'cure'}]
CORE_EXPECTED=[{'type':'core_confusion_start_turn','self_hit_max':8,'normal_max':15,'cure_min':16,
                'attack':'typeless_physical_struggle','resistance_steps':1,'no_other_actions':True}]


def _fingerprint(row,value):
    return R.fingerprint({'completion_id':row['id'],'actor_id':row['actor'].entity_id,
                          'move_id':row['move_id'],'value':value})


def policy(engine):
    effects=[{k:v for k,v in effect.items() if not k.startswith('_')}
             for effect in engine.r.condition_effects('혼란')]
    if engine.r._selected_rule(SOURCE,supports_versions=True)!=SOURCE or effects not in (EXPECTED,CORE_EXPECTED):
        raise ValueError('selected Confusion requires its reviewed attack-completion policy')
    return R.fingerprint(effects)


def core(engine):
    return policy(engine)==R.fingerprint(CORE_EXPECTED)


def start_turn(engine,actor):
    if not interested(actor) or not core(engine) or '잠듦' in actor.conditions:return None
    import condition_recovery as RECOVERY
    check=RECOVERY.saving_check(engine,actor,'혼란',16)
    __import__('eldritch_magic').after_confusion_save(engine,actor,check)
    # Compare the same adjusted save with all three printed bands.
    value=check['natural']+16-check['dc']
    result={'source':SOURCE,'version':'core-1.05','save':deepcopy(check),'outcome':'cured' if value>=16 else 'normal' if value>=9 else 'self_hit'}
    if value>=16:engine.cure_status(actor,'혼란')
    elif value<=8:
        if __import__('ace_trainer').replace_core_confusion(engine,actor,result):
            actor.custom_conditions.setdefault('core_confusion_turns',[]).append(result)
            return result
        before=DAMAGE.observe(actor);prior=set(getattr(engine,'_move_completions',{}))
        engine._core_confusion_struggle=actor
        try:amount=engine.use_move(actor,actor,'struggle')
        finally:del engine._core_confusion_struggle
        rows=[row for key,row in getattr(engine,'_move_completions',{}).items() if key not in prior and row['actor'] is actor and row['move_id']=='struggle']
        if rows:
            row=rows[-1]
            if row['phase']!='complete':raise ValueError('finish the actual Core Confusion self attack')
            result.update(move_id='struggle',completion_id=row['id'],damage_class='물리',type='None',resistance_steps=1,amount=amount,before=before,after=DAMAGE.observe(actor))
            __import__('provocateur').confusion_hit(engine,actor)
        else:result.update(outcome='self_attack_forbidden',amount=0)
        actor._turn_action_limit={'source':SOURCE,'choose_one_of':[]}
    actor.custom_conditions.setdefault('core_confusion_turns',[]).append(result)
    return result


def prepare(engine,actor,move):
    if getattr(engine,'_core_confusion_struggle',None) is not actor:return move
    if move['id']!='struggle' or not core(engine):raise ValueError('actual Core Confusion Struggle required')
    return dict(move,type='None',**{'class':'물리'},_core_confusion=True)


def automatic_hit(engine,actor,target,move):
    if not move.get('_core_confusion'):return False
    resistance(engine,actor,target,move)
    return True


def resistance(engine,actor,target,move):
    if not move.get('_core_confusion'):return 0
    if (getattr(engine,'_core_confusion_struggle',None) is not actor or target is not actor
            or move['id']!='struggle' or move['type']!='None' or move['class']!='물리' or not core(engine)):
        raise ValueError('actual Core Confusion self Struggle required')
    return 1


def permits_opportunity(engine,actor):
    if '혼란' not in actor.conditions:return True
    return core(engine) and not (getattr(engine,'_active_turn_actor',None) is actor and getattr(actor,'_turn_action_limit',None))


def interested(actor):
    import boss_transitions as BOSS
    if getattr(actor,'_duelist_ignoring',False):return False
    return '혼란' in __import__('blessing_effects').effective_conditions(actor) and BOSS.condition_applies_this_turn(actor,'혼란')


def preflight(engine,actor,move):
    if interested(actor):
        policy(engine)
        if move.get('class') not in ('물리','특수','변화'):
            raise ValueError('Confusion needs the actual attack class')


def begin(engine,row):
    scope=getattr(engine,'_pass_move_scope',None)
    if (scope is not None and scope['actor'] is row['actor']
            and scope['move_id']==row['move_id'] and FIELD in scope):
        import pass_moves as PASS
        PASS.require_scope(engine,row['actor'],scope)
        if not scope['paid']:raise ValueError('Confusion parent requires the actual paid Pass')
        if scope[FIELD] is not None:row['confusion_parent']={'producer':'pass','event_id':scope['event_id']}
        return
    _observe(engine,row)


def _observe(engine,row):
    actor=row['actor']
    if not interested(actor):return
    preflight(engine,actor,row['move'])
    if core(engine):return
    if FIELD in row:raise ValueError('Confusion attack observation already exists')
    asleep='잠듦' in actor.conditions
    row[FIELD]={'source':SOURCE,'policy':policy(engine),'damage_class':row['move']['class'],
                'asleep_at_start':asleep,'face':None if asleep else POOLS.die(engine.rng,2),
                'result':None}
    row[FIELD]['facts_hash']=_fingerprint(row,{k:v for k,v in row[FIELD].items() if k!='result'})


def amount(engine,actor,damage_class):
    return engine.tick_loss(actor,2) if damage_class=='변화' else M.ratio(actor.staged('atk' if damage_class=='물리' else 'spa'),2)


def validate(row):
    _validate_observation(row)
    if FIELD in row and row['phase']=='complete' and row[FIELD]['result'] is None:
        raise ValueError('completed Move lacks its Confusion consequence')


def _validate_observation(row):
    if FIELD not in row:return
    fact=row[FIELD]
    if (type(fact) is not dict or set(fact)!={'source','policy','damage_class','asleep_at_start','face','result','facts_hash'}
            or fact['source']!=SOURCE or fact['policy']!=R.fingerprint(EXPECTED)
            or fact['damage_class']!=row['move']['class'] or type(fact['asleep_at_start']) is not bool):
        raise ValueError('actual Confusion observation changed')
    if fact['facts_hash']!=_fingerprint(row,{k:v for k,v in fact.items() if k not in ('result','facts_hash')}):
        raise ValueError('Confusion draw changed its actual attack identity')
    if fact['asleep_at_start']:
        if fact['face'] is not None:raise ValueError('sleep exception cannot acquire a self-hit draw')
    else:C.integer(fact['face'],'actual confusion die',1,2)
    result=fact['result']
    if result is not None:
        if type(result) is not dict or set(result)!={'reason','amount','before','after','sha256'}:
            raise ValueError('identified Confusion result required')
        if result['sha256']!=_fingerprint(row,{k:v for k,v in result.items() if k!='sha256'}):
            raise ValueError('Confusion completion result changed')
        if result['reason'] not in ('applied','no_self_hit','asleep','cancelled'):
            raise ValueError('known Confusion completion reason required')
        C.integer(result['amount'],'actual Confusion loss',0)
        if result['reason']!='applied' and result['amount']:
            raise ValueError('skipped Confusion cannot lose HP')
        if result['reason']=='applied' and (fact['face']!=1 or fact['asleep_at_start']):
            raise ValueError('Confusion self-hit requires its original failed draw')
        if result['reason']=='no_self_hit' and fact['face']!=2:
            raise ValueError('Confusion successful draw result disagrees')
        for snapshot in (result['before'],result['after']):
            if type(snapshot) is not dict or set(snapshot)!={'hp','temporary_hp'} or any(type(v) is not int for v in snapshot.values()) or snapshot['temporary_hp']<0:
                raise ValueError('Confusion requires actual integral HP observations')
        if result['reason']!='applied' and result['before']!=result['after']:
            raise ValueError('skipped Confusion cannot change HP')


def _result(engine,actor,context,*,cancelled=False,completion_id=None):
    """Shared arithmetic/exception/loss consumer; the caller owns completion."""
    fact=context[FIELD];policy(engine);before=DAMAGE.observe(actor)
    reason=('asleep' if fact['asleep_at_start'] or '잠듦' in actor.conditions else
            'cancelled' if cancelled else 'no_self_hit' if fact['face']!=1 else 'applied')
    loss=amount(engine,actor,fact['damage_class']) if reason=='applied' else 0
    if loss:
        import control_mount as MOUNT
        prior=getattr(engine,'_confusion_applying',None)
        if completion_id is not None:engine._confusion_applying=completion_id
        try:MOUNT.confusion_loss(engine,actor,loss,_completion_id=completion_id)
        finally:
            if completion_id is not None:
                if prior is None:del engine._confusion_applying
                else:engine._confusion_applying=prior
    result={'reason':reason,'amount':loss,'before':before,'after':DAMAGE.observe(actor)}
    result['sha256']=_fingerprint(context,result)
    engine.log('    '+actor.name+': 혼란 공격 완료 '+reason+' / HP 손실 '+str(loss),SOURCE)
    return result


def _native_context(actor,move,producer,event_id):
    if producer not in ('physical','tool','combustion','pass','action'):
        raise ValueError('reviewed native Confusion producer required')
    G._text(event_id,'actual native attack identity')
    return {'id':producer+'-attack:'+event_id,'actor':actor,'move_id':move['id'],'move':move}


def begin_native(engine,actor,move,*,producer,event_id):
    """The already-paid native producer owns the returned observation."""
    context=_native_context(actor,move,producer,event_id)
    _observe(engine,context)
    return deepcopy(context.get(FIELD))


def finish_native(engine,actor,move,observation,*,producer,event_id,cancelled=False):
    """Called by the actual native tail inside its existing whole transaction."""
    if observation is None:return None
    context=_native_context(actor,move,producer,event_id);context[FIELD]=deepcopy(observation)
    _validate_observation(context)
    if context[FIELD]['result'] is not None:return deepcopy(context[FIELD])
    def apply(e,c):
        actual=_native_context(c,move,producer,event_id);actual[FIELD]=deepcopy(observation)
        actual[FIELD]['result']=_result(e,c,actual,cancelled=cancelled)
        if actual[FIELD]['result']['reason']=='applied':__import__('provocateur').confusion_hit(e,c)
        return actual[FIELD]
    return G.transition(engine,actor,apply)


def validate_native(actor,move,observation,*,producer,event_id):
    context=_native_context(actor,move,producer,event_id);context[FIELD]=observation
    _validate_observation(context)
    if observation['result'] is None:raise ValueError('native attack lost its completed Confusion consequence')


def require_loss(engine,actor,completion_id,loss):
    row=getattr(engine,'_move_completions',{}).get(completion_id)
    if row is None:
        action=getattr(engine,'_native_action_resolutions',{}).get(completion_id)
        if action is None:raise ValueError('actual Confusion attack completion required')
        trigger=_action_trigger(action);context=_action_context(action,trigger)
        _validate_observation(context)
        if (action['actor'] is not actor or action['phase']!='producer_returned'
                or trigger['status']=='completed' or context[FIELD]['result'] is not None
                or context[FIELD]['face']!=1 or '잠듦' in actor.conditions
                or loss!=amount(engine,actor,context[FIELD]['damage_class'])
                or getattr(engine,'_confusion_applying',None)!=completion_id):
            raise ValueError('actual pending native Confusion consequence required')
        return
    validate(row);fact=row.get(FIELD)
    if (row['actor'] is not actor or row['phase'] not in ('completion_effects','applying')
            or fact is None or fact['result'] is not None or fact['face']!=1
            or '잠듦' in actor.conditions or loss!=amount(engine,actor,fact['damage_class'])
            or getattr(engine,'_confusion_applying',None)!=completion_id):
        raise ValueError('actual pending Confusion consequence required')


def finish(engine,row):
    if FIELD not in row:return
    validate(row)
    if row[FIELD]['result'] is not None:return
    import action_lifecycle as ACTION
    if (row['phase'] not in ('completion_effects','applying') or not row['sealed']
            or set(row['results'])!={t.entity_id for t in row['targets']}
            or ACTION.pending_resolution_effects(engine,row)):
        raise ValueError('Confusion requires all actual attack targets and effects')
    token=row['id'];actor=row['actor']
    def apply(e,c):
        actual=e._move_completions[token]
        cancelled=bool(actual['targets'] and all(r['cancelled'] for r in actual['results'].values()))
        result=_result(e,c,actual,cancelled=cancelled,completion_id=token)
        e._move_completions[token][FIELD]['result']=result
        if result['reason']=='applied':__import__('provocateur').confusion_hit(e,c)
    G.transition(engine,actor,apply)


def ensure_clear(engine):
    for row in getattr(engine,'_move_completions',{}).values():
        if (row['phase']=='completion_effects' and FIELD in row and row[FIELD]['result'] is None
                and getattr(engine,'_confusion_applying',None)!=row['id']):
            raise ValueError('finish the actual pending Confusion consequence before another action')


def resume(engine,completion_id):
    import move_completion as COMPLETE
    row=getattr(engine,COMPLETE.KEY,{}).get(completion_id)
    if row is None:
        import action_lifecycle as ACTION
        row=getattr(engine,'_native_action_resolutions',{}).get(completion_id)
        if row is None or row['phase']!='producer_returned' or _action_trigger(row) is None:
            raise ValueError('actual returned native attack required')
        ACTION.finish_resolution(engine,row)
        return {'completion_id':completion_id,'phase':row['phase'],'confusion':deepcopy(_action_trigger(row)[FIELD])}
    if row is None or row['phase'] not in ('completion_effects','complete') or FIELD not in row:
        raise ValueError('actual returned Move with a Confusion completion required')
    def apply(e,c):
        actual=COMPLETE.refresh(e,completion_id)
        return {'completion_id':completion_id,'phase':actual['phase'],'confusion':deepcopy(actual[FIELD])}
    return G.transition(engine,row['actor'],apply)


def _action_trigger(row):
    return next((t for t in row['triggers'] if t['source']==SOURCE),None)


def _action_context(row,trigger):
    if (row['kind'] not in ACTION_KINDS or trigger is None or trigger['actor'] is not row['actor']
            or type(trigger.get('attack')) is not dict or set(trigger['attack'])!={'id','class'}):
        raise ValueError('actual native attack identity and class required')
    context=_native_context(row['actor'],trigger['attack'],'action',row['id'])
    context[FIELD]=trigger[FIELD]
    return context


def observe_action(engine,actor,move):
    """Called after payment/permission at the actual non-Move attack start."""
    if not interested(actor):return None
    preflight(engine,actor,move)
    stack=getattr(engine,'_native_action_stack',[])
    if not stack or stack[-1]['actor'] is not actor or stack[-1]['kind'] not in ACTION_KINDS:
        raise ValueError('live native attack producer required for Confusion')
    import action_lifecycle as ACTION
    row=ACTION.observe_resolution(engine,actor,SOURCE,{'event':'attack_started','move_id':move['id'],'damage_class':move['class']})
    trigger=_action_trigger(row)
    if FIELD in trigger:raise ValueError('one Confusion observation per actual native attack')
    trigger['attack']={'id':move['id'],'class':move['class']}
    trigger[FIELD]=begin_native(engine,actor,move,producer='action',event_id=row['id'])
    return row['id']


def finish_action(engine,row):
    trigger=_action_trigger(row)
    if trigger is None or trigger['status']=='completed':return True
    import action_lifecycle as ACTION
    if row['phase']!='producer_returned' or ACTION.pending_resolution_effects(engine,row):return False
    context=_action_context(row,trigger);_validate_observation(context)
    def apply(e,c):
        actual=e._native_action_resolutions[row['id']];active=_action_trigger(actual)
        result=_result(e,c,_action_context(actual,active),completion_id=actual['id'])
        active=_action_trigger(e._native_action_resolutions[row['id']])
        active[FIELD]['result']=result;active['status']='completed'
        if result['reason']=='applied':__import__('provocateur').confusion_hit(e,c)
    G.transition(engine,row['actor'],apply)
    return True


def refresh_actions(engine):
    import action_lifecycle as ACTION
    for row in list(getattr(engine,'_native_action_resolutions',{}).values()):
        if row['phase']=='producer_returned' and _action_trigger(row) is not None:
            ACTION.finish_resolution(engine,row)


def resuming_action(engine,actor,source,kind):
    identity=getattr(engine,'_confusion_resuming_action',None)
    row=getattr(engine,'_native_action_resolutions',{}).get(identity)
    if row is not None and row['actor'] is actor and row['source']==source and row['kind']==kind:
        if row['phase']!='interrupted':raise ValueError('native maneuver is not waiting for its original continuation')
        _action_context(row,_action_trigger(row))
        return identity
    return None


def validate_actions(engine,index):
    for identity,row in getattr(engine,'_native_action_resolutions',{}).items():
        trigger=_action_trigger(row)
        if trigger is None:continue
        if identity!=row['id'] or index.get(row['actor'].entity_id) is not row['actor']:
            raise ValueError('actual native Confusion actor required')
        _validate_observation(_action_context(row,trigger))
        if (trigger['status']=='completed')!=(trigger[FIELD]['result'] is not None):
            raise ValueError('native Confusion completion and result disagree')
