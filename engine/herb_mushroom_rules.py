"""Chapter 9's distinct Snack Herbs and actual held mushroom consumers.

Food owns intake/buffs; stock owns the physical body; native checks own appraisal.
Only a mushroom's unrevealed/identified random result belongs to that same body.
"""
from copy import deepcopy
import common_checks as C
import combat_stage_sources as STAGES

SOURCE = 'ch09-equipment/모험-도구/규토리-나무열매-허브'
PLAN = 'mushroom_effect'
APPRAISALS = 'mushroom_appraisals'
SNACK_EFFECTS = {
    'item/멘탈허브': {'kind': 'herb_cure_volatile'},
    'item/하양허브': {'kind': 'herb_reset_lowered'},
    'item/파워풀허브': {'kind': 'herb_skip_setup'},
}
SNACK_HERBS = frozenset(SNACK_EFFECTS)
MUSHROOMS = {'item/작은버섯': 1, 'item/큰버섯': 2, 'item/향기버섯': 1}


def selected(rules, uid):
    if uid not in SNACK_HERBS and uid not in MUSHROOMS:
        raise ValueError('reviewed Chapter 9 herb or mushroom required')
    if rules._selected_rule(SOURCE) != SOURCE or rules._selected_rule(uid) != uid:
        raise ValueError('selected herb/mushroom source needs its own consumer')
    if rules.item_effects(uid)[1].get('id') != uid:
        raise ValueError('selected herb/mushroom catalog identity changed')


def snack_effect(rules, uid):
    if uid not in SNACK_HERBS:
        return None
    selected(rules, uid)
    return deepcopy(SNACK_EFFECTS.get(uid))


def power_herb_interested(actor):
    choice = actor.spec.get('food_move_choice')
    return isinstance(choice, dict) and any(
        isinstance(buff, dict) and buff.get('id') == choice.get('buff_id')
        and buff.get('effect', {}).get('kind') == 'herb_skip_setup'
        for buff in actor.buffs)


def _power_herb_setup(rules, move_id):
    if not isinstance(move_id, str) or move_id not in rules.moves or rules._selected_rule(move_id) != move_id:
        raise ValueError('Power Herb requires an actual selected Move')
    mechanics, _ = rules.move_mech(move_id)
    setup = next((effect for effect in mechanics.get('effects_exec', [])
                  if effect.get('type') == 'set_up_move'), None)
    if setup is None or '준비' not in rules.move(move_id).get('keywords', ()):
        raise ValueError('Power Herb requires a Move with the Set-Up keyword')
    return setup


def validate_power_herb_choice(actor):
    if not power_herb_interested(actor):
        return None
    import food_effects as FOOD
    choice = actor.spec['food_move_choice']
    if set(choice) != {'buff_id', 'move_id'}:
        raise ValueError('typed Power Herb Move choice required')
    buff = FOOD.get_buff(actor, choice['buff_id'])
    if buff['item'] != 'item/파워풀허브' or buff['effect'] != SNACK_EFFECTS[buff['item']]:
        raise ValueError('Power Herb choice needs its actual selected Digestion Buff')
    _power_herb_setup(actor.r, choice['move_id'])
    return buff


def prepare_power_herb(engine, actor, buff, move_id):
    _power_herb_setup(engine.r, move_id)
    if actor.setup_move is not None:
        raise ValueError('Power Herb skips a new Set-Up turn, not an already prepared Move')
    if 'food_move_choice' in actor.spec:
        raise ValueError('one actual Move food choice at a time')
    actor.spec['food_move_choice'] = {'move_id': move_id, 'buff_id': buff['id']}
    validate_power_herb_choice(actor)
    return {'status': 'prepared_for_actual_move', 'move_id': move_id, 'buff_id': buff['id']}


def power_herb_plan(engine, actor, move_id):
    buff = validate_power_herb_choice(actor)
    if buff is None or actor.spec['food_move_choice']['move_id'] != move_id:
        return None
    setup = _power_herb_setup(engine.r, move_id)
    import effects as FX
    if setup.get('skip_setup_if_weather') and FX.weather_matches(
            engine, setup['skip_setup_if_weather'], actor):
        return None
    if actor.setup_move is not None:
        raise ValueError('Power Herb cannot remove a Set-Up turn already taken')
    import food_effects as FOOD
    FOOD.consumption_allowed(engine, actor, buff)
    return buff


