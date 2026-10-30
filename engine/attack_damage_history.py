"""Actual native attack applications, shared by retrospective Move effects."""
from copy import deepcopy
from contextlib import contextmanager
import common_checks as C
import combat_damage as DAMAGE
import type_state as TYPES
import root_resolution as RESOLUTION
import math

TURN_WINDOW = 'attack_damage_turn_window'

KEY = 'attack_damage_history'


def direct_hp_loss(move, mechanics):
    """The selected variable-DB declaration supplies loss, not rolled damage."""
    if __import__('fling_move').no_damage(move,mechanics):return True
    if __import__('hp_setting_moves').final_gambit(move,mechanics):return True
    effects=mechanics.get('effects_exec',[])
    return (move.get('damage_base')=='variable' and move.get('class') in ('물리','특수')
            and sum(e.get('type')=='hp_loss' and e.get('target','target')=='target'
                    and not any(k in e for k in ('if','on','when','on_miss')) for e in effects)==1
            and all(e.get('type') in ('hp_loss','rule','no_wake') for e in effects))


@contextmanager
def damage_source(engine, target, move):
    """A native damage producer carries its selected no-wake exception."""
    stack=engine.__dict__.setdefault('_sleep_damage_sources',[])
    stack.append((target,move))
    try:yield
    finally:
        stack.pop()
        if not stack:del engine._sleep_damage_sources


def wake_after_loss(engine, target, move, before):
    """Actual damage or received active HP loss; never a passive HP mutation."""
    after=DAMAGE.observe(target)
    lost=max(0,before['hp']-after['hp'])+max(0,before['temporary_hp']-after['temporary_hp'])
    if not lost or '잠듦' not in target.conditions:return False
    if move is None:
        move=next((m for c,m in reversed(getattr(engine,'_sleep_damage_sources',[])) if c is target),None)
    if move is not None and move['id'] in engine.r.moves:
        mechanics,_=engine.r.move_mech(move['id'])
        if any(e.get('type')=='no_wake' and not any(k in e for k in
               ('if','on','when','except','target')) for e in mechanics.get('effects_exec',[])):
            return False
    definitions=engine.r.condition_effects('잠듦')
    if not any(e.get('type')=='cured_by_damage' and e.get('excluding')=='passive_hp_loss'
               for e in definitions):
        raise ValueError('selected Sleep source needs its attack-loss wake policy')
    engine.cure_status(target,'잠듦')
    return '잠듦' not in target.conditions


def received_loss(engine, target, amount, *, source, move=None, **options):
    """Internal adapter called after an active producer validates its actual hit.

    The caller's existing receipt owns provenance/replay. Do not use this for
    poison, weather, contact retaliation or a self cost; lose_hp stays neutral.
    """
    import state_grants as G
    def apply(staged,actual):
        before=DAMAGE.observe(actual)
        staged.lose_hp(actual,amount,source=source,**options)
        wake_after_loss(staged,actual,move,before)
    return G.transition(engine,target,apply)


def native_recipient(engine, attacker, target, context, *, error='HP consequence must belong to its actual native recipient', allow_miss=False):
    """Validate a live producer frame; callers own the absent-frame policy."""
    stack=getattr(engine,'_attack_loss_effect_scopes',[])
    if not stack:return None
    actor,recipient,move,completion=stack[-1]
    if (actor is not attacker or recipient is not target or
            context.get('move_completion')!=completion or (context.get('hit') is not True and not (allow_miss and context.get('hit') is False)) or
            context.get('source_id')!=move['id']):
        raise ValueError(error)
    return stack[-1]


def wake_effect_loss(engine,attacker,target,context,before):
    """Existing native recipient scope also covers active HP redistribution."""
    frame=native_recipient(engine,attacker,target,context)
    if frame is None:return False
    actor,recipient,move,completion=frame
    return wake_after_loss(engine,target,move,before)


