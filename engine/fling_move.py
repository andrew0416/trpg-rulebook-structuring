"""Fling's table over real hand/held possession and the native Move producer.

Declaration is preparation only. Native Standard/frequency/accuracy/damage stay
in Engine; only the actual paid activation may detach the physical projectile.
"""
from copy import deepcopy
from contextvars import ContextVar
from functools import wraps
from inspect import signature
_ATOMIC = ContextVar('native_fling_atomic', default=False)
import world_entities as W
import state_grants as G

SOURCE = 'move/내던지기'
CHOICE = 'fling_declaration'
RESULT = {'type': 'fling_result', 'target': 'target'}
RARE = {'item/금속파우더', 'item/대파', 'item/굵은뼈', 'item/분홍진주'}
LAGGING = {'item/검은철구', 'item/느림보꼬리', 'item/느림보-도구',
           *('item/느림보-도구-'+str(n) for n in range(1, 5))}
TYPED = {'item/타입부스터', 'item/타입깁스', 'item/타입플레이트'}


def definition(rules):
    from source_context import verified_source
    verified_source(rules, {'file': 'input/db/moves.csv',
        'sha256': 'ab83f872e5eca67a41db7d126b842f0165437e0fa70bb77ddad832a0b7396c93'}, label='Fling Move')
    verified_source(rules, {'file': 'input/ch10-index-reference.md',
        'sha256': 'c3a1d783b4f649f0f6e25a9443a90ca8079a6e036c42c6f8797e100127157abe'}, label='Fling nine-category table')
    verified_source(rules, {'file': 'source-audit/ptu-core-1.05.pdf',
        'sha256': 'e5e0371031601c3ad0a04056771c17599a2d8826e5a5102ccd37f9b368108907'},
        label='Core Fling table p339', source_root='source-audit')
    if rules._selected_rule(SOURCE) != SOURCE:raise ValueError('selected Fling Move needs its own adapter')


def mechanics(rules, source, mechanics):
    if source != SOURCE:return mechanics
    definition(rules)
    if mechanics.get('effects_exec', []):raise ValueError('Fling source effects changed')
    return dict(mechanics, effects_exec=[deepcopy(RESULT)])


def slots(actor):return ('held',) if actor.kind == 'pokemon' else ('주요손', '반대손')


def possession(engine, actor, instance_id):
    import items as I, physical_hands as HANDS
    W.require_actors(engine, actor)
    obj = getattr(engine, '_physical_objects', {}).get(instance_id)
    if not isinstance(obj, dict):raise ValueError('Fling requires an existing physical object')
    W.require_physical_access(obj)
    __import__('environmental_item_state').require_usable(engine, obj)
    if actor.kind not in ('trainer', 'pokemon'):raise ValueError('actual Fling user required')
    if actor.kind == 'trainer' and HANDS.inspect(engine, actor, instance_id):
        return obj, {'mode': 'hand', 'instance_id': instance_id}
    rows = [r for r in I.equipment_options(actor, slots(actor)) if r.get('instance_id') == instance_id]
    if len(rows) != 1 or obj.get('equipped_by') != actor.entity_id:
        raise ValueError('Fling requires this actual hand or held item, not inventory/accessory/remote possession')
    row = rows[0]
    if actor.kind == 'trainer' and not set(row.get('slots', ())) & {'주요손', '반대손'}:
        raise ValueError('Trainer Fling requires an actual hand')
    load = actor.spec.get('_carried_load', {})
    if load.get('mode', 'physical') != 'physical' or load.get('blocked_actions') or load.get('failure_pending'):
        raise ValueError('resolve actual physical carrying state before Fling')
    if obj.get('carrier_id') and (obj['carrier_id'] != actor.entity_id or not any(
            x['id'] == instance_id and x['weight_kg'] == obj.get('weight_kg') for x in load.get('objects', []))):
        raise ValueError('Fling item carrier and physical load disagree')
    __import__('equipment_protection').require(engine, actor, row, 'drop', (actor,))
    return obj, dict(row, mode='equipped')