def consume_power_herb(engine, actor, move_id):
    buff = power_herb_plan(engine, actor, move_id)
    if buff is None:
        raise ValueError('actual Power Herb choice changed before resolution')
    import food_effects as FOOD
    receipt = FOOD.remove_buff(engine, actor, buff, producer=move_id)
    receipt['benefit'] = {'kind': 'skip_setup', 'move_id': move_id}
    return receipt


def immediate_preflight(engine, actor, buff):
    selected(engine.r, buff['item'])
    if buff['effect'] != SNACK_EFFECTS.get(buff['item']):
        raise ValueError('herb Digestion Buff and exact selected source disagree')
    STAGES.validate(actor)


def immediate_commit(engine, actor, buff):
    if buff['effect']['kind'] == 'herb_cure_volatile':
        import status_sets as STATUS
        cured = []
        for condition in STATUS.afflictions(actor, 'volatile'):
            engine.cure_status(actor, condition)
            if condition not in STATUS.afflictions(actor):
                cured.append(condition)
        return {'cured': cured}
    values = {stat: 0 for stat, stage in actor.stages.items() if stage < 0}
    if values:
        STAGES.assign_combat(actor, values)
    return {'reset_stats': list(values)}


def _derive_stats(uid, faces):
    if not isinstance(faces, list) or not faces:
        raise ValueError('mushroom effect needs its actual random faces')
    stats = []
    for index, face in enumerate(faces):
        C.integer(face, 'mushroom stat d6 face', 1, 6)
        if face != 6 and STAGES.STATS[face - 1] not in stats:
            stats.append(STAGES.STATS[face - 1])
        if len(stats) == MUSHROOMS[uid] and index != len(faces) - 1:
            raise ValueError('mushroom random selection continued after its result')
    if len(stats) != MUSHROOMS[uid]:
        raise ValueError('mushroom random faces do not select its distinct stats')
    return stats


def validate_object(rules, obj, index=None):
    plan = obj.get(PLAN)
    appraisals = obj.get(APPRAISALS)
    if plan is None and appraisals is None:
        return None
    uid = obj.get('item_rule_id')
    if obj.get('kind') != 'item_instance' or uid not in MUSHROOMS:
        raise ValueError('mushroom knowledge needs its actual mushroom body')
    selected(rules, uid)
    if plan is not None:
        if (not isinstance(plan, dict)
                or set(plan) != {'source', 'item_id', 'instance_id', 'faces', 'stats'}
                or plan['source'] != SOURCE or plan['item_id'] != uid
                or plan['instance_id'] != obj['id']
                or plan['stats'] != _derive_stats(uid, plan['faces'])):
            raise ValueError('mushroom effect differs from its actual source/body/faces')
    if appraisals is not None:
        if not isinstance(appraisals, list) or not appraisals:
            raise ValueError('actual mushroom appraisal history required')
        for row in appraisals:
            if (not isinstance(row, dict)
                    or set(row) != {'actor_id', 'source', 'dc', 'total', 'passed'}
                    or row['source'] != SOURCE or row['dc'] != 20
                    or type(row['passed']) is not bool
                    or not isinstance(row['actor_id'], str) or not row['actor_id']):
                raise ValueError('typed DC20 Survival appraisal required')
            C.integer(row['total'], 'mushroom Survival check total')
            if row['passed'] != (row['total'] >= 20):
                raise ValueError('mushroom appraisal and actual DC result disagree')
            if index is not None and row['actor_id'] not in index:
                raise ValueError('mushroom appraiser is absent from the actual world')
            if row['passed'] and plan is None:
                raise ValueError('successful mushroom appraisal lost its fixed result')
    return plan


def _ensure_plan(engine, obj):
    plan = validate_object(engine.r, obj)
    if plan is not None:
        return plan
    uid = obj['item_rule_id']
    faces, stats = [], []
    while len(stats) < MUSHROOMS[uid]:
        face = engine.rng.randint(1, 6)
        faces.append(face)
        if face != 6 and STAGES.STATS[face - 1] not in stats:
            stats.append(STAGES.STATS[face - 1])
    plan = dict(source=SOURCE, item_id=uid, instance_id=obj['id'], faces=faces, stats=stats)
    obj[PLAN] = plan
    return plan