@contextmanager
def native_effects(engine, attacker, target, move, completion_id):
    """Live native recipient leaf; caller hit labels alone cannot open this scope."""
    import move_completion as COMPLETE
    row=getattr(engine,COMPLETE.KEY,{}).get(completion_id)
    if not row or row['actor'] is not attacker or row['move_id']!=move['id'] or row['phase']!='targets':
        raise ValueError('active native Move effect producer required')
    frame=(attacker,target,move,completion_id)
    stack=getattr(engine,'_attack_loss_effect_scopes',None)
    if stack is None:stack=engine._attack_loss_effect_scopes=[]
    stack.append(frame)
    try:yield
    finally:
        stack.pop()
        if not stack:del engine._attack_loss_effect_scopes


def effect_loss(engine, attacker, target, recipient, effect, context, amount):
    """Bind a direct HP-loss effect to its paid actual native Move and receipt."""
    import effect_contracts as EC
    import state_grants as G
    frame=native_recipient(engine,attacker,target,context,error='HP loss must belong to the active native recipient',allow_miss=recipient is attacker and effect.get('on_miss') is True)
    if effect.get('as') not in (None,'damage'):
        raise ValueError('HP-loss as mode must be damage or absent')
    if effect.get('as')=='damage' and frame is None:
        raise ValueError('fixed damage requires an actual native Move recipient')
    if frame is None:
        if context.get('move_completion'):
            raise ValueError('HP-loss continuation needs its native Move producer')
        engine.lose_hp(recipient,amount,source=context.get('source_id','체력 손실'),
                       unpreventable=effect.get('unpreventable') is True)
        return
    actor,actual_target,move,completion=frame
    # Self costs and independently timed effects are not a received attack.
    if effect.get('as')=='damage' and (recipient is not target or move.get('class') not in ('물리','특수')):
        raise ValueError('fixed damage requires its actual damaging Move recipient')
    if recipient is not target or move.get('class') not in ('물리','특수'):
        engine.lose_hp(recipient,amount,source=move['id'],unpreventable=effect.get('unpreventable') is True)
        return
    token=context.get('effect_receipt')
    EC.validate_receipt(engine,token,move['id'],context.get('effect_occurrence'),attacker,target,effect)
    entry=engine._effect_dispatch_receipts[token]
    if entry['status']!='dispatching' or 'attack_hp_loss' in entry or 'attack_damage' in entry:
        raise ValueError('one actual dispatched HP-loss occurrence required')
    if effect.get('as')=='damage' and context.get('multiplier')==0:
        entry['fixed_damage_immunity']=True
        return
    substitute=__import__('substitute').receive_damage(engine,attacker,target,move,amount)
    if substitute is not None:
        entry['substitute_hp_loss']=deepcopy(substitute)
        return
    def apply(staged,actual,source_actor):
        # Native Move payloads retain actor bindings; use this staged world's actors.
        staged_move=G._stage_transition_payload(engine,staged,move)
        before=DAMAGE.observe(actual)
        is_damage=effect.get('as')=='damage'
        leaf=None
        if is_damage:
            import heavy_injury_adapter as HEAVY
            with _application_scope(staged,source_actor,actual,staged_move) as history_token:
                HEAVY.apply_attack_damage(staged,source_actor,actual,amount,staged_move,
                    producer=HEAVY.Producer.EFFECT_DAMAGE, remainder='remaining native fixed-damage effect continuation',
                    actual_damage_type=context.get('actual_damage_type',staged_move['type']))
                leaf=deepcopy(staged._attack_history_scopes[history_token].get('native_application'))
        else:
            staged.lose_hp(actual,amount,source=staged_move['id'],unpreventable=effect.get('unpreventable') is True)
        receipt=DAMAGE.application(requested=amount,before=before,after=DAMAGE.observe(actual),
                                   source=staged_move['id'],damage_class=staged_move['class'])
        woke=wake_after_loss(staged,actual,staged_move,before)
        _record(staged,source_actor,actual,receipt,context.get('actual_damage_type',staged_move['type']),
            application_kind='damage' if is_damage else 'hp_loss',
            native_hit_facts=_hit_facts(staged,source_actor,actual,staged_move,completion,context.get('multiplier'),application=leaf))
        staged._effect_dispatch_receipts[token]['attack_damage' if is_damage else 'attack_hp_loss']={
            'kind':'native_attack_damage' if is_damage else 'native_attack_hp_loss','completion_id':completion,'receipt':deepcopy(receipt),
            'woke_sleep':woke,'unpreventable':effect.get('unpreventable') is True}
        __import__('food_effects').berry_after_hit(staged,source_actor,actual,staged_move,{'attacker':source_actor,'target':actual,'move':staged_move},receipt)
    G.transition(engine,recipient,apply,participants=(attacker,))


