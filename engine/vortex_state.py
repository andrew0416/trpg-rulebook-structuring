"""Own the existing Vortex record, its derived restrictions and escape progress.

Engine and effect hooks supply actual events. This module neither imports their
dispatch adapters nor creates a second condition or timing ledger.
"""
from copy import deepcopy

KEY = "vortex"
SOURCE = "keyword/조이기"

def _policies(rules):
    import json
    from pathlib import Path
    from source_context import verified_source
    value=json.loads((Path(rules.root)/'data/exhaust-vortex-source-policy.json').read_text(encoding='utf-8'))
    if value.get('schema_version')!=1:
        raise ValueError('known Exhaust/Vortex source policy required')
    value=value['rules']['vortex']
    if value['source']!='keyword/조이기':
        raise ValueError('exact vortex keyword required')
    verified_source(rules,value['source_reference'],label='vortex policy')
    for definition in value['definitions'].values():
        reference=definition['source']
        verified_source(rules,reference,label='vortex definition',
                        source_root='source-audit' if reference['file'].startswith('source-audit/') else 'input')
    return value


def _document(value):
    return {'schema':1,'id':'native/vortex-source','variants':[{
        'rule_id':value['source'],'source':value['source_reference'],
        'values':{'variant':{'$input':'source_text'},'definitions':value['definitions']},
        'inputs':{'source_text':{'type':'string','authority':'gm','decision_kind':'source_conflict',
            'choices':list(value['definitions']),'question':value['question']}}}]}


def source_choices(actor):
    import source_policy as POLICY
    return POLICY.resolve(actor.r,_document(_policies(actor.r)))


def _selected_policy(actor):
    import source_policy as POLICY
    value=_policies(actor.r);choice=actor.spec.get('vortex_source_choice')
    result=POLICY.resolve(actor.r,_document(value),
                          decisions={} if choice is None else {'source_text':choice})
    variant=value['default'] if choice is None else result['values']['variant']
    return variant,deepcopy(value['definitions'][variant]['policy']),deepcopy(choice)


def select_source(engine,actor,choice):
    import world_entities as WORLD,state_grants as G,action_lifecycle as ACTION
    WORLD.require_actors(engine,actor)
    ACTION.ensure_resolutions_clear(engine)
    if choice is None:raise ValueError('actual scoped vortex source decision required')
    def apply(e,c):
        import source_policy as POLICY
        result=POLICY.resolve(e.r,_document(_policies(e.r)),decisions={'source_text':choice})
        if result['status']!='PolicyValuesReady':raise ValueError('actual vortex source decision required')
        c.spec['vortex_source_choice']=deepcopy(choice)
        return deepcopy(choice)
    return G.transition(engine,actor,apply,include_rulings=True)


def _recorded_policy(actor,row):
    fields={'policy_variant','source_choice','policy'}
    if not fields&set(row):
        return deepcopy({'attempt':'mandatory','comparison':'strict'})
    if not fields<=set(row):raise ValueError('complete producing vortex policy required')
    value=_policies(actor.r);variant=row['policy_variant'];choice=row['source_choice']
    if variant not in value['definitions'] or row['policy']!=value['definitions'][variant]['policy']:
        raise ValueError('original complete vortex definition required')
    if choice is None:
        if variant!='korean_mandatory_strict':
            raise ValueError('nondefault vortex needs its actual source decision')
    else:
        import root_resolution as ROOT
        scope=choice.get('scope') if type(choice)is dict else None
        if (type(choice)is not dict or set(choice)!={'value','reason','scope'}
            or choice['value']!=variant or type(choice['reason'])is not str or not choice['reason'].strip()
            or type(scope)is not dict or set(scope)!={'policy_id','selected_id','selected_version','definition_hash','profile_hash'}
            or scope['policy_id']!='native/vortex-source' or scope['selected_id']!=value['source']
            or scope['selected_version'] is not None or scope['definition_hash']!=ROOT.fingerprint(_document(value))
            or type(scope['profile_hash'])is not str or not scope['profile_hash'].strip()):
            raise ValueError('original scoped vortex source decision required')
    # Producing scope is history. Current future profile choices cannot rewrite it.
    return deepcopy(row['policy'])