def observe_type(engine, actor, instance_id, move_type, *, reason):
    """Observe the actual type of a generic Booster/Brace/Plate, not a bonus."""
    if not isinstance(reason, str) or not reason.strip():raise ValueError('actual item type observation reason required')
    __import__('type_state').validate_attack(engine.r, move_type)
    def apply(e, a):
        obj, _ = possession(e, a, instance_id)
        if obj.get('item_rule_id') not in TYPED:raise ValueError('only a generic typed item needs this observation')
        before = deepcopy(obj.get('fling_item_type'))
        obj['fling_item_type'] = {'type': move_type, 'reason': reason, 'source': SOURCE}
        e.gm._rec('physical typed item', before, obj['fling_item_type'], reason, a)
    return G.transition(engine, actor, apply)


def rare_benefit(actor, uid):
    # Eligibility is the printed species restriction, not current suppression of
    # a passive benefit. Pink Pearl's Psychic Booster is not Spoink-exclusive.
    if uid == 'item/분홍진주':return True
    if actor.kind != 'pokemon':return False
    species = actor.spec.get('species')
    if uid == 'item/금속파우더':
        return species == '메타몽' and not actor.custom_conditions.get('transformed') and getattr(actor, 'form', None) != 'transformed'
    return species in ({'파오리'} if uid == 'item/대파' else {'탕구리', '텅구리'})


def profile(engine, actor, target, instance_id, edition, consumer_options=None):
    import items as I, weapon_actions as WEAPONS
    obj, held = possession(engine, actor, instance_id)
    uid = obj.get('item_rule_id')
    result = {'instance_id': instance_id, 'item_rule_id': uid, 'possession': deepcopy(held)}
    if held.get('weapon_key'):
        entry = actor.custom_conditions['equipped_weapons'][held['weapon_key']]
        weapon = WEAPONS.prepare(engine, actor, engine.r.move(entry['struggle_id']), held['weapon_key'])
        result.update(category='weapon', weapon=deepcopy(weapon), damage_base=weapon['damage_base'])
        return result
    # An observed native weapon cannot be disguised as a DB6 ordinary object.
    if __import__('optional_weapon_framework').PROFILE in obj:
        raise ValueError('equip the actual observed weapon before selecting its native Struggle damage')
    if uid is None:
        return dict(result, category='other', damage_base=6)
    effects, header = engine.r.item_effects(uid)
    if header.get('id') != uid:raise ValueError('physical Fling item source changed')
    result['item_name'] = engine.r.items_mech.get(uid, {}).get('name', uid.split('/', 1)[1])
    if uid in RARE:
        eligible = rare_benefit(actor, uid)
        if not eligible and edition == 'korean':raise ValueError('Korean Fling rare item requires a suitable user')
        return dict(result, category='rare' if eligible else 'held', damage_base=10 if eligible else 7)
    if uid in LAGGING:return dict(result, category='lagging', damage_base=12)
    item_type = {'item/맹독구슬': '독', 'item/맹독플레이트': '독',
                 'item/화염구슬': '불꽃', 'item/불구슬플레이트': '불꽃'}.get(uid)
    if uid in TYPED:
        observed = obj.get('fling_item_type', {})
        if observed.get('source') != SOURCE or not observed.get('reason'):
            raise ValueError('observe this actual generic item type before classifying Fling')
        item_type = observed['type']
        __import__('type_state').validate_attack(engine.r, item_type)
    if item_type in ('독', '불꽃'):
        return dict(result, category='poison' if item_type == '독' else 'fire', damage_base=3)
    if header.get('use') == 'ball':
        __import__('missed_ball_body').physical(engine, actor, instance_id)
        return dict(result, category='ball', damage_base=3)
    consumer = __import__('fling_consumables').profile(engine, actor, target, uid, consumer_options, instance_id=instance_id)
    if consumer is not None:
        return dict(result, category='consumable', damage_base=0, consumer_plan=consumer)
    return dict(result, category='held' if header.get('use') == 'held' or header.get('category') == '진화 도구' else 'other',
                damage_base=7 if header.get('use') == 'held' or header.get('category') == '진화 도구' else 6)