def records(actor):
    return actor.spec.get(KEY, [])


def validate_actor(actor):
    rows = records(actor)
    if not isinstance(rows, list): raise ValueError('attack history must be a list')
    for number, row in enumerate(rows, 1):
        if not isinstance(row, dict) or set(row)-{'application_kind','native_hit_facts','native_hit_fingerprint'} != {
                'sequence', 'attacker_id', 'target_id', 'round', 'at', 'move_type', 'receipt'}:
            raise ValueError('attack history shape changed')
        if row.get('application_kind','damage') not in ('damage','hp_loss'):raise ValueError('typed attack application required')
        if row['sequence'] != number or row['target_id'] != actor.entity_id:
            raise ValueError('attack history identity changed')
        if not isinstance(row['attacker_id'], str) or not row['attacker_id']:
            raise ValueError('attack history needs an attacker')
        C.integer(row['round'], 'attack round', 0)
        C.integer(row['at'], 'attack time', 0)
        TYPES.validate_attack(actor.r, row['move_type'])
        receipt = row['receipt']
        expected = DAMAGE.application(**{k: receipt[k] for k in
            ('requested', 'before', 'after', 'source', 'damage_class')})
        import special_entities as SPECIAL
        instance=SPECIAL.prime_instance(actor.r,receipt['source'])
        innovation=__import__('coordinator').innovation_instance(actor.r,receipt['source'])
        valid_source=receipt['source'] in actor.r.moves or (instance is not None and instance['host_id']==row['attacker_id']) or (innovation is not None and innovation['template']==3)
        if receipt != expected or not valid_source:
            raise ValueError('attack observation changed')
        _validate_hit_facts(row)
    _validate_turn_window(actor)
    return True


@contextmanager
def native_application(engine, attacker, target, move, native_context, *, precision_event=None):
    import heavy_injury_adapter as HEAVY
    HEAVY.validate_native_receipt(engine,native_context,attacker,target,move)
    origin=None
    if native_context is None:
        origin=_live_grapple_origin(engine,attacker,target,move,precision_event)
        if origin is not None and (any(r.get('native_hit_facts',{}).get('grapple_origin')==origin for r in records(target))
                or any(s.get('grapple_origin')==origin for s in getattr(engine,'_attack_history_scopes',{}).values())):
            raise ValueError('native grapple Attack already observed or applying')
        if origin is None:
            # Raw damage calculations do not invent an actual attack occurrence.
            yield None
            return
    with _application_scope(engine, attacker, target, move) as token:
        if origin is not None:engine._attack_history_scopes[token]['grapple_origin']=origin
        yield token


@contextmanager
def _application_scope(engine, attacker, target, move):
    token = object()
    scopes = getattr(engine, '_attack_history_scopes', None)
    if scopes is None: scopes = engine._attack_history_scopes = {}
    scopes[token] = dict(attacker=attacker,target=target,move_id=move['id'])
    try: yield token
    finally:
        scopes.pop(token, None)
        if not scopes: del engine._attack_history_scopes