def escape_bonus(parameters):
    if parameters is None:
        return 0
    if not isinstance(parameters, dict) or set(parameters) - {"escape_dc_bonus"}:
        raise ValueError("Vortex parameters support only escape_dc_bonus")
    bonus = parameters.get("escape_dc_bonus", 0)
    if type(bonus) is not int or bonus < 0:
        raise ValueError("Vortex escape bonus must be a nonnegative integer")
    return bonus


def configure(actor, parameters):
    bonus = escape_bonus(parameters)
    state = actor.custom_conditions.get(KEY)
    if state is None:
        raise ValueError("Vortex parameters need the actual applied condition")
    current = escape_bonus({"escape_dc_bonus": state.get("escape_dc_bonus", 0)})
    if bonus > current:
        state["escape_dc_bonus"] = bonus


def before_apply(engine, actor, condition):
    if condition == "조이기":
        engine.r._selected_rule(SOURCE)
        if actor.custom_conditions.get(KEY) is None:
            _selected_policy(actor)
    state = actor.custom_conditions.get(KEY)
    if state and not state.get("installing") and condition in ("둔화", "수렁"):
        state["owned"].discard(condition)


def applied(engine, actor, condition):
    if condition != "조이기":
        return
    _expire_type_ace(engine, actor)
    variant, policy, choice = _selected_policy(actor)
    state = {"ends": 0, "owned": set(), "installing": True,
             "policy_variant": variant, "source_choice": choice, "policy": policy}
    actor.custom_conditions[KEY] = state
    for child in ("둔화", "수렁"):
        if child not in actor.conditions and engine.apply_status(actor, child):
            state["owned"].add(child)
    state["installing"] = False


def before_cure(engine, actor, condition):
    state = actor.custom_conditions.get(KEY)
    if condition == "조이기":
        _expire_type_ace(engine, actor)
        state = actor.custom_conditions.pop(KEY, None)
        if state:
            for child in sorted(state["owned"]):
                engine.cure_status(actor, child)
    elif state:
        state["owned"].discard(condition)


def _expire_type_ace(engine, actor):
    import combat_timing as TIMING
    for row in list(TIMING.records(actor)):
        if row.get('ace_vortex'):
            TIMING.expire(engine, actor, row)


def turn_start(engine, actor, *, _boss_round=False):
    import boss_transitions as BOSS
    boss = BOSS.state(actor) is not None
    if boss != _boss_round:
        return
    if "조이기" in actor.conditions:
        engine.r._selected_rule(SOURCE)
        engine.lose_hp(actor, engine.tick_loss(actor, 1), source=SOURCE,
                       loss_kind="percentage" if boss else "loss")


def turn_end(engine, actor):
    if "조이기" not in actor.conditions:
        return
    engine.r._selected_rule(SOURCE)
    state = actor.custom_conditions.get(KEY)
    if state is None:
        raise ValueError("Vortex needs an applied condition record; use Engine.apply_status")
    policy = _recorded_policy(actor, state)
    bonus = escape_bonus({"escape_dc_bonus": state.get("escape_dc_bonus", 0)})
    state["ends"] += 1
    if state["ends"] >= 5:
        engine.cure_status(actor, "조이기")
        engine.log(f"    {actor.name}: 조이기 다섯 번째 턴 종료, 자동 탈출", SOURCE)
    else:
        threshold = 20 - 6 * (state["ends"] - 1) + bonus
        if policy['attempt'] == 'optional':
            choice = engine.rulings.decide({'type':'vortex_escape_attempt','unit':SOURCE,
                'actor':actor.name,'turn_end':state['ends'],'threshold':threshold,
                'text':'Attempt this optional English Vortex escape roll?'})
            if type(choice) is not bool:
                raise ValueError('choose whether to attempt the optional Vortex escape')
            if not choice:
                engine.log(f"    {actor.name}: 조이기 탈출 굴림 거절 (자기 턴 종료 {state['ends']})", SOURCE)
                return
        import duelist as DUELIST
        roll = 11 if DUELIST.choose_eleven(engine,actor,'vortex_escape') else engine.d20()
        import fashion_items as FASHION
        modifier = FASHION.all_roll_modifier(actor)
        total = roll + modifier
        escaped = total > threshold if policy['comparison'] == 'strict' else total >= threshold
        operator = '>' if policy['comparison'] == 'strict' else '>='
        engine.log(f"    {actor.name}: 조이기 탈출 d20={roll}{modifier:+d}={total} {operator} {threshold}: {escaped}", SOURCE)
        if escaped:
            engine.cure_status(actor, "조이기")