def declare(engine, actor, target, instance_id, *, edition='core_105', capture=False, capture_options=None, consumer_options=None):
    """Select one real projectile; this does not use the Move or spend anything."""
    definition(engine.r);W.require_actors(engine, actor, target)
    if edition not in ('core_105', 'korean') or type(capture) is not bool:
        raise ValueError('explicit Fling text edition and optional capture declaration required')
    if capture_options is not None and type(capture_options) is not dict:raise ValueError('capture options must be a plain mapping')
    if consumer_options is not None and type(consumer_options) is not dict:raise ValueError('consumer options must be a plain mapping')
    import json
    try:json.dumps({'capture': capture_options, 'consumer': consumer_options}, allow_nan=False)
    except (TypeError, ValueError) as error:raise ValueError('Fling declarations must be plain saveable data') from error
    def apply(e, a, t):
        choice = {'instance_id': instance_id, 'actor_id': a.entity_id, 'target_id': t.entity_id,
                  'edition': edition, 'capture': capture, 'capture_options': deepcopy(capture_options or {}),
                  'consumer_options': deepcopy(consumer_options or {}),
                  'round': e.round_no, 'scene': __import__('frequency').state(a)['scene'],
                  'turn_serial': a.custom_conditions.get('combat_turn_serial', 0)}
        _prepare(e, a, t, choice)
        a.spec[CHOICE] = choice
        return deepcopy(choice)
    return G.transition(engine, actor, apply, participants=(target,))


def _capture_eligible(actor, target):
    return actor.kind == 'trainer' and target.kind == 'pokemon' and not target.dead and not target.captured and getattr(target, 'side', None) != 'party' and not target.spec.get('trainer_id') and not target.spec.get('trainer')


def _prepare(engine, actor, target, choice):
    if (type(choice) is not dict or choice.get('actor_id') != actor.entity_id or choice.get('target_id') != target.entity_id
            or choice.get('round') != engine.round_no or choice.get('scene') != __import__('frequency').state(actor)['scene']
            or choice.get('turn_serial') != actor.custom_conditions.get('combat_turn_serial', 0)):
        raise ValueError('Fling needs a current actual actor/target/projectile declaration')
    plan = dict(deepcopy(choice), **profile(engine, actor, target, choice['instance_id'], choice['edition'], choice['consumer_options']))
    if plan['category'] == 'ball':
        wanted = choice['edition'] == 'korean' or choice['capture']
        if wanted and _capture_eligible(actor, target) and not target.fainted and target.hp > 0:
            if engine._physical_objects[plan['instance_id']].get('owner_id') != actor.entity_id:
                raise ValueError('capture attempt requires its actual legal ball owner')
            plan['capture_plan'] = __import__('capture_resolution').fling_preflight(engine, actor, target,
                __import__('items').ball_name(plan['item_name']), choice['capture_options'])
    elif choice['capture'] or choice['capture_options']:
        raise ValueError('capture declaration requires a real Poke Ball')
    return plan


def prepare_move(engine, actor, target, move):
    if move['id'] != SOURCE:return move
    definition(engine.r)
    plan = _prepare(engine, actor, target, actor.spec.get(CHOICE))
    out = dict(move, damage_base=plan['damage_base'], _fling=plan)
    if plan['category'] == 'weapon':
        weapon = deepcopy(plan['weapon'])
        # Preserve native weapon DB/class/type/bonuses; replace only Fling's
        # accuracy/range/frequency/identity, as directed by the table.
        out.update({k: v for k, v in weapon.items() if k.startswith('_')})
        out.update(type=weapon['type'], **{'class': weapon['class']})
        out['_weapon_attack'].update(range={'raw': '6, 대상 1', 'origin': 6, 'targets': 1, 'parsed': True},
                                     accuracy_bonus=0, minimum_distance=0)
    return out