def apply_smite(engine, attacker, target, move, amount, actual_type):
    """Record genuine miss damage without entering any successful-hit consumer."""
    stack = getattr(engine, '_attack_loss_effect_scopes', ())
    if not stack:
        raise ValueError('Smite damage requires its live native Move recipient')
    completion_id = stack[-1][3]
    frame = native_recipient(engine, attacker, target, {'move_completion': completion_id,
        'source_id': move['id'], 'hit': False}, allow_miss=True)
    if frame[2] is not move:
        raise ValueError('Smite damage must use its actual prepared Move')
    completion = engine._move_completions[completion_id]
    defense = getattr(engine, '_defense_recipient_scope', None)
    if defense is not None:
        import move_defense_reactions as DEFENSE
        DEFENSE.require_recipient(engine, defense, attacker, target, move, completion_id)
    elif target not in completion['targets'] or target.entity_id not in completion['started']:
        raise ValueError('Smite damage requires its actual started recipient')
    C.integer(amount, 'Smite damage', 0)
    TYPES.validate_attack(engine.r, actual_type)
    before = DAMAGE.observe(target)
    with _application_scope(engine, attacker, target, move) as token, damage_source(engine, target, move):
        engine.take_damage(target, amount)
        receipt = DAMAGE.application(requested=amount, before=before, after=DAMAGE.observe(target),
                                     source=move['id'], damage_class=move['class'])
        record(engine, attacker, target, move, receipt, actual_type, token, completion_id=completion_id, hit=False)
    return receipt


def record(engine, attacker, target, move, receipt, actual_type, native_context, *, completion_id=None, multiplier=None, hit=True):
    """Called only while the native damage application still owns its token."""
    token = getattr(engine, '_attack_history_scopes', {}).get(native_context)
    if (token is None or token['attacker'] is not attacker or token['target'] is not target
            or token['move_id'] != move['id'] or token.get('history_recorded')):
        raise ValueError('one actual native attack application required')
    application=token.get('native_application')
    if application is None and completion_id is not None and hit:
        candidates=[event for event in getattr(engine,'_heavy_events',{}).values() if
            event.get('native_completion_id')==completion_id and event['attacker'] is attacker
            and event['target'] is target and event['move']['id']==move['id']
            and event['producer']==__import__('heavy_injury_adapter').Producer.RESOLVED_HIT.value]
        if len(candidates)==1 and 'attack_after' in candidates[0]:
            event=candidates[0];application={'damage_event_id':event['event_id'],'attack_application':_event_attack_application(event)}
    facts = _hit_facts(engine,attacker,target,move,completion_id,multiplier,hit=hit,application=application,grapple_origin=token.get('grapple_origin'))
    _record(engine,attacker,target,receipt,actual_type,native_hit_facts=facts)
    token['history_recorded'] = True


def _record(engine, attacker, target, receipt, actual_type,*,application_kind='damage',native_hit_facts=None):
    validate_actor(target)
    row = dict(sequence=len(records(target))+1, attacker_id=attacker.entity_id,
               target_id=target.entity_id, round=engine.round_no, at=engine.elapsed_seconds,
               move_type=actual_type, receipt=deepcopy(receipt))
    target.spec.setdefault(KEY, []).append(row)
    if application_kind!='damage':row['application_kind']=application_kind
    if native_hit_facts is not None:
        row['native_hit_facts']=native_hit_facts
        row['native_hit_fingerprint']=RESOLUTION.fingerprint(row)
    _seal_history_head(target)
    validate_actor(target)


def amount(row):
    receipt = row['receipt']
    return max(0, receipt['net_hp_loss']) + max(0, receipt['net_temporary_hp_loss'])


def current_round(engine, actor):
    validate_actor(actor)
    return sum(amount(row) for row in records(actor) if row['round'] == engine.round_no)


def last_damage(actor):
    validate_actor(actor)
    return next((row for row in reversed(records(actor)) if amount(row) > 0), None)