def appraise(engine, actor, *, instance_id, fixed=None, **check_options):
    """Observe the actual held body with the native Survival check; no invented cost."""
    import world_entities as WORLD
    import item_stock as STOCK
    import movement_actions as MOVEMENT
    WORLD.require_actors(engine, actor)
    MOVEMENT.boundary(engine, 'appraise_mushroom')
    obj = getattr(engine, '_physical_objects', {}).get(instance_id)
    if not isinstance(obj, dict) or obj.get('item_rule_id') not in MUSHROOMS:
        raise ValueError('an actual registered mushroom instance is required')
    uid = obj['item_rule_id']
    selected(engine.r, uid)
    STOCK.inspect_held(engine, actor, uid, instance_id)
    validate_object(engine.r, obj, WORLD.actor_index(engine))
    import turn as TURN
    import action_lifecycle as ACTION
    if not TURN.can_act(engine, actor) or not ACTION.status_permission(engine, actor, 'free'):
        return False
    # The native observed roll stays observed, even when it fails identification.
    roll = engine.skill_roll(actor, '생존', fixed=fixed, **check_options)
    check = __import__('skill_feature_actions').resolve_check(engine,actor,'생존',20,roll,check_options)
    if check.passed:
        plan = _ensure_plan(engine, obj)
    obj.setdefault(APPRAISALS, []).append(dict(actor_id=actor.entity_id, source=SOURCE,
                                               dc=20, total=check.total, passed=check.passed))
    result = {'status': 'identified' if check.passed else 'unidentified',
              'instance_id': instance_id, 'check': check}
    if check.passed:
        result['stats'] = list(plan['stats'])
    return result


def prepare_use(engine, request):
    r = request
    selected(engine.r, r.source_id)
    if r.target is not r.user:
        raise ValueError('the actual mushroom holder consumes its own held item')
    if (r.free or r.count != 1 or r.held_selection is None
            or any(value is not None for value in (r.duration_minutes, r.duration_reason,
                r.food_policy, r.selected_move, r.container_selection, r.shell_batch_id))):
        raise ValueError('one actual held mushroom uses its ordinary Swift Action')
    import item_stock as STOCK
    import world_entities as WORLD
    obj = STOCK.inspect_held(engine, r.user, r.source_id, r.held_selection)
    validate_object(engine.r, obj, WORLD.actor_index(engine))
    STAGES.validate(r.user)
    return None


def consume(engine, request):
    import state_grants as GRANTS
    import item_stock as STOCK
    import turn as TURN
    r = request
    prepare_use(engine, r)
    stock = STOCK.prepare(engine, r.user, r.source_id, held_selection=r.held_selection)

    def apply(staged, actor):
        if not TURN.spend(staged, actor, 'swift', r.item_name):
            return False
        obj = staged._physical_objects[stock['instance_id']]
        plan = _ensure_plan(staged, obj)
        stats = list(plan['stats'])
        receipt = STOCK.debit(staged, actor, stock)
        uid = r.source_id
        cured = []
        if uid == 'item/작은버섯':
            staged.lose_hp(actor, 5, source=uid)
        elif uid == 'item/큰버섯':
            staged.apply_status(actor, '독', source=uid)
        else:
            import boss_transitions as BOSS
            for condition in ('화상', '마비', '독'):
                stored = BOSS.condition_variant(actor, condition)
                before = stored in actor.conditions
                staged.cure_status(actor, condition)
                if before and stored not in actor.conditions:
                    cured.append(condition)
        delta = -1 if uid == 'item/향기버섯' else 1
        changed = []
        if delta > 0 or cured:
            for stat in stats:
                staged.change_stage(actor, stat, delta)
                changed.append(stat)
        result = dict(status='consumed', item=uid, instance_id=obj['id'],
                      stats=changed, delta=delta if changed else 0, cured=cured,
                      item_stock=receipt)
        import consumption_execution as EXECUTION
        EXECUTION.finish(actor, receipt, target_id=actor.entity_id, outcome='applied',
                         results=[{'kind': 'mushroom', 'id': obj['id']}])
        return result

    return GRANTS.transition(engine, r.user, apply)


def validate_world(engine, index):
    for obj in getattr(engine, '_physical_objects', {}).values():
        validate_object(engine.r, obj, index)
    return True