def launch(engine, actor, target, move, completion_id):
    if move['id'] != SOURCE:return
    row = getattr(engine, '_move_completions', {}).get(completion_id)
    if (row is None or row['actor'] is not actor or row['phase'] != 'targets' or row['move_id'] != SOURCE
            or row['move'].get('_fling') != move.get('_fling') or not row.get('native_action_frame')):
        raise ValueError('Fling launch requires the issued native Move activation')
    if 'fling_launch' in row:raise ValueError('one Fling activation throws one actual projectile')
    plan = move['_fling']
    actual = _prepare(engine, actor, target, actor.spec.get(CHOICE))
    if actual != plan:raise ValueError('Fling source or actual possession changed before launch')
    uid = plan['instance_id'];held = plan['possession']
    if held['mode'] == 'equipped':
        __import__('items').drop_equipment(engine, actor, [held['key']], slots=slots(actor), consent_by=(actor,), source=SOURCE)
    else:
        load = actor.spec['_carried_load']
        __import__('capability_actions').set_carried(engine, actor, [r for r in load['objects'] if r['id'] != uid], 'actual native Fling launch')
    obj = engine._physical_objects[uid]
    W._set_object_location(obj, {'kind': 'unknown'})
    _ground_record_location(engine, uid, {'kind': 'unknown'})
    # World transitions may replace engine-owned registries. Re-fetch owners.
    row = engine._move_completions[completion_id]
    row['fling_launch'] = {'plan': deepcopy(plan), 'actor_id': actor.entity_id, 'completion_id': completion_id,
        'status': 'launched', 'origin': W.location_of(actor), 'aim': W.location_of(target)}
    actor.spec.pop(CHOICE, None)


def weapon_snapshot(engine, actor, move):
    plan = move.get('_fling')
    if move.get('id') != SOURCE or not plan or plan.get('category') != 'weapon':return None
    # Before launch, verify the actual equipped source; after launch, only its
    # issued current native completion owns the preserved projectile damage.
    matches = [row for row in getattr(engine, '_move_completions', {}).values()
               if row.get('actor') is actor and row.get('phase') == 'targets'
               and row.get('fling_launch', {}).get('plan') == plan]
    if not matches:
        target = W.actor_index(engine).get(plan['target_id'])
        if target is None or _prepare(engine, actor, target, actor.spec.get(CHOICE)) != plan:
            raise ValueError('Fling weapon snapshot has no actual possession or live launch')
    elif len(matches) != 1:raise ValueError('Fling weapon snapshot is ambiguous')
    expected = deepcopy(plan['weapon'])
    expected['_weapon_attack'].update(range={'raw': '6, 대상 1', 'origin': 6, 'targets': 1, 'parsed': True}, accuracy_bonus=0, minimum_distance=0)
    if (move.get('type') != expected['type'] or move.get('class') != expected['class']
            or move.get('damage_base') != expected['damage_base'] or move.get('_weapon_attack') != expected['_weapon_attack']):
        raise ValueError('actual thrown weapon damage declaration changed')
    for key, value in expected.items():
        if key.startswith('_') and key != '_weapon_attack' and move.get(key) != value:
            raise ValueError('actual thrown weapon native modifier changed')
    return move


def no_damage(move, mechanics):
    return move.get('id') == SOURCE and move.get('_fling', {}).get('category') == 'consumable' and mechanics.get('effects_exec') == [RESULT]


def preflight(engine, actor, target, effect, source):
    if source != SOURCE or {k: v for k, v in effect.items() if not k.startswith('_')} != RESULT:
        raise ValueError('exact Fling table effect required')
    definition(engine.r)
    # Before launch the declaration is required. Native post-hit dispatch has
    # already consumed it and is checked against the issued completion instead.
    if actor.spec.get(CHOICE) is not None:_prepare(engine, actor, target, actor.spec[CHOICE])