def validate_world(engine, index):
    for actor in index.values():
        validate_actor(actor)
        for row in records(actor):
            if (row['attacker_id'] not in index or row['round'] > engine.round_no
                    or row['at'] > engine.elapsed_seconds):
                raise ValueError('attack history references missing actor or future event')
            facts=row.get('native_hit_facts')
            if facts is None:continue
            if facts.get('grapple_origin') is not None:
                _grapple_result(engine,row)
            else:
                completion=getattr(engine,'_move_completions',{}).get(facts['completion_id'])
                if (completion is None or completion['actor'] is not index[row['attacker_id']]
                        or completion['move_id']!=row['receipt']['source']):
                    raise ValueError('native attack completion identity changed')
            if 'damage_event_id' in facts:
                event=getattr(engine,'_heavy_events',{}).get(facts['damage_event_id'])
                if (event is None or event['attacker'] is not index[row['attacker_id']] or event['target'] is not actor
                        or event['move']['id']!=row['receipt']['source']
                        or _event_attack_application(event)!=facts.get('attack_application')):
                    raise ValueError('native attack application event changed')



def effect_damage_total(engine, attacker, target, source, prior_receipts):
    total=0
    for token,row in engine._effect_dispatch_receipts.items():
        if (token in prior_receipts or row['actor'] is not attacker or row['target'] is not target
                or row['source_id']!=source):continue
        if 'substitute_hp_loss' in row and row['effect'].get('as')=='damage':
            total+=row['substitute_hp_loss']['damage']
            continue
        if 'attack_damage' not in row:continue
        receipt=row['attack_damage']['receipt']
        total+=max(0,receipt['net_hp_loss'])+max(0,receipt['net_temporary_hp_loss'])
    return total


def _hit_facts(engine, attacker, target, move, completion_id, multiplier, *, hit=True, application=None, grapple_origin=None):
    if completion_id is None and grapple_origin is None or hit and multiplier is None:return None
    import move_completion as COMPLETE
    row=getattr(engine,COMPLETE.KEY,{}).get(completion_id)
    if grapple_origin is None:
        if (row is None or row['actor'] is not attacker or row['move_id']!=move['id']
                or row['phase']!='targets'):
            raise ValueError('actual in-progress native hit required')
        defense=getattr(engine,'_defense_recipient_scope',None)
        if defense is not None:
            __import__('move_defense_reactions').require_recipient(engine,defense,attacker,target,move,completion_id)
        elif target not in row['targets'] or target.entity_id not in row['started']:
            raise ValueError('actual started hit recipient required')
    if hit and (type(multiplier) not in (int,float) or not math.isfinite(multiplier) or multiplier<0):
        raise ValueError('observed finite nonnegative type multiplier required')
    facts={'completion_id':completion_id,'hit':hit,'multiplier':multiplier}
    if application is not None:facts.update(deepcopy(application))
    if grapple_origin is not None:facts['grapple_origin']=deepcopy(grapple_origin)
    return facts


def _validate_hit_facts(row):
    facts=row.get('native_hit_facts')
    if facts is None:
        if 'native_hit_fingerprint' in row:raise ValueError('native hit facts missing')
        return
    if (type(facts) is not dict or set(facts)-{'damage_event_id','attack_application','grapple_origin'}!={'completion_id','hit','multiplier'}
            or (facts.get('grapple_origin') is None and (type(facts['completion_id']) is not str or not facts['completion_id']))
            or type(facts['hit']) is not bool or (facts['hit'] and (type(facts['multiplier']) not in (int,float)
            or not math.isfinite(facts['multiplier']) or facts['multiplier']<0))
            or (not facts['hit'] and facts['multiplier'] is not None)):
        raise ValueError('native hit facts changed')
    if 'damage_event_id' in facts and (type(facts['damage_event_id']) is not str or not facts['damage_event_id']):
        raise ValueError('native damage event identity required')
    origin=facts.get('grapple_origin')
    if origin is not None:
        if type(origin) is not dict or set(origin)!={'relation_id','history_index','precision_id'} or facts['completion_id'] is not None:
            raise ValueError('native grapple attack origin changed')
        C.integer(origin['history_index'],'native grapple history index',0)
        C.integer(origin['precision_id'],'native grapple precision event',1)
        if type(origin['relation_id']) is not str or not origin['relation_id']:raise ValueError('native grapple relation required')
    application=facts.get('attack_application')
    if application is not None:
        expected=DAMAGE.application(**{k:application[k] for k in ('requested','before','after','source','damage_class')})
        if (application!=expected or application['source']!=row['receipt']['source']
                or application['damage_class']!=row['receipt']['damage_class'] or 'damage_event_id' not in facts):
            raise ValueError('actual native attack leaf changed')
    payload={k:v for k,v in row.items() if k!='native_hit_fingerprint'}
    if row.get('native_hit_fingerprint')!=RESOLUTION.fingerprint(payload):
        raise ValueError('native hit observation changed')


