"""Actual native attack applications, shared by retrospective Move effects."""
from copy import deepcopy
from contextlib import contextmanager
import common_checks as C
import combat_damage as DAMAGE
import type_state as TYPES

KEY = 'attack_damage_history'


def direct_hp_loss(move, mechanics):
    """The selected variable-DB declaration supplies loss, not rolled damage."""
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
        before=DAMAGE.observe(actual)
        is_damage=effect.get('as')=='damage'
        if is_damage:
            import heavy_injury_adapter as HEAVY
            HEAVY.apply_attack_damage(staged,source_actor,actual,amount,move,
                producer=HEAVY.Producer.EFFECT_DAMAGE, remainder='remaining native fixed-damage effect continuation',
                actual_damage_type=context.get('actual_damage_type',move['type']))
        else:
            staged.lose_hp(actual,amount,source=move['id'],unpreventable=effect.get('unpreventable') is True)
        receipt=DAMAGE.application(requested=amount,before=before,after=DAMAGE.observe(actual),
                                   source=move['id'],damage_class=move['class'])
        woke=wake_after_loss(staged,actual,move,before)
        _record(staged,source_actor,actual,receipt,context.get('actual_damage_type',move['type']),application_kind='damage' if is_damage else 'hp_loss')
        staged._effect_dispatch_receipts[token]['attack_damage' if is_damage else 'attack_hp_loss']={
            'kind':'native_attack_damage' if is_damage else 'native_attack_hp_loss','completion_id':completion,'receipt':deepcopy(receipt),
            'woke_sleep':woke,'unpreventable':effect.get('unpreventable') is True}
    G.transition(engine,recipient,apply,participants=(attacker,))


def records(actor):
    return actor.spec.get(KEY, [])


def validate_actor(actor):
    rows = records(actor)
    if not isinstance(rows, list): raise ValueError('attack history must be a list')
    for number, row in enumerate(rows, 1):
        if not isinstance(row, dict) or set(row)-{'application_kind'} != {
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
    return True


@contextmanager
def native_application(engine, attacker, target, move, native_context):
    import heavy_injury_adapter as HEAVY
    HEAVY.validate_native_receipt(engine,native_context,attacker,target,move)
    if native_context is None:
        # The public damage calculation/application API also permits an isolated
        # call. Preserve it without inventing a Move activation receipt.
        yield None
        return
    with _application_scope(engine, attacker, target, move) as token:
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
        record(engine, attacker, target, move, receipt, actual_type, token)
    return receipt


def record(engine, attacker, target, move, receipt, actual_type, native_context):
    """Called only while the native damage application still owns its token."""
    token = getattr(engine, '_attack_history_scopes', {}).get(native_context)
    if (token is None or token['attacker'] is not attacker or token['target'] is not target
            or token['move_id'] != move['id'] or token.get('history_recorded')):
        raise ValueError('one actual native attack application required')
    _record(engine,attacker,target,receipt,actual_type)
    token['history_recorded'] = True


def _record(engine, attacker, target, receipt, actual_type,*,application_kind='damage'):
    validate_actor(target)
    row = dict(sequence=len(records(target))+1, attacker_id=attacker.entity_id,
               target_id=target.entity_id, round=engine.round_no, at=engine.elapsed_seconds,
               move_type=actual_type, receipt=deepcopy(receipt))
    target.spec.setdefault(KEY, []).append(row)
    if application_kind!='damage':row['application_kind']=application_kind
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