def _receipt(engine, actor, target, effect, ctx):
    preflight(engine, actor, target, effect, ctx.get('source_id'))
    frame = __import__('attack_damage_history').native_recipient(engine, actor, target, ctx)
    if frame is None or frame[2] is not ctx.get('move'):raise ValueError('actual native Fling hit producer required')
    row = getattr(engine, '_move_completions', {}).get(frame[3])
    launch = row.get('fling_launch') if row else None
    if (not launch or row['actor'] is not actor or row['phase'] != 'targets' or row['move_id'] != SOURCE
            or launch['actor_id'] != actor.entity_id or launch['completion_id'] != frame[3]
            or launch['plan'] != frame[2].get('_fling') or launch['status'] != 'launched'):
        raise ValueError('same issued actual physical Fling launch required')
    import effect_contracts as EC
    token = ctx.get('effect_receipt')
    EC.validate_receipt(engine, token, SOURCE, ctx.get('effect_occurrence'), actor, target, effect)
    receipt = engine._effect_dispatch_receipts[token]
    if receipt['status'] != 'dispatching' or receipt.get('fling_applied'):
        raise ValueError('Fling result must dispatch exactly once')
    receipt['fling_applied'] = True
    launch['recipient_id'] = target.entity_id
    launch['effect_receipt'] = token
    return launch, token, frame[3]


def _admission(engine, actor, target, launch, receipt, completion, kind, plan, ctx):
    rows = engine._move_completions[completion]['fling_launch'].setdefault('admissions', {})
    token = completion+'|'+kind
    if token in rows:raise ValueError('one Fling result admission per actual launch')
    rows[token] = {'actor_id': actor.entity_id, 'target_id': target.entity_id, 'instance_id': launch['plan']['instance_id'],
        'item_rule_id': launch['plan']['item_rule_id'], 'ball_name': launch['plan'].get('item_name'),
        'completion_id': completion, 'move_id': SOURCE, 'edition': launch['plan']['edition'],
        'nat': ctx.get('nat'), 'effect_receipt': receipt, 'kind': kind, 'plan': deepcopy(plan), 'consumed': False}
    return token


def _consume_admission(engine, actor, target, token, plan, kind):
    if type(token) is not str:raise ValueError('actual unused Fling effect admission required')
    completion_id = token.rsplit('|', 1)[0]
    owner = getattr(engine, '_move_completions', {}).get(completion_id, {}).get('fling_launch', {})
    row = owner.get('admissions', {}).get(token)
    if not row or row['consumed'] or row['kind'] != kind or row['plan'] != plan:
        raise ValueError('actual unused Fling effect admission required')
    scopes = getattr(engine, '_attack_loss_effect_scopes', ())
    frame = scopes[-1] if scopes else None
    complete = getattr(engine, '_move_completions', {}).get(row['completion_id'])
    dispatch = getattr(engine, '_effect_dispatch_receipts', {}).get(row['effect_receipt'])
    if (frame is None or frame[0] is not actor or frame[1] is not target or frame[3] != row['completion_id']
            or frame[2]['id'] != SOURCE or row['actor_id'] != actor.entity_id or row['target_id'] != target.entity_id
            or not complete or complete['phase'] != 'targets' or complete.get('fling_launch', {}).get('plan') != frame[2].get('_fling')
            or not dispatch or dispatch['status'] != 'dispatching' or not dispatch.get('fling_applied')):
        raise ValueError('Fling admission is outside its actual native effect')
    obj = engine._physical_objects.get(row['instance_id'])
    if not obj or obj.get('item_rule_id') != row['item_rule_id'] or any(obj.get(k) for k in ('equipped_by','carrier_id','telekinetic_holder_id')):
        raise ValueError('same detached Fling item required')
    W.require_usable_object(obj)
    row['consumed'] = True
    return dict(row, **{kind+'_plan': deepcopy(plan)})


def consume_capture_admission(engine, actor, target, token, prepared_plan):
    return _consume_admission(engine, actor, target, token, prepared_plan, 'capture')


def consume_item_admission(engine, actor, target, token, prepared_plan):
    return _consume_admission(engine, actor, target, token, prepared_plan, 'consumer')