def _seal_history_head(actor):
    state=actor.spec.get(TURN_WINDOW)
    if state is None:return
    state['history_length']=len(records(actor))
    state['history_fingerprint']=RESOLUTION.fingerprint(records(actor))
    state['fingerprint']=RESOLUTION.fingerprint({k:v for k,v in state.items() if k!='fingerprint'})


def _validate_turn_window(actor):
    state=actor.spec.get(TURN_WINDOW)
    if state is None:return
    if (type(state) is not dict or set(state)!={'actor_id','starts','history_length',
            'history_fingerprint','fingerprint'} or state['actor_id']!=actor.entity_id):
        raise ValueError('native attack turn window changed')
    if state['fingerprint']!=RESOLUTION.fingerprint({k:v for k,v in state.items() if k!='fingerprint'}):
        raise ValueError('native attack turn boundary changed')
    if state['history_length']!=len(records(actor)) or state['history_fingerprint']!=RESOLUTION.fingerprint(records(actor)):
        raise ValueError('native attack history was truncated or changed')
    starts=state['starts']
    if type(starts) is not list or not 1<=len(starts)<=2:raise ValueError('two ordered native turn starts required')
    previous=0;previous_sequence=0
    for start in starts:
        if type(start) is not dict or set(start)!={'serial','history_sequence','move_boundary','damage_sequence'}:
            raise ValueError('native turn boundary shape changed')
        C.integer(start['serial'],'native owner turn serial',previous+1)
        C.integer(start['history_sequence'],'native turn history sequence',previous_sequence,len(records(actor)))
        C.integer(start['damage_sequence'],'native damage sequence',0)
        boundary=start['move_boundary']
        if boundary is not None:
            if type(boundary) is not dict or set(boundary)!={'sequence','pending'}:
                raise ValueError('native completed Move boundary required')
            C.integer(boundary['sequence'],'native Move sequence',0)
            if type(boundary['pending']) is not list or any(type(k) is not str for k in boundary['pending']):
                raise ValueError('native pending Move identities required')
        previous=start['serial'];previous_sequence=start['history_sequence']


def begin_turn(engine, actor):
    """Called by the actual owner-turn clock, never by a Move/Swarm continuation."""
    if not engine.encounter_active or engine._active_turn_actor is not actor:return
    validate_actor(actor)
    state=actor.spec.get(TURN_WINDOW)
    if state is None:
        state={'actor_id':actor.entity_id,'starts':[]}
        actor.spec[TURN_WINDOW]=state
    serial=actor.custom_conditions['combat_turn_serial']
    if state['starts'] and serial<=state['starts'][-1]['serial']:
        raise ValueError('native owner turn must advance')
    state['starts']=(state['starts']+[{'serial':serial,'history_sequence':len(records(actor)),
        'move_boundary':__import__('move_completion').history_watermark(engine),
        'damage_sequence':engine._heavy_sequence}])[-2:]
    _seal_history_head(actor)