def effect(engine, actor, target, effect, ctx):
    launch, receipt, completion = _receipt(engine, actor, target, effect, ctx)
    plan = launch['plan'];category = plan['category']
    if category in ('poison', 'fire'):
        engine.apply_status(target, '독' if category == 'poison' else '화상', source=SOURCE, applied_by=actor)
    elif category == 'consumable':
        consumer = __import__('fling_consumables')
        actual = consumer.profile(engine, actor, target, plan['item_rule_id'], plan['consumer_options'], instance_id=plan['instance_id'])
        token = _admission(engine, actor, target, launch, receipt, completion, 'consumer', actual, ctx)
        result = consumer.consume(engine, actor, target, token, actual)
        engine._move_completions[completion]['fling_launch']['consumer_result'] = deepcopy(result)
    elif category == 'ball' and (plan['edition'] == 'korean' or plan['capture']) and _capture_eligible(actor, target):
        capture = __import__('capture_resolution')
        actual = plan.get('capture_plan') if target.entity_id == plan['target_id'] else None
        if actual is None:
            actual = capture.fling_preflight(engine, actor, target, __import__('items').ball_name(plan['item_name']), plan['capture_options'], after_damage=True)
        token = _admission(engine, actor, target, launch, receipt, completion, 'capture', actual, ctx)
        result = capture.fling_post_hit(engine, actor, target, token, actual)
        engine._move_completions[completion]['fling_launch']['capture_result'] = result
    engine._move_completions[completion]['fling_launch']['status'] = 'hit'


def finish_target(engine, row, target):
    launch = row.get('fling_launch')
    if not launch:return
    result = row['results'][target.entity_id]
    if launch['status'] == 'launched':launch['status'] = 'prevented' if result.get('hit_prevented') or result.get('cancelled') else 'miss' if not result['hit'] else 'hit_no_effect'
    obj = engine._physical_objects[launch['plan']['instance_id']]
    if not obj.get('consumed'):
        launch['landing'] = {'status': 'pending', 'reason': 'GM actual projectile landing observation required'}


def observe_landing(engine, actor, completion_id, location, *, reason):
    """Observe a surviving actual thrown object; no pickup, repair or ownership change."""
    W.require_actors(engine, actor)
    def apply(e, a):
        row = getattr(e, '_move_completions', {}).get(completion_id)
        launch = row.get('fling_launch') if row else None
        if not launch or row['actor'] is not a or launch.get('landing', {}).get('status') != 'pending':
            raise ValueError('actual completed Fling awaiting landing required')
        obj = e._physical_objects[launch['plan']['instance_id']]
        W.require_present_object(obj)
        W.observe_location(e, obj, location, reason=reason, source=SOURCE)
        _ground_record_location(e, obj['id'], W.location_of(obj))
        launch['landing'] = {'status': 'observed', 'location': W.location_of(obj), 'reason': reason}
        return deepcopy(launch['landing'])
    return G.transition(engine, actor, apply)






def atomic_move(fn):
    """Stage the native action, preserving its existing paid pending exceptions."""
    sig = signature(fn)
    @wraps(fn)
    def run(engine, *args, **kwargs):
        bound = sig.bind(engine, *args, **kwargs).arguments
        if bound.get('move_id') != SOURCE or _ATOMIC.get():return fn(engine, *args, **kwargs)
        actor = bound['attacker'];pending = []
        def apply(staged, actual):
            staged_args, staged_kwargs = G._stage_transition_payload(engine, staged, (args, kwargs))
            context = _ATOMIC.set(True)
            before = set(getattr(staged, '_effect_dispatch_receipts', {}))
            try:
                result = fn(staged, *staged_args, **staged_kwargs)
                for token, receipt in getattr(staged, '_effect_dispatch_receipts', {}).items():
                    if token not in before and receipt.get('source_id') == SOURCE and receipt.get('status') == 'execution_failed':
                        raise ValueError('native Fling effect failed: '+str(receipt.get('result')))
                return result
            except Exception as error:
                if G.record_native_pending(staged, error, pending):return None
                raise
            finally:_ATOMIC.reset(context)
        result = G.transition(engine, actor, apply, include_grid=engine.grid is not None, include_rulings=True)
        if pending:
            exception, event_id = pending[0]
            raise exception(event_id)
        return result
    return run


def validate_world(engine, index):
    """Additional checks for Fling-owned state; existing native guards stay intact."""
    import physical_hands as HANDS
    import effect_contracts as EC
    import move_completion as COMPLETE
    for actor in index.values():
        for grip in HANDS.entries(actor).values():HANDS.inspect(engine, actor, grip['instance_id'])
    for completion in getattr(engine, COMPLETE.KEY, {}).values():
        launch = completion.get('fling_launch')
        if launch is None:continue
        actor = completion['actor'];plan = launch.get('plan', {})
        if (completion['move_id'] != SOURCE or completion['move'].get('_fling') != plan
                or launch.get('completion_id') != completion['id'] or launch.get('actor_id') != actor.entity_id
                or plan.get('actor_id') != actor.entity_id or index.get(actor.entity_id) is not actor
                or plan.get('round') != completion['round'] or plan.get('turn_serial') != completion['turn_serial']
                or plan.get('edition') not in ('core_105', 'korean') or not completion.get('native_action_frame')
                or launch.get('status') not in ('launched', 'hit', 'miss', 'prevented', 'hit_no_effect')):
            raise ValueError('Fling launch lost its actual native Move completion')
        obj = getattr(engine, '_physical_objects', {}).get(plan.get('instance_id'))
        if not obj or obj.get('item_rule_id') != plan.get('item_rule_id'):
            raise ValueError('Fling launch lost its actual physical source')
        token = launch.get('effect_receipt')
        if token is not None:
            receipt = getattr(engine, '_effect_dispatch_receipts', {}).get(token)
            recipient = index.get(launch.get('recipient_id'))
            if not receipt or recipient is None or not receipt.get('fling_applied'):
                raise ValueError('Fling hit lost its actual dispatched effect')
            if {k: v for k, v in receipt['effect'].items() if not k.startswith('_')} != RESULT:
                raise ValueError('Fling dispatched effect changed')
            EC.validate_receipt(engine, token, SOURCE, receipt['occurrence'], actor, recipient, receipt['effect'])
            if completion['phase'] == 'complete':
                result = COMPLETE.recipient_result(completion, recipient)
                if not result or not result['hit'] or result.get('cancelled') or result.get('hit_prevented'):
                    raise ValueError('Fling effect requires its completed actual hit')
        elif launch['status'] == 'hit':raise ValueError('Fling hit needs its actual effect receipt')
        admissions = launch.get('admissions', {})
        if type(admissions) is not dict:raise ValueError('Fling completion admission mapping required')
        for key, admission in admissions.items():
            if (admission.get('kind') not in ('consumer', 'capture') or key != completion['id']+'|'+admission['kind']
                    or admission.get('completion_id') != completion['id'] or admission.get('actor_id') != actor.entity_id
                    or admission.get('target_id') != launch.get('recipient_id') or admission.get('instance_id') != obj['id']
                    or admission.get('item_rule_id') != plan.get('item_rule_id') or admission.get('effect_receipt') is not token
                    or type(admission.get('consumed')) is not bool):
                raise ValueError('Fling admission lost its actual completion/recipient/projectile')
            if completion['phase'] == 'complete' and not admission['consumed']:
                raise ValueError('completed Fling left an unused native admission')
        if launch.get('consumer_result') is not None:
            __import__('fling_consumables').validate_result(engine, completion, launch)
        if 'capture_result' in launch:
            attempts = [r for r in actor.spec.get('capture_attempts', {}).values()
                        if r.get('move_origin', {}).get('completion_id') == completion['id']]
            if len(attempts) != 1 or attempts[0].get('physical_instance_id') != obj['id'] or attempts[0].get('captured') is not launch['capture_result']:
                raise ValueError('Fling capture result lost its actual physical attempt')
        landing = launch.get('landing')
        if landing is not None and (type(landing) is not dict or landing.get('status') not in ('pending', 'observed')):
            raise ValueError('Fling actual landing observation required')



def _ground_record_location(engine, instance_id, location):
    # The ordinary drop owner preserves a weapon recovery record. Keep its
    # location aligned with the real projectile instead of a false actor-cell.
    for record in getattr(engine, 'ground_items', ()):
        if (record.get('source') == SOURCE and
                (record.get('weapon_record', {}).get('instance_id') == instance_id
                 or record.get('item', {}).get('instance_id') == instance_id)):
            record['location'] = deepcopy(location)