def record_delayed_hit(engine, attacker, target, move, completion_id, before, actual_type, multiplier):
    """The native delayed queue supplies the observed pre/post damage pair."""
    row=getattr(engine,'_move_completions',{}).get(completion_id)
    if (row is None or target not in row['targets'] or target.entity_id in row['results']
            or not any(e.get('type')=='delayed_attack' for e in engine.r.move_mech(move['id'])[0].get('effects_exec',[]))):
        raise ValueError('actual unresolved delayed Move recipient required')
    if any(r.get('native_hit_facts',{}).get('completion_id')==completion_id for r in records(target)):
        raise ValueError('delayed hit already observed')
    import heavy_injury_adapter as HEAVY
    sequence=C.integer(before['heavy_sequence'],'prior native damage sequence',0)
    event_id='heavy-attack-'+str(engine._heavy_sequence)
    event=getattr(engine,'_heavy_events',{}).get(event_id)
    if (engine._heavy_sequence<=sequence or event is None or event['producer']!=HEAVY.Producer.DELAYED_HIT.value
            or event['attacker'] is not attacker or event['target'] is not target or event['move']['id']!=move['id']
            or event['amount']!=before['requested'] or event['status'] not in ('not_applicable','applied')
            or {k:event['before'][k] for k in ('hp','temporary_hp')}!=before['state']
            or event['round']!=engine.round_no or event['elapsed_seconds']!=engine.elapsed_seconds):
        raise ValueError('actual just-applied delayed damage event required')
    after=DAMAGE.observe(target)
    retained_after=event.get('heavy_consequence',{}).get('after',event['observed_after'])
    if {k:retained_after[k] for k in ('hp','temporary_hp')}!=after:
        raise ValueError('native delayed damage endpoint changed')
    application=({'damage_event_id':event_id,'attack_application':_event_attack_application(event)}
                 if 'attack_after' in event else None)
    facts=_hit_facts(engine,attacker,target,move,completion_id,multiplier,application=application)
    receipt=DAMAGE.application(requested=event['amount'],before=before['state'],after=after,
                               source=move['id'],damage_class=move['class'])
    _record(engine,attacker,target,receipt,actual_type,native_hit_facts=facts)


def target_hit_user_super_effectively_since_previous_own_turn(engine, user, target):
    """U-011: True/False from retained native facts; None means unknown coverage."""
    import move_completion as COMPLETE
    import world_entities as WORLD
    index=WORLD.actor_index(engine)
    if index.get(user.entity_id) is not user or index.get(target.entity_id) is not target:
        raise ValueError('actual world participants required')
    validate_actor(user)
    state=user.spec.get(TURN_WINDOW)
    if (state is None or len(state['starts'])<2
            or state['starts'][-1]['serial']!=user.custom_conditions.get('combat_turn_serial')):
        return None
    start=state['starts'][0]
    if start['damage_sequence']>engine._heavy_sequence:return None
    completions=getattr(engine,COMPLETE.KEY,{})
    covered=set();unknown=False
    for observation in records(user)[start['history_sequence']:]:
        if observation['attacker_id']!=target.entity_id:continue
        if observation.get('application_kind','damage')!='damage':continue
        facts=observation.get('native_hit_facts')
        if facts is None:
            if amount(observation)>0:unknown=True
            continue
        if not facts['hit']:continue
        application=facts.get('attack_application')
        if application is None:
            unknown=True;continue
        if facts.get('grapple_origin') is not None:
            result=_grapple_result(engine,observation)
        else:
            row=completions.get(facts['completion_id'])
            if row is None:
                unknown=True;continue
            if row['actor'] is not target or row['move_id']!=observation['receipt']['source']:
                raise ValueError('native hit completion identity changed')
            result=COMPLETE.recipient_result(row,user)
            covered.add(row['id'])
        if result is None:
            unknown=True;continue
        if (result['hit'] and not result.get('cancelled') and not result.get('hit_prevented')
                and _application_loss(application)>0 and facts['multiplier']>1):return True
    # A returned damaging hit without an application observation is not a miss.
    later=COMPLETE.after_history_watermark(engine,start['move_boundary'])
    if later is None:return None
    for row in later:
        key=row['id']
        if row['actor'] is not target or row['move'].get('class') not in ('물리','특수'):continue
        result=COMPLETE.recipient_result(row,user)
        if result is None:
            if row['phase']!='complete' and user in row['targets']:unknown=True
            continue
        if (not result['hit'] or result.get('cancelled') or result.get('hit_prevented')
                or result['dealt']==0 or row['move'].get('class') not in ('물리','특수')):continue
        matching=[r for r in records(user)[start['history_sequence']:] if
            r.get('native_hit_facts',{}).get('completion_id')==key and r['attacker_id']==target.entity_id]
        if key not in covered and not (matching and all(r.get('application_kind')=='hp_loss' for r in matching)):
            unknown=True
    observed={r.get('native_hit_facts',{}).get('damage_event_id') for r in records(user)[start['history_sequence']:]}
    events=getattr(engine,'_heavy_events',{})
    for sequence in range(start['damage_sequence']+1,engine._heavy_sequence+1):
        event_id='heavy-attack-'+str(sequence);event=events.get(event_id)
        if event is None:
            equipment_id='heavy-equipment-'+str(sequence)
            equipment=events.get(equipment_id)
            if (equipment is not None and equipment.get('event_id')==equipment_id
                    and equipment.get('kind')=='action_taken'
                    and equipment.get('producer')=='manual_equipment.actual_standard'):
                continue
            unknown=True;continue
        if event.get('event_id')!=event_id or event.get('kind')!='attack_damage':
            unknown=True;continue
        if event_id not in observed and event['attacker'] is target and event['target'] is user:
            application=_event_attack_application(event)
            if application is None or _application_loss(application)>0:unknown=True
    return None if unknown else False







def note_native_application(engine, attacker, target, move, event_id):
    """Retain only the matching active history producer's actual attack leaf."""
    for scope in reversed(list(getattr(engine,'_attack_history_scopes',{}).values())):
        if scope['attacker'] is attacker and scope['target'] is target and scope['move_id']==move['id']:
            value={'damage_event_id':event_id,'attack_application':_event_attack_application(engine._heavy_events[event_id])}
            old=scope.get('native_application')
            if old is not None and old!=value:raise ValueError('one native attack application per history producer required')
            scope['native_application']=value
            return


def _application_loss(application):
    return max(0,application['net_hp_loss'])+max(0,application['net_temporary_hp_loss'])


def _event_attack_application(event):
    if 'attack_after' not in event:return None
    return DAMAGE.application(requested=event['amount'],
        before={k:event['before'][k] for k in ('hp','temporary_hp')},after=event['attack_after'],
        source=event['move']['id'],damage_class=event['move']['class'])


def _live_grapple_origin(engine, attacker, target, move, event):
    if event is None or move['id']!='struggle':return None
    import grapple_state as GRAPPLE
    relation=GRAPPLE.relation(engine,attacker)
    pending=None if relation is None else relation.get('native_attack')
    if pending is None:return None
    if (pending['phase']!='damage' or pending['actor_id']!=attacker.entity_id or pending['target_id']!=target.entity_id
            or pending['history_index']!=len(relation['history']) or pending['round']!=engine.round_no
            or pending['precision_id']!=event['id'] or not any(item is event for item in engine._precision_events)
            or event.get('actor') is not attacker or event['target'] is not target
            or event.get('producer')!='combat_maneuver' or event['source']!='struggle'
            or event['result']!='damaging_hit'):
        raise ValueError('actual paid native grapple Attack required')
    return {'relation_id':relation['id'],'history_index':pending['history_index'],'precision_id':event['id']}


def _grapple_result(engine, observation):
    import grapple_state as GRAPPLE
    origin=observation['native_hit_facts']['grapple_origin']
    relation=GRAPPLE._state(engine)['relations'].get(origin['relation_id'])
    if relation is None:return None
    GRAPPLE._verify(relation)
    number=origin['history_index']
    if number>=len(relation['history']):return None
    entry=relation['history'][number];proof=entry.get('attack')
    if (entry.get('action')!='attack' or proof is None or proof['event_id']!=origin['precision_id']
            or proof['source']!=observation['receipt']['source'] or proof['actor_id']!=observation['attacker_id']
            or proof['target_id']!=observation['target_id']):
        raise ValueError('native grapple hit history changed')
    return {'hit':not proof['hit_prevented'],'hit_prevented':proof['hit_prevented'],'cancelled':False}
